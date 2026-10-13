# Copyright (C) 2023- The Tidalapi Developers
# Copyright (C) 2021-2022 morguldir
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
"""
Module for parsing TIDAL's pages format found at https://listen.tidal.com/v1/pages
"""

import copy
import logging
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    Union,
    cast,
)

from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.album import Album
    from tidalapi.artist import Artist
    from tidalapi.media import Track, Video
    from tidalapi.mix import Mix
    from tidalapi.playlist import Playlist, UserPlaylist
    from tidalapi.request import Requests
    from tidalapi.session import Session


PageCategories = Union[
    "Album",
    "PageLinks",
    "FeaturedItems",
    "ItemList",
    "TextBlock",
    "LinkList",
    "Mix",
]

AllCategories = Union["Artist", PageCategories]

PageCategoriesV2 = Union[
    "TrackList",
    "ShortcutList",
    "HorizontalList",
    "HorizontalListWithContext",
]

AllCategoriesV2 = Union[PageCategoriesV2]

log = logging.getLogger(__name__)


class Page:
    """
    A page from the https://listen.tidal.com/view/pages/ endpoint

    The :class:`categories` field will the most complete information
    However it is an iterable that goes through all the visible items on the page as well, in the natural reading order
    """

    title: str = ""
    categories: Optional[List[Union["AllCategories", "AllCategoriesV2"]]] = None
    _categories_iter: Optional[Iterator[Union["AllCategories", "AllCategoriesV2"]]] = (
        None
    )
    _items_iter: Optional[Iterator[Callable[..., Any]]] = None
    page_category: "PageCategory"
    page_category_v2: "PageCategoryV2"
    request: "Requests"

    def __init__(self, session: "Session", title: str):
        self.request = session.request
        self.categories = None
        self.title = title
        self.page_category = PageCategory(session)
        self.page_category_v2 = PageCategoryV2(session)

    def __iter__(self) -> "Page":
        if self.categories is None:
            raise AttributeError("No categories found")
        self._categories_iter = iter(self.categories)
        self._category = next(self._categories_iter)
        self._items_iter = iter(cast(List[Callable[..., Any]], self._category.items))
        return self

    def __next__(self) -> Callable[..., Any]:
        if self._items_iter is None:
            return StopIteration
        try:
            item = next(self._items_iter)
        except StopIteration:
            if self._categories_iter is None:
                raise AttributeError("No categories found")
            self._category = next(self._categories_iter)
            self._items_iter = iter(
                cast(List[Callable[..., Any]], self._category.items)
            )
            return self.__next__()
        return item

    def next(self) -> Callable[..., Any]:
        return self.__next__()

    def parse(self, json_obj: JsonObj) -> "Page":
        """Goes through everything in the page, and gets the title and adds all the rows
        to the categories field :param json_obj: The json to be parsed :return: A copy
        of the Page that you can use to browse all the items."""
        self.categories = []

        if json_obj.get("rows"):
            self.title = json_obj["title"]
            for row in json_obj["rows"]:
                page_item = self.page_category.parse(row["modules"][0])
                self.categories.append(page_item)
        else:
            for item in json_obj["items"]:
                page_item = self.page_category_v2.parse_item(item)
                self.categories.append(page_item)

        return copy.copy(self)

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> "Page":
        """Retrieve a page from the specified endpoint, overwrites the calling page.

        :param params: Parameter to retrieve the page with
        :param endpoint: The endpoint you want to retrieve
        :return: A copy of the new :class:`.Page` at the requested endpoint
        """
        url = endpoint

        if params is None:
            params = {}
        if "deviceType" not in params:
            params["deviceType"] = "BROWSER"

        json_obj = self.request.request("GET", url, params=params).json()
        return self.parse(json_obj)


@dataclass
class More:
    api_path: str
    title: str

    @classmethod
    def parse(cls, json_obj: JsonObj) -> Optional["More"]:
        show_more = json_obj.get("showMore")
        view_all = json_obj.get("viewAll")
        if show_more is not None:
            return cls(api_path=show_more["apiPath"], title=show_more["title"])
        elif view_all is not None:
            return cls(api_path=view_all, title=json_obj.get("title"))
        else:
            return None


