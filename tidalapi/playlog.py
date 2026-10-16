# Copyright (C) 2023- The Tidalapi Developers
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
"""Reporting plays to TIDAL (the play log).

Fetching and playing a stream doesn't count as a play: the official TIDAL players report
every play as a ``playback_session`` event to TIDAL's event producer. Reported plays
show up in Recently played on all devices and in the listening history TIDAL uses for
recommendations.

The event layout follows TIDAL's open source SDK (

https://github.com/tidal-music/tidal-sdk-android,
modules ``eventproducer`` and
``player/events``). The events describe the real client (the operating system and
the application version), they don't pretend to come from an official TIDAL app.
"""

from __future__ import annotations

import base64
import json
import logging
import platform
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Iterable, List, Optional, Union

import requests

from tidalapi import media
from tidalapi.exceptions import AuthenticationError, http_error_to_tidal_error
from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.session import Session

log = logging.getLogger(__name__)

#: The most events TIDAL's event producer accepts in one request
MAX_BATCH_SIZE = 10


class SourceType(str, Enum):
    """What a track was played from.

    A track played on its own (from search, a list of tracks, the play queue) is an
    ``ITEM`` with the track's own id as source id.
    """

    album = "ALBUM"
    playlist = "PLAYLIST"
    mix = "MIX"
    artist = "ARTIST"
    item = "ITEM"

    def __str__(self) -> str:
        return self.value


class ActionType(str, Enum):
    """A change during a play: playback stopped (paused) or started (resumed)."""

    playback_start = "PLAYBACK_START"
    playback_stop = "PLAYBACK_STOP"

    def __str__(self) -> str:
        return self.value


@dataclass
class PlaybackAction:
    """A pause, resume or seek during a play.

    A pause is a ``PLAYBACK_STOP``, resuming is a ``PLAYBACK_START``. A seek is a
    ``PLAYBACK_STOP`` at the old position followed by a ``PLAYBACK_START`` at the new
    one.

    :param timestamp: When it happened, in milliseconds since the epoch
    :param position: The position in the track, in seconds
    :param action_type: :class:`ActionType`
    """

    timestamp: int
    position: float
    action_type: ActionType

    def to_json(self) -> JsonObj:
        return {
            "timestamp": self.timestamp,
            "assetPosition": self.position,
            "actionType": str(self.action_type),
        }


@dataclass
class PlaybackSession:
    """One play of a track, from the moment it started to the moment it stopped.

    TIDAL counts a play after 30 seconds of listening, so shorter plays don't need to be
    reported.

    :param track_id: The id of the played track
    :param start_timestamp: When the play started, in milliseconds since the epoch
    :param end_timestamp: When the play ended, in milliseconds since the epoch
    :param end_position: The position in the track when the play ended, in seconds
    :param start_position: The position in the track when the play started, in seconds
    :param source_type: What the track was played from, see :class:`SourceType`
    :param source_id: The id of the album, playlist, mix or artist the track was played
        from. Defaults to the track id, for a track played on its own
    :param actions: Pauses, resumes and seeks during the play, see
        :class:`PlaybackAction`
    :param quality: The audio quality that was played, see :class:`.media.Quality`
    :param audio_mode: The audio mode that was played, see :class:`.media.AudioMode`
    :param playback_session_id: A unique id for this play. Generated if not given
    """

    track_id: Union[int, str]
    start_timestamp: int
    end_timestamp: int
    end_position: float
    start_position: float = 0.0
    source_type: SourceType = SourceType.item
    source_id: Optional[Union[int, str]] = None
    actions: List[PlaybackAction] = field(default_factory=list)
    quality: str = media.Quality.high_lossless
    audio_mode: str = media.AudioMode.stereo
    playback_session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self) -> JsonObj:
        """The event payload, as TIDAL's players send it."""
        source_id = self.source_id if self.source_id is not None else self.track_id
        return {
            "playbackSessionId": self.playback_session_id,
            "startTimestamp": self.start_timestamp,
            "startAssetPosition": self.start_position,
            "isPostPaywall": True,
            "productType": "TRACK",
            "requestedProductId": str(self.track_id),
            "actualProductId": str(self.track_id),
            "actualAssetPresentation": "FULL",
            "actualAudioMode": str(self.audio_mode),
            "actualQuality": str(self.quality),
            "sourceType": str(self.source_type),
            "sourceId": str(source_id),
            "actions": [action.to_json() for action in self.actions],
            "endTimestamp": self.end_timestamp,
            "endAssetPosition": self.end_position,
        }


