# Copyright (C) 2023- The Tidalapi Developers
# Copyright (C) 2019-2022 morguldir
# Copyright (C) 2014 Thomas Amland
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

import logging
from abc import ABC
from contextlib import suppress
from json import dumps, loads
from os import getenv
from pathlib import Path

import keyring
import keyring.backends
import keyring.errors
import pytest

import tidalapi


@pytest.fixture(scope="session")
def session(request):
    logging.basicConfig(level=logging.DEBUG)
    return login(request)


class Credentials(ABC):
    def load(self, key: str) -> dict | None:
        """Load secret."""

    def save(self, key: str, val: dict) -> None:
        """Save secret."""


class EnvCredentials(Credentials):
    def load(self, key: str) -> dict | None:
        credentials = {
            "token_type": getenv("TIDAL_TOKEN_TYPE", "Bearer"),
            "access_token": getenv("TIDAL_ACCESS_TOKEN"),
            "refresh_token": getenv("TIDAL_REFRESH_TOKEN"),
        }
        return (
            credentials
            if credentials["access_token"] and credentials["refresh_token"]
            else None
        )

    def save(self, key: str, val: dict) -> None:
        print("Credentials are:")
        print(val)


class KeyringCredentials(Credentials):
    def load(self, key: str) -> dict | None:
        with suppress(Exception):
            credentials = keyring.get_password(key, key)
            return loads(credentials)
        return None

    def save(self, key: str, val: dict) -> None:
        keyring.set_password(key, key, dumps(val))


class CachedCredentials(Credentials):
    def __init__(self):
        base_dir = Path("~/.local/cache").expanduser()
        if not base_dir.exists():
            raise FileNotFoundError(f"No cache directory {base_dir}")
        self.cache_dir = base_dir / "python-tidal"
        self.cache_dir.mkdir(exist_ok=True)

    def load(self, key: str) -> dict | None:
        cachef = self.cache_dir / f"{key}.json"
        try:
            return loads(cachef.read_text())
        except Exception:
            return None

    def save(self, key: str, val: dict) -> None:
        cachef = self.cache_dir / f"{key}.json"
        cachef.write_text(dumps(val))


KEY = "python-tidal"


def get_credential_store(
    datastore_key: str = KEY,
) -> tuple[list[Credentials], dict | None]:
    stores = []
    for store in (EnvCredentials, CachedCredentials, KeyringCredentials):
        with suppress(Exception):
            stores.append(store())
    for store in stores:
        data = store.load(datastore_key)
        if data:
            return [store], data
    stores = [s for s in stores if not isinstance(s, EnvCredentials)]
    return stores, None


def login(request, use_pkce_auth: bool = False):
    # Select datastore depending on the required authentication method
    if use_pkce_auth:
        datastore_key = f"{KEY}-pkce"
    else:
        datastore_key = KEY
    stores, credentials = get_credential_store(datastore_key)
    config = tidalapi.Config()

    tidal_session = tidalapi.Session(config)
    if credentials and tidal_session.load_oauth_session(**credentials):
        # override pkce state to allow returning non DASH streams
        return tidal_session
    else:
        # Generate a new login using the required authentication method
        if use_pkce_auth:
            _pkce_login(request, tidal_session)
        else:
            _oauth_login(request, tidal_session)
    if stores:
        # Update credentials datastore
        for store in stores:
            with suppress(Exception):
                store.save(
                    datastore_key,
                    {
                        "token_type": tidal_session.token_type,
                        "access_token": tidal_session.access_token,
                        "refresh_token": tidal_session.refresh_token,
                        "is_pkce": tidal_session.is_pkce,
                    },
                )
                break
    return tidal_session


def _oauth_login(request, tidal_session):
    login, future = tidal_session.login_oauth()
    # https://github.com/pytest-dev/pytest/issues/2704
    # To be able to print to terminal, global capture must be disabled temporarily:
    capmanager = request.config.pluginmanager.getplugin("capturemanager")
    with capmanager.global_and_fixture_disabled():
        print(
            "Visit",
            "https://" + login.verification_uri_complete,
            "to log in, the link expires in",
            login.expires_in,
            "seconds",
        )
    future.result()


def _pkce_login(request, tidal_session):
    # To be able to print to terminal; read from stdin, global capture must be disabled temporarily:
    capmanager = request.config.pluginmanager.getplugin("capturemanager")
    capmanager.suspend_global_capture(in_=True)
    tidal_session.login_pkce()
    capmanager.resume_global_capture()


def pytest_collection_modifyitems(config, items):
    if config.getoption("--interactive"):
        return
    for item in items:
        if "interactive" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Skipping interactive tests"))


def pytest_addoption(parser):
    parser.addoption(
        "--interactive",
        action="store_true",
        default=False,
        help="Run tests that require user input",
    )