class PageCategory:
    type = None
    title: Optional[str] = None
    description: Optional[str] = ""
    request: "Requests"
    _more: Optional[More] = None

    def __init__(self, session: "Session"):
        self.session = session
        self.request = session.request
        self.item_types: Dict[str, Callable[..., Any]] = {
            "ALBUM_LIST": self.session.parse_album,
            "ARTIST_LIST": self.session.parse_artist,
            "TRACK_LIST": self.session.parse_track,
            "PLAYLIST_LIST": self.session.parse_playlist,
            "VIDEO_LIST": self.session.parse_video,
            "MIX_LIST": self.session.parse_mix,
        }

    def parse(self, json_obj: JsonObj) -> AllCategories:
        result = None
        category_type = json_obj["type"]
        if category_type in ("PAGE_LINKS_CLOUD", "PAGE_LINKS"):
            category: PageCategories = PageLinks(self.session)
        elif category_type in ("FEATURED_PROMOTIONS", "MULTIPLE_TOP_PROMOTIONS"):
            category = FeaturedItems(self.session)
        elif category_type in self.item_types.keys():
            category = ItemList(self.session)
        elif category_type == "MIX_HEADER":
            return self.session.parse_mix(json_obj["mix"])
        elif category_type == "ARTIST_HEADER":
            result = self.session.parse_artist(json_obj["artist"])
            result.bio = json_obj["bio"]
            return ItemHeader(result)
        elif category_type == "ALBUM_HEADER":
            return ItemHeader(self.session.parse_album(json_obj["album"]))
        elif category_type == "HIGHLIGHT_MODULE":
            category = ItemList(self.session)
        elif category_type == "MIXED_TYPES_LIST":
            category = ItemList(self.session)
        elif category_type == "TEXT_BLOCK":
            category = TextBlock(self.session)
        elif category_type in ("ITEM_LIST_WITH_ROLES", "ALBUM_ITEMS"):
            category = ItemList(self.session)
        elif category_type == "ARTICLE_LIST":
            json_obj["items"] = json_obj["pagedList"]["items"]
            category = LinkList(self.session)
        elif category_type == "SOCIAL":
            json_obj["items"] = json_obj["socialProfiles"]
            category = LinkList(self.session)
        else:
            raise NotImplementedError(f"PageType {category_type} not implemented")

        return category.parse(json_obj)

    def show_more(self) -> Optional[Page]:
        """Get the full list of items on their own :class:`.Page` from a
        :class:`.PageCategory`

        :return: A :class:`.Page` more of the items in the category, None if there
            aren't any
        """
        api_path = self._more.api_path if self._more else None
        return (
            Page(self.session, self._more.title).get(api_path)
            if api_path and self._more
            else None
        )


class PageCategoryV2:
    """Base class for all V2 homepage page categories (e.g., TRACK_LIST, SHORTCUT_LIST).

    Handles shared fields and parsing logic, and automatically dispatches to the correct
    subclass based on the 'type' field in the JSON object.
    """

    # Registry mapping 'type' strings to subclass types
    _type_map: Dict[str, Type["PageCategoryV2"]] = {}

    # Common metadata fields for all category types
    type: Optional[str] = None
    module_id: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = ""
    _more: Optional["More"] = None

    def __init__(self, session: "Session"):
        """Store the shared session object and initialize common fields.

        Subclasses should implement their own `parse()` method but not override
        __init__.
        """
        self.session = session
        self.request = session.request

        # Common item parsers by type (can be used by subclasses like SimpleList)
        self.item_types: Dict[str, Callable[..., Any]] = {
            "PLAYLIST": self.session.parse_playlist,
            "VIDEO": self.session.parse_video,
            "TRACK": self.session.parse_track,
            "ARTIST": self.session.parse_artist,
            "ALBUM": self.session.parse_album,
            "MIX": self.session.parse_v2_mix,
        }

    @classmethod
    def register_subclass(cls, category_type: str):
        """Decorator to register subclasses in the _type_map.

        Usage:
        @PageCategoryV2.register_subclass("TRACK_LIST")
        class TrackList(PageCategoryV2):
            ...
        """

        def decorator(subclass):
            cls._type_map[category_type] = subclass
            subclass.category_type = category_type
            return subclass

        return decorator

    def parse_item(self, list_item: Dict) -> "PageCategoryV2":
        """Factory method that creates the correct subclass instance based on the 'type'
        field in item Dict, parses base fields, and then calls subclass parse()."""
        category_type = list_item.get("type")
        cls = self._type_map.get(category_type)
        if cls is None:
            raise NotImplementedError(f"Category {category_type} not implemented")
        instance = cls(self.session)
        instance._parse_base(list_item)
        instance.parse(list_item)
        return instance

    def _parse_base(self, list_item: Dict):
        """Parse fields common to all categories."""
        self.type = list_item.get("type")
        self.module_id = list_item.get("moduleId")
        self.title = list_item.get("title")
        self.subtitle = list_item.get("subtitle")
        self.description = list_item.get("description", self.title)
        self._more = More.parse(list_item)

    def parse(self, json_obj: JsonObj):
        """Subclasses implement this method to parse category-specific data."""
        raise NotImplementedError("Subclasses must implement parse()")

    def view_all(self) -> Optional[Page]:
        """View all items in a Get the full list of items on their own :class:`.Page`
        from a :class:`.PageCategory`

        :return: A :class:`.Page` more of the items in the category, None if there
            aren't any
        """
        api_path = self._more.api_path if self._more else None
        return self.session.view_all(api_path) if api_path and self._more else None


