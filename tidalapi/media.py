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
"""A module containing information about various media types.

Classes: :class:`Media`, :class:`Track`, :class:`Video`
"""

from __future__ import annotations

import copy
from abc import abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Union, cast

import dateutil.parser

if TYPE_CHECKING:
    import tidalapi

import base64
import json

from isodate import parse_duration
from mpegdash.parser import MPEGDASHParser

from tidalapi.album import Album
from tidalapi.exceptions import (
    ManifestDecodeError,
    MetadataNotAvailable,
    MPDNotAvailableError,
    ObjectNotFound,
    StreamNotAvailable,
    TooManyRequests,
    UnknownManifestFormat,
    URLNotAvailable,
)
from tidalapi.types import JsonObj

from . import mix


class Quality(str, Enum):
    low_96k: str = "LOW"
    low_320k: str = "HIGH"
    high_lossless: str = "LOSSLESS"
    hi_res_lossless: str = "HI_RES_LOSSLESS"
    default: str = low_320k

    def __str__(self) -> str:
        return self.value


class VideoQuality(str, Enum):
    high: str = "HIGH"
    medium: str = "MEDIUM"
    low: str = "LOW"
    audio_only: str = "AUDIO_ONLY"
    default: str = high

    def __str__(self) -> str:
        return self.value


class AudioMode(str, Enum):
    stereo: str = "STEREO"
    dolby_atmos: str = "DOLBY_ATMOS"

    def __str__(self) -> str:
        return self.value


class MediaMetadataTags(str, Enum):
    hi_res_lossless: str = "HIRES_LOSSLESS"
    lossless: str = "LOSSLESS"
    dolby_atmos: str = "DOLBY_ATMOS"

    def __str__(self) -> str:
        return self.value


class AudioExtensions(str, Enum):
    FLAC: str = ".flac"
    M4A: str = ".m4a"
    MP4: str = ".mp4"

    def __str__(self) -> str:
        return self.value


class VideoExtensions(str, Enum):
    TS: str = ".ts"

    def __str__(self) -> str:
        return self.value


class ManifestMimeType(str, Enum):
    # EMU: str = "application/vnd.tidal.emu"
    # APPL: str = "application/vnd.apple.mpegurl"
    MPD: str = "application/dash+xml"
    BTS: str = "application/vnd.tidal.bts"
    VIDEO: str = "video/mp2t"

    def __str__(self) -> str:
        return self.value


class Codec(str, Enum):
    MP3: str = "MP3"
    AAC: str = "AAC"
    MP4A: str = "MP4A"
    FLAC: str = "FLAC"
    Atmos: str = "EAC3"
    AC4: str = "AC4"
    LowResCodecs: [str] = [MP3, AAC, MP4A]
    PremiumCodecs: [str] = [Atmos, AC4]
    HQCodecs: [str] = PremiumCodecs + [FLAC]

    def __str__(self) -> str:
        return self.value


class MimeType(str, Enum):
    audio_mpeg = "audio/mpeg"
    audio_mp3 = "audio/mp3"
    audio_mp4 = "audio/mp4"
    audio_m4a = "audio/m4a"
    audio_flac = "audio/flac"
    audio_xflac = "audio/x-flac"
    audio_eac3 = "audio/eac3"
    audio_ac4 = "audio/mp4"
    audio_m3u8 = "audio/mpegurl"
    video_mp4 = "video/mp4"
    video_m3u8 = "video/mpegurl"
    audio_map = {
        Codec.MP3: audio_mp3,
        Codec.AAC: audio_m4a,
        Codec.MP4A: audio_m4a,
        Codec.FLAC: audio_xflac,
        Codec.Atmos: audio_eac3,
        Codec.AC4: audio_ac4,
    }

    def __str__(self) -> str:
        return self.value

    @staticmethod
    def from_audio_codec(codec):
        return MimeType.audio_map.get(codec, MimeType.audio_m4a)

    @staticmethod
    def is_flac(mime_type):
        return (
            True if mime_type in [MimeType.audio_flac, MimeType.audio_xflac] else False
        )


