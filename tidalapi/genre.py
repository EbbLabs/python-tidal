# Copyright (C) 2023- The Tidalapi Developers
# Copyright (C) 2019-2020 morguldir
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
""""""

import copy
from typing import TYPE_CHECKING, Any, cast

from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.session import Session, TypeRelation


class Genre:
    name: str = ""
    path: str = ""
    playlists: bool = False
    artists: bool = False
    albums: bool = False
    tracks: bool = False
    videos: bool = False
    image: str = ""

    def __init__(self, session: "Session"):
        self.session = session
        self.requests = session.request

    def parse_genre(self, json_obj: JsonObj) -> "Genre":
        self.name = json_obj["name"]
        self.path = json_obj["path"]
        self.playlists = json_obj["hasPlaylists"]
        self.artists = json_obj["hasArtists"]
        self.albums = json_obj["hasAlbums"]
        self.tracks = json_obj["hasTracks"]
        self.videos = json_obj["hasVideos"]
        image_path = json_obj["image"].replace("-", "/")
        self.image = f"http://resources.wimpmusic.com/images/{image_path}/460x306.jpg"

        return copy.copy(self)

    def parse_genres(self, json_obj: list[JsonObj]) -> list["Genre"]:
        return list(map(self.parse_genre, json_obj))

    def get_genres(self) -> list["Genre"]:
        return self.parse_genres(self.requests.request("GET", "genres").json())

    def items(self, model: list[Any | None]) -> list[Any | None]:
        """Gets the current genre's items of the specified type :param model: The
        tidalapi model you want returned.

        See :class:`Genre`
        :return:
        """
        type_relations: TypeRelation = next(
            x for x in self.session.type_conversions if x.type == model
        )
        name = type_relations.identifier
        parse = type_relations.parse
        if getattr(self, name):
            location = f"genres/{self.path}/{name}"
            return cast(
                list[Any | None], self.requests.map_request(location, parse=parse)
            )
        raise TypeError(f"This genre does not contain {name}")
