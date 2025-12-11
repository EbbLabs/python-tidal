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

import dateutil.tz
import pytest

import tidalapi
from tidalapi.exceptions import ObjectNotFound
from tidalapi.types import (
    AlbumOrder,
    ArtistOrder,
    MixOrder,
    OrderDirection,
    PlaylistOrder,
)


def test_user(session):
    assert isinstance(session.user, tidalapi.LoggedInUser)
    user = session.get_user(session.user.id)
    assert isinstance(user, tidalapi.LoggedInUser)
    assert "@" in user.email


def test_get_user(session):
    user = session.get_user(58600091)
    assert isinstance(user, tidalapi.FetchedUser)
    assert user.first_name == "Five Dragons"
    assert user.last_name == "Music"
    assert not user.picture_id


def test_get_user_playlists(session):
    user_playlists = session.user.playlists()
    user_favorite_playlists = session.user.favorites.playlists()
    user_playlists_and_favorite_playlists = []
    offset = 0
    while True:
        playlists = session.user.playlist_and_favorite_playlists(offset=offset)
        if playlists:
            user_playlists_and_favorite_playlists += playlists
        else:
            break
        offset += 50
    playlist_ids = set(x.id for x in user_playlists)
    favourite_ids = set(x.id for x in user_favorite_playlists)
    both_ids = set(x.id for x in user_playlists_and_favorite_playlists)

    assert playlist_ids | favourite_ids == both_ids


def test_get_playlist_folders(session):
    folder = session.user.create_folder(title="testfolder")
    assert folder
    folder_ids = [folder.id for folder in session.user.favorites.playlist_folders()]
    assert folder.id in folder_ids
    folder.remove()
    folder_ids = [folder.id for folder in session.user.favorites.playlist_folders()]
    assert folder.id not in folder_ids


def test_get_user_playlist_creator(session):
    playlist = session.playlist("944dd087-f65c-4954-a9a3-042a574e86e3")
    creator = playlist.creator
    assert isinstance(creator, tidalapi.PlaylistCreator)
    assert creator.id == 169584258
    assert creator.name == "user"


def test_get_editorial_playlist_creator(session):
    playlist = session.playlist("aa3611ff-5b25-4bbe-8ce4-36c678c3438f")
    creator = playlist.creator
    assert isinstance(creator, tidalapi.PlaylistCreator)
    assert creator.id == 0
    assert creator.name == "TIDAL"


def test_create_playlist(session):
    playlist = session.user.create_playlist("Testing", "Testing1234")
    playlist.add(["125169484"])
    assert playlist.tracks()[0].name == "Alone, Pt. II"
    assert playlist.description == "Testing1234"
    assert playlist.name == "Testing"
    playlist.remove_by_id("125169484")
    assert len(playlist.tracks()) == 0
    playlist.add(["64728757", "125169484"])
    for index, item in enumerate(playlist.tracks()):
        if item.name == "Alone, Pt. II":
            playlist.remove_by_index(index)
            break

    assert playlist.items()[0].id == 64728757
    playlist.remove_by_index(0)
    assert len(playlist.tracks()) == 0

    playlist.edit()
    playlist._reparse()
    assert playlist.name == "Testing"
    assert playlist.description == "Testing1234"

    playlist.edit("testing", "testing1234")
    playlist._reparse()
    assert playlist.name == "testing"
    assert playlist.description == "testing1234"

    assert any(
        [playlist.id == user_playlist.id for user_playlist in session.user.playlists()]
    )
    assert any(
        [isinstance(user_playlist, tidalapi.UserPlaylist)]
        for user_playlist in session.user.playlists()
    )

    long_playlist = session.playlist("944dd087-f65c-4954-a9a3-042a574e86e3")
    playlist_tracks = long_playlist.tracks(limit=250)

    playlist.add([track.id for track in playlist_tracks])
    playlist._reparse()
    playlist.remove_by_id("199477058")
    playlist._reparse()

    track_ids = [track.id for track in playlist.tracks(limit=250)]
    assert 199477058 not in track_ids

    playlist.delete()


def test_create_folder(session):
    folder = session.user.create_folder(title="testfolder")
    assert folder.name == "testfolder"
    assert folder.parent is None
    assert folder.parent_folder_id == "root"
    assert folder.listen_url == f"https://listen.tidal.com/folder/{folder.id}"
    assert folder.total_number_of_items == 0
    assert folder.trn == f"trn:folder:{folder.id}"
    folder_id = folder.id

    # update name
    folder.rename(name="testfolder1")
    assert folder.name == "testfolder1"

    # cleanup
    folder.remove()

    # check if folder has been removed
    with pytest.raises(ObjectNotFound):
        session.folder(folder_id)


