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

The library measures each play with a :class:`PlaybackTracker` and refuses implausible
plays, so reports describe real listening. This keeps honest applications from sending
bad data and makes faking plays less convenient, it can't stop someone who changes the
code.

The event layout and the handling of replies follow TIDAL's open source SDKs on GitHub:
tidal-music/tidal-sdk-android (modules ``eventproducer`` and ``player/events``) and
tidal-music/tidal-sdk-web (module ``event-producer``). The events describe the real
client (the operating system and the application version), they don't pretend to come
from an official TIDAL app.
"""

from __future__ import annotations

import base64
import json
import logging
import platform
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

import requests

from tidalapi import media
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.exceptions import (
    AuthenticationError,
    TidalAPIError,
    http_error_to_tidal_error,
)
from tidalapi.mix import Mix, MixV2
from tidalapi.playlist import Playlist
from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.session import Session

log = logging.getLogger(__name__)

#: The most events TIDAL's event producer accepts in one request
MAX_BATCH_SIZE = 10
#: TIDAL counts a play after this much listening, shorter plays aren't reported
MIN_LISTENED_SECONDS = 30
#: Plays older than this aren't reported anymore, in milliseconds
MAX_PLAY_AGE_MS = 14 * 24 * 3600 * 1000
#: Slack for clocks being adjusted during a play, in milliseconds
CLOCK_TOLERANCE_MS = 2000
#: Slack for track durations being rounded to whole seconds, and for the position
#: advancing ahead of the clock, in seconds
POSITION_TOLERANCE_SECONDS = 2.0


class SourceType(StrEnum):
    """What a track was played from.

    A track played on its own (from search, a list of tracks, the play queue) is an
    ``ITEM`` with the track's own id as source id.
    """

    album = "ALBUM"
    playlist = "PLAYLIST"
    mix = "MIX"
    artist = "ARTIST"
    item = "ITEM"


class ActionType(StrEnum):
    """A change during a play: playback stopped (paused) or started (resumed)."""

    playback_start = "PLAYBACK_START"
    playback_stop = "PLAYBACK_STOP"


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
    """One finished play of a track, as measured by a :class:`PlaybackTracker`.

    Keep it with :meth:`to_dict` and :meth:`from_dict` to report it later, for example
    after playing offline. It goes through the same checks when it's reported.
    """

    track_id: int | str
    track_duration: int | None
    start_timestamp: int
    end_timestamp: int
    start_position: float
    end_position: float
    source_type: SourceType = SourceType.item
    source_id: int | str | None = None
    actions: list[PlaybackAction] = field(default_factory=list)
    quality: str = media.Quality.high_lossless
    audio_mode: str = media.AudioMode.stereo
    playback_session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

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

    def to_dict(self) -> dict[str, Any]:
        """The play as JSON-compatible data, for :meth:`from_dict`."""
        data = asdict(self)
        data["source_type"] = str(self.source_type)
        data["quality"] = str(self.quality)
        data["audio_mode"] = str(self.audio_mode)
        for action in data["actions"]:
            action["action_type"] = str(action["action_type"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlaybackSession:
        """A play kept with :meth:`to_dict`."""
        data = dict(data)
        data["source_type"] = SourceType(data["source_type"])
        data["actions"] = [
            PlaybackAction(
                action["timestamp"],
                action["position"],
                ActionType(action["action_type"]),
            )
            for action in data["actions"]
        ]
        return cls(**data)

    def get_problem(self, now: int) -> str | None:
        """Why this play can't have happened, if so.

        :param now: The current time, in milliseconds since the epoch
        :return: A description of the problem, or None if the play is plausible
        """
        if self.end_timestamp < self.start_timestamp:
            return "it ends before it starts"
        if self.end_timestamp > now + CLOCK_TOLERANCE_MS:
            return "it ends in the future"
        if now - self.end_timestamp > MAX_PLAY_AGE_MS:
            return "it is too old"

        positions = [self.start_position, self.end_position]
        positions += [action.position for action in self.actions]
        if min(positions) < 0:
            return "a position is negative"
        if (
            self.track_duration
            and max(positions) > self.track_duration + POSITION_TOLERANCE_SECONDS
        ):
            return "a position is past the end of the track"

        return self._get_timeline_problem()

    def _get_timeline_problem(self) -> str | None:
        last_timestamp = self.start_timestamp
        playing_from = (self.start_timestamp, self.start_position)
        for action in self.actions:
            if action.timestamp < last_timestamp - CLOCK_TOLERANCE_MS:
                return "its pauses and seeks are out of order"
            if action.timestamp > self.end_timestamp + CLOCK_TOLERANCE_MS:
                return "a pause or seek comes after its end"
            last_timestamp = action.timestamp

            if action.action_type == ActionType.playback_start:
                playing_from = (action.timestamp, action.position)
            elif playing_from is not None:
                if _advances_too_fast(playing_from, action.timestamp, action.position):
                    return "more was listened to than time passed"
                playing_from = None

        if playing_from is not None and _advances_too_fast(
            playing_from, self.end_timestamp, self.end_position
        ):
            return "more was listened to than time passed"
        return None


def _advances_too_fast(
    playing_from: tuple[int, float], timestamp: int, position: float
) -> bool:
    start_timestamp, start_position = playing_from
    elapsed = (timestamp - start_timestamp) / 1000
    return position - start_position > elapsed + POSITION_TOLERANCE_SECONDS


class PlaybackTracker:
    """Measures one play of a track, see :meth:`.Session.start_playback`.

    Tell it when the player pauses (also while it's buffering), resumes or seeks, and
    stop it when the track stops playing.
    """

    def __init__(
        self,
        track: media.Track,
        source_type: SourceType,
        source_id: int | str,
        position: float,
        paused: bool,
        quality: str,
        audio_mode: str,
    ):
        self.track = track
        self.source_type = source_type
        self.source_id = source_id
        self.quality = quality
        self.audio_mode = audio_mode

        self.duration = track.duration if track.duration and track.duration > 0 else 0
        self.actions: list[PlaybackAction] = []
        self.start_timestamp: int | None = None
        self.start_position = 0.0
        self.listened_seconds = 0.0
        self.play: PlaybackSession | None = None
        self.stopped = False

        self._position = self._limit_position(position)
        self._resumed_at: float | None = None
        if not paused:
            self.resume()

    @property
    def position(self) -> float:
        """The position in the track, in seconds."""
        self._update()
        return self._position

    def pause(self) -> None:
        """The player paused, or stopped to buffer."""
        if self.stopped or self._resumed_at is None:
            return
        self._update()
        self._resumed_at = None
        self._add_action(ActionType.playback_stop, self._position)

    def resume(self) -> None:
        """The player started playing.

        A play starts when it first does.
        """
        if self.stopped or self._resumed_at is not None:
            return
        if self.start_timestamp is None:
            self.start_timestamp = _now()
            self.start_position = self._position
        else:
            self._add_action(ActionType.playback_start, self._position)
        self._resumed_at = time.monotonic()

    def seek(self, position: float) -> None:
        """The player moved to another position.

        :param position: The new position in the track, in seconds
        """
        if self.stopped:
            return
        self._update()
        position = self._limit_position(position)
        if self._resumed_at is not None:
            self._add_action(ActionType.playback_stop, self._position)
            self._add_action(ActionType.playback_start, position)
        self._position = position

    def stop(self) -> PlaybackSession | None:
        """The track stopped playing.

        :return: The finished play, to pass to :meth:`.Session.report_playback`, or None
            if too little was listened to for TIDAL to count it
        """
        if self.stopped:
            return self.play
        self._update()
        self._resumed_at = None
        self.stopped = True

        if self.start_timestamp is None or not self._counts():
            return None
        self.play = PlaybackSession(
            track_id=self.track.id,
            track_duration=self.duration or None,
            start_timestamp=self.start_timestamp,
            end_timestamp=_now(),
            start_position=self.start_position,
            end_position=self._position,
            source_type=self.source_type,
            source_id=self.source_id,
            actions=self.actions,
            quality=self.quality,
            audio_mode=self.audio_mode,
        )
        return self.play

    def _counts(self) -> bool:
        needed = float(MIN_LISTENED_SECONDS)
        if self.duration:
            needed = min(needed, self.duration - 1)
        return self.listened_seconds >= needed

    def _update(self) -> None:
        if self._resumed_at is None:
            return
        now = time.monotonic()
        elapsed = now - self._resumed_at
        self._resumed_at = now
        self.listened_seconds += elapsed
        self._position = self._limit_position(self._position + elapsed)

    def _limit_position(self, position: float) -> float:
        position = max(0.0, position)
        return min(position, self.duration) if self.duration else position

    def _add_action(self, action_type: ActionType, position: float) -> None:
        self.actions.append(PlaybackAction(_now(), position, action_type))


@dataclass
class PlaybackReport:
    """What happened to the plays given to :meth:`.Session.report_playback`.

    :param accepted: Plays TIDAL took. Don't report them again
    :param rejected: Plays that were refused for good, by the library or by TIDAL. They
        would be refused again
    :param unsent: Plays that couldn't be sent or weren't confirmed. Keep them and try
        again later
    :param error: What stopped the sending, if an exception did
    """

    accepted: list[PlaybackSession] = field(default_factory=list)
    rejected: list[PlaybackSession] = field(default_factory=list)
    unsent: list[PlaybackSession] = field(default_factory=list)
    error: Exception | None = None


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


def _now() -> int:
    return int(time.time() * 1000)


def _get_source(source: Any, track: media.Track) -> tuple[SourceType, int | str]:
    if isinstance(source, Album):
        return SourceType.album, source.id
    if isinstance(source, Playlist):
        return SourceType.playlist, source.id
    if isinstance(source, (Mix, MixV2)):
        return SourceType.mix, source.id
    if isinstance(source, Artist):
        return SourceType.artist, source.id
    return SourceType.item, track.id


class PlayLog:
    """Measures plays and reports them to TIDAL, see :meth:`.Session.start_playback` and
    :meth:`.Session.report_playback`."""

    def __init__(self, session: Session):
        self.session = session
        # The quality and audio mode of the streams fetched with this session, by track
        self._streams: dict[int | str, tuple[str, str]] = {}
        # When the plays this session reported happened, by id
        self._reported: dict[str, tuple[int, int]] = {}

    def note_stream(self, track_id: int | str, quality: str, audio_mode: str) -> None:
        """Remember that this session fetched a stream for a track."""
        self._streams[track_id] = (quality, audio_mode)

    def start(
        self,
        track: media.Track,
        source: Any,
        position: float,
        paused: bool,
        local_copy: bool,
    ) -> PlaybackTracker:
        """See :meth:`.Session.start_playback`."""
        stream = self._streams.get(track.id)
        if stream is None and not local_copy:
            raise ValueError(
                f"This session didn't fetch a stream for track {track.id}, and it's "
                "not playing from a local copy"
            )
        quality, audio_mode = stream or (
            media.Quality.high_lossless,
            media.AudioMode.stereo,
        )
        source_type, source_id = _get_source(source, track)
        return PlaybackTracker(
            track, source_type, source_id, position, paused, quality, audio_mode
        )

    def report(
        self, plays: Iterable[PlaybackSession], app_version: str
    ) -> PlaybackReport:
        """See :meth:`.Session.report_playback`."""
        report = PlaybackReport()
        now = _now()
        to_send: list[PlaybackSession] = []
        for play in plays:
            problem = self._get_problem(play, to_send, now)
            if problem:
                log.warning("Not reporting play of %s: %s", play.track_id, problem)
                report.rejected.append(play)
            else:
                to_send.append(play)

        for start in range(0, len(to_send), MAX_BATCH_SIZE):
            batch = to_send[start : start + MAX_BATCH_SIZE]
            # Like TIDAL's SDKs, stop at the first batch that doesn't go through
            if report.unsent:
                report.unsent += batch
                continue
            try:
                accepted, rejected, unsent = self._post(batch, app_version)
            except (requests.RequestException, TidalAPIError) as e:
                log.info("Couldn't report plays to TIDAL: %s", e)
                report.error = e
                report.unsent += batch
                continue
            for play in accepted:
                self._reported[play.playback_session_id] = (
                    play.start_timestamp,
                    play.end_timestamp,
                )
            report.accepted += accepted
            report.rejected += rejected
            report.unsent += unsent
        return report

    def _get_problem(
        self, play: PlaybackSession, earlier: list[PlaybackSession], now: int
    ) -> str | None:
        problem = play.get_problem(now)
        if problem:
            return problem
        earlier_ids = {other.playback_session_id for other in earlier}
        if (
            play.playback_session_id in self._reported
            or play.playback_session_id in earlier_ids
        ):
            return "it was reported already"

        times = list(self._reported.values())
        times += [(other.start_timestamp, other.end_timestamp) for other in earlier]
        for start, end in times:
            if (
                play.start_timestamp < end - CLOCK_TOLERANCE_MS
                and start < play.end_timestamp - CLOCK_TOLERANCE_MS
            ):
                return "it overlaps another play"
        return None

    def _post(
        self, plays: list[PlaybackSession], app_version: str
    ) -> tuple[list[PlaybackSession], list[PlaybackSession], list[PlaybackSession]]:
        """Send one batch.

        :return: The plays TIDAL accepted, rejected, and those to send again
        :raises: :class:`requests.RequestException` or a :class:`.TidalAPIError` if the
            batch couldn't be sent, which TIDAL's SDKs retry whatever the error
        """
        requests_ = self.session.request
        if requests_._access_token_expired():
            try:
                requests_._refresh_access_token(self.session.access_token)
            except AuthenticationError as e:
                log.warning("Access token refresh failed: %s", e)

        sent_access_token = self.session.access_token
        response = self._send(plays, app_version)
        if response.status_code == 401 and requests_._refresh_access_token(
            sent_access_token
        ):
            response = self._send(plays, app_version)

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            if err := http_error_to_tidal_error(e):
                raise err from e
            raise
        return self._read_reply(plays, response.text)

    def _read_reply(
        self, plays: list[PlaybackSession], reply: str
    ) -> tuple[list[PlaybackSession], list[PlaybackSession], list[PlaybackSession]]:
        """Sort a batch by the reply.

        As in TIDAL's SDKs a play is only done when the reply lists it, as sent or as
        malformed (``SenderFault``).

        Anything else answering with a success, like a Wi-Fi login page, confirms
        nothing.
        """
        accepted_ids: set[str | None] = set()
        rejected_ids: set[str | None] = set()
        try:
            root = ElementTree.fromstring(reply)
        except ElementTree.ParseError:
            log.info("Couldn't read TIDAL's reply: %s", reply[:500])
        else:
            for entry in root.iterfind(".//{*}SendMessageBatchResultEntry"):
                accepted_ids.add(entry.findtext("{*}Id"))
            for entry in root.iterfind(".//{*}BatchResultErrorEntry"):
                if entry.findtext("{*}SenderFault") == "true":
                    log.warning("TIDAL rejected a reported play: %s", reply[:500])
                    rejected_ids.add(entry.findtext("{*}Id"))

        accepted = [play for play in plays if play.event_id in accepted_ids]
        rejected = [play for play in plays if play.event_id in rejected_ids]
        done = accepted_ids | rejected_ids
        return accepted, rejected, [p for p in plays if p.event_id not in done]

    def _send(
        self, plays: list[PlaybackSession], app_version: str
    ) -> requests.Response:
        form = self.get_form(plays, app_version)
        return self.session.request._send(
            "POST", self.session.config.event_producer_location, {}, form, {}
        )

    def get_form(
        self, plays: list[PlaybackSession], app_version: str
    ) -> dict[str, str]:
        """The request body for a batch of plays: an SQS ``SendMessageBatch`` form, with
        one ``playback_session`` event per play.

        :param plays: At most :data:`MAX_BATCH_SIZE` plays
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

        sent_timestamp = str(_now())

        form = {}
        for index, play in enumerate(plays, 1):
            body = {
                "group": "play_log",
                "version": 2,
                "ts": play.end_timestamp,
                "uuid": play.event_id,
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
                "payload": play.to_json(),
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
            form[entry + "Id"] = play.event_id
            form[entry + "MessageBody"] = json.dumps(body)
            form[entry + "MessageAttribute.1.Name"] = "Name"
            form[entry + "MessageAttribute.1.Value.StringValue"] = "playback_session"
            form[entry + "MessageAttribute.1.Value.DataType"] = "String"
            form[entry + "MessageAttribute.2.Name"] = "Headers"
            form[entry + "MessageAttribute.2.Value.StringValue"] = json.dumps(headers)
            form[entry + "MessageAttribute.2.Value.DataType"] = "String"
        return form