class Media:
    """Base class for generic media, specifically :class:`Track` and :class:`Video`

    This class includes data used by both of the subclasses, and a function to parse
    both of them.

    The date_added attribute is only relevant for playlists. For the release date of the
    actual media, use the release date of the album.
    """

    id: Optional[int] = -1
    name: Optional[str] = None
    duration: Optional[int] = -1
    available: bool = True
    tidal_release_date: Optional[datetime] = None
    user_date_added: Optional[datetime] = None
    track_num: int = -1
    volume_num: int = 1
    explicit: bool = False
    popularity: int = -1
    artist: Optional["tidalapi.artist.Artist"] = None
    #: For the artist credit page
    artist_roles = None
    artists: Optional[List["tidalapi.artist.Artist"]] = None
    album: Optional["tidalapi.album.Album"] = None
    type: Optional[str] = None
    # Direct URL to media https://listen.tidal.com/track/<id> or https://listen.tidal.com/browse/album/<album_id>/track/<track_id>
    listen_url: str = ""
    # Direct URL to media https://tidal.com/browse/track/<id>
    share_url: str = ""

    def __init__(
        self, session: "tidalapi.session.Session", media_id: Optional[str] = None
    ):
        self.session = session
        self.requests = self.session.request
        self.album = session.album()
        self.id = media_id
        if self.id is not None:
            self._get(self.id)

    @abstractmethod
    def _get(self, media_id: str) -> Media:
        raise NotImplementedError(
            "You are not supposed to use the media class directly."
        )

    def parse(self, json_obj: JsonObj, album: Optional[Album] = None) -> None:
        """Assigns all :param json_obj:

        :param json_obj: The JSON object to parse
        :param album: The (optional) album to use, instead of parsing the JSON object
        :return:
        """
        artists = self.session.parse_artists(json_obj["artists"])

        # Sometimes the artist field is not filled, example: 62300893
        if "artist" in json_obj:
            artist = self.session.parse_artist(json_obj["artist"])
        else:
            artist = artists[0]

        if album is None and json_obj["album"]:
            album = self.session.album().parse(json_obj["album"], artist, artists)
        self.album = album

        self.id = json_obj["id"]
        self.name = json_obj["title"]
        self.duration = json_obj["duration"]
        self.available = bool(json_obj["streamReady"])

        # Removed media does not have a release date.
        self.tidal_release_date = None
        release_date = json_obj.get("streamStartDate")
        self.tidal_release_date = (
            dateutil.parser.isoparse(release_date) if release_date else None
        )

        # When getting items from playlists they have a date added attribute, same with
        #  favorites.
        user_date_added = json_obj.get("dateAdded")
        self.user_date_added = (
            dateutil.parser.isoparse(user_date_added) if user_date_added else None
        )

        self.track_num = json_obj["trackNumber"]
        self.volume_num = json_obj["volumeNumber"]
        self.explicit = bool(json_obj["explicit"])
        self.popularity = json_obj["popularity"]
        self.artist = artist
        self.artists = artists
        self.type = json_obj.get("type")

        self.artist_roles = json_obj.get("artistRoles")

    def parse_media(
        self, json_obj: JsonObj, album: Optional[Album] = None
    ) -> Union["Track", "Video"]:
        """Selects the media type when checking lists that can contain both.

        :param json_obj: The json containing the media
        :param album: The (optional) album to use, instead of parsing the JSON object
        :return: Returns a new Video or Track object.
        """
        if json_obj.get("type") is None or json_obj["type"] == "Track":
            return Track(self.session).parse_track(json_obj, album)
        # There are other types like Event, Live, and Video which match the video class
        return Video(self.session).parse_video(json_obj, album)


