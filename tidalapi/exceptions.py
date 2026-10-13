from __future__ import annotations

import json
import logging

from requests import HTTPError, Response

log = logging.getLogger(__name__)


class TidalAPIError(Exception):
    pass


class AuthenticationError(TidalAPIError):
    pass


class AssetNotAvailable(TidalAPIError):
    pass


class TooManyRequests(TidalAPIError):
    retry_after: int

    def __init__(self, message: str = "Too many requests", retry_after: int = -1):
        super().__init__(message)
        self.retry_after = retry_after


class AbuseDetected(TidalAPIError):
    """TIDAL's anti-abuse system rejected the request (HTTP 403 mentioning abuse or a
    suspension).

    Making further requests while this is in effect can escalate to a permanent ban.
    """

    retry_after: int
    reason: str

    def __init__(
        self,
        message: str = "Abuse detected by TIDAL",
        retry_after: int = -1,
        reason: str = "",
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.reason = reason


class TidalBackoffError(TidalAPIError):
    """Raised instead of sending a request while a backoff period, started by a rate
    limit or abuse response, is still in effect.

    See :attr:`Config.backoff`.
    """

    seconds_remaining: float
    reason: str

    def __init__(self, seconds_remaining: float, reason: str):
        super().__init__(
            f"Backing off from TIDAL for another {seconds_remaining:.0f}s: {reason}"
        )
        self.seconds_remaining = seconds_remaining
        self.reason = reason


class URLNotAvailable(TidalAPIError):
    pass


class StreamNotAvailable(TidalAPIError):
    pass


class MetadataNotAvailable(TidalAPIError):
    pass


class ObjectNotFound(TidalAPIError):
    pass


class UnknownManifestFormat(TidalAPIError):
    pass


class ManifestDecodeError(TidalAPIError):
    pass


class MPDNotAvailableError(TidalAPIError):
    pass


class InvalidISRC(TidalAPIError):
    pass


class InvalidUPC(TidalAPIError):
    pass


def get_retry_after(response: Response) -> int:
    """The Retry-After header of a response in seconds, or -1 if absent or not a number
    of seconds."""
    try:
        return int(response.headers.get("Retry-After", -1))
    except ValueError:
        return -1


def is_abuse_response(response: Response) -> bool:
    """Whether the response is TIDAL's anti-abuse rejection: HTTP 403 whose body
    mentions abuse or a suspension."""
    if response.status_code != 403:
        return False
    text = (response.text or "").lower()
    return "abuse" in text or "suspend" in text


def http_error_to_tidal_error(http_error: HTTPError) -> TidalAPIError | None:
    response = http_error.response

    if response.content:
        try:
            json_data = response.json()
        except ValueError:
            # Not every error body is JSON, e.g. gateway or anti-abuse rejections
            log.debug("Request response: '%s'", response.text[:200])
        else:
            # Make sure request response contains the detailed error message
            if "errors" in json_data:
                log.debug("Request response: '%s'", json_data["errors"][0]["detail"])
            elif "userMessage" in json_data:
                log.debug("Request response: '%s'", json_data["userMessage"])
            else:
                log.debug("Request response: '%s'", json.dumps(json_data))

    if response.status_code == 404:
        return ObjectNotFound("Object not found")
    elif response.status_code == 429:
        return TooManyRequests(
            "Too many requests", retry_after=get_retry_after(response)
        )
    elif is_abuse_response(response):
        return AbuseDetected(
            retry_after=get_retry_after(response), reason=response.text[:200]
        )

    return None
