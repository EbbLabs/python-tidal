# Copyright (C) 2023- The Tidalapi Developers
# Copyright (C) 2022 morguldir
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
"""A module containing functions relating to TIDAL mixes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Union

import dateutil.parser

from tidalapi.exceptions import ObjectNotFound, TooManyRequests
from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.media import Track, Video
    from tidalapi.session import Session


class MixType(Enum):
    """An enum to track all the different types of mixes."""

    welcome_mix = "WELCOME_MIX"
    video_daily = "VIDEO_DAILY_MIX"
    daily = "DAILY_MIX"
    discovery = "DISCOVERY_MIX"
    new_release = "NEW_RELEASE_MIX"
    track = "TRACK_MIX"
    artist = "ARTIST_MIX"
    songwriter = "SONGWRITER_MIX"
    producter = "PRODUCER_MIX"
    history_alltime = "HISTORY_ALLTIME_MIX"
    history_monthly = "HISTORY_MONTHLY_MIX"
    history_yearly = "HISTORY_YEARLY_MIX"


@dataclass
class ImageResponse:
    small: str
    medium: str
    large: str


class Mix:
    """A mix from TIDAL, e.g. the listen.tidal.com/view/pages/my_collection_my_mixes.

    These get used for many things, like artist/track radio's, recommendations, and
    historical plays
    """

    id: str = ""
    title: str = ""
    sub_title: str = ""
    sharing_images = None
    mix_type: Optional[MixType] = None
    content_behaviour: str = ""
    short_subtitle: str = ""
    images: Optional[ImageResponse] = None
    _retrieved = False
    _items: Optional[List[Union["Video", "Track"]]] = None

    def __init__(self, session: Session, mix_id: Optional[str]):
        self.session = session
        self.request = session.request
        if mix_id is not None:
            self.get(mix_id)

    def get(self, mix_id: Optional[str] = None) -> "Mix":
        """Returns information about a mix, and also replaces the mix object used to
        call this function.

        :param mix_id: TIDAL's identifier of the mix
        :return: A :class:`Mix` object containing all the information about the mix
        """
        if mix_id is None:
            mix_id = self.id

        params = {"mixId": mix_id, "deviceType": "BROWSER"}

        try:
            request = self.request.request("GET", "pages/mix", params=params)
        except ObjectNotFound as e:
            e.args = ("Mix with id %s not found" % mix_id,)
            raise e
        except TooManyRequests as e:
            e.args = ("Mix unavailable",)
            raise e
        else:
            result = self.session.parse_page(request.json())
            assert not isinstance(result, list)
            if len(result.categories) <= 1:
                # An empty page with no mixes was returned. Assume that the selected mix was not available
                raise ObjectNotFound("Mix not found")
            else:
                self._retrieved = True
                self.__dict__.update(result.categories[0].__dict__)
                self._items = result.categories[1].items
                return self

    def parse(self, json_obj: JsonObj) -> "Mix":
        """Parse a mix into a :class:`Mix`, replaces the calling object.

        :param json_obj: The json of a mix to be parsed
        :return: A copy of the parsed mix
        """
        self.id = json_obj["id"]
        self.title = json_obj["title"]
        self.sub_title = json_obj["subTitle"]
        self.sharing_images = json_obj["sharingImages"]
        self.mix_type = MixType(json_obj["mixType"])
        self.content_behaviour = json_obj["contentBehavior"]
        self.short_subtitle = json_obj["shortSubtitle"]
        images = json_obj["images"]
        self.images = ImageResponse(
            small=images["SMALL"]["url"],
            medium=images["MEDIUM"]["url"],
            large=images["LARGE"]["url"],
        )

        return copy.copy(self)

    def items(self) -> List[Union["Video", "Track"]]:
        """Returns all the items in the mix, retrieves them with :class:`get` as well if
        not already done.

        :return: A :class:`list` of videos and/or tracks from the mix
        """
        if not self._retrieved:
            self.get(self.id)
        if not self._items:
            raise ValueError("Retrieved items missing")
        return self._items

    def image(self, dimensions: int = 320) -> str:
        """A URL to a Mix picture.

        :param dimensions: The width and height the requested image should be
        :type dimensions: int
        :return: A url to the image

        Original sizes: 320x320, 640x640, 1500x1500
        """
        if not self.images:
            raise ValueError("No images present.")

        if dimensions == 320:
            return self.images.small
        elif dimensions == 640:
            return self.images.medium
        elif dimensions == 1500:
            return self.images.large

        raise ValueError(f"Invalid resolution {dimensions} x {dimensions}")


@dataclass
class TextInfo:
    text: str
    color: str


class MixV2:
    """A mix from TIDALs v2 api endpoint."""

    mix_type: Optional[MixType] = None
    country_code: Optional[str] = None
    date_added: Optional[datetime] = None
    id: Optional[str] = None
    artifact_id_type: Optional[str] = None
    content_behavior: Optional[str] = None
    images: Optional[ImageResponse] = None
    detail_images: Optional[ImageResponse] = None
    master = False
    is_stable_id = False
    title: Optional[str] = None
    sub_title: Optional[str] = None
    short_subtitle: Optional[str] = None
    title_text_info: Optional[TextInfo] = None
    sub_title_text_info: Optional[TextInfo] = None
    short_subtitle_text_info: Optional[TextInfo] = None
    updated: Optional[datetime] = None
    _retrieved = False
    _items: Optional[List[Union["Video", "Track"]]] = None

    def __init__(self, session: Session, mix_id: str):
        self.session = session
        self.request = session.request
        if mix_id is not None:
            self.get(mix_id)

    def get(self, mix_id: Optional[str] = None) -> "MixV2":
        """Returns information about a mix, and also replaces the mix object used to
        call this function.

        :param mix_id: TIDAL's identifier of the mix
        :return: A :class:`Mix` object containing all the information about the mix
        """
        if mix_id is None:
            mix_id = self.id

        params = {"mixId": mix_id, "deviceType": "BROWSER"}
        try:
            request = self.request.request("GET", "pages/mix", params=params)
        except ObjectNotFound as e:
            e.args = ("Mix with id %s not found" % mix_id,)
            raise e
        except TooManyRequests as e:
            e.args = ("Mix unavailable",)
            raise e
        else:
            result = self.session.parse_page(request.json())
            assert not isinstance(result, list)

            if len(result.categories) <= 1:
                # An empty page with no mixes was returned. Assume that the selected mix was not available
                raise ObjectNotFound("Mix not found")
            else:
                self._retrieved = True
                self.__dict__.update(result.categories[0].__dict__)
                self._items = result.categories[1].items
                return self

    def parse(self, json_obj: JsonObj) -> "MixV2":
        """Parse a mix into a :class:`MixV2`, replaces the calling object.

        :param json_obj: The json of a mix to be parsed
        :return: A copy of the parsed mix
        """

        self.id = json_obj["id"]
        if json_obj.get("mixType"):
            date_added = json_obj.get("dateAdded")
            self.date_added = (
                dateutil.parser.isoparse(date_added) if date_added else None
            )
            self.title = json_obj["title"]
            self.sub_title = json_obj["subTitle"]
            images = json_obj["images"]
            self.images = ImageResponse(
                small=images["SMALL"]["url"],
                medium=images["MEDIUM"]["url"],
                large=images["LARGE"]["url"],
            )
            detail_images = json_obj["detailImages"]
            self.detail_images = ImageResponse(
                small=detail_images["SMALL"]["url"],
                medium=detail_images["MEDIUM"]["url"],
                large=detail_images["LARGE"]["url"],
            )
            self.master = json_obj["master"]
            title_text_info = json_obj["titleTextInfo"]
            self.title_text_info = TextInfo(
                text=title_text_info["text"],
                color=title_text_info["color"],
            )
            sub_title_text_info = json_obj["subTitleTextInfo"]
            self.sub_title_text_info = TextInfo(
                text=sub_title_text_info["text"],
                color=sub_title_text_info["color"],
            )
            updated = json_obj.get("updated")
            self.updated = dateutil.parser.isoparse(updated) if updated else None
        elif json_obj.get("type"):
            # Certain mix types (e.g. when returned from Page) must be parsed differently. Why, TIDAL?
            self.country_code = json_obj.get("countryCode", None)
            self.is_stable_id = json_obj.get("isStableId", False)
            self.artifact_id_type = json_obj.get("trackGroupId", None)
            self.content_behavior = json_obj.get("contentBehavior", None)

            images = json_obj["mixImages"]
            self.images = ImageResponse(
                small=images[0]["url"],
                medium=images[1]["url"],
                large=images[0]["url"],
            )

            detail_images = json_obj["detailMixImages"]
            self.detail_images = ImageResponse(
                small=detail_images[0]["url"],
                medium=detail_images[1]["url"],
                large=detail_images[2]["url"],
            )

            title_text_info = json_obj["titleTextInfo"]
            self.title_text_info = TextInfo(
                text=title_text_info["text"],
                color=title_text_info["color"],
            )
            self.title = title_text_info["text"]

            sub_title_text_info = json_obj["subtitleTextInfo"]
            self.sub_title_text_info = TextInfo(
                text=sub_title_text_info["text"],
                color=sub_title_text_info["color"],
            )
            self.sub_title = sub_title_text_info["text"]

            short_subtitle_text_info = json_obj["shortSubtitleTextInfo"]
            self.short_subtitle_text_info = TextInfo(
                text=sub_title_text_info["text"],
                color=sub_title_text_info["color"],
            )
            self.short_subtitle = short_subtitle_text_info["text"]

            if json_obj.get("updated"):
                self.updated = datetime.fromtimestamp(json_obj["updated"] / 1000)

        return copy.copy(self)

    def image(self, dimensions: int = 320) -> str:
        """A URL to a Mix picture.

        :param dimensions: The width and height the requested image should be
        :type dimensions: int
        :return: A url to the image

        Original sizes: 320x320, 640x640, 1500x1500
        """
        if not self.images:
            raise ValueError("No images present.")

        if dimensions == 320:
            return self.images.small
        elif dimensions == 640:
            return self.images.medium
        elif dimensions == 1500:
            return self.images.large

        raise ValueError(f"Invalid resolution {dimensions} x {dimensions}")
