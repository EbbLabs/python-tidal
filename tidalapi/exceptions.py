from __future__ import annotations

import json
import logging

from requests import HTTPError

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


def http_error_to_tidal_error(http_error: HTTPError) -> TidalAPIError | None:
    response = http_error.response

    if response.content:
        json_data = response.json()
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
        retry_after = int(response.headers.get("Retry-After", -1))
        return TooManyRequests("Too many requests", retry_after=retry_after)

    return None
