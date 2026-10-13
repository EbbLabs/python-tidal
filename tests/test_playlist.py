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

import datetime

import pytest
from dateutil import tz

import tidalapi
from tidalapi.exceptions import ObjectNotFound
from tidalapi.types import ItemOrder, OrderDirection

from .cover import verify_image_cover, verify_image_resolution


def test_playlist(session):
    playlist = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")

    assert playlist.id == "7eafb342-141a-4092-91eb-da0012da3a19"
    assert playlist.name == "JAY-Z's Year End Picks 2019"
    assert playlist.num_tracks == 40
    assert (
        playlist.description
        == "JAY-Z shares his favorite Hip-Hop and R&B songs from the year."
        " (Photo: Ravie B.)"
    )
    assert playlist.duration == 8008
    assert playlist.last_updated == datetime.datetime(
        2021, 12, 9, 17, 13, 40, 932000, tzinfo=tz.tzutc()
    )

    assert playlist.created == datetime.datetime(
        2019, 12, 19, 17, 15, 5, 500000, tzinfo=tz.tzutc()
    )
    assert playlist.type == "ARTIST"
    assert playlist.public is True
    assert playlist.popularity is None
    assert len(playlist.promoted_artists) == 4

    creator = playlist.creator
    assert creator.id == 7804
    assert creator.name == "JAY Z"
    assert isinstance(creator, tidalapi.Artist)

    assert (
        playlist.listen_url
        == "https://listen.tidal.com/playlist/7eafb342-141a-4092-91eb-da0012da3a19"
    )
    assert (
        playlist.share_url
        == "https://tidal.com/browse/playlist/7eafb342-141a-4092-91eb-da0012da3a19"
    )


def test_updated_playlist(session):
    playlist = session.playlist("944dd087-f65c-4954-a9a3-042a574e86e3")
    assert playlist.id == "944dd087-f65c-4954-a9a3-042a574e86e3"
    assert playlist.name == "lofi"
    assert playlist.num_tracks >= 5288
    assert playlist.description == ""
    assert playlist.duration >= 693350
    assert playlist.last_updated >= datetime.datetime(2020, 5, 14, tzinfo=tz.tzutc())
    assert playlist.created == datetime.datetime(
        2020, 4, 15, 15, 15, 37, 282000, tzinfo=tz.tzutc()
    )
    assert playlist.type == "USER"
    assert playlist.public is False
    assert playlist.popularity is None
    assert playlist.promoted_artists is None

    creator = playlist.creator
    assert creator.id == 169584258
    assert creator.name == "user"


def test_playlist_not_found(session):
    with pytest.raises(ObjectNotFound):
        session.playlist("12345678")


