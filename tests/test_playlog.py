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
"""Offline tests for reporting plays (no TIDAL account needed, nothing is sent)."""

import base64
import dataclasses
import json
import platform
from unittest import mock

import pytest
import requests

import tidalapi
from tidalapi.exceptions import TidalBackoffError
from tidalapi.media import Stream
from tidalapi.playlog import (
    MAX_PLAY_AGE_MS,
    ActionType,
    PlaybackAction,
    PlaybackSession,
    SourceType,
    get_token_claims,
)

NOW = 1_800_000_000_000


def make_token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def fake_response(status_code=200, text=""):
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode()
    response.request = requests.Request(
        "POST", "https://ec.tidal.com/api/event-batch"
    ).prepare()
    return response


def reply_xml(sent=(), failed=(), sender_fault=True):
    """A reply as TIDAL sends it, with the namespace."""
    entries = [
        f"<SendMessageBatchResultEntry><Id>{event_id}</Id>"
        "<MessageId>m</MessageId></SendMessageBatchResultEntry>"
        for event_id in sent
    ]
    entries += [
        f"<BatchResultErrorEntry><Id>{event_id}</Id>"
        f"<SenderFault>{str(sender_fault).lower()}</SenderFault>"
        "</BatchResultErrorEntry>"
        for event_id in failed
    ]
    return (
        '<?xml version="1.0"?><SendMessageBatchResponse '
        'xmlns="http://queue.amazonaws.com/doc/2012-11-05/">'
        f"<SendMessageBatchResult>{''.join(entries)}</SendMessageBatchResult>"
        "</SendMessageBatchResponse>"
    )


def event_ids(form):
    return [v for k, v in form.items() if k.endswith(".Id")]


def accept_everything(method, url, data, **kwargs):
    return fake_response(text=reply_xml(event_ids(data)))


def make_session():
    session = tidalapi.Session(tidalapi.Config())
    session.token_type = "Bearer"
    session.access_token = make_token({"uid": 123, "cid": 8017, "sid": "s-1"})
    session.refresh_token = "refresh"
    session.is_pkce = True
    session.request_session = mock.Mock()
    session.request_session.request.side_effect = accept_everything
    return session


def make_track(session, track_id=1, duration=200, fetched=True):
    track = tidalapi.Track(session)
    track.id = track_id
    track.duration = duration
    if fetched:
        session.playlog.note_stream(track_id, "HI_RES_LOSSLESS", "DOLBY_ATMOS")
    return track


def make_play(start=NOW - 300_000, seconds=200, **kwargs):
    """A plausible play, `seconds` long, ending before NOW."""
    values = {
        "track_id": 1,
        "track_duration": 200,
        "start_timestamp": start,
        "end_timestamp": start + seconds * 1000,
        "start_position": 0.0,
        "end_position": float(seconds),
    }
    return PlaybackSession(**{**values, **kwargs})


def sent_forms(session):
    return [c.kwargs["data"] for c in session.request_session.request.call_args_list]


def entries(form):
    """The (body, headers, name) of each event in a SendMessageBatch form."""
    events = []
    index = 1
    while f"SendMessageBatchRequestEntry.{index}.Id" in form:
        entry = f"SendMessageBatchRequestEntry.{index}."
        events.append(
            (
                json.loads(form[entry + "MessageBody"]),
                json.loads(form[entry + "MessageAttribute.2.Value.StringValue"]),
                form[entry + "MessageAttribute.1.Value.StringValue"],
            )
        )
        index += 1
    return events


class FakeTime:
    """The clocks the library measures with: seconds of wall clock and monotonic."""

    def __init__(self):
        self.now = NOW / 1000

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    fake = FakeTime()
    with mock.patch("tidalapi.playlog.time", fake):
        yield fake


@pytest.fixture
def session(clock):
    return make_session()


# Measuring a play


