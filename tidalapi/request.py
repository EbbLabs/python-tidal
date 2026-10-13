# Copyright (C) 2023- The Tidalapi Developers
# Copyright (C) 2019-2022 morguldir
# Copyright (C) 2014 Thomas Amland
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""A module containing functions relating to TIDAL api requests."""

import datetime
import json
import logging
import threading
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Union,
    cast,
)
from urllib.parse import urljoin

import requests

from tidalapi.exceptions import (
    AuthenticationError,
    TidalBackoffError,
    get_retry_after,
    http_error_to_tidal_error,
    is_abuse_response,
)
from tidalapi.types import JsonObj

log = logging.getLogger(__name__)

Params = Mapping[str, Union[str, int, None]]

Methods = Literal["GET", "POST", "PUT", "DELETE"]

if TYPE_CHECKING:
    from tidalapi.session import Session


#: Backoff after a rate limit (HTTP 429) without a Retry-After header, in seconds.
RATE_LIMIT_BACKOFF = 60
#: Backoff after an anti-abuse rejection without a Retry-After header, in seconds.
ABUSE_BACKOFF = 30 * 60

#: Refresh the access token this long before it expires, so requests don't race the expiry.
TOKEN_EXPIRY_MARGIN = datetime.timedelta(seconds=60)


class Requests(object):
    """A class for handling api requests to TIDAL."""

    user_agent: str
    # Latest error response that can be returned and parsed after request has been completed
    latest_err_response: requests.Response

    def __init__(self, session: "Session"):
        # More Android User-Agents here: https://user-agents.net/browsers/android
        self.user_agent = "Mozilla/5.0 (Linux; Android 12; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Safari/537.36"
        self.client_version = "2025.7.16"
        self.session = session
        self.config = session.config
        self.latest_err_response = requests.Response()
        # Serializes access-token refreshes, see `_refresh_access_token`.
        self._refresh_lock = threading.Lock()
        # Backoff state, see `Config.backoff`.
        self._backoff_lock = threading.Lock()
        self._backoff_until = 0.0
        self._backoff_reason = ""

    def _refresh_access_token(self, stale_access_token: Optional[str]) -> bool:
        """Refresh the access token, at most once for concurrent callers.

        Requests are often issued from several threads (e.g. the paginated workers). If
        they all hit an expired token at the same time, each would POST the same
        refresh token. TIDAL rotates refresh tokens, so every POST after the first
        would use a token that has just been invalidated.

        :param stale_access_token: The access token the caller's request was sent
            with. If the session holds a different one by the time the lock is
            acquired, another thread has already refreshed and no new refresh is made.
        :return: True if the session holds a valid, refreshed access token.
        """
        with self._refresh_lock:
            if self.session.access_token != stale_access_token:
                return True
            refresh_token = self.session.refresh_token
            if not refresh_token:
                return False
            return self.session.token_refresh(refresh_token)

    def backoff_remaining(self) -> float:
        """Seconds left of the current backoff, 0 if requests are not being held back.

        Backoff only ever starts if :attr:`Config.backoff` is enabled.
        """
        with self._backoff_lock:
            return max(0.0, self._backoff_until - time.monotonic())

    def _raise_if_backing_off(self) -> None:
        with self._backoff_lock:
            remaining = self._backoff_until - time.monotonic()
            reason = self._backoff_reason
        if remaining > 0:
            raise TidalBackoffError(remaining, reason)

    def _start_backoff_if_needed(self, response: requests.Response) -> None:
        """Hold back further requests after a rate limit or anti-abuse response.

        Requests made while TIDAL is limiting or suspecting the account only prolong
        it, and can lead to a permanent ban.
        """
        if not self.config.backoff:
            return
        # Only inspect error responses, this runs for every request
        if response.status_code == 429:
            retry_after = get_retry_after(response)
            seconds = retry_after if retry_after > 0 else RATE_LIMIT_BACKOFF
            reason = "rate limited (HTTP 429)"
        elif is_abuse_response(response):
            retry_after = get_retry_after(response)
            seconds = retry_after if retry_after > 0 else ABUSE_BACKOFF
            reason = f"abuse detected (HTTP 403): {response.text[:200]}"
        else:
            return
        log.warning("Backing off from TIDAL for %ds: %s", seconds, reason)
        with self._backoff_lock:
            # Never shorten a backoff that is already running
            until = time.monotonic() + seconds
            if until > self._backoff_until:
                self._backoff_until = until
                self._backoff_reason = reason

    def _access_token_expired(self) -> bool:
        """Whether the session's access token is expired, or about to be.

        TIDAL signals an expired token with a `userMessage` that has changed over time,
        so relying on that alone lets raw 401s reach the caller. The expiry time is
        checked up front whenever it is known.
        """
        expiry_time = self.session.expiry_time
        if not expiry_time or not self.session.refresh_token:
            return False
        if expiry_time.tzinfo is None:
            now = datetime.datetime.utcnow()
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
        return expiry_time - now <= TOKEN_EXPIRY_MARGIN

    def _send(
        self,
        method: Methods,
        url: str,
        request_params: Mapping[str, Union[str, int, None]],
        data: Optional[JsonObj],
        headers: MutableMapping[str, str],
    ) -> requests.Response:
        """Send a request with the session's current access token."""
        self._raise_if_backing_off()
        access_token = self.session.access_token
        if self.session.token_type and access_token is not None:
            headers["authorization"] = self.session.token_type + " " + access_token
        response = self.session.request_session.request(
            method, url, params=request_params, data=data, headers=headers
        )
        self._start_backoff_if_needed(response)
        return response

    def basic_request(
        self,
        method: Methods,
        path: str,
        params: Optional[Params] = None,
        data: Optional[JsonObj] = None,
        headers: Optional[MutableMapping[str, str]] = None,
        base_url: Optional[str] = None,
    ) -> requests.Response:
        self._raise_if_backing_off()
        request_params = {
            "sessionId": self.session.session_id,
            "countryCode": self.session.country_code,
            "limit": self.config.item_limit,
        }

        if params:
            # Don't update items with a none value, as we prefer a default value.
            # requests also does not support them.
            not_none = filter(lambda item: item[1] is not None, params.items())
            request_params.update(not_none)

        if not headers:
            headers = {}

        if "x-tidal-client-version" not in headers:
            headers["x-tidal-client-version"] = self.client_version

        if "User-Agent" not in headers:
            headers["User-Agent"] = self.user_agent

        if self._access_token_expired():
            log.debug("The access token is about to expire, trying to refresh it.")
            try:
                self._refresh_access_token(self.session.access_token)
            except AuthenticationError as e:
                # Don't fail the request: the token may still be accepted, and if
                # it isn't, the expired-token handling below reports the failure.
                log.warning("Proactive access token refresh failed: %s", e)

        if base_url is None:
            base_url = self.session.config.api_v1_location

        url = urljoin(base_url, path)
        sent_access_token = self.session.access_token
        request = self._send(method, url, request_params, data, headers)

        refresh_token = self.session.refresh_token
        if not request.ok and refresh_token:
            json_resp = None
            try:
                json_resp = request.json()
            except json.decoder.JSONDecodeError:
                pass

            if json_resp and json_resp.get("userMessage", "").startswith(
                "The token has expired."
            ):
                log.debug("The access token has expired, trying to refresh it.")
                refreshed = self._refresh_access_token(sent_access_token)
                if refreshed:
                    # Retry exactly once. If TIDAL still reports an expired token
                    # (e.g. clock skew), return that response instead of looping.
                    request = self._send(method, url, request_params, data, headers)
            else:
                log.debug("HTTP error on %d", request.status_code)
                log.debug("Response text\n%s", request.text)

        return request

    def request(
        self,
        method: Methods,
        path: str,
        params: Optional[Params] = None,
        data: Optional[JsonObj] = None,
        headers: Optional[MutableMapping[str, str]] = None,
        base_url: Optional[str] = None,
    ) -> requests.Response:
        """Method for tidal requests.

        Not meant for use outside of this library.

        :param method: The type of request to make
        :param path: The TIDAL api endpoint you want to use.
        :param params: The parameters you want to supply with the request.
        :param data: The data you want to supply with the request.
        :param headers: The headers you want to include with the request
        :param base_url: The base url to use for the request
        :return: The json data at specified api endpoint.
        """

        request = self.basic_request(method, path, params, data, headers, base_url)
        log.debug("request: %s", request.request.url)
        try:
            request.raise_for_status()
        except requests.HTTPError as e:
            log.info("Request resulted in exception {}".format(e))
            self.latest_err_response = request
            if err := http_error_to_tidal_error(e):
                raise err from e
            else:
                raise  # re-raise last error, usually HTTPError
        return request

    def get_latest_err_response(self) -> dict:
        """Get the latest request Response that resulted in an Exception.

        :return: The request Response that resulted in the Exception, returned as a dict
            An empty dict will be returned, if no response was returned.
        """
        if self.latest_err_response.content:
            return self.latest_err_response.json()
        else:
            return {}

    def get_latest_err_response_str(self) -> str:
        """Get the latest request response message as a string.

        :return: The contents of the (detailed) error response, returned as a string An
            empty str will be returned, if no response was returned.
        """
        if self.latest_err_response.content:
            resp = self.latest_err_response.json()
            return resp["errors"][0]["detail"]
        else:
            return ""

    def map_request(
        self,
        url: str,
        params: Optional[Params] = None,
        parse: Optional[Callable[..., Any]] = None,
    ) -> Any:
        """Returns the data about object(s) at the specified url, with the method
        specified in the parse argument.

        Not meant for use outside of this library

        :param url: TIDAL api endpoint that contains the data
        :param params: TIDAL parameters to use when getting the data
        :param parse: (Optional) The method used to parse the data at the url. If not
            set, jsonObj will be returned
        :return: The object(s) at the url, with the same type as the class of the parse
            method.
        """
        json_obj = self.request("GET", url, params).json()
        if parse:
            return self.map_json(json_obj, parse=parse)
        else:
            return json_obj

    @classmethod
    def map_json(
        cls,
        json_obj: JsonObj,
        parse: Optional[Callable[..., Any]] = None,
        session: Optional["Session"] = None,
    ) -> Any:
        items = json_obj.get("items")

        if items is None:
            # Not a collection of items, so returning a single object
            if parse is None:
                raise ValueError("A parser must be supplied")
            return parse(json_obj)

        if len(items) > 0 and "item" in items[0]:
            # Move created date into the item json data like it is done for playlists tracks.
            if "created" in items[0]:
                for item in items:
                    item["item"]["dateAdded"] = item["created"]

            lists: List[Any] = []
            for item in items:
                if session is not None:
                    parse = cast(
                        Callable[..., Any],
                        session.convert_type(
                            cast(str, item["type"]).lower() + "s", output="parse"
                        ),
                    )
                if parse is None:
                    raise ValueError("A parser must be supplied")
                lists.append(parse(item["item"]))

            return lists
        if parse is None:
            raise ValueError("A parser must be supplied")
        return list(map(parse, items))