class Track(Media):
    """An object containing information about a track."""

    replay_gain = None
    peak = None
    isrc = None
    audio_quality: Optional[str] = None
    audio_modes: Optional[List[str]] = None
    version = None
    full_name: Optional[str] = None
    copyright = None
    media_metadata_tags = None

    def parse_track(self, json_obj: JsonObj, album: Optional[Album] = None) -> Track:
        Media.parse(self, json_obj, album)
        self.replay_gain = json_obj["replayGain"]
        # Tracks from the pages endpoints might not actually exist
        if "peak" in json_obj and "isrc" in json_obj:
            self.peak = json_obj["peak"]
            self.isrc = json_obj["isrc"]
            self.copyright = json_obj["copyright"]
        self.audio_quality = json_obj["audioQuality"]
        self.audio_modes = json_obj["audioModes"]
        self.version = json_obj["version"]
        self.media_metadata_tags = json_obj.get("mediaMetadata", {}).get("tags", {})

        if self.version is not None:
            self.full_name = f"{json_obj['title']} ({json_obj['version']})"
        else:
            self.full_name = json_obj["title"]
        # Generate share URLs from track ID and album (if it exists)
        if self.album:
            self.listen_url = f"{self.session.config.listen_base_url}/album/{self.album.id}/track/{self.id}"
        else:
            self.listen_url = f"{self.session.config.listen_base_url}/track/{self.id}"
        self.share_url = f"{self.session.config.share_base_url}/track/{self.id}"

        return copy.copy(self)

    def _get(self, media_id: str) -> "Track":
        """Returns information about a track, and also replaces the track used to call
        this function.

        :param media_id: TIDAL's identifier of the track
        :return: A :class:`Track` object containing all the information about the track
        """

        try:
            request = self.requests.request("GET", "tracks/%s" % media_id)
        except ObjectNotFound as e:
            e.args = ("Track with id %s not found" % media_id,)
            raise e
        except TooManyRequests as e:
            e.args = ("Track unavailable",)
            raise e
        else:
            json_obj = request.json()
            track = self.requests.map_json(json_obj, parse=self.parse_track)
            assert not isinstance(track, list)
            return cast("Track", track)

    def get_url(self) -> str:
        """Retrieves the URL for a track.

        :return: A `str` object containing the direct track URL
        :raises: A :class:`exceptions.URLNotAvailable` if no URL is available for this track
        """
        if self.session.is_pkce:
            raise URLNotAvailable(
                "Track URL not available with quality:'{}'".format(
                    self.session.config.quality
                )
            )
        params = {
            "urlusagemode": "STREAM",
            "audioquality": self.session.config.quality,
            "assetpresentation": "FULL",
        }
        try:
            request = self.requests.request(
                "GET", "tracks/%s/urlpostpaywall" % self.id, params
            )
        except ObjectNotFound:
            raise URLNotAvailable("URL not available for this track")
        except TooManyRequests as e:
            e.args = ("URL unavailable",)
            raise e
        else:
            json_obj = request.json()
            return cast(str, json_obj["urls"][0])

    def lyrics(self) -> "Lyrics":
        """Retrieves the lyrics for a song.

        :return: A :class:`Lyrics` object containing the lyrics
        :raises: A :class:`exceptions.MetadataNotAvailable` if there aren't any lyrics
        """
        try:
            request = self.requests.request("GET", "tracks/%s/lyrics" % self.id)
        except ObjectNotFound:
            raise MetadataNotAvailable("No lyrics exists for this track")
        except TooManyRequests as e:
            e.args = ("Lyrics unavailable",)
            raise e
        else:
            json_obj = request.json()
            lyrics = self.requests.map_json(json_obj, parse=Lyrics().parse)
            assert not isinstance(lyrics, list)
            return cast("Lyrics", lyrics)

    def get_track_radio(self, limit: int = 100) -> List["Track"]:
        """Queries TIDAL for the track radio mix as a list of tracks similar to this
        track.

        :return: A list of :class:`Tracks <tidalapi.media.Track>`
        :raises: A :class:`exceptions.MetadataNotAvailable` if no track radio mix is available
        """
        params = {"limit": limit}

        try:
            request = self.requests.request(
                "GET", "tracks/%s/radio" % self.id, params=params
            )
        except ObjectNotFound:
            raise MetadataNotAvailable("Track radio not available for this track")
        except TooManyRequests as e:
            e.args = ("Track radio unavailable",)
            raise e
        else:
            json_obj = request.json()
            tracks = self.requests.map_json(json_obj, parse=self.session.parse_track)
            assert isinstance(tracks, list)
            return cast(List["Track"], tracks)

    def get_radio_mix(self) -> mix.Mix:
        """Queries TIDAL for the track radio mix of tracks that are similar to this
        track.

        :return: A :class:`Mix <tidalapi.mix.Mix>`
        :raises: A :class:`exceptions.MetadataNotAvailable` if no track radio mix is available
        """
        try:
            request = self.requests.request("GET", "tracks/%s/mix" % self.id)
        except ObjectNotFound:
            raise MetadataNotAvailable("Track radio not available for this track")
        except TooManyRequests as e:
            e.args = ("Track radio unavailable",)
            raise e
        else:
            json_obj = request.json()
            return self.session.mix(json_obj.get("id"))

    def get_stream(self) -> "Stream":
        """Retrieves the track streaming object, allowing for audio transmission.

        :return: A :class:`Stream` object which holds audio file properties and
            parameters needed for streaming via `MPEG-DASH` protocol.
        :raises: A :class:`exceptions.StreamNotAvailable` if there is no stream available for this track
        """
        params = {
            "playbackmode": "STREAM",
            "audioquality": self.session.config.quality,
            "assetpresentation": "FULL",
        }

        try:
            request = self.requests.request(
                "GET", "tracks/%s/playbackinfopostpaywall" % self.id, params
            )
        except ObjectNotFound:
            raise StreamNotAvailable("Stream not available for this track")
        except TooManyRequests as e:
            e.args = ("Stream unavailable",)
            raise e
        else:
            json_obj = request.json()
            stream = self.requests.map_json(json_obj, parse=Stream().parse)
            assert not isinstance(stream, list)
            return cast("Stream", stream)

    @property
    def is_hi_res_lossless(self) -> bool:
        try:
            if (
                self.media_metadata_tags
                and MediaMetadataTags.hi_res_lossless in self.media_metadata_tags
            ):
                return True
        except:
            pass
        return False

    @property
    def is_lossless(self) -> bool:
        try:
            if (
                self.media_metadata_tags
                and MediaMetadataTags.lossless in self.media_metadata_tags
            ):
                return True
        except:
            pass
        return False

    @property
    def is_dolby_atmos(self) -> bool:
        try:
            return True if AudioMode.dolby_atmos in self.audio_modes else False
        except:
            return False