class SimpleList(PageCategoryV2):
    """A generic list of items (tracks, albums, playlists, etc.) using the shared
    self.item_types parser dictionary."""

    def __init__(self, session: "Session"):
        super().__init__(session)
        self.items: List[Any] = []

    def parse(self, json_obj: "JsonObj"):
        self.items = [
            self.get_item(item) for item in json_obj["items"] if item is not None
        ]
        return self

    def get_item(self, json_obj: "JsonObj") -> Any:
        item_type = json_obj.get("type")
        if item_type not in self.item_types:
            log.warning(f"Item type '{item_type}' not implemented")
            return None

        return self.item_types[item_type](json_obj["data"])


@PageCategoryV2.register_subclass("SHORTCUT_LIST")
class ShortcutList(SimpleList):
    """A list of "shortcut" links (typically small horizontally scrollable rows)."""


@PageCategoryV2.register_subclass("HORIZONTAL_LIST")
class HorizontalList(SimpleList):
    """A horizontal scrollable row of items."""


@PageCategoryV2.register_subclass("HORIZONTAL_LIST_WITH_CONTEXT")
class HorizontalListWithContext(HorizontalList):
    """A horizontal list of items with additional context."""


@PageCategoryV2.register_subclass("TRACK_LIST")
class TrackList(PageCategoryV2):
    """A category that represents a list of tracks, each one parsed with
    parse_track()."""

    def __init__(self, session: "Session"):
        super().__init__(session)
        self.items: List[Any] = []

    def parse(self, json_obj: "JsonObj"):
        self.items = [
            self.session.parse_track(item["data"]) for item in json_obj["items"]
        ]

        return self


class FeaturedItems(PageCategory):
    """Items that have been featured by TIDAL."""

    items: Optional[List["PageItem"]] = None

    def __init__(self, session: "Session"):
        super().__init__(session)

    def parse(self, json_obj: JsonObj) -> "FeaturedItems":
        self.items = []
        self.title = json_obj["title"]
        self.description = json_obj["description"]

        for item in json_obj["items"]:
            self.items.append(PageItem(self.session, item))

        return self


class PageLinks(PageCategory):
    """A list of :class:`.PageLink` to other parts of TIDAL."""

    items: Optional[List["PageLink"]] = None

    def parse(self, json_obj: JsonObj) -> "PageLinks":
        """Parse the list of links from TIDAL.

        :param json_obj: The json to be parsed
        :return: A copy of this page category containing the links in the items field
        """
        self._more = More.parse(json_obj)
        self.title = json_obj["title"]
        self.items = []
        for item in json_obj["pagedList"]["items"]:
            self.items.append(PageLink(self.session, item))

        return copy.copy(self)