def test_folder_add_items(session):
    folder = session.user.create_folder(title="testfolder")
    folder_a = session.folder(folder.id)
    assert isinstance(folder_a, tidalapi.playlist.Folder)
    assert folder_a.id == folder.id

    # create a playlist and add it to the folder
    playlist_a = session.user.create_playlist("TestingA", "Testing1234")
    playlist_a.add(["125169484"])
    playlist_b = session.user.create_playlist("TestingB", "Testing1234")
    playlist_b.add(["125169484"])
    folder.add_items([playlist_a.id, playlist_b.id])

    # verify items
    assert folder.total_number_of_items == 2
    items = folder.items()
    assert len(items) == 2
    item_ids = [item.id for item in items]
    assert playlist_a.id in item_ids
    assert playlist_b.id in item_ids

    # cleanup (This will also delete playlists inside the folder!)
    folder.remove()


def test_folder_moves(session):
    folder_a = session.user.create_folder(title="testfolderA")
    folder_b = session.user.create_folder(title="testfolderB")

    # create a playlist and add it to the folder
    playlist_a = session.user.create_playlist("TestingA", "Testing1234")
    playlist_a.add(["125169484"])
    playlist_b = session.user.create_playlist("TestingB", "Testing1234")
    playlist_b.add(["125169484"])
    folder_a.add_items([playlist_a.id, playlist_b.id])

    # verify items
    assert folder_a.total_number_of_items == 2
    assert folder_b.total_number_of_items == 0
    items = folder_a.items()
    item_ids = [item.id for item in items]

    # move items to folder B
    folder_a.move_items_to_folder(trns=item_ids, folder=folder_b.id)
    folder_b._reparse()  # Manually refresh, as src folder contents will have changed
    assert folder_a.total_number_of_items == 0
    assert folder_b.total_number_of_items == 2
    item_a_ids = [item.id for item in folder_a.items()]
    item_b_ids = [item.id for item in folder_b.items()]
    assert playlist_a.id not in item_a_ids
    assert playlist_b.id not in item_a_ids
    assert playlist_a.id in item_b_ids
    assert playlist_b.id in item_b_ids

    # move items to the root folder
    folder_b.move_items_to_root(trns=item_ids)
    assert folder_a.total_number_of_items == 0
    assert folder_b.total_number_of_items == 0
    folder_b.move_items_to_folder(trns=item_ids)
    assert folder_b.total_number_of_items == 2

    # cleanup (This will also delete playlists inside the folders, if they are still there
    folder_a.remove()
    folder_b.remove()


def test_add_remove_favorite_mix(session):
    mix_ids_single = ["0007646f7c64d03d56846ed25dae3d"]
    mix_ids_multiple = [
        "0000fc7cda952f508279ad2f66222a",
        "0002411cdd08aceba45671ba1f41a2",
    ]

    def assert_mixes_present(expected_ids: list[str], should_exist: bool):
        current_ids = [mix.id for mix in session.user.favorites.mixes()]
        for mix_id in expected_ids:
            if should_exist:
                assert mix_id in current_ids
            else:
                assert mix_id not in current_ids

    # Add single and verify
    assert session.user.favorites.add_mixes(mix_ids_single)
    assert_mixes_present(mix_ids_single, should_exist=True)

    # Add multiple and verify
    assert session.user.favorites.add_mixes(mix_ids_multiple)
    assert_mixes_present(mix_ids_multiple, should_exist=True)

    # Remove single and verify
    assert session.user.favorites.remove_mixes(mix_ids_single)
    assert_mixes_present(mix_ids_single, should_exist=False)

    # Remove multiple and verify
    assert session.user.favorites.remove_mixes(mix_ids_multiple)
    assert_mixes_present(mix_ids_multiple, should_exist=False)


def test_add_remove_favorite_mix_validate(session):
    # Add the same mix twice (Second time will fail, if validate is enabled)
    # Add a single artist mix
    assert session.user.favorites.add_mixes("0000343aa1769e75f54f900febba7e")
    # Add it again. No validate: Success. Validate: Failure
    assert session.user.favorites.add_mixes("0000343aa1769e75f54f900febba7e")
    assert not session.user.favorites.add_mixes(
        "0000343aa1769e75f54f900febba7e", validate=True
    )
    # Cleanup after tests & validate
    assert session.user.favorites.remove_mixes("0000343aa1769e75f54f900febba7e")
    assert not session.user.favorites.remove_mixes(
        "0000343aa1769e75f54f900febba7e", validate=True
    )


