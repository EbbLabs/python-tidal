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
"""A module containing classes and functions related to tidal users.

:class:`User` is a class with user information.
:class:`Favorites` is class with a users favorites.
"""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, List, Optional, Union, cast
from urllib.parse import urljoin

from tidalapi.exceptions import ObjectNotFound
from tidalapi.types import (
    AlbumOrder,
    ArtistOrder,
    ItemOrder,
    JsonObj,
    MixOrder,
    OrderDirection,
    PlaylistOrder,
    VideoOrder,
)
from tidalapi.workers import get_items

if TYPE_CHECKING:
    from tidalapi.album import Album
    from tidalapi.artist import Artist
    from tidalapi.media import Track, Video
    from tidalapi.mix import MixV2
    from tidalapi.playlist import Folder, Playlist, UserPlaylist
    from tidalapi.session import Session


def list_validate(lst):
    if isinstance(lst, str):
        lst = [lst]
    if isinstance(lst, int):
        lst = [str(lst)]
    if len(lst) == 0:
        raise ValueError("An empty list was provided.")
    return lst


class User:
    """A class containing various information about a TIDAL user.

    The attributes of this class are pretty varied. ID is the only attribute you can
    rely on being set. If you initialized a specific user, you will get id, first_name,
    last_name, and picture_id. If parsed as a playlist creator, you will get an ID and a
    name, if the creator isn't an artist, name will be 'user'. If the parsed user is the
    one logged in, for example in session.user, you will get the remaining attributes,
    and id.
    """

    id: Optional[int] = -1

    def __init__(self, session: "Session", user_id: Optional[int]):
        self.id = user_id
        self.session = session
        self.request = session.request
        self.playlist = session.playlist()
        self.folder = session.folder()

    def factory(self) -> Union["LoggedInUser", "FetchedUser", "PlaylistCreator"]:
        return cast(
            Union["LoggedInUser", "FetchedUser", "PlaylistCreator"],
            self.request.map_request("users/%s" % self.id, parse=self.parse),
        )

    def parse(
        self, json_obj: JsonObj
    ) -> Union["LoggedInUser", "FetchedUser", "PlaylistCreator"]:
        if "username" in json_obj:
            user: Union[LoggedInUser, FetchedUser, PlaylistCreator] = LoggedInUser(
                self.session, json_obj["id"]
            )

        elif "firstName" in json_obj:
            user = FetchedUser(self.session, json_obj["id"])

        elif json_obj:
            user = PlaylistCreator(self.session, json_obj["id"])

        # When searching TIDAL does not show up as a creator in the json data.
        else:
            user = PlaylistCreator(self.session, 0)

        return user.parse(json_obj)


class FetchedUser(User):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    picture_id: Optional[str] = None

    def parse(self, json_obj: JsonObj) -> "FetchedUser":
        self.id = json_obj["id"]
        self.first_name = json_obj["firstName"]
        self.last_name = json_obj["lastName"]
        self.picture_id = json_obj.get("picture", None)

        return copy(self)

    def image(self, dimensions: int) -> str:
        if dimensions not in [100, 210, 600]:
            raise ValueError("Invalid resolution {0} x {0}".format(dimensions))

        if self.picture_id is None:
            raise AttributeError("No picture available")

        return self.session.config.image_url % (
            self.picture_id.replace("-", "/"),
            dimensions,
            dimensions,
        )


