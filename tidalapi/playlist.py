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
"""A module containing things related to TIDAL playlists."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Sequence, Union, cast

from tidalapi.exceptions import ObjectNotFound, TooManyRequests
from tidalapi.types import ItemOrder, JsonObj, OrderDirection
from tidalapi.user import LoggedInUser

if TYPE_CHECKING:
    from tidalapi.artist import Artist
    from tidalapi.media import Track, Video
    from tidalapi.session import Session
    from tidalapi.user import User

import dateutil.parser


def list_validate(lst):
    if isinstance(lst, str):
        lst = [lst]
    if len(lst) == 0:
        raise ValueError("An empty list was provided.")
    return lst


class Playlist:
    """An object containing various data about a playlist and methods to work with
    them."""

    id: Optional[str] = None
    trn: Optional[str] = None
    name: Optional[str] = None
    num_tracks: int = -1
    num_videos: int = -1
    creator: Optional[Union["Artist", "User"]] = None
    description: Optional[str] = None
    duration: int = -1
    last_updated: Optional[datetime] = None
    created: Optional[datetime] = None
    type = None
    public: Optional[bool] = False
    popularity: Optional[int] = None
    promoted_artists: Optional[List["Artist"]] = None
    last_item_added_at: Optional[datetime] = None
    picture: Optional[str] = None
    square_picture: Optional[str] = None
    user_date_added: Optional[datetime] = None
    _etag: Optional[str] = None

    # Direct URL to https://listen.tidal.com/playlist/<playlist_id>
    listen_url: str = ""
    # Direct URL to https://tidal.com/browse/playlist/<playlist_id>
    share_url: str = ""

    def __init__(self, session: "Session", playlist_id: Optional[str]):
        self.id = playlist_id
        self.session = session
        self.request = session.request
        self._base_url = "playlists/%s"
        if playlist_id:
            try:
                request = self.request.request("GET", self._base_url % self.id)
            except ObjectNotFound:
                raise ObjectNotFound("Playlist not found")
            except TooManyRequests:
                raise TooManyRequests("Playlist unavailable")
            else:
                self._etag = request.headers["etag"]
                self.parse(request.json())

    def parse(self, json_obj: JsonObj) -> "Playlist":
        """Parses a playlist from tidal, replaces the current playlist object.

        :param json_obj: Json data returned from api.tidal.com containing a playlist
        :return: Returns a copy of the original :exc: 'Playlist': object
        """
        self.id = json_obj["uuid"]
        self.trn = f"trn:playlist:{self.id}"
        self.name = json_obj["title"]
        self.num_tracks = int(json_obj["numberOfTracks"])
        self.num_videos = int(json_obj["numberOfVideos"])
        self.description = json_obj["description"]
        self.duration = int(json_obj["duration"])

        # These can be missing on from the /pages endpoints
        last_updated = json_obj.get("lastUpdated")
        self.last_updated = (
            dateutil.parser.isoparse(last_updated) if last_updated else None
        )
        created = json_obj.get("created")
        self.created = dateutil.parser.isoparse(created) if created else None
        public = json_obj.get("publicPlaylist")
        self.public = None if public is None else bool(public)
        popularity = json_obj.get("popularity")
        self.popularity = int(popularity) if popularity else None

        self.type = json_obj["type"]
        self.picture = json_obj["image"]
        self.square_picture = json_obj["squareImage"]

        promoted_artists = json_obj["promotedArtists"]
        self.promoted_artists = (
            self.session.parse_artists(promoted_artists) if promoted_artists else None
        )

        last_item_added_at = json_obj.get("lastItemAddedAt")
        self.last_item_added_at = (
            dateutil.parser.isoparse(last_item_added_at) if last_item_added_at else None
        )

        user_date_added = json_obj.get("dateAdded")
        self.user_date_added = (
            dateutil.parser.isoparse(user_date_added) if user_date_added else None
        )

        creator = json_obj.get("creator")
        if self.type == "ARTIST" and creator and creator.get("id"):
            self.creator = self.session.parse_artist(creator)
        else:
            self.creator = self.session.parse_user(creator) if creator else None

        self.listen_url = f"{self.session.config.listen_base_url}/playlist/{self.id}"
        self.share_url = f"{self.session.config.share_base_url}/playlist/{self.id}"

        return copy.copy(self)

    def factory(self) -> Union["Playlist", "UserPlaylist"]:
        if (
            self.id
            and self.creator
            and isinstance(self.session.user, LoggedInUser)
            and self.creator.id == self.session.user.id
        ):
            return UserPlaylist(self.session, self.id)

        return self

    def parse_factory(self, json_obj: JsonObj) -> "Playlist":
        self.parse(json_obj)
        return copy.copy(self.factory())

    def tracks(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        order: Optional[ItemOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List["Track"]:
        """Gets the playlists' tracks from TIDAL.

        :param limit: The amount of items you want returned.
        :param offset: The index of the first item you want included.
        :param order: Optional; A :class:`ItemOrder` describing the ordering type when returning the playlist tracks. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A list of :class:`Tracks <.Track>`
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        request = self.request.request(
            "GET", self._base_url % self.id + "/tracks", params=params
        )
        self._etag = request.headers["etag"]
        return list(
            self.request.map_json(
                json_obj=request.json(), parse=self.session.parse_track
            )
        )

    def items(
        self,
        limit: int = 100,
        offset: int = 0,
        order: Optional[ItemOrder] = None,
        order_direction: Optional[OrderDirection] = None,
    ) -> List[Union["Track", "Video"]]:
        """Fetches up to the first 100 items, including tracks and videos.

        :param limit: The amount of items you want, up to 100.
        :param offset: The index of the first item you want returned
        :param order: Optional; A :class:`ItemOrder` describing the ordering type when returning the playlist items. eg.: "NAME, "DATE"
        :param order_direction: Optional; A :class:`OrderDirection` describing the ordering direction when sorting by `order`. eg.: "ASC", "DESC"
        :return: A list of :class:`Tracks<.Track>` and :class:`Videos<.Video>`
        """
        params = {"limit": limit, "offset": offset}
        if order:
            params["order"] = order.value
        if order_direction:
            params["orderDirection"] = order_direction.value

        request = self.request.request(
            "GET", self._base_url % self.id + "/items", params=params
        )
        self._etag = request.headers["etag"]
        return list(
            self.request.map_json(request.json(), parse=self.session.parse_media)
        )

    def image(self, dimensions: int = 480, wide_fallback: bool = True) -> str:
        """A URL to a playlist picture.

        :param dimensions: The width and height that want from the image
        :type dimensions: int
        :param wide_fallback: Use wide image as fallback if no square cover picture exists
        :type wide_fallback: bool
        :return: A url to the image

        Original sizes: 160x160, 320x320, 480x480, 640x640, 750x750, 1080x1080
        """

        if dimensions not in [160, 320, 480, 640, 750, 1080]:
            raise ValueError("Invalid resolution {0} x {0}".format(dimensions))
        if self.square_picture:
            return self.session.config.image_url % (
                self.square_picture.replace("-", "/"),
                dimensions,
                dimensions,
            )
        elif self.picture and wide_fallback:
            return self.wide_image()
        else:
            raise AttributeError("No picture available")

    def wide_image(self, width: int = 1080, height: int = 720) -> str:
        """Create a url to a wider playlist image.

        :param width: The width of the image
        :param height: The height of the image
        :return: Returns a url to the image with the specified resolution

        Valid sizes: 160x107, 480x320, 750x500, 1080x720
        """

        if (width, height) not in [(160, 107), (480, 320), (750, 500), (1080, 720)]:
            raise ValueError("Invalid resolution {} x {}".format(width, height))
        if self.picture is None:
            raise AttributeError("No picture available")
        return self.session.config.image_url % (
            self.picture.replace("-", "/"),
            width,
            height,
        )