def test_add_remove_favorite_artist(session):
    favorites = session.user.favorites
    artist_id = 5247488
    add_remove(
        artist_id, favorites.add_artist, favorites.remove_artist, favorites.artists
    )


def test_add_remove_favorite_artist_multiple(session):
    artist_single = ["1566"]
    artists_multiple = [
        "33236",
        "30395",
        "24996",
        "16928",
        "1728",
    ]

    def assert_artists_present(expected_ids: list[str], should_exist: bool):
        current_ids = [
            str(artist.id) for artist in session.user.favorites.artists_paginated()
        ]
        for artist_id in expected_ids:
            if should_exist:
                assert artist_id in current_ids
            else:
                assert artist_id not in current_ids

    # Add single and verify
    assert session.user.favorites.add_artist(artist_single)
    assert_artists_present(artist_single, should_exist=True)

    # Add multiple and verify
    assert session.user.favorites.add_artist(artists_multiple)
    assert_artists_present(artists_multiple, should_exist=True)

    # Remove single and verify
    assert session.user.favorites.remove_artist(artist_single[0])
    assert_artists_present(artist_single, should_exist=False)

    # Remove multiple (one by one) and verify
    for artist_id in artists_multiple:
        assert session.user.favorites.remove_artist(artist_id)
    assert_artists_present(artists_multiple, should_exist=False)


def test_add_remove_favorite_album(session):
    favorites = session.user.favorites
    album_id = 32961852
    add_remove(
        album_id,
        favorites.add_album,
        favorites.remove_album,
        favorites.albums_paginated,
    )


def test_add_remove_favorite_album_multiple(session):
    album_single = ["32961852"]
    albums_multiple = [
        "446470480",
        "436252631",
        "426730499",
        "437654760",
        "206012740",
    ]

    def assert_albums_present(expected_ids: list[str], should_exist: bool):
        current_ids = [
            str(album.id) for album in session.user.favorites.albums_paginated()
        ]
        for album_id in expected_ids:
            if should_exist:
                assert album_id in current_ids
            else:
                assert album_id not in current_ids

    # Add single and verify
    assert session.user.favorites.add_album(album_single)
    assert_albums_present(album_single, should_exist=True)

    # Add multiple and verify
    assert session.user.favorites.add_album(albums_multiple)
    assert_albums_present(albums_multiple, should_exist=True)

    # Remove single and verify
    assert session.user.favorites.remove_album(album_single[0])
    assert_albums_present(album_single, should_exist=False)

    # Remove multiple and verify
    for album in albums_multiple:
        assert session.user.favorites.remove_album(album)
    assert_albums_present(albums_multiple, should_exist=False)


def test_add_remove_favorite_playlist(session):
    favorites = session.user.favorites
    playlists_and_favorite_playlists = session.user.playlist_and_favorite_playlists
    playlist_id = "e676056d-fbc6-499a-be9d-7191d2d0bfee"
    add_remove(
        playlist_id,
        favorites.add_playlist,
        favorites.remove_playlist,
        favorites.playlists,
    )
    add_remove(
        playlist_id,
        favorites.add_playlist,
        favorites.remove_playlist,
        playlists_and_favorite_playlists,
    )


def test_add_remove_favorite_playlists(session):
    playlist_single = ["94fe2b9b-096d-4b39-8129-d5b8e774e9b3"]
    playlists_multiple = [
        "285d6293-8f77-4dc1-8dab-a262f3d0cb43",
        "6bd2a3a8-a84e-4540-9077-f99858c230d5",
        "e89f8af0-cf8c-4f5d-81fc-7b5955c558f1",
        "13aacb6d-aa07-4186-8fb1-41b6a617d1c8",
        "ca372375-7d98-4970-a7b0-04db88b68c6d",
    ]

    def assert_playlists_present(expected_ids: list[str], should_exist: bool):
        current_ids = [pl.id for pl in session.user.favorites.playlists()]
        for pl_id in expected_ids:
            if should_exist:
                assert pl_id in current_ids
            else:
                assert pl_id not in current_ids

    # Add single and verify
    assert session.user.favorites.add_playlist(playlist_single)
    assert_playlists_present(playlist_single, should_exist=True)

    # Add multiple and verify
    assert session.user.favorites.add_playlist(playlists_multiple)
    assert_playlists_present(playlists_multiple, should_exist=True)

    # Remove single and verify
    assert session.user.favorites.remove_playlist(playlist_single[0])
    assert_playlists_present(playlist_single, should_exist=False)

    # Remove multiple and verify
    for playlist in playlists_multiple:
        assert session.user.favorites.remove_playlist(playlist)
    assert_playlists_present(playlists_multiple, should_exist=False)


