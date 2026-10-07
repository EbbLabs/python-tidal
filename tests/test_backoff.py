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

"""Offline tests for abuse detection and request backoff (no TIDAL account needed)."""

import datetime
from unittest import mock

import pytest
import requests

import tidalapi
from tidalapi.exceptions import (
    AbuseDetected,
    TidalBackoffError,
    TooManyRequests,
    http_error_to_tidal_error,
)

ABUSE_BODY = '{"status": 403, "userMessage": "abuse_detected"}'


def fake_response(status_code=200, text="{}", headers=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode()
    response.headers.update(headers or {})
    response.request = requests.Request("GET", "https://api.tidal.com/v1/x").prepare()
    return response


def make_session(responses, backoff=True):
    session = tidalapi.Session(tidalapi.Config(backoff=backoff))
    session.request_session = mock.Mock()
    session.request_session.request.side_effect = list(responses)
    return session


def http_error(response):
    return requests.HTTPError(response=response)


def test_abuse_response_maps_to_abuse_detected():
    error = http_error_to_tidal_error(
        http_error(fake_response(403, ABUSE_BODY, {"Retry-After": "120"}))
    )

    assert isinstance(error, AbuseDetected)
    assert error.retry_after == 120
    assert "abuse_detected" in error.reason


def test_suspended_account_maps_to_abuse_detected():
    response = fake_response(403, '{"userMessage": "Account suspended"}')

    assert isinstance(http_error_to_tidal_error(http_error(response)), AbuseDetected)


def test_plain_forbidden_is_not_abuse():
    response = fake_response(403, '{"userMessage": "Not allowed"}')

    assert http_error_to_tidal_error(http_error(response)) is None


def test_non_json_error_body_does_not_break_error_mapping():
    response = fake_response(403, "<html>abuse detected</html>")

    assert isinstance(http_error_to_tidal_error(http_error(response)), AbuseDetected)


def test_retry_after_as_http_date_is_ignored():
    response = fake_response(
        429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    )

    error = http_error_to_tidal_error(http_error(response))

    assert isinstance(error, TooManyRequests)
    assert error.retry_after == -1


def test_request_raises_abuse_detected():
    session = make_session([fake_response(403, ABUSE_BODY)], backoff=False)

    with pytest.raises(AbuseDetected):
        session.request.request("GET", "tracks/1")


def test_abuse_response_starts_backoff():
    session = make_session([fake_response(403, ABUSE_BODY)])

    with pytest.raises(AbuseDetected):
        session.request.request("GET", "tracks/1")

    assert session.request.backoff_remaining() > 29 * 60
    with pytest.raises(TidalBackoffError) as exc_info:
        session.request.request("GET", "tracks/2")
    assert "abuse detected" in exc_info.value.reason
    assert exc_info.value.seconds_remaining > 29 * 60
    # The second request never reached TIDAL
    assert session.request_session.request.call_count == 1


def test_rate_limit_backoff_uses_retry_after():
    session = make_session([fake_response(429, headers={"Retry-After": "7"})])

    with pytest.raises(TooManyRequests):
        session.request.request("GET", "tracks/1")

    assert 5 < session.request.backoff_remaining() <= 7


def test_rate_limit_backoff_defaults_to_a_minute():
    session = make_session([fake_response(429)])

    with pytest.raises(TooManyRequests):
        session.request.request("GET", "tracks/1")

    assert 55 < session.request.backoff_remaining() <= 60


def test_backoff_is_off_by_default():
    session = make_session([fake_response(429), fake_response(200)], backoff=False)

    with pytest.raises(TooManyRequests):
        session.request.request("GET", "tracks/1")

    assert session.request.backoff_remaining() == 0
    assert session.request.request("GET", "tracks/2").ok


def test_backoff_is_never_shortened():
    session = make_session([])
    requests_ = session.request

    requests_._start_backoff_if_needed(
        fake_response(429, headers={"Retry-After": "600"})
    )
    requests_._start_backoff_if_needed(fake_response(429, headers={"Retry-After": "5"}))

    assert requests_.backoff_remaining() > 500


def test_backoff_ends():
    session = make_session([fake_response(429), fake_response(200)])
    with pytest.raises(TooManyRequests):
        session.request.request("GET", "tracks/1")

    session.request._backoff_until -= 61

    assert session.request.backoff_remaining() == 0
    assert session.request.request("GET", "tracks/2").ok


def test_token_refresh_is_not_attempted_during_backoff():
    session = make_session([fake_response(429)])
    session.refresh_token = "refresh"
    session.access_token = "access"
    session.token_type = "Bearer"
    with pytest.raises(TooManyRequests):
        session.request.request("GET", "tracks/1")
    session.expiry_time = datetime.datetime(2000, 1, 1)

    with pytest.raises(TidalBackoffError):
        session.request.request("GET", "tracks/2")

    session.request_session.post.assert_not_called()