class Stream:
    """An object that stores the audio file properties and parameters needed for
    streaming via `MPEG-DASH` protocol.

    The `manifest` attribute holds the MPD file content encoded in base64.
    """

    track_id: int = -1
    audio_mode: str = AudioMode.stereo  # STEREO, DOLBY_ATMOS
    audio_quality: str = Quality.low_320k  # LOW, HIGH, LOSSLESS, HI_RES_LOSSLESS
    manifest_mime_type: str = ""
    manifest_hash: str = ""
    manifest: str = ""
    asset_presentation: str = "FULL"
    album_replay_gain: float = 1.0
    album_peak_amplitude: float = 1.0
    track_replay_gain: float = 1.0
    track_peak_amplitude: float = 1.0
    bit_depth: int = 16
    sample_rate: int = 44100

    def parse(self, json_obj: JsonObj) -> "Stream":
        self.track_id = json_obj.get("trackId")
        self.audio_mode = json_obj.get("audioMode")
        self.audio_quality = json_obj.get("audioQuality")
        self.manifest_mime_type = json_obj.get("manifestMimeType")
        self.manifest_hash = json_obj.get("manifestHash")
        self.manifest = json_obj.get("manifest")

        # Use default values for gain, amplitude if unavailable
        self.album_replay_gain = json_obj.get("albumReplayGain", 1.0)
        self.album_peak_amplitude = json_obj.get("albumPeakAmplitude", 1.0)
        self.track_replay_gain = json_obj.get("trackReplayGain", 1.0)
        self.track_peak_amplitude = json_obj.get("trackPeakAmplitude", 1.0)

        # Bit depth, Sample rate not available for low,hi_res quality modes. Assuming 16bit/44100Hz
        self.bit_depth = json_obj.get("bitDepth", 16)
        self.sample_rate = json_obj.get("sampleRate", 44100)

        return copy.copy(self)

    def get_audio_resolution(self):
        return self.bit_depth, self.sample_rate

    def get_stream_manifest(self) -> "StreamManifest":
        return StreamManifest(self)

    def get_manifest_data(self) -> str:
        try:
            # Stream Manifest is base64 encoded.
            return base64.b64decode(self.manifest).decode("utf-8")
        except:
            raise ManifestDecodeError

    @property
    def is_mpd(self) -> bool:
        return True if ManifestMimeType.MPD in self.manifest_mime_type else False

    @property
    def is_bts(self) -> bool:
        return True if ManifestMimeType.BTS in self.manifest_mime_type else False