def test_get_favorite_tracks(session):
    favorites = session.user.favorites
    tracks = favorites.tracks_paginated()
    tracks_count = favorites.get_tracks_count()
    # Only the available tracks are returned so the final track count might be lower
    assert len(tracks) > 0 and tracks_count >= len(tracks)
    assert isinstance(tracks[0], tidalapi.Track)


def test_add_remove_favorite_track(session):
    favorites = session.user.favorites
    track_id = 32961853
    add_remove(
        track_id,
        favorites.add_track,
        favorites.remove_track,
        favorites.tracks_paginated,
    )


def test_add_remove_favorite_track_multiple(session):
    track_single = ["444306564"]
    tracks_multiple = [
        "439159646",
        "445292352",
        "444053782",
        "426730500",
    ]

    def assert_tracks_present(expected_ids: list[str], should_exist: bool):
        current_ids = [
            str(track.id) for track in session.user.favorites.tracks_paginated()
        ]
        for track_id in expected_ids:
            if should_exist:
                assert track_id in current_ids
            else:
                assert track_id not in current_ids

    # Add single and verify
    assert session.user.favorites.add_track(track_single)
    assert_tracks_present(track_single, should_exist=True)

    # Add multiple and verify
    assert session.user.favorites.add_track(tracks_multiple)
    assert_tracks_present(tracks_multiple, should_exist=True)

    # Remove single and verify
    assert session.user.favorites.remove_track(track_single[0])
    assert_tracks_present(track_single, should_exist=False)

    # Remove multiple (one by one) and verify
    for track_id in tracks_multiple:
        assert session.user.favorites.remove_track(track_id)
    assert_tracks_present(tracks_multiple, should_exist=False)


def test_get_favorite_videos(session):
    favorites = session.user.favorites
    videos = favorites.videos_paginated()
    videos_count = favorites.get_videos_count()
    assert videos_count > 0 and len(videos) == videos_count
    assert isinstance(videos[0], tidalapi.media.Video)


def test_add_remove_favorite_video(session):
    favorites = session.user.favorites
    video_id = 160850422
    add_remove(video_id, favorites.add_video, favorites.remove_video, favorites.videos)


def test_get_favorite_playlists(session):
    favorites = session.user.favorites
    playlists = favorites.playlists_paginated()
    playlists_count = favorites.get_playlists_count()
    assert len(playlists) > 0 and playlists_count == len(playlists)
    assert isinstance(playlists[0], tidalapi.Playlist)


def test_get_favorite_playlists_order(session):
    # Add 5 favourite playlists to ensure enough playlists exist for the tests
    playlist_ids = [
        "285d6293-8f77-4dc1-8dab-a262f3d0cb43",
        "6bd2a3a8-a84e-4540-9077-f99858c230d5",
        "e89f8af0-cf8c-4f5d-81fc-7b5955c558f1",
        "13aacb6d-aa07-4186-8fb1-41b6a617d1c8",
        "ca372375-7d98-4970-a7b0-04db88b68c6d",
    ]
    # Add playlist one at a time (will ensure non-identical DateCreated)
    for playlist_id in playlist_ids:
        assert session.user.favorites.add_playlist(playlist_id)

    def get_playlist_ids(**kwargs) -> list[str]:
        return [
            str(pl.id) for pl in session.user.favorites.playlists_paginated(**kwargs)
        ]

    # Default sort should equal DateCreated ascending
    ids_default = get_playlist_ids()
    ids_date_created_asc = get_playlist_ids(
        order=PlaylistOrder.DateCreated,
        order_direction=OrderDirection.Ascending,
    )
    # DateCreated descending is reverse of ascending
    ids_date_created_desc = get_playlist_ids(
        order=PlaylistOrder.DateCreated,
        order_direction=OrderDirection.Descending,
    )
    # Note: Default direction seems inconsistent (not always the same) so this check might fail
    assert ids_default == ids_date_created_desc
    assert list_mismatch_count(ids_date_created_desc, ids_date_created_asc, True) < 5

    # Name ascending vs. descending
    ids_name_asc = get_playlist_ids(
        order=PlaylistOrder.Name,
        order_direction=OrderDirection.Ascending,
    )
    ids_name_desc = get_playlist_ids(
        order=PlaylistOrder.Name,
        order_direction=OrderDirection.Descending,
    )
    assert list_mismatch_count(ids_name_desc, ids_name_asc, True) < 5

    # Cleanup
    assert session.user.favorites.remove_playlist(playlist_ids)


