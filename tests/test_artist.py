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

import pytest
import requests

import tidalapi
from tidalapi.exceptions import ObjectNotFound

from .cover import verify_image_cover


def test_artist(session):
    artist = session.artist(16147)
    assert artist.id == 16147
    assert artist.name == "Lasgo"
    assert artist.listen_url == "https://listen.tidal.com/artist/16147"
    assert artist.share_url == "https://tidal.com/browse/artist/16147"
    assert all(
        role in artist.roles
        for role in [tidalapi.Role.artist, tidalapi.Role.contributor]
    )

    with pytest.raises(ValueError):
        requests.get(artist.image(2000))
    assert requests.get(artist.image(750)).status_code == 200
    assert requests.get(artist.image(480)).status_code == 200
    assert requests.get(artist.image(320)).status_code == 200
    assert requests.get(artist.image(160)).status_code == 200


def test_artist_not_found(session):
    with pytest.raises(ObjectNotFound):
        session.artist(123456789)


def test_get_albums(session):
    artist = session.artist(16147)
    albums = [
        session.album(17927863),
        session.album(36292296),
        session.album(17925106),
        session.album(17926279),
    ]

    find_ids(albums, artist.get_albums)


def test_get_ep_singles(session):
    artist = session.artist(16147)
    albums = [
        session.album(20903364),
        session.album(17926933),
        session.album(24855863),
        session.album(28876081),
        session.album(19384377),
    ]

    find_ids(albums, artist.get_ep_singles)


def test_get_other(session):
    artist = session.artist(17123)
    albums = [
        session.album(327452387),
        session.album(322406553),
    ]
    other_albums = artist.get_other
    # artist_item_ids = [item.id for item in other_albums()]
    find_ids(albums, artist.get_other)


def test_get_top_tracks(session):
    artist = session.artist(16147)
    tracks = [
        session.track(17927865),
        session.track(17927867),
        session.track(17926280),
        session.track(17927869),
    ]

    find_ids(tracks, artist.get_top_tracks)


def test_get_videos_release_date(session):
    artist = session.artist(9341252)

    videos = [
        session.video(298985403),
        session.video(288495954),
        session.video(281813762),
        session.video(271621957),
        session.video(267866493),
        session.video(260469454),
    ]

    find_ids(videos, artist.get_videos)


def test_get_videos(session):
    artist = session.artist(4822757)
    videos = [
        session.video(131869431),
        session.video(110282599),
        session.video(107910706),
    ]
    find_ids(videos, artist.get_videos)


def test_get_bio(session):
    artist = session.artist(4822757)
    bio = artist.get_bio()
    assert all(keyword in bio for keyword in ["Syn Cole", "Estonia", "EDM"])


def test_get_similar(session):
    artist = session.artist(4822757)
    similar = [artist.name for artist in artist.get_similar()]
    assert all(artist in similar for artist in ["Avicii", "CAZZETTE", "Didrick"])


def test_get_radio(session):
    artist = session.artist(19275)
    radio = artist.get_radio()
    assert len(radio) >= 99
    assert radio[0].artist.name == artist.name


def test_get_radio_mix(session):
    artist = session.artist(3514310)
    radio = artist.get_radio_mix()
    assert radio.id == "000038b3b74d5ce3a17b43a36d62bb"


def test_artist_image(session):
    artist = session.artist(4822757)
    verify_image_cover(session, artist, [160, 320, 480, 750])
    album = session.album(108043414)
    verify_image_cover(session, album.artist, [160, 320, 480, 750])


def find_ids(items, function):
    """Makes sure that the items argument has id attributes that exist in the list
    returned by function.

    :param items: A list of items that you expect in the list returned by `function`
    :param function: A function that returns a list of items of the same type as items.
    """

    artist_item_ids = [item.id for item in function()]
    assert all(item.id in artist_item_ids for item in items)