def test_playlist_categories(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    playlist_id = playlist.id
    assert playlist.add("125169484", allow_duplicates=True)
    # Playlist should be found in (user) playlists
    user_playlists = session.user.playlists()
    playlist_ids = [playlist.id for playlist in user_playlists]
    assert playlist_id in playlist_ids

    # Playlist not found in user favourite playlists
    # playlists_favs = session.user.favorites.playlists()
    # playlist_ids = [playlist.id for playlist in playlists_favs]
    # assert playlist_id in playlist_ids

    # Playlist is found in user (created) playlists and favourite playlists
    playlists_and_favs = session.user.playlist_and_favorite_playlists()
    playlist_ids = [playlist.id for playlist in playlists_and_favs]
    assert playlist_id in playlist_ids

    # Check if playlist is found in list of public playlists
    public_playlists = session.user.public_playlists()
    playlist_ids = [playlist.id for playlist in public_playlists]
    assert playlist_id not in playlist_ids
    playlist.set_playlist_public()

    # Check if playlist is found in list of public playlists
    public_playlists = session.user.public_playlists()
    playlist_ids = [playlist.id for playlist in public_playlists]
    assert playlist_id in playlist_ids
    playlist.delete()


def test_playlist_add_duplicate(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # track id 125169484
    assert 125169484 in playlist.add("125169484", allow_duplicates=True)
    assert 125169484 in playlist.add("125169484", allow_duplicates=True)
    assert 125169484 not in playlist.add("125169484", allow_duplicates=False)
    playlist.add(["125169484", "125169484", "125169484"], allow_duplicates=False)
    # Check if track has been added more than 2 times
    item_ids = [item.id for item in playlist.items()]
    assert item_ids.count(125169484) == 2
    # Add again, this time allowing duplicates
    assert playlist.add(["125169484", "125169484", "125169484"], allow_duplicates=True)
    item_ids = [item.id for item in playlist.items()]
    assert item_ids.count(125169484) == 5
    playlist.delete()


def test_playlist_add_at_position(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    # Add 10 tracks to the new playlist
    track_ids = [track.id for track in playlist_a.tracks()]
    playlist.add(track_ids[0:10])
    # Add a track to the end of the playlist (default)
    assert playlist.add("125169484")
    item_ids = [item.id for item in playlist.items()]
    assert str(item_ids[-1]) == "125169484"
    # Add a new track to a specific position
    assert playlist.add("77692131", position=2)
    # Verify that track matches the expected position
    item_ids = [item.id for item in playlist.items()]
    assert str(item_ids[2]) == "77692131"
    # Add last four tracks to position 2 in the playlist and verify they are stored at the expected location
    playlist.add(track_ids[-4:], position=2)
    tracks = [item.id for item in playlist.items()][2:6]
    for idx, track_id in enumerate(track_ids[-4:]):
        assert tracks[idx] == track_id
    playlist.delete()


def test_playlist_remove_by_indices(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    track_ids = [track.id for track in playlist_a.tracks()][0:9]
    playlist.add(track_ids)
    # Remove odd tracks
    playlist.remove_by_indices([1, 3, 5, 7])
    # Verify remaining tracks
    tracks = [item.id for item in playlist.items()]
    for idx, track_id in enumerate(tracks):
        assert track_id == track_ids[idx * 2]
    # Remove last track in playlist and check that track has been removed
    last_track = tracks[-1]
    playlist.remove_by_index(playlist.num_tracks - 1)
    tracks = [item.id for item in playlist.items()]
    assert last_track not in tracks
    playlist.delete()


def test_playlist_remove_by_id(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    track_ids = [track.id for track in playlist_a.tracks()][0:9]
    playlist.add(track_ids)
    # Remove track with specific ID
    playlist.remove_by_id(str(track_ids[2]))
    tracks = [item.id for item in playlist.items()]
    assert track_ids[2] not in tracks
    playlist.delete()


def test_playlist_add_isrc(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # track id 125169484
    assert playlist.add_by_isrc("NOG841907010", allow_duplicates=True)
    assert playlist.add_by_isrc("NOG841907010", allow_duplicates=True)
    assert not playlist.add_by_isrc("NOG841907010", allow_duplicates=False)
    assert not playlist.add_by_isrc(
        "NOG841907123", allow_duplicates=True, position=0
    )  # Does not exist, returns false
    # Check if track has been added more than 2 times
    item_ids = [item.id for item in playlist.items()]
    assert item_ids.count(125169484) == 2
    playlist.delete()


def test_playlist_move_by_id(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # Add tracks from existing playlist
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    track_ids = [track.id for track in playlist_a.tracks()]
    playlist.add(track_ids[0:9])
    # Move first track to the end
    first_track_id = track_ids[0]
    playlist.move_by_id(media_id=str(first_track_id), position=playlist.num_tracks - 2)
    # Last track(-2) should now match the previous first track
    tracks = playlist.tracks()
    assert first_track_id == tracks[playlist.num_tracks - 2].id
    playlist.delete()


def test_playlist_move_by_index(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # Add tracks from existing playlist
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    track_ids = [track.id for track in playlist_a.tracks()]
    playlist.add(track_ids[0:9])
    # Move first track to the end
    first_track_id = track_ids[0]
    playlist.move_by_index(index=0, position=playlist.num_tracks - 2)
    # Last track(-2) should now match the previous first track
    track_ids = [track.id for track in playlist.tracks()]
    assert track_ids.index(first_track_id) == playlist.num_tracks - 2
    playlist.delete()


def test_playlist_move_by_indices(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # Add tracks from existing playlist
    playlist_a = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    track_ids = [track.id for track in playlist_a.tracks()]
    playlist.add(track_ids[0:9])
    # Move first 4 tracks to the end
    playlist.move_by_indices(indices=[0, 1, 2, 3], position=playlist.num_tracks)
    # First four tracks should now be moved to the end
    last_tracks = [track.id for track in playlist.tracks()][-4:]
    for idx, track_id in enumerate(last_tracks):
        assert track_ids[idx] == track_id
    playlist.delete()


def test_playlist_merge(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # Add tracks from existing playlist
    added_items = playlist.merge("7eafb342-141a-4092-91eb-da0012da3a19")
    # Check if tracks were added
    # Note: Certain tracks might be skipped for unknown reasons. (Why?)
    # Therefore, we will compare the list of added items with the actual playlist content.
    tracks = [track.id for track in playlist.tracks()]
    for track in tracks:
        assert track in added_items
    playlist.delete()


def test_playlist_public_private(session):
    playlist = session.user.create_playlist("TestingA", "Testing1234")
    # Default: UserPlaylist is not public
    assert not playlist.public
    playlist.set_playlist_public()
    assert playlist.public
    playlist.set_playlist_private()
    assert not playlist.public
    playlist.delete()


def test_video_playlist(session):
    playlist = session.playlist("aa3611ff-5b25-4bbe-8ce4-36c678c3438f")
    assert playlist.id == "aa3611ff-5b25-4bbe-8ce4-36c678c3438f"
    assert playlist.name == "TIDAL X Sundance"
    assert playlist.num_tracks == 0
    assert playlist.num_videos == 12
    assert (
        playlist.description == "In partnership with Vulture, "
        "TIDAL talks to actors and musicians at the 2017 Sundance Film Festival "
        "about the meeting of music and film. #tidalxvulture (Photo: TIDAL) "
    )
    assert playlist.duration == 1996
    assert playlist.last_updated == datetime.datetime(
        2024, 8, 14, 16, 26, 58, 898000, tzinfo=tz.tzutc()
    )
    assert playlist.created == datetime.datetime(
        2017, 1, 23, 18, 34, 56, 930000, tzinfo=tz.tzutc()
    )
    assert playlist.type == "EDITORIAL"
    assert playlist.public is False
    assert playlist.promoted_artists[0].name == "Sundance Film Festival"

    creator = playlist.creator
    assert creator.id == 0
    assert creator.name == "TIDAL"


def test_get_tracks(session):
    playlist = session.playlist("944dd087-f65c-4954-a9a3-042a574e86e3")
    remaining = 0

    items = []
    while remaining < playlist.num_tracks:
        new_items = playlist.tracks(limit=1000, offset=remaining)
        remaining += len(new_items)
        items.extend(new_items)

    assert len(items) >= 5288
    assert items[0].id == 199477058
    assert items[5287].id == 209284860


def test_get_tracks_order(session):
    pl = session.user.create_playlist("TestingOrder", "TestingOrder")
    # Add four tracks, one after the other (Thus user_date_added is NOT identical)
    assert pl.add("246567991")
    assert pl.add("23749237")
    assert pl.add("185042773")
    assert pl.add("180688234")

    # Default order
    tracks = pl.tracks()
    tr = tracks[0]
    # Default order: First track should correspond to first track added
    assert tr.id == 246567991

    # Index, ascending/descending
    trs = pl.tracks(order=ItemOrder.Index, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "23749237" (First track added)
    assert trs[0].id == 246567991
    trs = pl.tracks(order=ItemOrder.Index, order_direction=OrderDirection.Descending)
    # Descending: First track should be "180688234" (Last track added)
    assert trs[0].id == 180688234

    # Title Name, ascending/descending
    trs = pl.tracks(order=ItemOrder.Name, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "Beam Me Up", "180688234"
    assert trs[0].id == 180688234
    trs = pl.tracks(order=ItemOrder.Name, order_direction=OrderDirection.Descending)
    # Descending: First track should be "Joakim,Nothing Gold", "185042773"
    assert trs[0].id == 185042773

    # Artist Name, ascending/descending
    trs = pl.tracks(order=ItemOrder.Artist, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be by Artist:"Hubbabubbaklubb"; "23749237"
    assert trs[0].id == 23749237
    trs = pl.tracks(order=ItemOrder.Artist, order_direction=OrderDirection.Descending)
    # Descending: First track should be by Artist:"Todd Terje"; "23749237"
    assert trs[0].id == 246567991

    # Album Name, ascending/descending
    trs = pl.tracks(order=ItemOrder.Album, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be from Album: "It's Album Time"; "246567991"
    assert trs[0].id == 246567991
    trs = pl.tracks(order=ItemOrder.Album, order_direction=OrderDirection.Descending)
    # Descending: First track should be from Album: "Walking the Midnight Streets"; "23749237"
    assert trs[0].id == 180688234

    # Date, ascending/descending
    trs = pl.tracks(order=ItemOrder.Album, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "246567991"
    assert trs[0].id == 246567991
    added_first = trs[0].user_date_added
    trs = pl.tracks(order=ItemOrder.Album, order_direction=OrderDirection.Descending)
    # Descending: First track should be "23749237"
    assert trs[0].id == 180688234
    added_last = trs[0].user_date_added
    # Tracks are added one after the other so first track should be added before last
    assert added_first < added_last

    # Track Length, ascending/descending
    trs = pl.tracks(order=ItemOrder.Length, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "23749237"
    assert trs[0].id == 23749237
    length_first = trs[0].duration
    trs = pl.tracks(order=ItemOrder.Length, order_direction=OrderDirection.Descending)
    # Descending: First track should be "185042773"
    assert trs[0].id == 185042773
    length_last = trs[0].duration
    assert length_first < length_last
    # Cleanup
    pl.delete()


def test_get_items_order(session):
    pl = session.user.create_playlist("TestingOrder", "TestingOrder")
    # Add four tracks, one after the other (Thus user_date_added is NOT identical)
    assert pl.add("246567991")
    assert pl.add("23749237")
    assert pl.add("185042773")
    assert pl.add("180688234")

    # Default order
    tracks = pl.items()
    tr = tracks[0]
    # Default order: First track should correspond to first track added
    assert tr.id == 246567991

    # Index, ascending/descending
    trs = pl.items(order=ItemOrder.Index, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "23749237" (First track added)
    assert trs[0].id == 246567991
    trs = pl.items(order=ItemOrder.Index, order_direction=OrderDirection.Descending)
    # Descending: First track should be "180688234" (Last track added)
    assert trs[0].id == 180688234

    # Title Name, ascending/descending
    trs = pl.items(order=ItemOrder.Name, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "Beam Me Up", "180688234"
    assert trs[0].id == 180688234
    trs = pl.items(order=ItemOrder.Name, order_direction=OrderDirection.Descending)
    # Descending: First track should be "Joakim,Nothing Gold", "185042773"
    assert trs[0].id == 185042773

    # Artist Name, ascending/descending
    trs = pl.items(order=ItemOrder.Artist, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be by Artist:"Hubbabubbaklubb"; "23749237"
    assert trs[0].id == 23749237
    trs = pl.items(order=ItemOrder.Artist, order_direction=OrderDirection.Descending)
    # Descending: First track should be by Artist:"Todd Terje"; "23749237"
    assert trs[0].id == 246567991

    # Album Name, ascending/descending
    trs = pl.items(order=ItemOrder.Album, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be from Album: "It's Album Time"; "246567991"
    assert trs[0].id == 246567991
    trs = pl.items(order=ItemOrder.Album, order_direction=OrderDirection.Descending)
    # Descending: First track should be from Album: "Walking the Midnight Streets"; "23749237"
    assert trs[0].id == 180688234

    # Date, ascending/descending
    trs = pl.items(order=ItemOrder.Album, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "246567991"
    assert trs[0].id == 246567991
    added_first = trs[0].user_date_added
    trs = pl.items(order=ItemOrder.Album, order_direction=OrderDirection.Descending)
    # Descending: First track should be "23749237"
    assert trs[0].id == 180688234
    added_last = trs[0].user_date_added
    # Tracks are added one after the other so first track should be added before last
    assert added_first < added_last

    # Track Length, ascending/descending
    trs = pl.items(order=ItemOrder.Length, order_direction=OrderDirection.Ascending)
    # Ascending: First track should be "23749237"
    assert trs[0].id == 23749237
    length_first = trs[0].duration
    trs = pl.items(order=ItemOrder.Length, order_direction=OrderDirection.Descending)
    # Descending: First track should be "185042773"
    assert trs[0].id == 185042773
    length_last = trs[0].duration
    assert length_first < length_last
    # Cleanup
    pl.delete()


def test_get_videos(session):
    playlist = session.playlist("aa3611ff-5b25-4bbe-8ce4-36c678c3438f")
    items = playlist.items()
    assert all([isinstance(item, tidalapi.Video) for item in items])
    assert items[0].name == "Day 1: Part 1"
    assert items[-1].name == "Sundance 2017 Recap"


def test_image(session):
    playlist = session.playlist("33136f5a-d93a-4469-9353-8365897aaf94")
    verify_image_cover(session, playlist, [160, 320, 480, 640, 750, 1080])


def test_wide_image(session):
    playlist = session.playlist("7eafb342-141a-4092-91eb-da0012da3a19")
    resolutions = [(160, 107), (480, 320), (750, 500), (1080, 720)]

    for width, height in resolutions:
        verify_image_resolution(
            session, playlist.wide_image(width, height), width, height
        )

    with pytest.raises(ValueError):
        playlist.wide_image(81, 21)

    with pytest.raises(AssertionError):
        verify_image_resolution(session, playlist.wide_image(1080, 720), 1270, 1270)
