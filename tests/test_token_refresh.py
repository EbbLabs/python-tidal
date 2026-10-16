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

import datetime
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


def _refreshing_session(expiry_time):
    session = make_session()
    session.expiry_time = expiry_time
    session.request_session = mock.Mock()
    session.request_session.post.return_value = fake_response(
        json_data={
            "access_token": "new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    session.request_session.request.return_value = fake_response(200, {})
    return session


def test_request_refreshes_expired_token_before_sending():
    session = _refreshing_session(
        datetime.datetime.utcnow() - datetime.timedelta(days=1)
    )

    assert session.request.basic_request("GET", "tracks/1").ok

    session.request_session.post.assert_called_once()
    sent = session.request_session.request.call_args.kwargs["headers"]
    assert sent["authorization"] == "Bearer new-access"


def test_request_refreshes_token_expiring_within_margin():
    session = _refreshing_session(
        datetime.datetime.utcnow() + datetime.timedelta(seconds=10)
    )

    session.request.basic_request("GET", "tracks/1")

    session.request_session.post.assert_called_once()


def test_request_does_not_refresh_valid_token():
    session = _refreshing_session(
        datetime.datetime.utcnow() + datetime.timedelta(days=1)
    )

    session.request.basic_request("GET", "tracks/1")

    session.request_session.post.assert_not_called()


def test_request_without_expiry_time_does_not_refresh_up_front():
    session = _refreshing_session(None)

    session.request.basic_request("GET", "tracks/1")

    session.request_session.post.assert_not_called()


def test_request_handles_timezone_aware_expiry_time():
    expired = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(1)
    session = _refreshing_session(expired)

    session.request.basic_request("GET", "tracks/1")

    session.request_session.post.assert_called_once()


def test_failed_proactive_refresh_does_not_fail_the_request():
    session = _refreshing_session(
        datetime.datetime.utcnow() + datetime.timedelta(seconds=10)
    )
    session.request_session.post.return_value = fake_response(
        400, {"error": "invalid_grant", "error_description": "dead"}
    )

    assert session.request.basic_request("GET", "tracks/1").ok


def _load_oauth_session(expiry_time):
    session = _refreshing_session(None)
    session.request_session.request.return_value = fake_response(
        200, {"sessionId": "sid", "countryCode": "US", "userId": 1}
    )
    with mock.patch.object(tidalapi.user.User, "factory"):
        assert session.load_oauth_session(
            "Bearer", "old-access", "old-refresh", expiry_time, is_pkce=True
        )
    return session


def test_load_oauth_session_accepts_expiry_time_string():
    expired = datetime.datetime.utcnow() - datetime.timedelta(days=1)

    session = _load_oauth_session(str(expired))

    # The expired token is refreshed up front, which sets a new expiry time
    session.request_session.post.assert_called_once()
    assert session.access_token == "new-access"
    assert session.expiry_time > datetime.datetime.utcnow()


def test_load_oauth_session_accepts_iso_format_expiry_time():
    expiry_time = datetime.datetime(2030, 1, 2, 3, 4, 5)

    session = _load_oauth_session(expiry_time.isoformat())

    assert session.expiry_time == expiry_time
    session.request_session.post.assert_not_called()


def test_load_oauth_session_ignores_invalid_expiry_time_string():
    session = _load_oauth_session("None")

    assert session.expiry_time is None
    session.request_session.post.assert_not_called()


def test_session_file_round_trips_expiry_time(tmp_path):
    session_file = tmp_path / "session.json"
    expiry_time = datetime.datetime(2030, 1, 2, 3, 4, 5)
    session = make_session()
    session.expiry_time = expiry_time
    session.check_login = mock.Mock(return_value=True)
    session.save_session_to_file(session_file)

    loaded = tidalapi.Session(tidalapi.Config())
    loaded.load_oauth_session = mock.Mock(return_value=True)
    assert loaded.load_session_from_file(session_file)

    assert loaded.load_oauth_session.call_args.kwargs["expiry_time"] == expiry_time


def test_session_file_without_expiry_time_still_loads(tmp_path):
    session_file = tmp_path / "session.json"
    session_file.write_text(
        '{"token_type": {"data": "Bearer"}, "access_token": {"data": "a"},'
        ' "refresh_token": {"data": "r"}, "is_pkce": {"data": false}}'
    )

    loaded = tidalapi.Session(tidalapi.Config())
    loaded.load_oauth_session = mock.Mock(return_value=True)
    assert loaded.load_session_from_file(session_file)

    assert loaded.load_oauth_session.call_args.kwargs["expiry_time"] is None


def test_device_login_ignores_hires_client_swap():
    config = tidalapi.Config()
    device_client_id = config.client_id
    device_client_secret = config.client_secret
    session = tidalapi.Session(config)
    session.request_session = mock.Mock()
    session.request_session.post.return_value = fake_response(
        json_data={
            "deviceCode": "dc",
            "userCode": "uc",
            "verificationUri": "link.tidal.com",
            "verificationUriComplete": "link.tidal.com/uc",
            "expiresIn": 300,
            "interval": 2,
        }
    )

    session.client_enable_hires()
    assert config.client_id == config.client_id_pkce

    link_login = session.get_link_login()
    sent = session.request_session.post.call_args.args[1]
    assert sent["client_id"] == device_client_id

    session.request_session.post.return_value = fake_response(json_data={"a": "b"})
    session._check_link_login(link_login, until_expiry=False)
    sent = session.request_session.post.call_args.args[1]
    assert sent["client_id"] == device_client_id
    assert sent["client_secret"] == device_client_secret


def test_enable_hires_twice_keeps_device_client():
    config = tidalapi.Config()
    device_client = (config.client_id, config.client_secret)
    session = tidalapi.Session(config)

    session.client_enable_hires()
    session.client_enable_hires()

    assert session._device_client_credentials() == device_client


def test_sessions_do_not_share_a_default_config():
    first = tidalapi.Session()
    second = tidalapi.Session()
    device_client_id = second.config.client_id

    first.client_enable_hires()

    assert first.config is not second.config
    assert second.config.client_id == device_client_id


def test_expired_token_is_retried_only_once():
    session = make_session()
    session.request_session = mock.Mock()
    session.request_session.post.return_value = fake_response(
        json_data={
            "access_token": "new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    # TIDAL keeps reporting an expired token even after a successful refresh.
    session.request_session.request.return_value = fake_response(
        401, {"userMessage": "The token has expired. (Expired on time)"}
    )

    response = session.request.basic_request("GET", "tracks/1")

    assert response.status_code == 401
    assert session.request_session.post.call_count == 1
    assert session.request_session.request.call_count == 2
    retry_headers = session.request_session.request.call_args.kwargs["headers"]
    assert retry_headers["authorization"] == "Bearer new-access"