class ItemList(PageCategory):
    """A list of items from TIDAL, can be a list of mixes, for example, or a list of
    playlists and mixes in some cases."""

    items: Optional[List[Any]] = None

    def parse(self, json_obj: JsonObj) -> "ItemList":
        """Parse a list of items on TIDAL from the pages endpoints.

        :param json_obj: The json from TIDAL to be parsed
        :return: A copy of the ItemList with a list of items
        """
        self._more = More.parse(json_obj)
        self.title = json_obj["title"]
        item_type = json_obj["type"]
        list_key = "pagedList"
        session: Optional["Session"] = None
        parse: Optional[Callable[..., Any]] = None

        if item_type in self.item_types.keys():
            parse = self.item_types[item_type]
        elif item_type == "HIGHLIGHT_MODULE":
            session = self.session
            # Unwrap subtitle, maybe add a field for it later
            json_obj[list_key] = {"items": [x["item"] for x in json_obj["highlights"]]}
        elif item_type in ("MIXED_TYPES_LIST", "ALBUM_ITEMS"):
            session = self.session
        elif item_type == "ITEM_LIST_WITH_ROLES":
            for item in json_obj[list_key]["items"]:
                item["item"]["artistRoles"] = item["roles"]
            session = self.session
        else:
            raise NotImplementedError("PageType {} not implemented".format(item_type))

        self.items = self.request.map_json(json_obj[list_key], parse, session)

        return copy.copy(self)


class PageLink:
    """A Link to another :class:`.Page` on TIDAL, Call get() to retrieve the Page."""

    title: str
    icon = None
    image_id = None

    def __init__(self, session: "Session", json_obj: JsonObj):
        self.session = session
        self.request = session.request
        self.title = json_obj["title"]
        self.icon = json_obj["icon"]
        self.api_path = cast(str, json_obj["apiPath"])
        self.image_id = json_obj["imageId"]

    def get(self) -> "Page":
        """Requests the linked page from TIDAL :return: A :class:`Page` at the
        api_path."""
        return cast(
            "Page",
            self.request.map_request(
                self.api_path,
                params={"deviceType": "DESKTOP"},
                parse=self.session.parse_page,
            ),
        )


class PageItem:
    """An Item from a :class:`.PageCategory` from the /pages endpoint, call get() to
    retrieve the actual item."""

    header: str = ""
    short_header: str = ""
    short_sub_header: str = ""
    image_id: str = ""
    type: str = ""
    artifact_id: str = ""
    text: str = ""
    featured: bool = False
    session: "Session"

    def __init__(self, session: "Session", json_obj: JsonObj):
        self.session = session
        self.request = session.request
        self.header = json_obj["header"]
        self.short_header = json_obj["shortHeader"]
        self.short_sub_header = json_obj["shortSubHeader"]
        self.image_id = json_obj["imageId"]
        self.type = json_obj["type"]
        self.artifact_id = json_obj["artifactId"]
        self.text = json_obj["text"]
        self.featured = bool(json_obj["featured"])

    def get(
        self,
    ) -> Union["Artist", "Playlist", "Track", "UserPlaylist", "Video", "Album"]:
        """Retrieve the PageItem with the artifact_id matching the type.

        :return: The fully parsed item, e.g. :class:`.Playlist`, :class:`.Video`,
            :class:`.Track`
        """
        if self.type == "PLAYLIST":
            return self.session.playlist(self.artifact_id)
        elif self.type == "VIDEO":
            return self.session.video(self.artifact_id)
        elif self.type == "TRACK":
            return self.session.track(self.artifact_id)
        elif self.type == "ARTIST":
            return self.session.artist(self.artifact_id)
        elif self.type == "ALBUM":
            return self.session.album(self.artifact_id)
        raise NotImplementedError(f"PageItem type {self.type} not implemented")


class TextBlock(object):
    """A block of text, with a named icon, which seems to be left up to the
    application."""

    text: str = ""
    icon: str = ""
    items: Optional[List[str]] = None

    def __init__(self, session: "Session"):
        self.session = session

    def parse(self, json_obj: JsonObj) -> "TextBlock":
        self.text = json_obj["text"]
        self.icon = json_obj["icon"]
        self.items = [self.text]

        return copy.copy(self)


class LinkList(PageCategory):
    """A list of items containing links, e.g. social links or articles."""

    items: Optional[List[Any]] = None
    title: Optional[str] = None
    description: Optional[str] = None

    def parse(self, json_obj: JsonObj) -> "LinkList":
        self.items = json_obj["items"]
        self.title = json_obj["title"]
        self.description = json_obj["description"]

        return copy.copy(self)


class ItemHeader(object):
    """Single item in a "category" of the page."""

    items: Optional[List[Any]] = None

    def __init__(self, item: Any):
        self.items = [item]