class LoggedInUser(FetchedUser):
    username: Optional[str] = None
    email: Optional[str] = None
    profile_metadata: Optional[JsonObj] = None

    def __init__(self, session: "Session", user_id: Optional[int]):
        super(LoggedInUser, self).__init__(session, user_id)
        assert self.id is not None, "User is not logged in"
        self.favorites = Favorites(session, self.id)

    def parse(self, json_obj: JsonObj) -> "LoggedInUser":
        super(LoggedInUser, self).parse(json_obj)
        self.username = json_obj["username"]
        self.email = json_obj["email"]
        self.profile_metadata = json_obj

        return copy(self)

    def playlists(self) -> List[Union["Playlist", "UserPlaylist"]]:
        """Get the (personal) playlists created by the user.

        :return: Returns a list of :class:`~tidalapi.playlist.Playlist` objects containing the playlists.
        """
        return cast(
            List[Union["Playlist", "UserPlaylist"]],
            self.request.map_request(
                "users/%s/playlists" % self.id, parse=self.playlist.parse_factory
            ),
        )

    def public_playlists(
        self, offset: int = 0, limit: int = 50
    ) -> List[Union["Playlist", "UserPlaylist"]]:
        """Get the (public) playlists created by the user.

        :param limit: The index of the first item you want included.
        :param offset: The amount of items you want returned.
        :return: List of public playlists.
        """
        params = {"limit": limit, "offset": offset}
        endpoint = "user-playlists/%s/public" % self.id
        json_obj = self.request.request(
            "GET", endpoint, base_url=self.session.config.api_v2_location, params=params
        ).json()

        # The response contains both playlists and user details (followInfo, profile) but we will discard the latter.
        playlists = {"items": []}
        for index, item in enumerate(json_obj["items"]):
            if item["playlist"]:
                playlists["items"].append(item["playlist"])

        return cast(
            List[Union["Playlist", "UserPlaylist"]],
            self.request.map_json(playlists, parse=self.playlist.parse_factory),
        )

    def playlist_and_favorite_playlists(
        self, offset: int = 0, limit: int = 50
    ) -> List[Union["Playlist", "UserPlaylist"]]:
        """Get the playlists created by the user, and the playlists favorited by the
        user. This function is limited to 50 by TIDAL, requiring pagination.

        :return: Returns a list of :class:`~tidalapi.playlist.Playlist` objects containing the playlists.
        """
        params = {"limit": limit, "offset": offset}
        endpoint = "users/%s/playlistsAndFavoritePlaylists" % self.id
        json_obj = self.request.request("GET", endpoint, params=params).json()

        # This endpoint sorts them into favorited and created playlists, but we already do that when parsing them.
        for index, item in enumerate(json_obj["items"]):
            item["playlist"]["dateAdded"] = item["created"]
            json_obj["items"][index] = item["playlist"]

        return cast(
            List[Union["Playlist", "UserPlaylist"]],
            self.request.map_json(json_obj, parse=self.playlist.parse_factory),
        )

    def create_playlist(
        self, title: str, description: str, parent_id: str = "root"
    ) -> "UserPlaylist":
        """Create a playlist in the specified parent folder.

        :param title: Playlist title
        :param description: Playlist description
        :param parent_id: Parent folder ID. Default: 'root' playlist folder
        :return: Returns an object of :class:`~tidalapi.playlist.UserPlaylist` containing the newly created playlist
        """
        params = {"name": title, "description": description, "folderId": parent_id}
        endpoint = "my-collection/playlists/folders/create-playlist"

        json_obj = self.request.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        ).json()
        json = json_obj.get("data")
        if json and json.get("uuid"):
            playlist = self.session.playlist().parse(json)
            return playlist.factory()
        else:
            raise ObjectNotFound("Playlist not found after creation")

    def create_folder(self, title: str, parent_id: str = "root") -> "Folder":
        """Create folder in the specified parent folder.

        :param title: Folder title
        :param parent_id: Folder parent ID. Default: 'root' playlist folder
        :return: Returns an object of :class:`~tidalapi.playlist.Folder` containing the newly created object
        """
        params = {"name": title, "folderId": parent_id}
        endpoint = "my-collection/playlists/folders/create-folder"

        json_obj = self.request.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        ).json()
        if json_obj and json_obj.get("data"):
            return self.request.map_json(json_obj, parse=self.folder.parse)
        else:
            raise ObjectNotFound("Folder not found after creation")


class PlaylistCreator(User):
    name: Optional[str] = None

    def parse(self, json_obj: JsonObj) -> "PlaylistCreator":
        if self.id == 0 or self.session.user is None:
            self.name = "TIDAL"

        elif "name" in json_obj:
            self.name = json_obj["name"]

        elif self.id == self.session.user.id:
            self.name = "me"

        else:
            self.name = "user"

        return copy(self)