class Folder:
    """An object containing various data about a folder and methods to work with
    them."""

    trn: Optional[str] = None
    id: Optional[str] = None
    parent_folder_id: Optional[str] = None
    name: Optional[str] = None
    parent: Optional[str] = None  # TODO Determine the correct type of the parent
    added: Optional[datetime] = None
    created: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    total_number_of_items: int = 0

    # Direct URL to https://listen.tidal.com/folder/<folder_id>
    listen_url: str = ""

    def __init__(
        self,
        session: "Session",
        folder_id: Optional[str],
        parent_folder_id: str = "root",
    ):
        self.id = folder_id
        self.parent_folder_id = parent_folder_id
        self.session = session
        self.request = session.request
        self.playlist = session.playlist()
        self._endpoint = "my-collection/playlists/folders"
        if folder_id:
            # Go through all available folders and see if the requested folder exists
            try:
                params = {
                    "folderId": parent_folder_id,
                    "offset": 0,
                    "limit": 50,
                    "order": "NAME",
                    "includeOnly": "FOLDER",
                }
                request = self.request.request(
                    "GET",
                    self._endpoint,
                    base_url=self.session.config.api_v2_location,
                    params=params,
                )
                for item in request.json().get("items"):
                    if item["data"].get("id") == folder_id:
                        self.parse(item)
                        return
                raise ObjectNotFound
            except ObjectNotFound:
                raise ObjectNotFound(f"Folder not found")
            except TooManyRequests:
                raise TooManyRequests("Folder unavailable")

    def _reparse(self) -> None:
        params = {
            "folderId": self.parent_folder_id,
            "offset": 0,
            "limit": 50,
            "order": "NAME",
            "includeOnly": "FOLDER",
        }
        request = self.request.request(
            "GET",
            self._endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )
        for item in request.json().get("items"):
            if item["data"].get("id") == self.id:
                self.parse(item)
                return

    def parse(self, json_obj: JsonObj) -> "Folder":
        """Parses a folder from tidal, replaces the current folder object.

        :param json_obj: Json data returned from api.tidal.com containing a folder
        :return: Returns a copy of the original :class:`Folder` object
        """
        self.trn = json_obj.get("trn")
        self.id = json_obj["data"].get("id")
        self.name = json_obj.get("name")
        self.parent = json_obj.get("parent")
        added = json_obj.get("addedAt")
        created = json_obj["data"].get("createdAt")
        last_modified = json_obj["data"].get("lastModifiedAt")
        self.added = dateutil.parser.isoparse(added) if added else None
        self.created = dateutil.parser.isoparse(created) if added else None
        self.last_modified = dateutil.parser.isoparse(last_modified) if added else None
        self.total_number_of_items = json_obj["data"].get("totalNumberOfItems")

        self.listen_url = f"{self.session.config.listen_base_url}/folder/{self.id}"

        return copy.copy(self)

    def rename(self, name: str) -> bool:
        """Rename the selected folder.

        :param name: The name to be used for the folder
        :return: True, if operation was successful.
        """
        params = {"trn": self.trn, "name": name}
        endpoint = "my-collection/playlists/folders/rename"
        res = self.request.request(
            "PUT",
            endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )
        self._reparse()
        return res.ok

    def remove(self) -> bool:
        """Remove the selected folder.

        :return: True, if operation was successful.
        """
        params = {"trns": self.trn}
        endpoint = "my-collection/playlists/folders/remove"
        return self.request.request(
            "PUT",
            endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        ).ok

    def items(
        self, offset: int = 0, limit: int = 50
    ) -> List[Union["Playlist", "UserPlaylist"]]:
        """Return the items in the folder.

        :param offset: Optional; The index of the first item to be returned. Default: 0
        :param limit: Optional; The amount of items you want returned. Default: 50
        :return: Returns a list of :class:`Playlist` or :class:`UserPlaylist` objects
        """
        params = {
            "folderId": self.id,
            "offset": offset,
            "limit": limit,
            "order": "NAME",
            "includeOnly": "PLAYLIST",
        }
        endpoint = "my-collection/playlists/folders"
        json_obj = self.request.request(
            "GET",
            endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        ).json()
        # Generate a dict of Playlist items from the response data
        if json_obj.get("items"):
            playlists = {"items": [item["data"] for item in json_obj.get("items")]}
            return cast(
                List[Union["Playlist", "UserPlaylist"]],
                self.request.map_json(playlists, parse=self.playlist.parse_factory),
            )
        else:
            return []

    def add_items(self, trns: [str]):
        """Convenience method to add items to the current folder.

        :param trns: List of playlist trns to be added to the current folder
        :return: True, if operation was successful.
        """
        self.move_items_to_folder(trns, self.id)

    def move_items_to_root(self, trns: [str]):
        """Convenience method to move items from the current folder to the root folder.

        :param trns: List of playlist trns to be moved from the current folder
        :return: True, if operation was successful.
        """
        self.move_items_to_folder(trns, folder="root")

    def move_items_to_folder(self, trns: [str], folder: str = None):
        """Move item(s) in one folder to another folder.

        :param trns: List of playlist trns to be moved.
        :param folder: Destination folder. Default: Use the current folder
        :return: True, if operation was successful.
        """
        trns = list_validate(trns)
        # Make sure all trns has the correct type prepended to it
        trns_full = []
        for trn in trns:
            if "trn:" in trn:
                trns_full.append(trn)
            else:
                trns_full.append(f"trn:playlist:{trn}")
        if not folder:
            folder = self.id
        params = {"folderId": folder, "trns": ",".join(trns_full)}
        endpoint = "my-collection/playlists/folders/move"
        res = self.request.request(
            "PUT",
            endpoint,
            base_url=self.session.config.api_v2_location,
            params=params,
        )
        self._reparse()
        return res.ok


