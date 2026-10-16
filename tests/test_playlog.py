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
import json
import platform
from unittest import mock

import pytest
import requests

import tidalapi
from tidalapi.exceptions import TidalAPIError
from tidalapi.playlog import (
    ActionType,
    PlaybackAction,
    PlaybackSession,
    SourceType,
    get_token_claims,
)

ACCEPTED = (
    '<?xml version="1.0"?><SendMessageBatchResponse><SendMessageBatchResult>'
    "<SendMessageBatchResultEntry><Id>x</Id></SendMessageBatchResultEntry>"
    "</SendMessageBatchResult></SendMessageBatchResponse>"
)
REJECTED = (
    "<SendMessageBatchResponse><SendMessageBatchResult><BatchResultErrorEntry>"
    "<SenderFault>true</SenderFault></BatchResultErrorEntry></SendMessageBatchResult>"
    "</SendMessageBatchResponse>"
)


def make_token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def fake_response(status_code=200, text=ACCEPTED):
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode()
    response.request = requests.Request(
        "POST", "https://ec.tidal.com/api/event-batch"
    ).prepare()
    return response


def make_session():
    session = tidalapi.Session(tidalapi.Config())
    session.token_type = "Bearer"
    session.access_token = make_token({"uid": 123, "cid": 8017, "sid": "s-1"})
    session.refresh_token = "refresh"
    session.is_pkce = True
    session.request_session = mock.Mock()
    session.request_session.request.return_value = fake_response()
    return session


def make_play(track_id=1, **kwargs):
    return PlaybackSession(
        track_id=track_id,
        start_timestamp=1_000,
        end_timestamp=201_000,
        end_position=200.0,
        **kwargs,
    )


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
    assert payload["startTimestamp"] == 1_000
    assert payload["endTimestamp"] == 201_000
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


def test_report_sends_one_playback_session_event_per_play():
    session = make_session()

    assert session.report_playback([make_play(1), make_play(2)], app_version="App 1.0")

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


def test_events_describe_the_real_client():
    session = make_session()
    session.report_playback([make_play()])

    body, headers, _ = entries(sent_forms(session)[0])[0]
    assert "device-model" not in headers
    assert "device-vendor" not in headers
    assert body["client"]["platform"] != "android"
    assert headers["app-version"] == f"tidalapi {tidalapi.__version__}"


def test_report_sends_at_most_ten_events_per_request():
    session = make_session()

    assert session.report_playback([make_play(i) for i in range(23)])

    assert [len(entries(form)) for form in sent_forms(session)] == [10, 10, 3]


def test_rejected_plays_return_false():
    session = make_session()
    session.request_session.request.return_value = fake_response(text=REJECTED)
    assert not session.report_playback([make_play()])

    session.request_session.request.return_value = fake_response(400, "bad request")
    assert not session.report_playback([make_play()])


def test_server_errors_raise_so_plays_can_be_sent_later():
    session = make_session()
    session.request_session.request.return_value = fake_response(503, "unavailable")

    with pytest.raises((requests.HTTPError, TidalAPIError)):
        session.report_playback([make_play()])


def test_expired_token_is_refreshed_and_the_request_retried_once():
    session = make_session()
    old_token = session.access_token
    new_token = make_token({"uid": 123, "cid": 8017, "sid": "s-2"})
    session.request_session.request.side_effect = [
        fake_response(401, '{"status": 401}'),
        fake_response(),
    ]

    def token_refresh(refresh_token):
        session.access_token = new_token
        return True

    with mock.patch.object(session, "token_refresh", side_effect=token_refresh):
        assert session.report_playback([make_play()])

    calls = session.request_session.request.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["headers"]["authorization"] == "Bearer " + old_token
    assert calls[1].kwargs["headers"]["authorization"] == "Bearer " + new_token
    body, headers, _ = entries(calls[1].kwargs["data"])[0]
    assert headers["authorization"] == new_token
    assert body["user"]["sessionId"] == "s-2"
