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

"""Offline tests for the OAuth token refresh logic (no TIDAL account needed)."""

import threading
import time
from unittest import mock

import tidalapi


def fake_response(status_code=200, json_data=None):
    response = mock.Mock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.json.return_value = json_data if json_data is not None else {}
    return response


def make_session(refresh_token="old-refresh"):
    session = tidalapi.Session(tidalapi.Config())
    session.token_type = "Bearer"
    session.access_token = "old-access"
    session.refresh_token = refresh_token
    return session


def test_token_refresh_keeps_rotated_refresh_token():
    session = make_session()
    session.request_session = mock.Mock()
    session.request_session.post.return_value = fake_response(
        json_data={
            "access_token": "new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
            "refresh_token": "rotated-refresh",
        }
    )

    assert session.token_refresh("old-refresh")

    assert session.access_token == "new-access"
    assert session.refresh_token == "rotated-refresh"


def test_token_refresh_keeps_refresh_token_when_not_rotated():
    session = make_session()
    session.request_session = mock.Mock()
    session.request_session.post.return_value = fake_response(
        json_data={
            "access_token": "new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )

    assert session.token_refresh("old-refresh")

    assert session.access_token == "new-access"
    assert session.refresh_token == "old-refresh"


def test_concurrent_expired_requests_refresh_only_once():
    session = make_session()
    session.session_id = "sid"
    session.country_code = "US"
    post_calls = []
    post_started = threading.Event()

    def post(url, params):
        post_calls.append(params["refresh_token"])
        post_started.set()
        # Hold the refresh open so the other threads pile up behind it.
        time.sleep(0.2)
        return fake_response(
            json_data={
                "access_token": "new-access",
                "expires_in": 3600,
                "token_type": "Bearer",
                "refresh_token": "rotated-refresh",
            }
        )

    def request(method, url, params=None, data=None, headers=None):
        if headers["authorization"] == "Bearer old-access":
            return fake_response(
                401, {"userMessage": "The token has expired. (Expired on time)"}
            )
        return fake_response(200, {"ok": True})

    session.request_session = mock.Mock()
    session.request_session.post.side_effect = post
    session.request_session.request.side_effect = request

    results = []

    def worker():
        results.append(session.request.basic_request("GET", "tracks/1").ok)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == [True] * 5
    assert post_calls == ["old-refresh"]
    assert session.refresh_token == "rotated-refresh"