def get_token_claims(access_token: str) -> JsonObj:
    """The claims of an access token, without verifying it.

    :param access_token: A TIDAL access token (a JWT)
    :return: The claims, or an empty dict if the token can't be decoded
    """
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


class PlayLog:
    """Reports plays to TIDAL, see :meth:`.Session.report_playback`."""

    def __init__(self, session: Session):
        self.session = session

    def report(
        self, playback_sessions: Iterable[PlaybackSession], app_version: str
    ) -> bool:
        """Report plays to TIDAL.

        :param playback_sessions: The plays to report
        :param app_version: The version of the application that played them
        :return: True if TIDAL accepted the plays, False if it rejected them. Rejected
            plays would be rejected again, so they shouldn't be sent again.
        :raises: :class:`requests.RequestException` or a :class:`.TidalAPIError` if the
            plays couldn't be sent (e.g. offline, server errors). They can be sent again
            later.
        """
        playback_sessions = list(playback_sessions)
        accepted = True
        for start in range(0, len(playback_sessions), MAX_BATCH_SIZE):
            batch = playback_sessions[start : start + MAX_BATCH_SIZE]
            accepted = self._post(batch, app_version) and accepted
        return accepted

    def _post(self, playback_sessions: List[PlaybackSession], app_version: str) -> bool:
        requests_ = self.session.request
        if requests_._access_token_expired():
            try:
                requests_._refresh_access_token(self.session.access_token)
            except AuthenticationError as e:
                log.warning("Access token refresh failed: %s", e)

        sent_access_token = self.session.access_token
        response = self._send(playback_sessions, app_version)
        if response.status_code == 401 and requests_._refresh_access_token(
            sent_access_token
        ):
            response = self._send(playback_sessions, app_version)

        if response.status_code in (401, 403) or response.status_code >= 500:
            try:
                response.raise_for_status()
            except requests.HTTPError as e:
                if err := http_error_to_tidal_error(e):
                    raise err from e
                raise

        if not response.ok or "BatchResultErrorEntry" in response.text:
            log.warning("TIDAL rejected the reported plays: %s", response.text[:500])
            return False
        return True

    def _send(
        self, playback_sessions: List[PlaybackSession], app_version: str
    ) -> requests.Response:
        form = self.get_form(playback_sessions, app_version)
        return self.session.request._send(
            "POST", self.session.config.event_producer_location, {}, form, {}
        )

    def get_form(
        self, playback_sessions: List[PlaybackSession], app_version: str
    ) -> dict:
        """The request body for a batch of plays: an SQS ``SendMessageBatch`` form, with
        one ``playback_session`` event per play.

        :param playback_sessions: At most :data:`MAX_BATCH_SIZE` plays
        :param app_version: The version of the application that played them
        :return: The form fields
        """
        access_token = self.session.access_token or ""
        claims = get_token_claims(access_token)
        os_name = platform.system()
        client_id = (
            self.session.config.client_id_pkce
            if self.session.is_pkce
            else self.session.config.client_id
        )

        sent_timestamp = str(int(time.time() * 1000))

        form = {}
        for index, playback_session in enumerate(playback_sessions, 1):
            event_id = str(uuid.uuid4())
            body = {
                "group": "play_log",
                "version": 2,
                "ts": playback_session.end_timestamp,
                "uuid": event_id,
                "user": {
                    "id": claims.get("uid"),
                    "clientId": claims.get("cid"),
                    "sessionId": claims.get("sid"),
                },
                "client": {
                    "token": str(claims.get("cid", "")),
                    "deviceType": "desktop",
                    "version": app_version,
                    "platform": os_name.lower(),
                },
                "payload": playback_session.to_json(),
            }
            headers = {
                "app-version": app_version,
                "os-name": os_name,
                "os-version": platform.release(),
                "consent-category": "NECESSARY",
                "requested-sent-timestamp": sent_timestamp,
                "authorization": access_token,
                "client-id": client_id,
            }
            entry = f"SendMessageBatchRequestEntry.{index}."
            form[entry + "Id"] = event_id
            form[entry + "MessageBody"] = json.dumps(body)
            form[entry + "MessageAttribute.1.Name"] = "Name"
            form[entry + "MessageAttribute.1.Value.StringValue"] = "playback_session"
            form[entry + "MessageAttribute.1.Value.DataType"] = "String"
            form[entry + "MessageAttribute.2.Name"] = "Headers"
            form[entry + "MessageAttribute.2.Value.StringValue"] = json.dumps(headers)
            form[entry + "MessageAttribute.2.Value.DataType"] = "String"
        return form
