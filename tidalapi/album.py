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

import copy
import functools
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Union, cast

import dateutil.parser

from tidalapi.exceptions import MetadataNotAvailable, ObjectNotFound, TooManyRequests
from tidalapi.types import JsonObj

if TYPE_CHECKING:
    from tidalapi.artist import Artist
    from tidalapi.media import Track, Video
    from tidalapi.page import Page
    from tidalapi.session import Session


DEFAULT_ALBUM_IMG = "0dfd3368-3aa1-49a3-935f-10ffb39803c0"


class Album:
    """Contains information about a TIDAL album.

    If the album is created from a media object, this object will only contain the id,
    name, cover and video cover. TIDAL does this to reduce the network load.
    """

    id: Optional[int] = -1
    name: Optional[str] = None
    cover = None
    video_cover = None
    type = None

    duration: Optional[int] = -1
    available: Optional[bool] = False
    ad_supported_ready: Optional[bool] = False
    dj_ready: Optional[bool] = False
    allow_streaming: Optional[bool] = False
    premium_streaming_only: Optional[bool] = False
    num_tracks: Optional[int] = -1
    num_videos: Optional[int] = -1
    num_volumes: Optional[int] = -1
    tidal_release_date: Optional[datetime] = None
    release_date: Optional[datetime] = None
    copyright = None
    upc = None
    version = None
    explicit: Optional[bool] = True
    universal_product_number: Optional[int] = -1
    popularity: Optional[int] = -1
    user_date_added: Optional[datetime] = None
    audio_quality: Optional[str] = ""
    audio_modes: Optional[List[str]] = [""]
    media_metadata_tags: Optional[List[str]] = [""]

    artist: Optional["Artist"] = None
    artists: Optional[List["Artist"]] = None

    # Direct URL to https://listen.tidal.com/album/<album_id>
    listen_url: str = ""
    # Direct URL to https://tidal.com/browse/album/<album_id>
    share_url: str = ""

    def __init__(self, session: "Session", album_id: Optional[str]):
        self.session = session
        self.request = session.request
        self.artist = session.artist()
        self.id = album_id

        if self.id:
            try:
                request = self.request.request("GET", "albums/%s" % self.id)
            except ObjectNotFound as e:
                e.args = ("Album with id %s not found" % self.id,)
                raise e
            except TooManyRequests as e:
                e.args = ("Album unavailable",)
                raise e
            else:
                self.request.map_json(request.json(), parse=self.parse)

    def parse(
        self,
        json_obj: JsonObj,
        artist: Optional["Artist"] = None,
        artists: Optional[List["Artist"]] = None,
    ) -> "Album":
        if artists is None:
            artists = self.session.parse_artists(json_obj["artists"])

        # Sometimes the artist field is not filled, an example is 140196345
        if "artist" not in json_obj:
            artist = artists[0]
        elif artist is None:
            artist = self.session.parse_artist(json_obj["artist"])

        self.id = json_obj["id"]
        self.name = json_obj["title"]
        self.cover = json_obj["cover"]
        self.video_cover = json_obj["videoCover"]
        self.duration = json_obj.get("duration")
        self.available = json_obj.get("streamReady")
        self.ad_supported_ready = json_obj.get("adSupportedStreamReady")
        self.dj_ready = json_obj.get("djReady")
        self.allow_streaming = json_obj.get("allowStreaming")
        self.premium_streaming_only = json_obj.get("premiumStreamingOnly")
        self.num_tracks = json_obj.get("numberOfTracks")
        self.num_videos = json_obj.get("numberOfVideos")
        self.num_volumes = json_obj.get("numberOfVolumes")
        self.copyright = json_obj.get("copyright")
        self.upc = json_obj.get("upc")
        self.version = json_obj.get("version")
        self.explicit = json_obj.get("explicit")
        self.universal_product_number = json_obj.get("upc")
        self.popularity = json_obj.get("popularity")
        self.type = json_obj.get("type")

        # Certain fields may not be available
        self.audio_quality = json_obj.get("audioQuality")
        self.audio_modes = json_obj.get("audioModes")

        if "mediaMetadata" in json_obj:
            self.media_metadata_tags = json_obj.get("mediaMetadata")["tags"]

        self.artist = artist
        self.artists = artists

        release_date = json_obj.get("releaseDate")
        self.release_date = (
            dateutil.parser.isoparse(release_date) if release_date else None
        )

        tidal_release_date = json_obj.get("streamStartDate")
        self.tidal_release_date = (
            dateutil.parser.isoparse(tidal_release_date) if tidal_release_date else None
        )

        user_date_added = json_obj.get("dateAdded")
        self.user_date_added = (
            dateutil.parser.isoparse(user_date_added) if user_date_added else None
        )
        self.listen_url = f"{self.session.config.listen_base_url}/album/{self.id}"
        self.share_url = f"{self.session.config.share_base_url}/album/{self.id}"

        return copy.copy(self)

    @property
    def year(self) -> Optional[int]:
        """Get the year using :class:`available_release_date`

        :return: An :any:`python:int` containing the year the track was released
        """
        return self.available_release_date.year if self.available_release_date else None

    @property
    def available_release_date(self) -> Optional[datetime]:
        """Get the release date if it's available, otherwise get the day it was released
        on TIDAL.

        :return: A :any:`python:datetime.datetime` object with the release date, or the
            tidal release date, can be None
        """
        if self.release_date:
            return self.release_date
        if self.tidal_release_date:
            return self.tidal_release_date
        return None

    def tracks(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        sparse_album: bool = False,
    ) -> List["Track"]:
        """Returns the tracks in classes album.

        :param limit: The amount of items you want returned.
        :param offset: The position of the first item you want to include.
        :param sparse_album: Provide a sparse track.album, containing only essential attributes from track JSON
            False: Populate the track.album attributes from the parent Album object (self)
        :return: A list of the :class:`Tracks <.Track>` in the album.
        """
        params = {"limit": limit, "offset": offset}

        if sparse_album:
            parse_track_callable = self.session.parse_track
        else:
            # Parse tracks attributes but provide the Album object directly from self
            parse_track_callable = functools.partial(
                self.session.parse_track, album=self
            )

        tracks = self.request.map_request(
            "albums/%s/tracks" % self.id, params, parse=parse_track_callable
        )
        assert isinstance(tracks, list)
        return cast(List["Track"], tracks)

    def items(
        self, limit: int = 100, offset: int = 0, sparse_album: bool = False
    ) -> List[Union["Track", "Video"]]:
        """Gets the first 'limit' tracks and videos in the album from TIDAL.

        :param limit: The number of items you want to retrieve
        :param offset: The index you want to start retrieving items from
        :param sparse_album: Provide a sparse track.album, containing only essential attributes from track JSON
            False: Populate the track.album attributes from the parent Album object (self)
        :return: A list of :class:`Tracks<.Track>` and :class:`Videos`<.Video>`
        """
        params = {"offset": offset, "limit": limit}

        if sparse_album:
            parse_media_callable = self.session.parse_media
        else:
            # Parse tracks attributes but provide the Album object directly from self
            parse_media_callable = functools.partial(
                self.session.parse_media, album=self
            )

        items = self.request.map_request(
            "albums/%s/items" % self.id, params=params, parse=parse_media_callable
        )
        assert isinstance(items, list)
        return cast(List[Union["Track", "Video"]], items)

    def image(
        self, dimensions: Union[int, str] = 320, default: str = DEFAULT_ALBUM_IMG
    ) -> str:
        """A url to an album image cover.

        :param dimensions: The width and height of the album image. If "origin", the original resolution will be used
        :param default: An optional default image to serve if one is not available
        :return: A url to the image.

        Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280, 3000x3000 (origin)
        """

        if dimensions not in [80, 160, 320, 640, 1280, "origin"]:
            raise ValueError("Invalid resolution {0} x {0}".format(dimensions))

        if dimensions == "origin":
            if not self.cover:
                return self.session.config.image_url_origin % (
                    default.replace("-", "/")
                )
            else:
                return self.session.config.image_url_origin % (
                    self.cover.replace("-", "/")
                )
        else:
            if not self.cover:
                return self.session.config.image_url % (
                    default.replace("-", "/"),
                    dimensions,
                    dimensions,
                )
            else:
                return self.session.config.image_url % (
                    self.cover.replace("-", "/"),
                    dimensions,
                    dimensions,
                )

    def video(self, dimensions: Union[int, str] = 320) -> str:
        """Creates a url to an mp4 video cover for the album.

        Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280

        :param dimensions: The width and height of the album video. If "origin", the original resolution will be used
        :type dimensions: int
        :return: A url to an mp4 of the video cover.
        """
        if not self.video_cover:
            raise AttributeError("This album does not have a video cover.")

        if dimensions not in [80, 160, 320, 640, 1280, "origin"]:
            raise ValueError("Invalid resolution {0} x {0}".format(dimensions))

        if dimensions == "origin":
            return self.session.config.video_url_origin % (
                self.video_cover.replace("-", "/")
            )
        else:
            return self.session.config.video_url % (
                self.video_cover.replace("-", "/"),
                dimensions,
                dimensions,
            )

    def page(self) -> "Page":
        """
        Retrieve the album page as seen on https://listen.tidal.com/album/$id

        :return: A :class:`Page` containing the different categories, e.g. similar artists and albums
        """
        return self.session.page.get("pages/album", params={"albumId": self.id})

    def similar(self) -> List["Album"]:
        """Retrieve albums similar to the current one. MetadataNotAvailable is raised,
        when no similar albums exist.

        :return: A :any:`list` of similar albums
        """
        try:
            request = self.request.request("GET", "albums/%s/similar" % self.id)
        except ObjectNotFound:
            raise MetadataNotAvailable("No similar albums exist for this album")
        except TooManyRequests as e:
            e.args = ("Similar artists unavailable",)
            raise e
        else:
            albums = self.request.map_json(
                request.json(), parse=self.session.parse_album
            )
            assert isinstance(albums, list)
            return cast(List["Album"], albums)

    def review(self) -> str:
        """Retrieve the album review.

        :return: A :class:`str` containing the album review, with wimp links
        :raises: :class:`requests.HTTPError` if there isn't a review yet
        """
        review = self.request.request("GET", "albums/%s/review" % self.id).json()[
            "text"
        ]
        assert isinstance(review, str)
        return review

    def get_audio_resolution(self, individual_tracks: bool = False) -> [[int, int]]:
        """Retrieve the audio resolution (bit rate + sample rate) for the album track(s)

        This function assumes that all album tracks use the same audio resolution.
        Some albums may consist of tracks with multiple audio resolution(s).
        The audio resolution can therefore be fetched for individual tracks by setting the `all_tracks` argument accordingly.

        WARNING: For individual tracks, many additional requests are needed. Handle with care!

        :param individual_tracks: Fetch individual track resolutions
        :type individual_tracks: bool
        :return: A :class:`tuple` containing the (bit_rate, sample_rate) for one or more tracks
        """
        if individual_tracks:
            # Return for individual tracks
            return [res.get_stream().get_audio_resolution() for res in self.tracks()]
        else:
            # Return for first track only
            return [self.tracks()[0].get_stream().get_audio_resolution()]
