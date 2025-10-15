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

from __future__ import annotations

import base64
import concurrent.futures
import datetime
import hashlib
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Literal,
    Optional,
    Tuple,
    TypedDict,
    Union,
    cast,
    no_type_check,
)
from urllib.parse import parse_qs, urlencode, urlsplit

import pyaes
import requests
from requests.exceptions import HTTPError

from tidalapi.exceptions import *
from tidalapi.types import JsonObj

from . import album, artist, genre, media, mix, page, playlist, request, user

if TYPE_CHECKING:
    from tidalapi.user import FetchedUser, LoggedInUser, PlaylistCreator

log = logging.getLogger(__name__)
SearchTypes: List[Optional[Any]] = [
    artist.Artist,
    album.Album,
    media.Track,
    media.Video,
    playlist.Playlist,
    None,
]


class LinkLogin:
    """The data required for logging in to TIDAL using a remote link, json is the data
    returned from TIDAL."""

    #: Amount of seconds until the code expires
    expires_in: int
    #: The code the user should enter at the uri
    user_code: str
    #: The link the user has to visit
    verification_uri: str
    #: The link the user has to visit, with the code already included
    verification_uri_complete: str
    #: After how much time the uri expires.
    expires_in: float
    #: The interval for authorization checks against the backend.
    interval: float
    #: The unique device code necessary for authorization.
    device_code: str

    def __init__(self, json: JsonObj):
        self.expires_in = int(json["expiresIn"])
        self.user_code = str(json["userCode"])
        self.verification_uri = str(json["verificationUri"])
        self.verification_uri_complete = str(json["verificationUriComplete"])
        self.expires_in = float(json["expiresIn"])
        self.interval = float(json["interval"])
        self.device_code = str(json["deviceCode"])


class Config:
    """Configuration for TIDAL services.

    The maximum item_limit is 10000, and some endpoints have a maximum of 100 items, which will be shown in the docs.
    In cases where the maximum is 100 items, you will have to use offsets to get more than 100 items.
    Note that changing the ALAC option requires you to log in again, and for you to create a new config object
    IMPORTANT: ALAC=false will mean that video streams turn into audio-only streams.
               Additionally, num_videos will turn into num_tracks in playlists.
    """

    api_oauth2_token: str = "https://auth.tidal.com/v1/oauth2/token"
    api_pkce_auth: str = "https://login.tidal.com/authorize"
    api_v1_location: str = "https://api.tidal.com/v1/"
    api_v2_location: str = "https://api.tidal.com/v2/"
    openapi_v2_location: str = "https://openapi.tidal.com/v2/"
    client_id: str
    client_secret: str
    image_url: str = "https://resources.tidal.com/images/%s/%ix%i.jpg"
    image_url_origin: str = "https://resources.tidal.com/images/%s/origin.jpg"
    item_limit: int
    quality: str
    video_quality: str
    video_url: str = "https://resources.tidal.com/videos/%s/%ix%i.mp4"
    video_url_origin: str = "https://resources.tidal.com/videos/%s/origin.mp4"
    # Necessary for PKCE authorization only
    client_unique_key: str
    code_verifier: str
    code_challenge: str
    pkce_uri_redirect: str = "https://tidal.com/android/login/auth"
    client_id_pkce: str
    # Base URLs for sharing, listen URLs
    listen_base_url: str = "https://listen.tidal.com"
    share_base_url: str = "https://tidal.com/browse"

    @no_type_check
    def __init__(
        self,
        quality: str = media.Quality.default,
        video_quality: str = media.VideoQuality.default,
        item_limit: int = 1000,
        alac: bool = True,
    ):
        self.quality = quality
        self.video_quality = video_quality
        self.alac = alac

        if item_limit > 10000:
            log.warning(
                "Item limit was set above 10000, which is not supported by TIDAL, setting to 10000"
            )
            self.item_limit = 10000
        else:
            self.item_limit = item_limit

        # OAuth Client Authorization
        self.client_id = base64.b64decode(
            base64.b64decode(b"V214bmVWTnVhR3RpVnpVdw==")
            + base64.b64decode(b"VjJ4a1RFMUhiRFJXUVQwOQ==")
        ).decode("utf-8")
        self.client_secret = base64.b64decode(
            base64.b64decode(
                b"VFZVMWRVOVZSbTFTUlVaeFpVaEtibE5yV2t0WmEzUlBWakI0YkZGWQ=="
            )
            + base64.b64decode(
                b"YkV4U01WcElZbFZzVDJSV2FGRlZSWGhKVm14b1FtUnVhRUphZWpBOQ=="
            )
        ).decode("utf-8")

        # If client_secret not supplied, fall back to client_id (matching original behavior)
        if not self.client_secret and self.client_id:
            self.client_secret = self.client_id

        # PKCE Client Authorization. We will keep the former `client_id` as a fallback / will only be used for non PCKE
        # authorizations.
        self.client_unique_key = format(random.getrandbits(64), "02x")
        self.code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1].decode(
            "utf-8"
        )
        self.code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self.code_verifier.encode("utf-8")).digest()
        )[:-1].decode("utf-8")
        self.client_id_pkce = base64.b64decode(
            base64.b64decode(b"TmtKRVUxSmtjRXM=")
            + base64.b64decode(b"NWFIRkZRbFJuVlE9PQ==")
        ).decode("utf-8")
        self.client_secret_pkce = base64.b64decode(
            base64.b64decode(b"ZUdWMVVHMVpOMjVpY0ZvNVNVbGlURUZqVVQ=")
            + base64.b64decode(b"a3pjMmhyWVRGV1RtaGxWVUZ4VGpaSlkzTjZhbFJIT0QwPQ==")
        ).decode("utf-8")