def test_get_favorite_albums(session):
    favorites = session.user.favorites
    albums = favorites.albums_paginated()
    albums_count = favorites.get_albums_count()
    assert len(albums) > 0 and albums_count == len(albums)
    assert isinstance(albums[0], tidalapi.Album)


def test_get_favorite_albums_order(session):
    album_ids = [
        "446470480",
        "436252631",
        "426730499",
        "437654760",
        "206012740",
    ]

    # Add playlist one at a time (will ensure non-identical DateAdded)
    for album_id in album_ids:
        assert session.user.favorites.add_album(album_id)

    def get_album_ids(**kwargs) -> list[str]:
        return [
            str(album.id) for album in session.user.favorites.albums_paginated(**kwargs)
        ]

    # Default sort should equal name ascending
    ids_default = get_album_ids()
    ids_name_asc = get_album_ids(
        order=AlbumOrder.Name,
        order_direction=OrderDirection.Ascending,
    )
    # Name descending is reverse of ascending
    ids_name_desc = get_album_ids(
        order=AlbumOrder.Name,
        order_direction=OrderDirection.Descending,
    )
    # Note: Default direction seems inconsistent (not always the same) so this check might fail
    assert ids_default == ids_name_asc
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_name_desc, ids_name_asc, True) < 3

    # Date added ascending vs. descending
    ids_date_created_asc = get_album_ids(
        order=AlbumOrder.DateAdded,
        order_direction=OrderDirection.Ascending,
    )
    ids_date_created_desc = get_album_ids(
        order=AlbumOrder.DateAdded,
        order_direction=OrderDirection.Descending,
    )
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_date_created_asc, ids_date_created_desc, True) < 3

    # Release date ascending vs. descending
    ids_rel_date_asc = get_album_ids(
        order=AlbumOrder.ReleaseDate,
        order_direction=OrderDirection.Ascending,
    )
    ids_rel_date_desc = get_album_ids(
        order=AlbumOrder.ReleaseDate,
        order_direction=OrderDirection.Descending,
    )
    # TODO Somehow these two are not 100% equal. Why?
    # assert list_match_count(ids_rel_date_asc, ids_rel_date_desc, True) < 3

    # Cleanup
    for album_id in album_ids:
        assert session.user.favorites.remove_album(album_id)


def test_get_favorite_mixes(session):
    favorites = session.user.favorites
    mixes = favorites.mixes()
    assert len(mixes) > 0
    assert isinstance(mixes[0], tidalapi.MixV2)


def test_get_favorite_mixes_order(session):
    mix_ids = [
        "0007646f7c64d03d56846ed25dae3d",
        "0000fc7cda952f508279ad2f66222a",
        "0002411cdd08aceba45671ba1f41a2",
        "00026ca3141ec4758599dda8801d84",
        "00031d3da7d212ac54e2b5d6a42849",
    ]

    # Add mix one at a time (will ensure non-identical DateAdded)
    for mix_id in mix_ids:
        assert session.user.favorites.add_mixes(mix_id)

    def get_mix_ids(**kwargs) -> list[str]:
        return [str(mix.id) for mix in session.user.favorites.mixes(**kwargs)]

    # Default sort should equal DateAdded ascending
    ids_default = get_mix_ids()
    ids_date_added_asc = get_mix_ids(
        order=MixOrder.DateAdded,
        order_direction=OrderDirection.Ascending,
    )
    # DateAdded descending is reverse of ascending
    ids_date_added_desc = get_mix_ids(
        order=MixOrder.DateAdded,
        order_direction=OrderDirection.Descending,
    )
    # Note: Default direction seems inconsistent (not always the same) so this check might fail
    assert ids_default == ids_date_added_asc
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_date_added_desc, ids_date_added_asc, True) < 3

    # Name ascending vs. descending
    ids_name_asc = get_mix_ids(
        order=MixOrder.Name,
        order_direction=OrderDirection.Ascending,
    )
    ids_name_desc = get_mix_ids(
        order=MixOrder.Name,
        order_direction=OrderDirection.Descending,
    )
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_name_desc, ids_name_asc, True) < 3

    # MixType ascending vs. descending
    ids_type_asc = get_mix_ids(
        order=MixOrder.MixType,
        order_direction=OrderDirection.Ascending,
    )
    ids_type_desc = get_mix_ids(
        order=MixOrder.MixType,
        order_direction=OrderDirection.Descending,
    )
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_type_desc, ids_type_asc, True) < 3

    # Cleanup
    assert session.user.favorites.remove_mixes(mix_ids, validate=True)