class UserPlaylist(Playlist):
    def _reparse(self) -> None:
        """Re-Read Playlist to get ETag."""
        request = self.request.request("GET", self._base_url % self.id)
        self._etag = request.headers["etag"]
        self.request.map_json(request.json(), parse=self.parse)

    def edit(
        self, title: Optional[str] = None, description: Optional[str] = None
    ) -> bool:
        """Edit UserPlaylist title & description.

        :param title: Playlist title
        :param description: Playlist title.
        :return: True, if successful.
        """
        if not title:
            title = self.name
        if not description:
            description = self.description

        data = {"title": title, "description": description}
        return self.request.request("POST", self._base_url % self.id, data=data).ok

    def delete_by_id(self, media_ids: List[str]) -> bool:
        """Delete one or more items from the UserPlaylist.

        :param media_ids: Lists of Media IDs to remove.
        :return: True, if successful.
        """
        media_ids = list_validate(media_ids)
        # Generate list of track indices of tracks found in the list of media_ids.
        track_ids = [str(track.id) for track in self.tracks()]
        matching_indices = [i for i, item in enumerate(track_ids) if item in media_ids]
        return self.remove_by_indices(matching_indices)

    def add(
        self,
        media_ids: List[str],
        allow_duplicates: bool = False,
        position: int = -1,
        limit: int = 100,
    ) -> List[int]:
        """Add one or more items to the UserPlaylist.

        :param media_ids: List of Media IDs to add.
        :param allow_duplicates: Allow adding duplicate items
        :param position: Insert items at a specific position.
            Default: insert at the end of the playlist
        :param limit: Maximum number of items to add
        :return: List of media IDs that has been added
        """
        media_ids = list_validate(media_ids)
        # Insert items at a specific index
        if position < 0 or position > self.num_tracks:
            position = self.num_tracks
        data = {
            "onArtifactNotFound": "SKIP",
            "trackIds": ",".join(map(str, media_ids)),
            "toIndex": position,
            "onDupes": "ADD" if allow_duplicates else "SKIP",
        }
        params = {"limit": limit}
        headers = {"If-None-Match": self._etag} if self._etag else None
        res = self.request.request(
            "POST",
            self._base_url % self.id + "/items",
            params=params,
            data=data,
            headers=headers,
        )
        self._reparse()
        # Respond with the added item IDs:
        added_items = res.json().get("addedItemIds")
        if added_items:
            return added_items
        else:
            return []

    def merge(
        self, playlist: str, allow_duplicates: bool = False, allow_missing: bool = True
    ) -> List[int]:
        """Add (merge) items from a playlist with the current playlist.

        :param playlist: Playlist UUID to be merged in the current playlist
        :param allow_duplicates: If true, duplicate tracks are allowed. Otherwise,
            tracks will be skipped.
        :param allow_missing: If true, missing tracks are allowed. Otherwise, exception
            will be thrown
        :return: List of items that has been added from the playlist
        """
        data = {
            "fromPlaylistUuid": str(playlist),
            "onArtifactNotFound": "SKIP" if allow_missing else "FAIL",
            "onDupes": "ADD" if allow_duplicates else "SKIP",
        }
        headers = {"If-None-Match": self._etag} if self._etag else None
        res = self.request.request(
            "POST",
            self._base_url % self.id + "/items",
            data=data,
            headers=headers,
        )
        self._reparse()
        # Respond with the added item IDs:
        added_items = res.json().get("addedItemIds")
        if added_items:
            return added_items
        else:
            return []

    def add_by_isrc(
        self,
        isrc: str,
        allow_duplicates: bool = False,
        position: int = -1,
    ) -> bool:
        """Add an item to a playlist, using the track ISRC.

        :param isrc: The ISRC of the track to be added
        :param allow_duplicates: Allow adding duplicate items
        :param position: Insert items at a specific position.
            Default: insert at the end of the playlist
        :return: True, if successful.
        """
        if not isinstance(isrc, str):
            isrc = str(isrc)
        try:
            track = self.session.get_tracks_by_isrc(isrc)
            if track:
                # Add the first track in the list
                track_id = track[0].id
                added = self.add(
                    [str(track_id)],
                    allow_duplicates=allow_duplicates,
                    position=position,
                )
                if track_id in added:
                    return True
                else:
                    return False
            else:
                return False
        except ObjectNotFound:
            return False

    def move_by_id(self, media_id: str, position: int) -> bool:
        """Move an item to a new position, by media ID.

        :param media_id: The index of the item to be moved
        :param position: The new position of the item
        :return: True, if successful.
        """
        if not isinstance(media_id, str):
            media_id = str(media_id)
        track_ids = [str(track.id) for track in self.tracks()]
        try:
            index = track_ids.index(media_id)
            if index is not None and index < self.num_tracks:
                return self.move_by_indices([index], position)
        except ValueError:
            return False

    def move_by_index(self, index: int, position: int) -> bool:
        """Move a single item to a new position.

        :param index: The index of the item to be moved
        :param position: The new position/offset of the item
        :return: True, if successful.
        """
        if not isinstance(index, int):
            raise ValueError
        return self.move_by_indices([index], position)

    def move_by_indices(self, indices: Sequence[int], position: int) -> bool:
        """Move one or more items to a new position.

        :param indices: List containing indices to move.
        :param position: The new position/offset of the item(s)
        :return: True, if successful.
        """
        # Move item to a new position
        if position < 0 or position >= self.num_tracks:
            position = self.num_tracks
        data = {
            "toIndex": position,
        }
        headers = {"If-None-Match": self._etag} if self._etag else None
        track_index_string = ",".join([str(x) for x in indices])
        res = self.request.request(
            "POST",
            (self._base_url + "/items/%s") % (self.id, track_index_string),
            data=data,
            headers=headers,
        )
        self._reparse()
        return res.ok

    def remove_by_id(self, media_id: str) -> bool:
        """Remove a single item from the playlist, using the media ID.

        :param media_id: Media ID to remove.
        :return: True, if successful.
        """
        if not isinstance(media_id, str):
            media_id = str(media_id)
        track_ids = [str(track.id) for track in self.tracks()]
        try:
            index = track_ids.index(media_id)
            if index is not None and index < self.num_tracks:
                return self.remove_by_index(index)
        except ValueError:
            return False

    def remove_by_index(self, index: int) -> bool:
        """Remove a single item from the UserPlaylist, using item index.

        :param index: Media index to remove
        :return: True, if successful.
        """
        return self.remove_by_indices([index])

    def remove_by_indices(self, indices: Sequence[int]) -> bool:
        """Remove one or more items from the UserPlaylist, using list of indices.

        :param indices: List containing indices to remove.
        :return: True, if successful.
        """
        headers = {"If-None-Match": self._etag} if self._etag else None
        track_index_string = ",".join([str(x) for x in indices])
        res = self.request.request(
            "DELETE",
            (self._base_url + "/items/%s") % (self.id, track_index_string),
            headers=headers,
        )
        self._reparse()
        return res.ok

    def clear(self, chunk_size: int = 50) -> bool:
        """Clear UserPlaylist.

        :param chunk_size: Number of items to remove per request
        :return: True, if successful.
        """
        while self.num_tracks:
            indices = range(min(self.num_tracks, chunk_size))
            if not self.remove_by_indices(indices):
                return False
        return True

    def set_playlist_public(self):
        """Set UserPlaylist as Public.

        :return: True, if successful.
        """
        res = self.request.request(
            "PUT",
            base_url=self.session.config.api_v2_location,
            path=(self._base_url + "/set-public") % self.id,
        )
        self.public = True
        self._reparse()
        return res.ok

    def set_playlist_private(self):
        """Set UserPlaylist as Private.

        :return: True, if successful.
        """
        res = self.request.request(
            "PUT",
            base_url=self.session.config.api_v2_location,
            path=(self._base_url + "/set-private") % self.id,
        )
        self.public = False
        self._reparse()
        return res.ok

    def delete(self) -> bool:
        """Delete UserPlaylist.

        :return: True, if successful.
        """
        return self.request.request("DELETE", path="playlists/%s" % self.id).ok
