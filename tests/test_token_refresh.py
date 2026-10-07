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