class StreamManifest:
    """An object containing a parsed StreamManifest."""

    manifest: str = None
    manifest_mime_type: str = None
    manifest_parsed: str = None
    codecs: str = None  # MP3, AAC, FLAC, ALAC, MQA, EAC3, AC4, MHA1
    encryption_key = None
    encryption_type = None
    sample_rate: int = 44100
    urls: [str] = []
    mime_type: MimeType = MimeType.audio_mpeg
    file_extension = None
    dash_info: DashInfo = None

    def __init__(self, stream: Stream):
        self.manifest = stream.manifest
        self.manifest_mime_type = stream.manifest_mime_type
        if stream.is_mpd:
            # See https://ottverse.com/structure-of-an-mpeg-dash-mpd/ for more details
            self.dash_info = DashInfo.from_mpd(stream.get_manifest_data())
            self.urls = self.dash_info.urls
            # MPD reports mp4a codecs slightly differently when compared to BTS. Both will be interpreted as MP4A
            if "flac" in self.dash_info.codecs:
                self.codecs = Codec.FLAC
            elif "mp4a.40.5" in self.dash_info.codecs:
                # LOW 96K: "mp4a.40.5"
                self.codecs = Codec.MP4A
            elif "mp4a.40.2" in self.dash_info.codecs:
                # LOW 320k "mp4a.40.2"
                self.codecs = Codec.MP4A
            else:
                self.codecs = self.dash_info.codecs
            self.mime_type = self.dash_info.mime_type
            self.sample_rate = self.dash_info.audio_sampling_rate
            # TODO: Handle encryption key.
            self.encryption_type = "NONE"
            self.encryption_key = None
        elif stream.is_bts:
            # Stream Manifest is base64 encoded.
            self.manifest_parsed = stream.get_manifest_data()
            # JSON string to object.
            stream_manifest = json.loads(self.manifest_parsed)
            # TODO: Handle more than one download URL
            self.urls = stream_manifest["urls"]
            # Codecs can be interpreted directly when using BTS
            self.codecs = stream_manifest["codecs"].upper().split(".")[0]
            self.mime_type = stream_manifest["mimeType"]
            self.encryption_type = stream_manifest["encryptionType"]
            self.encryption_key = (
                stream_manifest.get("keyId") if self.encryption_type else None
            )
        else:
            raise UnknownManifestFormat

        self.file_extension = self.get_file_extension(self.urls[0], self.codecs)

    def get_urls(self) -> [str]:
        return self.urls

    def get_hls(self) -> str:
        if self.is_mpd:
            return self.dash_info.get_hls()
        else:
            raise MPDNotAvailableError("HLS stream requires MPD MetaData")

    def get_codecs(self) -> str:
        return self.codecs

    def get_sampling_rate(self) -> int:
        return self.dash_info.audio_sampling_rate

    @staticmethod
    def get_mimetype(stream_codec, stream_url: Optional[str] = None) -> str:
        if stream_codec:
            return MimeType.from_audio_codec(stream_codec)
        if not stream_url:
            return MimeType.audio_m4a
        else:
            if AudioExtensions.FLAC in stream_url:
                return MimeType.audio_xflac
            elif AudioExtensions.MP4 in stream_url:
                return MimeType.audio_m4a

    @staticmethod
    def get_file_extension(stream_url: str, stream_codec: Optional[str] = None) -> str:
        if AudioExtensions.FLAC in stream_url:
            # If the file extension within the URL is '*.flac', this is simply a FLAC file.
            result: str = AudioExtensions.FLAC
        elif (
            AudioExtensions.MP4 in stream_url
            or AudioExtensions.M4A in stream_url
            or stream_codec == Codec.MP4A
        ):
            # MPEG-4 is simply a container format for different audio / video encoded lines, like FLAC, AAC, M4A etc.
            # '*.m4a' is usually used as file extension, if the container contains only audio lines
            # See https://en.wikipedia.org/wiki/MP4_file_format
            result: str = AudioExtensions.M4A
        elif VideoExtensions.TS in stream_url:
            # Video are streamed as '*.ts' files by TIDAL.
            result: str = VideoExtensions.TS
        else:
            # If everything fails it might be an '*.mp4' file
            result: str = AudioExtensions.MP4

        return result

    @property
    def is_encrypted(self) -> bool:
        return True if self.encryption_key else False

    @property
    def is_mpd(self) -> bool:
        return True if ManifestMimeType.MPD in self.manifest_mime_type else False

    @property
    def is_bts(self) -> bool:
        return True if ManifestMimeType.BTS in self.manifest_mime_type else False


