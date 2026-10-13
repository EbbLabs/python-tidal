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
"""Offline tests for parsing incomplete track and album metadata."""

import pytest

import tidalapi


@pytest.fixture
def session():
    return tidalapi.Session(tidalapi.Config())


def artist_json(artist_id=1, name="Artist"):
    return {"id": artist_id, "name": name, "type": "MAIN", "picture": None}


def track_json(**overrides):
    json_obj = {
        "id": 5,
        "title": "Track",
        "duration": 10,
        "explicit": False,
        "allowStreaming": False,
        "streamReady": False,
        "stemReady": False,
        "djReady": False,
        "adSupportedStreamReady": False,
        "trackNumber": 1,
        "volumeNumber": 1,
        "popularity": 0,
        "artists": [artist_json()],
        "album": None,
    }
    json_obj.update(overrides)
    return json_obj


def album_json(**overrides):
    json_obj = {
        "id": 1,
        "title": "Album",
        "cover": None,
        "videoCover": None,
        "artists": [artist_json()],
    }
    json_obj.update(overrides)
    return json_obj


def without(json_obj, key):
    return {k: v for k, v in json_obj.items() if k != key}


def test_track_artist_falls_back_to_first_artist(session):
    track = session.track().parse_track(track_json())

    assert track.artist.name == "Artist"
    assert [a.name for a in track.artists] == ["Artist"]


def test_track_prefers_explicit_artist(session):
    track = session.track().parse_track(
        track_json(artist=artist_json(2, "Main"), artists=[artist_json(1, "Other")])
    )

    assert track.artist.name == "Main"


@pytest.mark.parametrize(
    "overrides",
    [
        {"artists": []},
        {"artists": None},
        {"artists": [], "artist": None},
    ],
)
def test_track_without_any_artist_has_no_artist(session, overrides):
    track = session.track().parse_track(track_json(**overrides))

    assert track.artist is None
    assert track.artists == []


def test_track_without_artists_key_has_no_artist(session):
    track = session.track().parse_track(without(track_json(), "artists"))

    assert track.artist is None
    assert track.artists == []


def test_track_with_null_artist_falls_back_to_first_artist(session):
    track = session.track().parse_track(track_json(artist=None))

    assert track.artist.name == "Artist"


def test_unavailable_track_defaults_match_annotations(session):
    track = session.track().parse_track(track_json())

    assert track.available is False
    assert track.pay_to_stream is False
    assert track.premium_streaming_only is False
    assert track.editable is False
    assert track.upload is False
    assert track.spotlighted is False
    assert track.url == ""
    # Only set for available tracks, so this is the class default
    assert track.copyright == ""


def test_available_track_without_copyright_has_empty_copyright(session):
    track = session.track().parse_track(track_json(allowStreaming=True))

    assert track.copyright == ""


def test_track_flags_are_read_when_present(session):
    track = session.track().parse_track(
        track_json(payToStream=True, editable=True, url="https://tidal.com/t")
    )

    assert track.pay_to_stream is True
    assert track.editable is True
    assert track.url == "https://tidal.com/t"


def test_album_artist_falls_back_to_first_artist(session):
    album = session.album().parse(album_json())

    assert album.artist.name == "Artist"


@pytest.mark.parametrize("overrides", [{"artists": []}, {"artists": None}])
def test_album_without_any_artist_has_no_artist(session, overrides):
    album = session.album().parse(album_json(**overrides))

    assert album.artist is None
    assert album.artists == []


def test_album_without_artists_key_has_no_artist(session):
    album = session.album().parse(without(album_json(), "artists"))

    assert album.artist is None
    assert album.artists == []


def test_album_keeps_given_artist_when_json_has_no_artist_info(session):
    given = session.artist().parse_artist(artist_json(9, "Given"))

    album = session.album().parse(album_json(artists=[]), given)

    assert album.artist.name == "Given"


def test_album_keeps_given_artist_over_json_artist(session):
    given = session.artist().parse_artist(artist_json(9, "Given"))

    album = session.album().parse(album_json(artist=artist_json(2, "FromJson")), given)

    assert album.artist is given


def test_album_parses_json_artist_when_none_given(session):
    album = session.album().parse(album_json(artist=artist_json(2, "FromJson")))

    assert album.artist.name == "FromJson"


def test_album_json_without_artist_prefers_first_artist_over_given(session):
    # Existing behavior: the artist field is missing on some albums, and the first
    # artist of the album is used then.
    given = session.artist().parse_artist(artist_json(9, "Given"))

    album = session.album().parse(album_json(), given)

    assert album.artist.name == "Artist"


def test_track_with_album_parses_album_artist(session):
    track = session.track().parse_track(
        track_json(album=album_json(artists=[]), artists=[])
    )

    assert track.album.artist is None
    assert track.artist is None