def test_tracker_measures_a_play(session, clock):
    track = make_track(session)
    tracker = session.start_playback(track)
    clock.advance(120)
    play = tracker.stop()

    assert play.track_id == 1
    assert play.start_timestamp == NOW
    assert play.end_timestamp == NOW + 120_000
    assert play.start_position == 0.0
    assert play.end_position == 120.0
    assert play.actions == []
    assert play.quality == "HI_RES_LOSSLESS"
    assert play.audio_mode == "DOLBY_ATMOS"
    assert play.source_type == SourceType.item
    assert play.source_id == 1


def test_tracker_doesnt_count_pauses(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(40)
    tracker.pause()
    clock.advance(1000)
    assert tracker.position == 40.0
    tracker.resume()
    clock.advance(10)
    play = tracker.stop()

    assert play.end_position == 50.0
    assert tracker.listened_seconds == 50.0
    assert play.actions == [
        PlaybackAction(NOW + 40_000, 40.0, ActionType.playback_stop),
        PlaybackAction(NOW + 1_040_000, 40.0, ActionType.playback_start),
    ]


def test_tracker_records_seeks_as_the_players_do(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(40)
    tracker.seek(100.0)
    clock.advance(10)
    play = tracker.stop()

    assert play.end_position == 110.0
    assert play.actions == [
        PlaybackAction(NOW + 40_000, 40.0, ActionType.playback_stop),
        PlaybackAction(NOW + 40_000, 100.0, ActionType.playback_start),
    ]
    assert play.get_problem(int(clock.now * 1000)) is None


def test_seeking_back_counts_the_time_listened(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(20)
    tracker.seek(0.0)
    clock.advance(20)
    play = tracker.stop()

    assert play is not None
    assert play.end_position == 20.0
    assert play.get_problem(int(clock.now * 1000)) is None


def test_a_play_started_paused_begins_at_the_first_resume(session, clock):
    tracker = session.start_playback(make_track(session), position=30.0, paused=True)
    clock.advance(500)
    tracker.seek(50.0)
    tracker.resume()
    clock.advance(40)
    play = tracker.stop()

    assert play.start_timestamp == NOW + 500_000
    assert play.start_position == 50.0
    assert play.end_position == 90.0
    assert play.actions == []


def test_stopping_twice_gives_the_same_play(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(40)
    play = tracker.stop()
    clock.advance(40)
    assert tracker.stop() is play
    assert play.end_position == 40.0


def test_short_plays_dont_count(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(29)
    assert tracker.stop() is None

    tracker = session.start_playback(make_track(session), paused=True)
    clock.advance(100)
    assert tracker.stop() is None


def test_a_track_shorter_than_30_seconds_counts_when_played_through(session, clock):
    tracker = session.start_playback(make_track(session, duration=20))
    clock.advance(19.5)
    assert tracker.stop() is not None


def test_the_position_stops_at_the_end_of_the_track(session, clock):
    tracker = session.start_playback(make_track(session, duration=200))
    clock.advance(203)
    assert tracker.stop().end_position == 200.0


def test_only_tracks_with_a_fetched_stream_can_be_tracked(session):
    track = make_track(session, fetched=False)
    with pytest.raises(ValueError):
        session.start_playback(track)
    assert session.start_playback(track, local_copy=True) is not None


def test_get_stream_makes_a_track_playable(session, clock):
    track = make_track(session, fetched=False)
    stream = Stream()
    stream.audio_quality = "LOSSLESS"
    stream.audio_mode = "STEREO"
    with (
        mock.patch.object(track.requests, "request"),
        mock.patch.object(track.requests, "map_json", return_value=stream),
    ):
        track.get_stream()

    tracker = session.start_playback(track)
    clock.advance(40)
    assert tracker.stop().quality == "LOSSLESS"


@pytest.mark.parametrize(
    "source_class, source_type",
    [
        (tidalapi.Album, SourceType.album),
        (tidalapi.Playlist, SourceType.playlist),
        (tidalapi.Mix, SourceType.mix),
        (tidalapi.MixV2, SourceType.mix),
        (tidalapi.Artist, SourceType.artist),
    ],
)
def test_source(session, clock, source_class, source_type):
    source = source_class.__new__(source_class)
    source.id = "source-id"
    tracker = session.start_playback(make_track(session), source=source)
    clock.advance(40)
    play = tracker.stop()
    assert play.source_type == source_type
    assert play.source_id == "source-id"


# The events


def test_payload():
    play = make_play(
        source_type=SourceType.album,
        source_id=55,
        actions=[
            PlaybackAction(50_000, 49.5, ActionType.playback_stop),
            PlaybackAction(60_000, 49.5, ActionType.playback_start),
        ],
        quality=tidalapi.Quality.hi_res_lossless,
    )
    payload = play.to_json()

    assert payload["requestedProductId"] == "1"
    assert payload["actualProductId"] == "1"
    assert payload["productType"] == "TRACK"
    assert payload["sourceType"] == "ALBUM"
    assert payload["sourceId"] == "55"
    assert payload["actualQuality"] == "HI_RES_LOSSLESS"
    assert payload["actualAudioMode"] == "STEREO"
    assert payload["startTimestamp"] == play.start_timestamp
    assert payload["endTimestamp"] == play.end_timestamp
    assert payload["startAssetPosition"] == 0.0
    assert payload["endAssetPosition"] == 200.0
    assert payload["actions"] == [
        {"timestamp": 50_000, "assetPosition": 49.5, "actionType": "PLAYBACK_STOP"},
        {"timestamp": 60_000, "assetPosition": 49.5, "actionType": "PLAYBACK_START"},
    ]
    assert payload["playbackSessionId"]


def test_track_played_on_its_own_uses_its_own_id_as_source():
    payload = make_play(track_id=7).to_json()
    assert payload["sourceType"] == "ITEM"
    assert payload["sourceId"] == "7"


def test_token_claims():
    assert get_token_claims(make_token({"uid": 1, "cid": 2})) == {"uid": 1, "cid": 2}
    assert get_token_claims("not a token") == {}
    assert get_token_claims("a.%%%.b") == {}


def test_report_sends_one_playback_session_event_per_play(session):
    plays = [make_play(track_id=1), make_play(track_id=2, start=NOW - 700_000)]

    report = session.report_playback(plays, app_version="App 1.0")
    assert report.accepted == plays

    call = session.request_session.request.call_args
    assert call.args == ("POST", "https://ec.tidal.com/api/event-batch")
    assert call.kwargs["headers"]["authorization"] == "Bearer " + session.access_token

    events = entries(call.kwargs["data"])
    assert [body["payload"]["requestedProductId"] for body, _, _ in events] == [
        "1",
        "2",
    ]
    body, headers, name = events[0]
    assert name == "playback_session"
    assert body["group"] == "play_log"
    assert body["version"] == 2
    assert body["uuid"] == plays[0].event_id
    assert body["user"] == {"id": 123, "clientId": 8017, "sessionId": "s-1"}
    assert body["client"] == {
        "token": "8017",
        "deviceType": "desktop",
        "version": "App 1.0",
        "platform": platform.system().lower(),
    }
    assert headers["app-version"] == "App 1.0"
    assert headers["os-name"] == platform.system()
    assert headers["client-id"] == session.config.client_id_pkce
    assert headers["authorization"] == session.access_token
    assert headers["consent-category"] == "NECESSARY"


def test_events_describe_the_real_client(session):
    session.report_playback([make_play()])

    body, headers, _ = entries(sent_forms(session)[0])[0]
    assert "device-model" not in headers
    assert "device-vendor" not in headers
    assert body["client"]["platform"] != "android"
    assert headers["app-version"] == f"tidalapi {tidalapi.__version__}"


# TIDAL's replies


def spaced_plays(count):
    return [
        make_play(track_id=i, start=NOW - 1000 * 300 * (i + 1), seconds=200)
        for i in range(count)
    ]


def test_at_most_ten_events_per_request(session):
    report = session.report_playback(spaced_plays(23))
    assert [len(entries(form)) for form in sent_forms(session)] == [10, 10, 3]
    assert len(report.accepted) == 23


@pytest.mark.parametrize("status", [400, 403, 404, 408, 429, 500, 503])
def test_http_errors_keep_the_plays_for_later(session, status):
    session.request_session.request.side_effect = [fake_response(status, "no")]
    play = make_play()

    report = session.report_playback([play])

    assert report.unsent == [play]
    assert report.accepted == []
    assert report.rejected == []
    assert report.error is not None


def test_being_offline_keeps_the_plays_for_later(session):
    error = requests.ConnectionError("offline")
    session.request_session.request.side_effect = error
    play = make_play()

    report = session.report_playback([play])

    assert report.unsent == [play]
    assert report.error is error


def test_a_rate_limit_holds_back_the_next_report(session):
    session.request_session.request.side_effect = [fake_response(429, "slow down")]
    play = make_play()
    assert session.report_playback([play]).unsent == [play]

    report = session.report_playback([play])

    assert report.unsent == [play]
    assert isinstance(report.error, TidalBackoffError)
    assert session.request_session.request.call_count == 1


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "Log in to the Wi-Fi",
        "<html><body>Log in to the Wi-Fi</body></html>",
        reply_xml(["some-other-event"]),
        reply_xml(),
    ],
)
def test_a_success_that_doesnt_confirm_the_plays_keeps_them(session, reply):
    session.request_session.request.side_effect = [fake_response(text=reply)]
    play = make_play()

    report = session.report_playback([play])

    assert report.unsent == [play]
    assert report.accepted == []


def test_each_play_in_a_reply_gets_its_own_result(session):
    sent, sender_fault, server_fault = spaced_plays(3)
    reply = reply_xml([sent.event_id], [sender_fault.event_id]).replace(
        "</SendMessageBatchResult>",
        f"<BatchResultErrorEntry><Id>{server_fault.event_id}</Id>"
        "<SenderFault>false</SenderFault></BatchResultErrorEntry>"
        "</SendMessageBatchResult>",
    )
    session.request_session.request.side_effect = [fake_response(text=reply)]

    report = session.report_playback([sent, sender_fault, server_fault])

    assert report.accepted == [sent]
    assert report.rejected == [sender_fault]
    assert report.unsent == [server_fault]


def test_a_failed_batch_doesnt_hide_the_accepted_ones(session):
    plays = spaced_plays(25)
    first = fake_response(text=reply_xml([play.event_id for play in plays[:10]]))
    session.request_session.request.side_effect = [first, fake_response(503, "no")]

    report = session.report_playback(plays)

    assert report.accepted == plays[:10]
    assert report.unsent == plays[10:]
    assert session.request_session.request.call_count == 2


def test_retrying_sends_the_same_ids(session):
    session.request_session.request.side_effect = [fake_response(503, "no")]
    play = make_play()
    session.report_playback([play])
    session.request_session.request.side_effect = accept_everything

    assert session.report_playback([play]).accepted == [play]

    first, second = sent_forms(session)
    assert event_ids(first) == event_ids(second) == [play.event_id]


def test_expired_token_is_refreshed_and_the_request_retried_once(session):
    old_token = session.access_token
    new_token = make_token({"uid": 123, "cid": 8017, "sid": "s-2"})
    play = make_play()
    session.request_session.request.side_effect = [
        fake_response(401, '{"status": 401}'),
        fake_response(text=reply_xml([play.event_id])),
    ]

    def token_refresh(refresh_token):
        session.access_token = new_token
        return True

    with mock.patch.object(session, "token_refresh", side_effect=token_refresh):
        assert session.report_playback([play]).accepted == [play]

    calls = session.request_session.request.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["headers"]["authorization"] == "Bearer " + old_token
    assert calls[1].kwargs["headers"]["authorization"] == "Bearer " + new_token
    body, headers, _ = entries(calls[1].kwargs["data"])[0]
    assert headers["authorization"] == new_token
    assert body["user"]["sessionId"] == "s-2"


# Implausible plays


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param(
            {"start_timestamp": NOW - 1000, "end_timestamp": NOW - 200_000},
            id="ends before it starts",
        ),
        pytest.param(
            {"start_timestamp": NOW, "end_timestamp": NOW + 200_000},
            id="ends in the future",
        ),
        pytest.param(
            {
                "start_timestamp": NOW - MAX_PLAY_AGE_MS - 300_000,
                "end_timestamp": NOW - MAX_PLAY_AGE_MS - 100_000,
            },
            id="too old",
        ),
        pytest.param({"end_position": -1.0}, id="negative position"),
        pytest.param({"track_duration": 100}, id="position past the end of the track"),
        pytest.param(
            {"end_timestamp": NOW - 290_000}, id="more listening than time passed"
        ),
        pytest.param(
            {
                "actions": [
                    PlaybackAction(NOW - 290_000, 150.0, ActionType.playback_stop),
                    PlaybackAction(NOW - 289_000, 0.0, ActionType.playback_start),
                ]
            },
            id="listening before a pause faster than time",
        ),
        pytest.param(
            {
                "actions": [
                    PlaybackAction(NOW - 200_000, 50.0, ActionType.playback_stop),
                    PlaybackAction(NOW - 250_000, 50.0, ActionType.playback_start),
                ]
            },
            id="actions out of order",
        ),
        pytest.param(
            {"actions": [PlaybackAction(NOW, 50.0, ActionType.playback_stop)]},
            id="action after the end",
        ),
    ],
)
def test_implausible_plays_are_refused_without_sending(session, changes):
    play = make_play(**changes)

    report = session.report_playback([play])

    assert report.rejected == [play]
    session.request_session.request.assert_not_called()


def test_rounded_durations_are_allowed_for():
    assert make_play(track_duration=199).get_problem(NOW) is None


def test_a_clock_adjusted_during_a_play_is_allowed_for():
    play = make_play(seconds=199, end_position=200.5)
    assert play.get_problem(NOW) is None


def test_a_play_cant_be_reported_twice(session):
    play = make_play()
    assert session.report_playback([play]).accepted == [play]

    assert session.report_playback([play]).rejected == [play]
    assert session.request_session.request.call_count == 1


def test_a_play_cant_be_reported_twice_in_one_call(session):
    play = make_play()
    report = session.report_playback([play, play])
    assert report.accepted == [play]
    assert report.rejected == [play]


def test_plays_cant_overlap_a_reported_one(session):
    assert session.report_playback([make_play()]).accepted
    overlapping = make_play(start=NOW - 250_000, end_position=100.0, seconds=100)

    assert session.report_playback([overlapping]).rejected == [overlapping]


def test_plays_cant_overlap_in_one_call(session):
    first = make_play()
    overlapping = make_play(start=NOW - 250_000, end_position=100.0, seconds=100)

    report = session.report_playback([first, overlapping])

    assert report.accepted == [first]
    assert report.rejected == [overlapping]


def test_consecutive_plays_dont_overlap(session):
    first = make_play(start=NOW - 500_000)
    second = make_play(start=first.end_timestamp)
    assert session.report_playback([first, second]).accepted == [first, second]


def test_an_unsent_play_can_be_sent_again(session):
    session.request_session.request.side_effect = [fake_response(503, "no")]
    play = make_play()
    assert session.report_playback([play]).unsent == [play]
    session.request_session.request.side_effect = accept_everything
    assert session.report_playback([play]).accepted == [play]


# Keeping plays for later


def test_a_kept_play_can_be_reported_later(session, clock):
    tracker = session.start_playback(make_track(session))
    clock.advance(40)
    tracker.seek(100.0)
    clock.advance(10)
    tracker.pause()
    clock.advance(5)
    play = tracker.stop()

    kept = json.loads(json.dumps(play.to_dict()))
    restored = PlaybackSession.from_dict(kept)

    assert restored == play
    assert restored.to_json() == play.to_json()
    new_session = make_session()
    assert new_session.report_playback([restored]).accepted == [restored]


def test_a_kept_play_goes_through_the_same_checks(session, clock):
    kept = make_play().to_dict()
    kept["end_position"] = 5000.0
    restored = PlaybackSession.from_dict(kept)

    assert session.report_playback([restored]).rejected == [restored]


def test_to_dict_covers_every_field():
    play = make_play(actions=[PlaybackAction(1, 2.0, ActionType.playback_stop)])
    names = {f.name for f in dataclasses.fields(PlaybackSession)}
    assert set(play.to_dict()) == names