def test_get_favorite_artists(session):
    favorites = session.user.favorites
    artists = favorites.artists_paginated()
    artists_count = favorites.get_artists_count()
    assert len(artists) > 0 and artists_count == len(artists)
    assert isinstance(artists[0], tidalapi.Artist)


def test_get_favorite_artists_order(session):
    artist_ids = [
        "4836523",
        "3642059",
        "5652094",
        "9762896",
        "6777457",
    ]

    for artist_id in artist_ids:
        assert session.user.favorites.add_artist(artist_id)

    def get_artist_ids(**kwargs) -> list[str]:
        return [
            str(artist.id)
            for artist in session.user.favorites.artists_paginated(**kwargs)
        ]

    # Default sort should equal Name ascending
    ids_default = get_artist_ids()
    ids_name_asc = get_artist_ids(
        order=ArtistOrder.Name,
        order_direction=OrderDirection.Ascending,
    )

    # Name descending is reverse of ascending
    ids_name_desc = get_artist_ids(
        order=ArtistOrder.Name,
        order_direction=OrderDirection.Descending,
    )
    # Note: Default direction seems inconsistent (not always the same) so this check might fail
    assert ids_default == ids_name_asc
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks
    assert list_mismatch_count(ids_name_desc, ids_name_asc, True) < 3

    # DateAdded ascending vs. descending
    ids_date_added_asc = get_artist_ids(
        order=ArtistOrder.DateAdded,
        order_direction=OrderDirection.Ascending,
    )
    ids_date_added_desc = get_artist_ids(
        order=ArtistOrder.DateAdded,
        order_direction=OrderDirection.Descending,
    )
    # Check for mismatches, but allow a few of them being swapped due to tidal quirks due to tidal quirks
    assert list_mismatch_count(ids_date_added_desc, ids_date_added_asc, True) < 4

    # Cleanup
    for artist_id in artist_ids:
        assert session.user.favorites.remove_artist(artist_id)


def list_mismatch_count(a, b, reverse=False):
    """Check for matches in a list.

    Assumes identical number of items
    """
    mismatches = []
    if reverse:
        items = enumerate(zip(a, reversed(b)))
    else:
        items = enumerate(zip(a, b))
    for i, (left, right) in items:
        if left != right:
            mismatches.append((i, left, right))
    return len(mismatches)


def add_remove(object_id, add, remove, objects):
    """Add and remove an item from favorites. Skips the test if the item was already in
    your favorites.

    :param object_id: Identifier of the object
    :param add: Function to add object to favorites
    :param remove: Function to remove object from favorites
    :param objects: Function to list objects in favorites
    """
    # If the item is already favorited, we don't want to do anything with it,
    # as it would result in the date it was favorited changing. Avoiding it
    # also lets us make sure that we won't remove something from the favorites
    # if the tests are cancelled.
    exists = False
    for item in objects():
        if item.id == object_id:
            exists = True
            model = type(item).__name__
            name = item.name
    if exists:
        reason = (
            "%s '%s' is already favorited, skipping to avoid changing the date it was favorited"
            % (model, name)
        )
        pytest.skip(reason)

    current_time = datetime.datetime.now(tz=dateutil.tz.tzutc())
    assert add(object_id)
    for item in objects():
        if item.id == object_id:
            exists = True
            # Checks that the item was added after the function was called. TIDAL seems to be 150ms ahead some times.
            timedelta = current_time - item.user_date_added
            assert timedelta < datetime.timedelta(microseconds=150000)
    assert exists

    assert remove(object_id)
    assert any(item.id == object_id for item in objects()) is False
