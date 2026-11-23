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
"""Offline tests for parsing V2 page categories."""

import pytest

import tidalapi
from tidalapi.page import HorizontalList, HorizontalListWithContext


@pytest.fixture
def session():
    return tidalapi.Session(tidalapi.Config())


def album_json(album_id, title):
    return {
        "id": album_id,
        "title": title,
        "cover": None,
        "videoCover": None,
        "artists": [{"id": 1, "name": "Artist", "type": "MAIN", "picture": None}],
    }


def context_list_json(header):
    json_obj = {
        "type": "HORIZONTAL_LIST_WITH_CONTEXT",
        "moduleId": "BECAUSE_YOU_LISTENED_TO_ALBUM",
        "title": "Because you listened to",
        "items": [
            {"type": "ALBUM", "data": album_json(2, "Recommended 1")},
            {"type": "ALBUM", "data": album_json(3, "Recommended 2")},
        ],
    }
    if header is not None:
        json_obj["header"] = header
    return json_obj


def test_list_with_context_keeps_header(session):
    header = {"type": "ALBUM", "data": album_json(1, "Listened To")}
    page = session.page.parse({"items": [context_list_json(header)]})

    category = page.categories[0]
    assert isinstance(category, HorizontalListWithContext)
    assert isinstance(category.header, tidalapi.Album)
    assert category.header.id == 1
    assert category.header.name == "Listened To"
    assert [item.name for item in category.items] == ["Recommended 1", "Recommended 2"]


def test_list_with_context_without_header(session):
    page = session.page.parse({"items": [context_list_json(None)]})

    category = page.categories[0]
    assert category.header is None
    assert len(category.items) == 2


def test_list_with_context_unknown_header_type(session):
    header = {"type": "SOMETHING_NEW", "data": {"id": 1}}
    page = session.page.parse({"items": [context_list_json(header)]})

    category = page.categories[0]
    assert category.header is None
    assert len(category.items) == 2


def test_plain_horizontal_list_has_no_header(session):
    json_obj = context_list_json(None)
    json_obj["type"] = "HORIZONTAL_LIST"
    page = session.page.parse({"items": [json_obj]})

    assert type(page.categories[0]) is HorizontalList
    assert not hasattr(page.categories[0], "header")