class Favorites:
    """An object containing a users favourites."""

    def __init__(self, session: "Session", user_id: int):
        self.session = session
        self.requests = session.request
        self.base_url = f"users/{user_id}/favorites"
        self.v2_base_url = "favorites"

    def add_album(self, album_id: list[str] | str) -> bool:
        """Adds one or more albums to the users favorites.

        :param album_id: TIDAL's identifier of the album.
        :return: A boolean indicating whether the request was successful or not.
        """
        playlist_id = list_validate(album_id)

        response = self.requests.request(
            "POST", f"{self.base_url}/albums", data={"albumId": ",".join(playlist_id)}
        )

        return response.ok

    def add_artist(self, artist_id: list[str] | str) -> bool:
        """Adds one or more artists to the users favorites.

        :param artist_id: TIDAL's identifier of the artist
        :return: A boolean indicating whether the request was successful or not.
        """
        artist_id = list_validate(artist_id)

        return self.requests.request(
            "POST", f"{self.base_url}/artists", data={"artistId": ",".join(artist_id)}
        ).ok

    def add_playlist(
        self,
        playlist_id: list[str] | str,
        parent_folder_id: str = "root",
        validate: bool = False,
    ) -> bool:
        """Add one or more playlists to the users favorites (v2 endpoint)

        :param playlist_id: One or more playlists
        :param parent_folder_id: Parent folder ID. Default: 'root' playlist folder
        :param validate: Validate if the request was completed successfully
        :return: True if request was successful, False otherwise. If 'validate', added
            mixes will be checked.
        """
        playlist_id = list_validate(playlist_id)

        params = {"folderId": parent_folder_id, "uuids": ",".join(playlist_id)}
        endpoint = "my-collection/playlists/folders/add-favorites"

        response = self.requests.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )

        if validate:
            # Check if the expected playlists has been added
            json_obj = response.json()
            added_items = json_obj.get("addedItems", [])

            # No playlists added? Return early
            if not added_items:
                return False

            try:
                # Extract playlist IDs by stripping the 'trn:playlist:' prefix
                added_ids = {item["trn"].split(":")[2] for item in added_items}
            except (KeyError, IndexError):
                # Malformed response; fail gracefully
                return False

            # Check if all requested playlist IDs were successfully added
            return set(playlist_id).issubset(added_ids)
        else:
            return response.ok

    def add_track(self, track_id: list[str] | str) -> bool:
        """Add one or more tracks to the users favorites.

        :param track_id: TIDAL's identifier of the track.
        :return: A boolean indicating whether the request was successful or not.
        """
        track_id = list_validate(track_id)

        return self.requests.request(
            "POST", f"{self.base_url}/tracks", data={"trackId": ",".join(track_id)}
        ).ok

    def add_track_by_isrc(self, isrc: str) -> bool:
        """Adds a track to the users favorites, using isrc.

        :param isrc: The ISRC of the track to be added
        :return: True, if successful.
        """
        try:
            track = self.session.get_tracks_by_isrc(isrc)
            if track:
                # Add the first track in the list
                track_id = str(track[0].id)
                return self.requests.request(
                    "POST", f"{self.base_url}/tracks", data={"trackId": track_id}
                ).ok
            else:
                return False
        except ObjectNotFound:
            return False

    def add_video(self, video_id: str) -> bool:
        """Adds a video to the users favorites.

        :param video_id: TIDAL's identifier of the video.
        :return: A boolean indicating whether the request was successful or not.
        """
        params = {"limit": "100"}
        return self.requests.request(
            "POST",
            f"{self.base_url}/videos",
            data={"videoIds": video_id},
            params=params,
        ).ok

    def add_mixes(self, mix_ids: list[str] | str, validate: bool = False) -> bool:
        """Add one or more mixes (eg. artist, track mixes) to the users favorites (v2 endpoint)
        Note: Default behaviour on missing IDs is FAIL

        :param mix_ids: One or more mix_ids, usually associated to an artist radio or mix
        :param validate: Validate if the request was completed successfully
        :return: True if request was successful, False otherwise. If 'validate', added mixes will be checked.
        """
        mix_ids = list_validate(mix_ids)

        # Prepare request parameters
        params = {"mixIds": ",".join(mix_ids), "onArtifactNotFound": "FAIL"}
        endpoint = "favorites/mixes/add"

        # Send request
        response = self.requests.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )

        if validate:
            # Check if all requested mix IDs are in the added items
            json_obj = response.json()
            added_items = set(json_obj.get("addedItems", []))
            return set(mix_ids).issubset(added_items)
        else:
            return response.ok

    def remove_artist(self, artist_id: str) -> bool:
        """Removes a track from the users favorites.

        :param artist_id: TIDAL's identifier of the artist.
        :return: A boolean indicating whether the request was successful or not.
        """
        if isinstance(artist_id, list):
            return False
        return self.requests.request(
            "DELETE", f"{self.base_url}/artists/{artist_id}"
        ).ok

    def remove_album(self, album_id: str) -> bool:
        """Removes an album from the users favorites.

        :param album_id: TIDAL's identifier of the album
        :return: A boolean indicating whether the request was successful or not.
        """
        if isinstance(album_id, list):
            return False
        return self.requests.request("DELETE", f"{self.base_url}/albums/{album_id}").ok

    def remove_playlist(self, playlist_id: list[str] | str) -> bool:
        """Removes one or more playlists from the users favorites.

        :param playlist_id: TIDAL's identifier of the playlist.
        :return: A boolean indicating whether the request was successful or not.
        """
        return self.remove_folders_playlists(playlist_id, type="playlist")

    def remove_track(self, track_id: str) -> bool:
        """Removes a track from the users favorites.

        :param track_id: TIDAL's identifier of the track.
        :return: A boolean indicating whether the request was successful or not.
        """
        if isinstance(track_id, list):
            return False
        return self.requests.request("DELETE", f"{self.base_url}/tracks/{track_id}").ok

    def remove_video(self, video_id: str) -> bool:
        """Removes a video from the users favorites.

        :param video_id: TIDAL's identifier of the video.
        :return: A boolean indicating whether the request was successful or not.
        """
        if isinstance(video_id, list):
            return False
        return self.requests.request("DELETE", f"{self.base_url}/videos/{video_id}").ok

    def remove_mixes(self, mix_ids: list[str] | str, validate: bool = False) -> bool:
        """Remove one or more mixes (e.g. artist or track mixes) from the user's
        favorites (v2 endpoint).

        :param mix_ids: One or more mix IDs (typically artist or track radios)
        :param validate: Validate if the request was completed successfull
        :return: True if request was successful, False otherwise. If 'validate', deleted
            mixes will be checked.
        """
        mix_ids = list_validate(mix_ids)

        # Prepare request parameters
        params = {"mixIds": ",".join(mix_ids), "onArtifactNotFound": "FAIL"}
        endpoint = "favorites/mixes/remove"

        # Send request
        response = self.requests.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )

        if validate:
            # Check if all requested mix IDs are in the deleted items
            json_obj = response.json()
            deleted_items = set(json_obj.get("deletedItems", []))
            return set(mix_ids).issubset(deleted_items)
        else:
            return response.ok

    def remove_folders_playlists(
        self, trns: list[str] | str, type: str = "folder"
    ) -> bool:
        """Removes one or more folders or playlists from the users favourites (v2
        endpoint)

        :param trns: List of folder (or playlist) trns to be deleted
        :param type: Type of trn: as string, either `folder` or `playlist`. Default `folder`
        :return: A boolean indicating whether theś request was successful or not.
        """
        if type not in ("playlist", "folder"):
            raise ValueError("Invalid trn value used for playlist/folder endpoint")
        trns = list_validate(trns)
        # Make sure all trns has the correct type prepended to it
        trns_full = []
        for trn in trns:
            if "trn:" in trn:
                trns_full.append(trn)
            else:
                trns_full.append(f"trn:{type}:{trn}")
        params = {"trns": ",".join(trns_full)}
        endpoint = "my-collection/playlists/folders/remove"

        response = self.requests.request(
            method="PUT",
            path=endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )
        return response.ok

    def artists_paginated(
        self,
        order: Optional[ArtistOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Artist"]:
        """Get the users favorite artists, using pagination.

        :param order: Optional; A :class:`ArtistOrder` describing the ordering type when returning the user favorite artists. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` :class:`~tidalapi.artist.Artist` objects containing the favorite artists.
        """
        count = self.session.user.favorites.get_artists_count()
        return get_items(
            self.session.user.favorites.artists, count, order, order_direction
        )

    def artists(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[ArtistOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Artist"]:
        """Get the users favorite artists.

        :param limit: Optional; The amount of artists you want returned.
        :param offset: The index of the first artist you want included.
        :param order: Optional; A :class:`ArtistOrder` describing the ordering type when returning the user favorite artists. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` of :class:`~tidalapi.artist.Artist` objects containing the favorite artists.
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        return cast(
            List["Artist"],
            self.requests.map_request(
                f"{self.base_url}/artists",
                params=params,
                parse=self.session.parse_artist,
            ),
        )

    def get_artists_count(
        self,
    ) -> int:
        """Get the total number of artists in the user's collection.

        This performs a minimal API request (limit=1) to fetch metadata about the
        artists without retrieving all of them. The API response contains
        'totalNumberOfItems', which represents the total items (artists) available.
        :return: The number of items available.
        """
        params = {"limit": 1, "offset": 0}

        json_obj = self.requests.map_request(f"{self.base_url}/artists", params=params)
        return json_obj.get("totalNumberOfItems", 0)

    def albums_paginated(
        self,
        order: Optional[AlbumOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Album"]:
        """Get the users favorite albums, using pagination.

        :param order: Optional; A :class:`AlbumOrder` describing the ordering type when returning the user favorite albums. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` :class:`~tidalapi.album.Album` objects containing the favorite albums.
        """
        count = self.session.user.favorites.get_albums_count()
        return get_items(
            self.session.user.favorites.albums, count, order, order_direction
        )

    def albums(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[AlbumOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Album"]:
        """Get the users favorite albums.

        :param limit: Optional; The amount of albums you want returned.
        :param offset: The index of the first album you want included.
        :param order: Optional; A :class:`AlbumOrder` describing the ordering type when returning the user favorite albums. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` of :class:`~tidalapi.album.Album` objects containing the favorite albums.
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        return cast(
            List["Album"],
            self.requests.map_request(
                f"{self.base_url}/albums", params=params, parse=self.session.parse_album
            ),
        )

    def get_albums_count(
        self,
    ) -> int:
        """Get the total number of albums in the user's collection.

        This performs a minimal API request (limit=1) to fetch metadata about the albums
        without retrieving all of them. The API response contains 'totalNumberOfItems',
        which represents the total items (albums) available.
        :return: The number of items available.
        """
        params = {"limit": 1, "offset": 0}

        json_obj = self.requests.map_request(f"{self.base_url}/albums", params=params)
        return json_obj.get("totalNumberOfItems", 0)

    def playlists_paginated(
        self,
        order: Optional[PlaylistOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Playlist"]:
        """Get the users favorite playlists, using pagination.

        :param order: Optional; A :class:`PlaylistOrder` describing the ordering type when returning the user favorite playlists. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` :class:`~tidalapi.playlist.Playlist` objects containing the favorite playlists.
        """
        count = self.session.user.favorites.get_playlists_count()
        return get_items(
            self.session.user.favorites.playlists, count, order, order_direction
        )

    def playlists(
        self,
        limit: Optional[int] = 50,
        offset: int = 0,
        order: Optional[PlaylistOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Playlist"]:
        """Get the users favorite playlists (v2 endpoint), relative to the root folder
        This function is limited to 50 by TIDAL, requiring pagination.

        :param limit: Optional; The number of playlists you want returned (Note: Cannot exceed 50)
        :param offset: The index of the first playlist to fetch
        :param order: Optional; A :class:`PlaylistOrder` describing the ordering type when returning the user favorite playlists. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` :class:`~tidalapi.playlist.Playlist` objects containing the favorite playlists.
        """
        params = {
            "folderId": "root",
            "offset": offset,
            "limit": limit,
            "includeOnly": "PLAYLIST",  # Include only PLAYLIST types, FOLDER will be ignored
        }
        if order:
            params["order"] = order.value
        else:
            params["order"] = PlaylistOrder.DateCreated.value
        if order_direction:
            params["orderDirection"] = order_direction.value
        else:
            params["orderDirection"] = OrderDirection.Descending.value

        endpoint = "my-collection/playlists/folders"
        return cast(
            List["Playlist"],
            self.session.request.map_request(
                url=urljoin(
                    self.session.config.api_v2_location,
                    endpoint,
                ),
                params=params,
                parse=self.session.parse_playlist,
            ),
        )

    def playlist_folders(
        self,
        limit: Optional[int] = 50,
        offset: int = 0,
        order: Optional[PlaylistOrder] = None,
        order_direction: Optional[OrderDirection] = None,
        parent_folder_id: str = "root",
    ) -> List["Folder"]:
        """Get a list of folders created by the user.

        :param limit: Optional; The number of playlists you want returned (Note: Cannot exceed 50)
        :param offset: The index of the first playlist folder to fetch
        :param order: Optional; A :class:`PlaylistOrder` describing the ordering type when returning the user favorite playlists. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :param parent_folder_id: Parent folder ID. Default: 'root' playlist folder
        :return: Returns a list of :class:`~tidalapi.playlist.Folder` objects containing the Folders.
        """
        params = {
            "folderId": parent_folder_id,
            "offset": offset,
            "limit": limit,
            "order": "NAME",
            "includeOnly": "FOLDER",
        }
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        endpoint = "my-collection/playlists/folders"
        return cast(
            List["Folder"],
            self.session.request.map_request(
                url=urljoin(
                    self.session.config.api_v2_location,
                    endpoint,
                ),
                params=params,
                parse=self.session.parse_folder,
            ),
        )

    def get_playlists_count(self) -> int:
        """Get the total number of playlists in the user's root collection.

        This performs a minimal API request (limit=1) to fetch metadata about the
        playlists without retrieving all of them. The API response contains
        'totalNumberOfItems', which represents the total playlists available.
        :return: The number of items available.
        """
        params = {"folderId": "root", "offset": 0, "limit": 1, "includeOnly": ""}

        endpoint = "my-collection/playlists/folders"
        json_obj = self.session.request.map_request(
            url=urljoin(
                self.session.config.api_v2_location,
                endpoint,
            ),
            params=params,
        )
        return json_obj.get("totalNumberOfItems", 0)

    def tracks_paginated(
        self,
        order: Optional[ItemOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Playlist"]:
        """Get the users favorite tracks, using pagination.

        :param order: Optional; A :class:`ItemOrder` describing the ordering type when returning the user favorite tracks. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` :class:`~tidalapi.playlist.Playlist` objects containing the favorite tracks.
        """
        count = self.session.user.favorites.get_tracks_count()
        return get_items(
            self.session.user.favorites.tracks, count, order, order_direction
        )

    def tracks(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[ItemOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Track"]:
        """Get the users favorite tracks.

        :param limit: Optional; The amount of items you want returned.
        :param offset: The index of the first item you want included.
        :param order: Optional; A :class:`ItemOrder` describing the ordering type when returning the user favorite tracks. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` of :class:`~tidalapi.media.Track` objects containing all of the favorite tracks.
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        return cast(
            List["Track"],
            self.requests.map_request(
                f"{self.base_url}/tracks", params=params, parse=self.session.parse_track
            ),
        )

    def get_tracks_count(
        self,
    ) -> int:
        """Get the total number of tracks in the user's collection.

        This performs a minimal API request (limit=1) to fetch metadata about the tracks
        without retrieving all of them. The API response contains 'totalNumberOfItems',
        which represents the total items (tracks) available.
        :return: The number of items available.
        """
        params = {"limit": 1, "offset": 0}

        json_obj = self.requests.map_request(f"{self.base_url}/tracks", params=params)
        return json_obj.get("totalNumberOfItems", 0)

    def videos(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[VideoOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Video"]:
        """Get the users favorite videos.

        :param limit: Optional; The amount of videos you want returned.
        :param offset: The index of the first video you want included.
        :param order: Optional; A :class:`VideoOrder` describing the ordering type when returning the user favorite videos. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` of :class:`~tidalapi.media.Video` objects containing all the favorite videos
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        return cast(
            List["Video"],
            self.requests.map_request(
                f"{self.base_url}/videos",
                params=params,
                parse=self.session.parse_media,
            ),
        )

    def mixes(
        self,
        limit: Optional[int] = 50,
        offset: int = 0,
        order: Optional[MixOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["MixV2"]:
        """Get the users favorite mixes & radio.

        :param limit: Optional; The amount of mixes you want returned.
        :param offset: The index of the first mix you want included.
        :param order: Optional; A :class:`MixOrder` describing the ordering type when returning the user favorite mixes. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A :class:`list` of :class:`~tidalapi.media.Mix` objects containing the user favourite mixes & radio
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        return cast(
            List["MixV2"],
            self.requests.map_request(
                url=urljoin(
                    self.session.config.api_v2_location, f"{self.v2_base_url}/mixes"
                ),
                params=params,
                parse=self.session.parse_v2_mix,
            ),
        )