class DashInfo:
    """An object containing the decoded MPEG-DASH / MPD manifest."""

    duration: datetime = timedelta()
    content_type: str = "audio"
    mime_type: MimeType = MimeType.audio_ac4
    codecs: str = Codec.FLAC
    first_url: str = ""
    media_url: str = ""
    timescale: int = 44100
    audio_sampling_rate: int = 44100
    chunk_size: int = -1
    last_chunk_size: int = -1
    urls: [str] = [""]

    @staticmethod
    def from_stream(stream) -> "DashInfo":
        try:
            if stream.is_mpd and not stream.is_encrypted:
                return DashInfo(stream.get_manifest_data())
        except:
            raise ManifestDecodeError

    @staticmethod
    def from_mpd(mpd_manifest) -> "DashInfo":
        try:
            return DashInfo(mpd_manifest)
        except:
            raise ManifestDecodeError

    def __init__(self, mpd_xml):
        mpd = MPEGDASHParser.parse(
            mpd_xml.split("<?xml version='1.0' encoding='UTF-8'?>")[1]
        )

        self.duration = parse_duration(mpd.media_presentation_duration)
        self.content_type = mpd.periods[0].adaptation_sets[0].content_type
        self.mime_type = mpd.periods[0].adaptation_sets[0].mime_type
        self.codecs = mpd.periods[0].adaptation_sets[0].representations[0].codecs
        self.first_url = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .initialization
        )
        self.media_url = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .media
        )
        # self.startNumber = mpd.periods[0].adaptation_sets[0].representations[0].segment_templates[0].start_number
        self.timescale = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .timescale
        )
        self.audio_sampling_rate = int(
            mpd.periods[0].adaptation_sets[0].representations[0].audio_sampling_rate
        )
        self.chunk_size = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .segment_timelines[0]
            .Ss[0]
            .d
        )
        # self.chunkcount = mpd.periods[0].adaptation_sets[0].representations[0].segment_templates[0].segment_timelines[0].Ss[0].r + 1
        self.last_chunk_size = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .segment_timelines[0]
            .Ss[-1]  # Always use last element in segment timeline.
            .d
        )

        self.urls = self.get_urls(mpd)

    @staticmethod
    def get_urls(mpd) -> list[str]:
        # min segments count; i.e. .initialization + the very first of .media;
        # See https://developers.broadpeak.io/docs/foundations-dash
        segments_count = 1 + 1

        for s in (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .segment_timelines[0]
            .Ss
        ):
            segments_count += s.r if s.r else 1

        # Populate segment urls.
        segment_template = (
            mpd.periods[0]
            .adaptation_sets[0]
            .representations[0]
            .segment_templates[0]
            .media
        )
        stream_urls: list[str] = []

        for index in range(segments_count):
            stream_urls.append(segment_template.replace("$Number$", str(index)))

        return stream_urls

    def get_hls(self) -> str:
        hls = "#EXTM3U\n"
        hls += "#EXT-X-TARGETDURATION:%s\n" % int(self.duration.seconds)
        hls += "#EXT-X-VERSION:3\n"
        items = self.urls
        chunk_duration = "#EXTINF:%0.3f,\n" % (
            float(self.chunk_size) / float(self.timescale)
        )
        hls += "\n".join(chunk_duration + item for item in items[0:-1])
        chunk_duration = "#EXTINF:%0.3f,\n" % (
            float(self.last_chunk_size) / float(self.timescale)
        )
        hls += "\n" + chunk_duration + items[-1] + "\n"
        hls += "#EXT-X-ENDLIST\n"
        return hls


