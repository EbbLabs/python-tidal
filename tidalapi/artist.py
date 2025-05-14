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
"""A module containing information and functions related to TIDAL artists."""

import copy
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Mapping, Optional, Union, cast
from warnings import warn

import dateutil.parser
from typing_extensions import NoReturn

from tidalapi.exceptions import ObjectNotFound, TooManyRequests
from tidalapi.types import JsonObj

from . import mix

if TYPE_CHECKING:
    from tidalapi.album import Album
    from tidalapi.media import Track, Video
    from tidalapi.page import Page
    from tidalapi.session import Session

DEFAULT_ARTIST_IMG = "1e01cdb6-f15d-4d8b-8440-a047976c1cac"


class Artist:
    id: Optional[int] = -1
    name: Optional[str] = None
    roles: Optional[List["Role"]] = None
    role: Optional["Role"] = None
    picture: Optional[str] = None
    user_date_added: Optional[datetime] = None
    bio: Optional[str] = None

    # Direct URL to https://listen.tidal.com/artist/<artist_id>
    listen_url: str = ""
    # Direct URL to https://tidal.com/browse/artist/<artist_id>
    share_url: str = ""

    def __init__(self, session: "Session", artist_id: Optional[str]):
        """Initialize the :class:`Artist` object, given a TIDAL artist ID :param
        session: The current TIDAL :class:`Session` :param str artist_id: TIDAL artist
        ID :raises: Raises :class:`exceptions.ObjectNotFound`"""
        self.session = session
        self.request = self.session.request
        self.id = artist_id

        if self.id:
            try:
                request = self.request.request("GET", "artists/%s" % self.id)
            except ObjectNotFound:
                raise ObjectNotFound("Artist not found")
            except TooManyRequests:
                raise TooManyRequests("Artist unavailable")
            else:
                self.request.map_json(request.json(), parse=self.parse_artist)

    def parse_artist(self, json_obj: JsonObj) -> "Artist":
        """Parses a TIDAL artist, replaces the current :class:`Artist` object. Made for
        use within the python tidalapi module.

        :param json_obj: :class:`JsonObj` containing the artist metadata
        :return: Returns a copy of the :class:`Artist` object
        """
        self.id = json_obj["id"]
        self.name = json_obj["name"]

        # Artists do not have roles as playlist creators.
        self.roles = None
        self.role = None
        if json_obj.get("type") or json_obj.get("artistTypes"):
            roles: List["Role"] = []
            for role in json_obj.get("artistTypes", [json_obj.get("type")]):
                roles.append(Role(role))

            self.roles = roles
            self.role = roles[0]

        # Get artist picture or use default
        self.picture = json_obj.get("picture")
        if self.picture is None:
            self.picture = DEFAULT_ARTIST_IMG

        user_date_added = json_obj.get("dateAdded")
        self.user_date_added = (
            dateutil.parser.isoparse(user_date_added) if user_date_added else None
        )

        self.listen_url = f"{self.session.config.listen_base_url}/artist/{self.id}"
        self.share_url = f"{self.session.config.share_base_url}/artist/{self.id}"

        return copy.copy(self)

    def parse_artists(self, json_obj: List[JsonObj]) -> List["Artist"]:
        """Parses a list of TIDAL artists, returns a list of :class:`Artist` objects
        Made for use within the python tidalapi module.

        :param List[JsonObj] json_obj: List of :class:`JsonObj` containing the artist metadata for each artist
        :return: Returns a list of :class:`Artist` objects
        """
        return list(map(self.parse_artist, json_obj))

    def _get_albums(
        self, params: Optional[Mapping[str, Union[int, str, None]]] = None
    ) -> List["Album"]:
        return cast(
            List["Album"],
            self.request.map_request(
                f"artists/{self.id}/albums", params, parse=self.session.parse_album
            ),
        )

    def get_albums(self, limit: Optional[int] = None, offset: int = 0) -> List["Album"]:
        """Queries TIDAL for the artists albums.

        :return: A list of :class:`Albums<tidalapi.album.Album>`
        """
        params = {"limit": limit, "offset": offset}
        return self._get_albums(params)

    def get_albums_ep_singles(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List["Album"]:
        warn(
            "This method is deprecated an will be removed in a future release. Use instead `get_ep_singles`",
            DeprecationWarning,
            stacklevel=2,
        )

        return self.get_ep_singles(limit=limit, offset=offset)

    def get_ep_singles(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List["Album"]:
        """Queries TIDAL for the artists extended plays and singles.

        :return: A list of :class:`Albums <tidalapi.album.Album>`
        """
        params = {"filter": "EPSANDSINGLES", "limit": limit, "offset": offset}
        return self._get_albums(params)

    def get_albums_other(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List["Album"]:
        warn(
            "This method is deprecated an will be removed in a future release. Use instead `get_other`",
            DeprecationWarning,
            stacklevel=2,
        )

        return self.get_other(limit=limit, offset=offset)

    def get_other(self, limit: Optional[int] = None, offset: int = 0) -> List["Album"]:
        """Queries TIDAL for albums the artist has appeared on as a featured artist.

        :return: A list of :class:`Albums <tidalapi.album.Album>`
        """
        params = {"filter": "COMPILATIONS", "limit": limit, "offset": offset}
        return self._get_albums(params)

    def get_top_tracks(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List["Track"]:
        """Queries TIDAL for the artists tracks, sorted by popularity.

        :return: A list of :class:`Tracks <tidalapi.media.Track>`
        """
        params = {"limit": limit, "offset": offset}
        return cast(
            List["Track"],
            self.request.map_request(
                f"artists/{self.id}/toptracks",
                params=params,
                parse=self.session.parse_track,
            ),
        )

    def get_videos(self, limit: Optional[int] = None, offset: int = 0) -> List["Video"]:
        """Queries tidal for the artists videos.

        :return: A list of :class:`Videos <tidalapi.media.Video>`
        """
        params = {"limit": limit, "offset": offset}
        return cast(
            List["Video"],
            self.request.map_request(
                f"artists/{self.id}/videos",
                params=params,
                parse=self.session.parse_video,
            ),
        )

    def get_bio(self) -> str:
        """Queries TIDAL for the artists biography.

        :return: A string containing the bio, as well as identifiers to other TIDAL
            objects inside the bio.
        """
        return cast(
            str, self.request.request("GET", f"artists/{self.id}/bio").json()["text"]
        )

    def get_similar(self) -> List["Artist"]:
        """Queries TIDAL for similar artists.

        :return: A list of :class:`Artists <tidalapi.artist.Artist>`
        """
        return cast(
            List["Artist"],
            self.request.map_request(
                f"artists/{self.id}/similar", parse=self.session.parse_artist
            ),
        )

    def get_radio(self) -> List["Track"]:
        """Queries TIDAL for the artist radio, which is a mix of tracks that are similar
        to what the artist makes.

        :return: A list of :class:`Tracks <tidalapi.media.Track>`
        """
        params = {"limit": 100}
        return cast(
            List["Track"],
            self.request.map_request(
                f"artists/{self.id}/radio",
                params=params,
                parse=self.session.parse_track,
            ),
        )

    def get_radio_mix(self) -> mix.Mix:
        """Queries TIDAL for the artist radio, which is a mix of tracks that are similar
        to what the artist makes.

        :return: A :class:`Mix <tidalapi.mix.Mix>`
        """
        json = self.request.request("GET", f"artists/{self.id}/mix").json()

        return self.session.mix(json.get("id"))

    def items(self) -> List[NoReturn]:
        """The artist page does not supply any items. This only exists for symmetry with
        other model types.

        :return: An empty list.
        """
        return []

    def image(self, dimensions: int = 320) -> str:
        """A url to an artist picture.

        :param dimensions: The width and height that you want from the image
        :type dimensions: int
        :return: A url to the image.

        Valid resolutions: 160x160, 320x320, 480x480, 750x750
        """
        if dimensions not in [160, 320, 480, 750]:
            raise ValueError("Invalid resolution {0} x {0}".format(dimensions))

        if not self.picture:
            json = self.request.request("GET", f"artists/{self.id}").json()
            self.picture = json.get("picture")
            if not self.picture:
                raise ValueError("No image available")

        return self.session.config.image_url % (
            self.picture.replace("-", "/"),
            dimensions,
            dimensions,
        )

    def page(self) -> "Page":
        """
        Retrieve the artist page as seen on https://listen.tidal.com/artist/$id

        :return: A :class:`.Page` containing all the categories from the page, e.g. tracks, influencers and credits
        """
        return self.session.page.get("pages/artist", params={"artistId": self.id})


class Role(Enum):
    """An Enum with different roles an artist can have."""

    main = "MAIN"
    featured = "FEATURED"
    contributor = "CONTRIBUTOR"
    artist = "ARTIST"