class Case(Enum):
    pascal = id
    scream = id
    lower = id

    identifier: List[str]
    type: List[Union[object, None]]
    parse: List[Callable[..., Any]]


TypeConversionKeys = Literal["identifier", "type", "parse"]


@dataclass
class TypeRelation:
    identifier: str
    type: Optional[Any]
    parse: Callable[..., Any]


class SearchResults(TypedDict):
    artists: List[artist.Artist]
    albums: List[album.Album]
    tracks: List[media.Track]
    videos: List[media.Video]
    playlists: List[Union[playlist.Playlist, playlist.UserPlaylist]]
    top_hit: Optional[List[Any]]


class Session:
    """Object for interacting with the TIDAL api and."""

    #: The TIDAL access token, this is what you use with load_oauth_session
    access_token: Optional[str] = None
    #: A :class:`datetime` object containing the date the access token will expire
    expiry_time: Optional[datetime.datetime] = None
    #: A refresh token for retrieving a new access token through refresh_token
    refresh_token: Optional[str] = None
    #: The type of access token, e.g. Bearer
    token_type: Optional[str] = None
    #: The session id for a TIDAL session, you also need this to use load_oauth_session
    session_id: Optional[str] = None
    country_code: Optional[str] = None
    locale: Optional[str] = None
    #: A :class:`.User` object containing the currently logged in user.
    user: Optional[Union["FetchedUser", "LoggedInUser", "PlaylistCreator"]] = None

    def __init__(self, config: Config = Config()):
        self.config = config
        self.request_session = requests.Session()

        # Objects for keeping the session across all modules.
        self.request = request.Requests(session=self)
        self.genre = genre.Genre(session=self)

        self.parse_user = user.User(self, None).parse
        self.page = page.Page(self, "")
        self.parse_page = self.page.parse

        self.is_pkce = False  # True if current session is PKCE type, otherwise false

        self.type_conversions: List[TypeRelation] = [
            TypeRelation(
                identifier=identifier, type=type, parse=cast(Callable[..., Any], parse)
            )
            for identifier, type, parse in zip(
                (
                    "artists",
                    "albums",
                    "tracks",
                    "videos",
                    "playlists",
                    "mixs",
                ),
                SearchTypes,
                (
                    self.parse_artist,
                    self.parse_album,
                    self.parse_track,
                    self.parse_video,
                    self.parse_playlist,
                    self.parse_mix,
                ),
            )
        ]

    def parse_album(self, obj: JsonObj) -> album.Album:
        """Parse an album from the given response."""
        return self.album().parse(obj)

    def parse_track(
        self, obj: JsonObj, album: Optional[album.Album] = None
    ) -> media.Track:
        """Parse an album from the given response."""
        return self.track().parse_track(obj, album)

    def parse_video(self, obj: JsonObj) -> media.Video:
        """Parse an album from the given response."""
        return self.video().parse_video(obj)

    def parse_media(
        self, obj: JsonObj, album: Optional[album.Album] = None
    ) -> Union[media.Track, media.Video]:
        """Parse a media type (track, video) from the given response."""
        return self.track().parse_media(obj, album)

    def parse_artist(self, obj: JsonObj) -> artist.Artist:
        """Parse an artist from the given response."""
        return self.artist().parse_artist(obj)

    def parse_artists(self, obj: List[JsonObj]) -> List[artist.Artist]:
        """Parse an artist from the given response."""
        return self.artist().parse_artists(obj)

    def parse_mix(self, obj: JsonObj) -> mix.Mix:
        """Parse a mix from the given response."""
        return self.mix().parse(obj)

    def parse_v2_mix(self, obj: JsonObj) -> mix.Mix:
        """Parse a mixV2 from the given response."""
        return self.mixv2().parse(obj)

    def parse_playlist(self, obj: JsonObj) -> playlist.Playlist:
        """Parse a playlist from the given response."""
        # Note: When parsing playlists from v2 response, "data" field must be parsed
        return self.playlist().parse(obj)

    def parse_folder(self, obj: JsonObj) -> playlist.Folder:
        """Parse an album from the given response."""
        return self.folder().parse(obj)

    def convert_type(
        self,
        search: Any,
        search_type: TypeConversionKeys = "identifier",
        output: TypeConversionKeys = "identifier",
        case: Case = Case.lower,
        suffix: bool = True,
    ) -> Union[str, Callable[..., Any]]:
        type_relations = next(
            x for x in self.type_conversions if getattr(x, search_type) == search
        )
        result = getattr(type_relations, output)

        if output == "identifier":
            result = cast(str, result)
            if suffix is False:
                result = result.strip("s")
            if case == Case.scream:
                result = result.lower()
            elif case == Case.pascal:
                result = result[0].upper() + result[1:]

        return cast(Callable[..., Any], result)

    def load_session(
        self,
        session_id: str,
        country_code: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> bool:
        """Establishes TIDAL login details using a previous session id. May return true
        if the session-id is invalid/expired, you should verify the login afterwards.

        :param session_id: The UUID of the session you want to use.
        :param country_code: (Optional) Two-letter country code.
        :param user_id: (Optional) The number identifier of the user.
        :return: False if we know the session_id is incorrect, otherwise True
        """
        try:
            uuid.UUID(session_id)
        except ValueError:
            log.error("Session id did not have a valid UUID format")
            return False

        self.session_id = session_id
        if not user_id or not country_code:
            request = self.request.request("GET", "sessions").json()
            country_code = request["countryCode"]
            user_id = request["userId"]

        self.country_code = country_code
        self.user = user.User(self, user_id=user_id).factory()
        return True

    def load_oauth_session(
        self,
        token_type: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expiry_time: Optional[datetime.datetime] = None,
        is_pkce: Optional[bool] = False,
    ) -> bool:
        """Login to TIDAL using details from a previous OAuth login, automatically
        refreshes expired access tokens if refresh_token is supplied as well.

        :param token_type: The type of token, e.g. Bearer
        :param access_token: The access token received from an oauth login or refresh
        :param refresh_token: (Optional) A refresh token that lets you get a new access
            token after it has expired
        :param expiry_time: (Optional) The datetime the access token will expire
        :param is_pkce: (Optional) Is session pkce?
        :return: True if we believe the login was successful, otherwise false.
        """
        self.token_type = token_type
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expiry_time = expiry_time
        self.is_pkce = is_pkce

        request = self.request.request("GET", "sessions")
        json = request.json()
        if not request.ok:
            return False

        self.session_id = json["sessionId"]
        self.country_code = json["countryCode"]
        self.locale = "en_US"  # TODO Get locale from system configuration
        self.user = user.User(self, user_id=json["userId"]).factory()

        return True

    def login_session_file(
        self,
        session_file: Path,
        do_pkce: Optional[bool] = False,
        fn_print: Callable[[str], None] = print,
    ) -> bool:
        """Logs in to the TIDAL api using an existing OAuth/PKCE session file. If no
        session json file exists, a new one will be created after successful login.

        :param session_file: The session json file
        :param do_pkce: Perform PKCE login. Default: Use OAuth logon
        :param fn_print: A function which will be called to print the challenge text,
            defaults to `print()`.
        :return: Returns true if we think the login was successful.
        """
        self.load_session_from_file(session_file)

        # Session could not be loaded, attempt to create a new session
        if not self.check_login():
            if do_pkce:
                log.info("Creating new session (PKCE)...")
                self.login_pkce(fn_print=fn_print)
            else:
                log.info("Creating new session (OAuth)...")
                self.login_oauth_simple(fn_print=fn_print)

        if self.check_login():
            log.info("TIDAL Login OK")
            self.save_session_to_file(session_file)
            return True
        else:
            log.info("TIDAL Login KO")
            return False

    def login_pkce(self, fn_print: Callable[[str], None] = print) -> None:
        """Login handler for PKCE based authentication. This is the only way how to get
        access to HiRes (Up to 24-bit, 192 kHz) FLAC files.

        This handler will ask you to follow a URL, process with the login in the browser
        and copy & paste the URL of the redirected browser page.

        :param fn_print: A function which will be called to print the instructions,
            defaults to `print()`.
        :type fn_print: Callable, optional
        :return:
        """
        # Get login url
        url_login: str = self.pkce_login_url()

        fn_print("READ CAREFULLY!")
        fn_print("---------------")
        fn_print(
            "You need to open this link and login with your username and password. "
            "Afterwards you will be redirected to an 'Oops' page. "
            "To complete the login you must copy the URL from this 'Oops' page and paste it to the input field."
        )
        fn_print(url_login)

        # Get redirect URL from user input.
        url_redirect: str = input("Paste 'Ooops' page URL here and press <ENTER>:")
        # Query for auth tokens
        json: dict[str, Union[str, int]] = self.pkce_get_auth_token(url_redirect)

        # Parse and set tokens.
        self.process_auth_token(json, is_pkce_token=True)

        # Swap the client_id and secret
        # self.client_enable_hires()

    def client_enable_hires(self):
        self.config.client_id = self.config.client_id_pkce
        self.config.client_secret = self.config.client_secret_pkce

    def pkce_login_url(self) -> str:
        """Returns the Login-URL to login via web browser.

        :return: The URL the user has to use for login.
        :rtype: str
        """
        params: request.Params = {
            "response_type": "code",
            "redirect_uri": self.config.pkce_uri_redirect,
            "client_id": self.config.client_id_pkce,
            "lang": "EN",
            "appMode": "android",
            "client_unique_key": self.config.client_unique_key,
            "code_challenge": self.config.code_challenge,
            "code_challenge_method": "S256",
            "restrict_signup": "true",
        }

        return self.config.api_pkce_auth + "?" + urlencode(params)

    def pkce_get_auth_token(self, url_redirect: str) -> dict[str, Union[str, int]]:
        """Parses the redirect url to extract access and refresh tokens.

        :param url_redirect: URL of the 'Ooops' page, where the user was redirected to
            after login.
        :type url_redirect: str
        :return: A parsed JSON object with access and refresh tokens and other
            information.
        :rtype: dict[str, str | int]
        """
        # w_usr=WRITE_USR, r_usr=READ_USR_DATA, w_sub=WRITE_SUBSCRIPTION
        scope_default: str = "r_usr+w_usr+w_sub"

        # Extract the code parameter from query string
        if url_redirect and "https://" in url_redirect:
            code: str = parse_qs(urlsplit(url_redirect).query)["code"][0]
        else:
            raise Exception("The provided redirect url looks wrong: " + url_redirect)

        # Set post data and call the API
        data: request.Params = {
            "code": code,
            "client_id": self.config.client_id_pkce,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.pkce_uri_redirect,
            "scope": scope_default,
            "code_verifier": self.config.code_verifier,
            "client_unique_key": self.config.client_unique_key,
        }
        response = self.request_session.post(self.config.api_oauth2_token, data)

        # Check response
        if not response.ok:
            log.error("Login failed: %s", response.text)
            response.raise_for_status()

        # Parse the JSON response.
        try:
            token: dict[str, Union[str, int]] = response.json()
        except:
            raise Exception("Wrong one-time authorization code", response)

        return token

    def login_oauth_simple(self, fn_print: Callable[[str], None] = print) -> None:
        """Login to TIDAL using a remote link. You can select what function you want to
        use to display the link.

        :param fn_print: The function you want to display the link with
        :raises: TimeoutError: If the login takes too long
        """

        login, future = self.login_oauth()
        text = "Visit https://{0} to log in, the code will expire in {1} seconds"
        fn_print(text.format(login.verification_uri_complete, login.expires_in))
        future.result()

    def login_oauth(self) -> Tuple[LinkLogin, concurrent.futures.Future[Any]]:
        """Login to TIDAL with a remote link for limited input devices. The function
        will return everything you need to log in through a web browser, and will return
        a future that will run until login.

        :return: A :class:`LinkLogin` object containing all the data needed to log in remotely, and
            a :class:`concurrent.futures.Future` object that will poll until the login is completed, or until the link expires.
        :rtype: :class:`LinkLogin`
        :raises: TimeoutError: If the login takes too long
        """
        link_login: LinkLogin = self.get_link_login()
        executor = concurrent.futures.ThreadPoolExecutor()

        return link_login, executor.submit(self.process_link_login, link_login)

    def save_session_to_file(self, session_file: Path):
        # create a new session
        if self.check_login():
            # store current session session
            data = {
                "token_type": {"data": self.token_type},
                "session_id": {"data": self.session_id},
                "access_token": {"data": self.access_token},
                "refresh_token": {"data": self.refresh_token},
                "is_pkce": {"data": self.is_pkce},
                # "expiry_time": {"data": self.expiry_time},
            }
            with session_file.open("w") as file:
                json.dump(data, file)

    def load_session_from_file(self, session_file: Path):
        try:
            with session_file.open("r") as file:
                log.info("Loading session from %s...", session_file)
                data = json.load(file)
        except Exception as e:
            log.info("Could not load session from %s: %s", session_file, e)
            return False

        assert self, "No session loaded"
        args = {
            "token_type": data.get("token_type", {}).get("data"),
            "access_token": data.get("access_token", {}).get("data"),
            "refresh_token": data.get("refresh_token", {}).get("data"),
            "is_pkce": data.get("is_pkce", {}).get("data"),
            # "expiry_time": data.get("expiry_time", {}).get("data"),
        }

        return self.load_oauth_session(**args)

    def get_link_login(self) -> LinkLogin:
        """Return information required to login into TIDAL using a device authorization
        link.

        :return: Login information for device authorization retrieved from the TIDAL backend.
        :rtype: :class:`LinkLogin`
        """
        url = "https://auth.tidal.com/v1/oauth2/device_authorization"
        params = {"client_id": self.config.client_id, "scope": "r_usr w_usr w_sub"}

        request = self.request_session.post(url, params)

        if not request.ok:
            log.error("Login failed: %s", request.text)
            request.raise_for_status()

        json = request.json()

        return LinkLogin(json)

    def process_link_login(
        self, link_login: LinkLogin, until_expiry: bool = True
    ) -> bool:
        """Checks if device authorization was successful and processes the retrieved
        OAuth token from the Backend.

        :param link_login: Link login information containing the necessary device authorization information.
        :type link_login: :class:`LinkLogin`
        :param until_expiry: If `True` device authorization check is running until the link expires. If `False`check is running only once.
        :type until_expiry: :class:`bool`

        :return: `True` if login was successful.
        :rtype: bool
        """
        result: JsonObj = self._check_link_login(link_login, until_expiry)
        result_process: bool = self.process_auth_token(result, is_pkce_token=False)

        return result_process

    def process_auth_token(
        self, json: dict[str, Union[str, int]], is_pkce_token: bool = True
    ) -> bool:
        """Parses the authorization response and sets the token values to the specific
        variables for further usage.

        :param json: Parsed JSON response after login / authorization.
        :type json: dict[str, str | int]
        :param is_pkce_token: Set true if current token is obtained using PKCE
        :type is_pkce_token: bool
        :return: `True` if no error occurs.
        :rtype: bool
        """
        self.access_token = json["access_token"]
        self.expiry_time = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=json["expires_in"]
        )
        self.refresh_token = json["refresh_token"]
        self.token_type = json["token_type"]
        session = self.request.request("GET", "sessions")
        json = session.json()
        self.session_id = json["sessionId"]
        self.country_code = json["countryCode"]
        self.locale = "en_US"  # TODO Set locale from system configuration
        self.user = user.User(self, user_id=json["userId"]).factory()
        self.is_pkce = is_pkce_token

        return True

    def _check_link_login(
        self, link_login: LinkLogin, until_expiry: bool = True
    ) -> TimeoutError | JsonObj:
        """Checks if device authorization was successful and retrieves OAuth data. Can
        check the backend for successful device authrization until the link expires
        (with the given interval) or just once.

        :param link_login: Link login information containing the necessary device authorization information.
        :type link_login: :class:`LinkLogin`
        :param until_expiry: If `True` device authorization check is running until the link expires. If `False`check is running only once.
        :type until_expiry: :class:`bool`
        :return: Raise :class:`TimeoutError` if the link has expired otherwise returns retrieved OAuth information.
        :rtype: :class:`TimeoutError` | :class:`JsonObj`
        """
        expiry: float = link_login.expires_in if until_expiry else 1
        url = self.config.api_oauth2_token
        params = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "device_code": link_login.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr w_usr w_sub",
        }

        while expiry > 0:
            request = self.request_session.post(url, params)
            result: JsonObj = request.json()

            if request.ok:
                return result

            # Because the requests take time, the expiry variable won't be accurate, so stop if TIDAL says it's expired
            if result["error"] == "expired_token":
                break

            time.sleep(link_login.interval)
            expiry = expiry - link_login.interval

        raise TimeoutError("You took too long to log in")

    def token_refresh(self, refresh_token: str) -> bool:
        """Retrieves a new access token using the specified parameters, updating the
        current access token.

        :param refresh_token: The refresh token retrieved when using the OAuth login.
        :return: True if we believe the token was successfully refreshed, otherwise
            False
        """
        url = self.config.api_oauth2_token
        params = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": (
                self.config.client_id_pkce if self.is_pkce else self.config.client_id
            ),
            "client_secret": (
                self.config.client_secret_pkce
                if self.is_pkce
                else self.config.client_secret
            ),
        }

        request = self.request_session.post(url, params)
        json = request.json()
        if request.status_code != 200:
            raise AuthenticationError("Authentication failed")
            # raise AuthenticationError(Authentication failed json["error"], json["error_description"])
        if not request.ok:
            log.warning("The refresh token has expired, a new login is required.")
            return False
        self.access_token = json["access_token"]
        self.expiry_time = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=json["expires_in"]
        )
        self.token_type = json["token_type"]
        return True

    @property
    def audio_quality(self) -> str:
        return self.config.quality

    @audio_quality.setter
    def audio_quality(self, quality: str) -> None:
        self.config.quality = quality

    @property
    def video_quality(self) -> str:
        return self.config.video_quality

    @video_quality.setter
    def video_quality(self, quality: str) -> None:
        self.config.video_quality = quality

    def search(
        self,
        query: str,
        models: Optional[List[Optional[Any]]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResults:
        """Searches TIDAL with the specified query, you can also specify what models you
        want to search for. While you can set the offset, there aren't more than 300
        items available in a search.

        :param query: The string you want to search for
        :param models: A list of tidalapi models you want to include in the search.
            Valid models are :class:`.Artist`, :class:`.Album`, :class:`.Track`, :class:`.Video`, :class:`.Playlist`
        :param limit: The amount of items you want included, up to 300.
        :param offset: The index you want to start searching at.
        :return: Returns a dictionary of the different models, with the dictionary values containing the search results.
            The dictionary also contains a 'top_hit' result for the most relevant result, limited to the specified types
        """
        if not models:
            models = SearchTypes

        types: List[str] = []
        # This converts the specified TIDAL models in the models list into the text versions so we can parse it.
        for model in models:
            if model not in SearchTypes:
                raise ValueError("Tried to search for an invalid type")
            types.append(cast(str, self.convert_type(model, "type")))

        params: request.Params = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "types": ",".join(types),
        }

        json_obj = self.request.request("GET", "search", params=params).json()

        result: SearchResults = {
            "artists": self.request.map_json(json_obj["artists"], self.parse_artist),
            "albums": self.request.map_json(json_obj["albums"], self.parse_album),
            "tracks": self.request.map_json(json_obj["tracks"], self.parse_track),
            "videos": self.request.map_json(json_obj["videos"], self.parse_video),
            "playlists": self.request.map_json(
                json_obj["playlists"], self.parse_playlist
            ),
            "top_hit": None,
        }

        # Find the type of the top hit so we can parse it
        if json_obj["topHit"]:
            top_type = json_obj["topHit"]["type"].lower()
            parse = self.convert_type(top_type, output="parse")
            result["top_hit"] = self.request.map_json(
                json_obj["topHit"]["value"], cast(Callable[..., Any], parse)
            )

        return result

    def check_login(self) -> bool:
        """Returns true if current session is valid, false otherwise."""
        if self.user is None or not self.user.id or not self.session_id:
            return False
        return self.request.basic_request(
            "GET", "users/%s/subscription" % self.user.id
        ).ok

    def playlist(
        self, playlist_id: Optional[str] = None
    ) -> Union[playlist.Playlist, playlist.UserPlaylist]:
        """Function to create a playlist object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Playlist(session=session,
        playlist_id=playlist_id) <.Playlist>` internally.

        :param playlist_id: (Optional) The TIDAL id of the playlist. You may want access to the methods without an id.
        :return: Returns a :class:`.Playlist` object that has access to the session instance used.
        """
        try:
            return playlist.Playlist(session=self, playlist_id=playlist_id).factory()
        except ObjectNotFound:
            log.warning("Playlist '%s' is unavailable", playlist_id)
            raise

    def folder(self, folder_id: Optional[str] = None) -> playlist.Folder:
        """Function to create a Folder object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Folder(session=session, folder_id=track_id)
        <.Folder>` internally.

        :param folder_id:
        :return: Returns a :class:`.Folder` object that has access to the session instance used.
        """
        try:
            return playlist.Folder(session=self, folder_id=folder_id)
        except ObjectNotFound:
            log.warning("Folder '%s' is unavailable", folder_id)
            raise

    def track(
        self, track_id: Optional[str] = None, with_album: bool = False
    ) -> media.Track:
        """Function to create a Track object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Track(session=session, track_id=track_id)
        <.Track>` internally.

        :param track_id: (Optional) The TIDAL id of the Track. You may want access to the methods without an id.
        :param with_album: (Optional) Whether to fetch the complete :class:`.Album` for the track or not
        :return: Returns a :class:`.Track` object that has access to the session instance used.
        """
        try:
            item = media.Track(session=self, media_id=track_id)
            if item.album and with_album:
                alb = self.album(item.album.id)
                if alb:
                    item.album = alb
            return item
        except ObjectNotFound:
            log.warning("Track '%s' is unavailable", track_id)
            raise

    def get_tracks_by_isrc(self, isrc: str) -> list[media.Track]:
        """Function to search all tracks with a specific ISRC code. (eg. "USSM12209515")
        This method uses the TIDAL openapi (v2). See the apiref below for more details:
        https://apiref.developer.tidal.com/apiref?spec=catalogue-v2&ref=get-tracks-v2

        :param isrc: The ISRC of the Track.
        :return: Returns a list of :class:`.Track` objects that have access to the session instance used.
                 An empty list will be returned if no tracks matches the ISRC
        """
        try:
            params = {
                "filter[isrc]": isrc,
            }
            res = self.request.request(
                "GET",
                "tracks",
                params=params,
                base_url=self.config.openapi_v2_location,
            ).json()
            if res["data"]:
                tracks = []
                for tr in res["data"]:
                    try:
                        tracks.append(self.track(tr["id"]))
                    except ObjectNotFound:
                        continue
                return tracks
            else:
                log.warning("No matching tracks found for ISRC '%s'", isrc)
                raise ObjectNotFound
        except HTTPError:
            log.error("Invalid ISRC code '%s'", isrc)
            # Get latest detailed error response and return the response given from the TIDAL api
            resp_str = self.request.get_latest_err_response_str()
            if resp_str:
                log.error("API Response: '%s'", resp_str)
            raise InvalidISRC

    def get_albums_by_barcode(self, barcode: str) -> list[album.Album]:
        """Function to search all albums with a specific UPC code (eg. "196589525444")
        This method uses the TIDAL openapi (v2). See the apiref below for more details:
        https://apiref.developer.tidal.com/apiref?spec=catalogue-v2&ref=get-albums-v2

        :param barcode: The UPC of the Album. Eg.
        :return: Returns a list of :class:`.Album` objects that have access to the session instance used.
                 An empty list will be returned if no tracks matches the ISRC
        """
        try:
            params = {
                "filter[barcodeId]": barcode,
            }
            res = self.request.request(
                "GET",
                "albums",
                params=params,
                base_url=self.config.openapi_v2_location,
            ).json()
            if res["data"]:
                return [self.album(alb["id"]) for alb in res["data"]]
            else:
                log.warning("No matching albums found for UPC barcode '%s'", barcode)
                raise ObjectNotFound
        except HTTPError:
            log.error("Invalid UPC barcode '%s'.", barcode)
            # Get latest detailed error response and return the response given from the TIDAL api
            resp_str = self.request.get_latest_err_response_str()
            if resp_str:
                log.error("API Response: '%s'", resp_str)
            raise InvalidUPC

    def video(self, video_id: Optional[str] = None) -> media.Video:
        """Function to create a Video object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Video(session=session, video_id=video_id)
        <.Video>` internally.

        :param video_id: (Optional) The TIDAL id of the Video. You may want access to the methods without an id.
        :return: Returns a :class:`.Video` object that has access to the session instance used.
        """
        try:
            return media.Video(session=self, media_id=video_id)
        except ObjectNotFound:
            log.warning("Video '%s' is unavailable", video_id)
            raise

    def artist(self, artist_id: Optional[str] = None) -> artist.Artist:
        """Function to create a Artist object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Artist(session=session,
        artist_id=artist_id) <.Artist>` internally.

        :param artist_id: (Optional) The TIDAL id of the Artist. You may want access to the methods without an id.
        :return: Returns a :class:`.Artist` object that has access to the session instance used.
        """
        try:
            return artist.Artist(session=self, artist_id=artist_id)
        except ObjectNotFound:
            log.warning("Artist '%s' is unavailable", artist_id)
            raise

    def album(self, album_id: Optional[str] = None) -> album.Album:
        """Function to create a Album object with access to the session instance in a
        smoother way. Calls :class:`tidalapi.Album(session=session, album_id=album_id)
        <.Album>` internally.

        :param album_id: (Optional) The TIDAL id of the Album. You may want access to the methods without an id.
        :return: Returns a :class:`.Album` object that has access to the session instance used.
        """
        try:
            return album.Album(session=self, album_id=album_id)
        except ObjectNotFound:
            log.warning("Album '%s' is unavailable", album_id)
            raise

    def mix(self, mix_id: Optional[str] = None) -> mix.Mix:
        """Function to create a mix object with access to the session instance smoothly
        Calls :class:`tidalapi.Mix(session=session, mix_id=mix_id) <.Album>` internally.

        :param mix_id: (Optional) The TIDAL id of the Mix. You may want access to the mix methods without an id.
        :return: Returns a :class:`.Mix` object that has access to the session instance used.
        """
        try:
            return mix.Mix(session=self, mix_id=mix_id)
        except ObjectNotFound:
            log.warning("Mix '%s' is unavailable", mix_id)
            raise

    def mixv2(self, mix_id=None) -> mix.MixV2:
        """Function to create a mix object with access to the session instance smoothly
        Calls :class:`tidalapi.MixV2(session=session, mix_id=mix_id) <.Album>`
        internally.

        :param mix_id: (Optional) The TIDAL id of the Mix. You may want access to the mix methods without an id.
        :return: Returns a :class:`.MixV2` object that has access to the session instance used.
        """
        try:
            return mix.MixV2(session=self, mix_id=mix_id)
        except ObjectNotFound:
            log.warning("Mix '%s' is unavailable", mix_id)
            raise

    def get_user(
        self, user_id: Optional[int] = None
    ) -> Union["FetchedUser", "LoggedInUser", "PlaylistCreator"]:
        """Function to create a User object with access to the session instance in a
        smoother way. Calls :class:`user.User(session=session, user_id=user_id) <.User>`
        internally.

        :param user_id: (Optional) The TIDAL id of the User. You may want access to the methods without an id.
        :return: Returns a :class:`.User` object that has access to the session instance used.
        """

        return user.User(session=self, user_id=user_id).factory()

    def home(self, use_legacy_endpoint: bool = False) -> page.Page:
        """
        Retrieves the Home page, as seen on https://listen.tidal.com, using either the V2 or V1 (legacy) endpoint

        :param use_legacy_endpoint: (Optional) Request Page from legacy endpoint.
        :return: A :class:`.Page` object with the :class:`.PageCategory` list from the home page
        """
        if not use_legacy_endpoint:
            params = {"deviceType": "BROWSER", "locale": self.locale, "platform": "WEB"}

            json_obj = self.request.request(
                "GET",
                "home/feed/static",
                base_url=self.config.api_v2_location,
                params=params,
            ).json()
            return self.page.parse(json_obj)
        else:
            return self.page.get("pages/home")

    def explore(self) -> page.Page:
        """
        Retrieves the Explore page, as seen on https://listen.tidal.com/view/pages/explore

        :return: A :class:`.Page` object with the :class:`.PageCategory` list from the explore page
        """
        return self.page.get("pages/explore")

    def hires_page(self) -> page.Page:
        """
        Retrieves the HiRes page, as seen on https://listen.tidal.com/view/pages/hires

        :return: A :class:`.Page` object with the :class:`.PageCategory` list from the explore page
        """
        return self.page.get("pages/hires")

    def for_you(self) -> page.Page:
        """
        Retrieves the For You page, as seen on https://listen.tidal.com/view/pages/for_you

        :return: A :class:`.Page` object with the :class:`.PageCategory` list from the explore page
        """
        return self.page.get("pages/for_you")

    def videos(self) -> page.Page:
        """
        Retrieves the :class:`Videos<.Video>` page, as seen on https://listen.tidal.com/view/pages/videos

        :return: A :class:`.Page` object with a :class:`<.PageCategory>` list from the videos page
        """
        return self.page.get("pages/videos")

    def genres(self) -> page.Page:
        """
        Retrieves the global Genre page, as seen on https://listen.tidal.com/view/pages/genre_page

        :return: A :class:`.Page` object with the :class:`.PageCategory` list from the genre page
        """
        return self.page.get("pages/genre_page")

    def local_genres(self) -> page.Page:
        """
        Retrieves the local Genre page, as seen on https://listen.tidal.com/view/pages/genre_page_local

        :return: A :class:`.Page` object with the :class:`.PageLinks` list from the local genre page
        """
        return self.page.get("pages/genre_page_local")

    def moods(self) -> page.Page:
        """
        Retrieves the mood page, as seen on https://listen.tidal.com/view/pages/moods

        :return: A :class:`.Page` object with the :class:`.PageLinks` list from the moods page
        """
        return self.page.get("pages/moods")

    def mixes(self) -> page.Page:
        """
        Retrieves the current users mixes, as seen on https://listen.tidal.com/view/pages/my_collection_my_mixes

        :return: A list of :class:`.Mix`
        """
        return self.page.get("pages/my_collection_my_mixes")