class Lyrics:
    """An object containing lyrics for a track."""

    track_id: int = -1
    provider: str = ""
    provider_track_id: int = -1
    provider_lyrics_id: int = -1
    text: str = ""
    #: Contains timestamps as well
    subtitles: str = ""
    right_to_left: bool = False

    def parse(self, json_obj: JsonObj) -> "Lyrics":
        self.track_id = json_obj["trackId"]
        self.provider = json_obj["lyricsProvider"]
        self.provider_track_id = json_obj["providerCommontrackId"]
        self.provider_lyrics_id = json_obj["providerLyricsId"]
        self.text = json_obj["lyrics"]
        self.subtitles = json_obj["subtitles"]
        self.right_to_left = bool(json_obj["isRightToLeft"])

        return copy.copy(self)


class Video(Media):
    """An object containing information about a video."""

    release_date: Optional[datetime] = None
    video_quality: Optional[str] = None
    cover: Optional[str] = None

    def parse_video(self, json_obj: JsonObj, album: Optional[Album] = None) -> Video:
        Media.parse(self, json_obj, album)
        release_date = json_obj.get("releaseDate")
        self.release_date = (
            dateutil.parser.isoparse(release_date) if release_date else None
        )
        self.cover = json_obj["imageId"]
        # Videos found in the /pages endpoints don't have quality
        self.video_quality = json_obj.get("quality")

        # Generate share URLs from track ID and artist (if it exists)
        if self.artist:
            self.listen_url = f"{self.session.config.listen_base_url}/artist/{self.artist.id}/video/{self.id}"
        else:
            self.listen_url = f"{self.session.config.listen_base_url}/video/{self.id}"
        self.share_url = f"{self.session.config.share_base_url}/video/{self.id}"

        return copy.copy(self)

    def _get(self, media_id: str) -> Video:
        """Returns information about the video, and replaces the object used to call
        this function.

        :param media_id: TIDAL's identifier of the video
        :return: A :class:`Video` object containing all the information about the video.
        :raises: A :class:`exceptions.ObjectNotFound` if video is not found or unavailable
        """

        try:
            request = self.requests.request("GET", "videos/%s" % self.id)
        except ObjectNotFound as e:
            e.args = ("Video with id %s not found" % media_id,)
            raise e
        except TooManyRequests as e:
            e.args = ("Video unavailable",)
            raise e
        else:
            json_obj = request.json()
            video = self.requests.map_json(json_obj, parse=self.parse_video)
            assert not isinstance(video, list)
            return cast("Video", video)

    def get_url(self) -> str:
        """Retrieves the URL to the m3u8 video playlist.

        :return: A `str` object containing the direct video URL
        :raises: A :class:`exceptions.URLNotAvailable` if no URL is available for this video
        """
        params = {
            "urlusagemode": "STREAM",
            "videoquality": self.session.config.video_quality,
            "assetpresentation": "FULL",
        }

        try:
            request = self.requests.request(
                "GET", "videos/%s/urlpostpaywall" % self.id, params
            )
        except ObjectNotFound:
            raise URLNotAvailable("URL not available for this video")
        except TooManyRequests as e:
            e.args = ("URL unavailable",)
            raise e
        else:
            json_obj = request.json()
            return cast(str, json_obj["urls"][0])

    def image(self, width: int = 1080, height: int = 720) -> str:
        if (width, height) not in [(160, 107), (480, 320), (750, 500), (1080, 720)]:
            raise ValueError("Invalid resolution {} x {}".format(width, height))
        if not self.cover:
            raise AttributeError("No cover image")
        return self.session.config.image_url % (
            self.cover.replace("-", "/"),
            width,
            height,
        )
