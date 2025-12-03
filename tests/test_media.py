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

from datetime import datetime

import pytest
from dateutil import tz

import tidalapi
from tidalapi import VideoQuality
from tidalapi.exceptions import MetadataNotAvailable, ObjectNotFound
from tidalapi.media import (
    AudioExtensions,
    AudioMode,
    Codec,
    ManifestMimeType,
    MimeType,
    Quality,
)
from tidalapi.mix import MixType

from .cover import verify_image_resolution, verify_video_resolution


def test_media(session):
    with pytest.raises(NotImplementedError):
        tidalapi.media.Media(session, 440930)


def test_track(session):
    track = session.track(125169484)

    # Basic metadata
    assert track.id == 125169484
    assert track.title == "Alone, Pt. II"
    assert track.name == track.title
    assert track.version is None
    assert track.full_name == track.title  # Version is none, full_name == title
    assert track.duration == 179
    assert track.explicit is False
    assert track.popularity == 73
    assert track.available is True
    assert track.stream_start_date == datetime(2019, 12, 27, 0, 0, tzinfo=tz.tzutc())
    assert track.tidal_release_date == track.stream_start_date
    assert track.date_added is None
    assert track.user_date_added == track.user_date_added
    assert track.track_num == 1
    assert track.volume_num == 1

    # Album
    assert track.album.name == "Alone, Pt. II"
    assert track.album.id == 125169472
    assert track.album.cover == "345d81fd-3a06-4fe4-b77a-6f6e28baad25"
    assert track.album.video_cover is None

    # URLs
    assert track.url == "http://www.tidal.com/track/125169484"
    assert (
        track.listen_url == "https://listen.tidal.com/album/125169472/track/125169484"
    )
    assert track.share_url == "https://tidal.com/browse/track/125169484"

    # Artist(s)
    assert track.artist.name == "Alan Walker"
    assert track.artist.picture == "c46be937-9869-4454-8d80-ba6a6e23b6c6"
    artist_names = [artist.name for artist in track.artists]
    for name in ["Alan Walker", "Ava Max"]:
        assert name in artist_names

    # Audio / streaming
    assert track.audio_quality == tidalapi.Quality.high_lossless
    assert track.audio_modes == ["STEREO"]
    assert track.media_metadata_tags == ["LOSSLESS", "HIRES_LOSSLESS"]
    assert track.is_lossless is True
    assert track.is_hi_res_lossless is True
    assert track.is_dolby_atmos is False
    assert track.ad_supported_stream_ready is True
    assert track.allow_streaming is True
    assert track.stream_ready is True
    assert track.stem_ready is False
    assert track.dj_ready is True
    assert track.pay_to_stream is False
    assert track.premium_streaming_only is False
    assert track.access_type == "PUBLIC"

    # Music metadata
    assert track.bpm == 88
    assert track.replay_gain == -10.4
    assert track.peak == 0.988312
    assert track.mixes == {"TRACK_MIX": "001603cb31f1842e052770e0ad7647"}
    assert track.key == "FSharp"
    assert track.key_scale == "MAJOR"
    assert track.allow_streaming is True
    assert track.pay_to_stream is False
    assert track.date_added is None  # Missing
    assert track.description is None
    assert track.editable is False
    assert track.index is None
    assert track.item_uuid is None
    assert track.spotlighted is False
    assert track.upload is False

    # Copyright / ISRC
    assert (
        track.copyright
        == "(P) 2019 Kreatell Music under exclusive license to Sony Music Entertainment Sweden AB"
    )
    assert track.isrc == "NOG841907010"

    # Session / requests
    assert track.session is not None
    assert track.requests is not None

    # Type info
    assert track.type is None
    assert track.artist_roles is None


def test_unavailable_track(session):
    # Unavailable tracks are only "accessible" through playlist
    pl = session.playlist("93f6d95b-cdfe-4ee6-8c10-84098e265535")
    # Get an "Unavailable" track from playlist
    track = pl.tracks(1, 28)[0]
    # Unavailable track will have most of the below flags set to "False"
    assert track.available is False
    assert track.allow_streaming is False
    assert track.pay_to_stream is False
    assert track.premium_streaming_only is False
    assert track.editable is False
    assert track.upload is False
    assert track.spotlighted is False
    # Certain fields will have valid values
    assert track.id == 77909345
    assert track.title == "Fostul Remix"
    assert track.full_name == track.title
    assert track.url == "http://www.tidal.com/track/77909345"
    assert track.listen_url == "https://listen.tidal.com/album/77909343/track/77909345"
    assert track.share_url == "https://tidal.com/browse/track/77909345"

    assert track.audio_quality == "LOSSLESS"
    assert track.audio_modes == ["STEREO"]


def test_track_url(session):
    session.config = tidalapi.Config()
    track = session.track(142278122)
    assert "audio.tidal.com" in track.get_url()


def test_lyrics(session):
    track = session.track(56480040)
    lyrics = track.lyrics()
    assert "I think we're there" in lyrics.text
    assert "I think we're there" in lyrics.subtitles
    assert lyrics.right_to_left is False


def test_no_lyrics(session):
    track = session.track(17626400)
    # Tracks with no lyrics should trigger MetadataNotAvailable (response: 404)
    with pytest.raises(MetadataNotAvailable):
        track.lyrics()


def test_right_to_left(session):
    lyrics = session.track(95948697).lyrics()
    assert lyrics.right_to_left
    assert "أديني جيت" in lyrics.text


def test_track_with_album(session):
    track_id = 142278122
    track = session.track(track_id)
    print(track.album)
    assert track.album.duration is None
    track = session.track(track_id, True)
    assert track.album.duration == 221


def test_track_streaming(session):
    track = session.track(62392768)
    stream = track.get_stream()
    assert stream.audio_mode == AudioMode.stereo
    assert (
        stream.audio_quality == tidalapi.Quality.low_320k
    )  # i.e. the default quality for the current session


@pytest.mark.skip(reason="SONY360 support has been removed")
def test_track_quality_sony360(session):
    # TIDAL: For 360 Reality Audio: If you had a 360 Reality Audio track or album in your Collection –
    #   including in a playlist or downloaded for offline access –
    #   the track or album will be grayed out and unavailable for streaming if you try to select it.
    # Ref: https://support.tidal.com/hc/en-us/articles/25876825185425-Audio-Format-Updates
    # Session should allow highest possible quality (but will fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    # Alice In Chains / We Die Young (Max quality: HI_RES MHA1 SONY360; Album has now been removed)
    with pytest.raises(ObjectNotFound):
        session.album("249593867")


@pytest.mark.skip(reason="Atmos appears to fallback to HI_RES_LOSSLESS")
def test_track_quality_atmos(session):
    # Session should allow highest possible quality (but should fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    album = session.album("355472560")  # DOLBY_ATMOS, will fallback to HI_RES_LOSSLESS
    track = album.tracks()[0]
    assert track.audio_quality == "LOW"
    assert track.audio_modes == ["DOLBY_ATMOS"]
    assert track.is_dolby_atmos
    stream = track.get_stream()
    assert stream.is_mpd and not stream.is_bts
    assert stream.audio_quality == "HIGH"  # Expected this to be LOW?
    assert stream.audio_mode == "STEREO"  # Expected this to be DOLBY_ATMOS?
    assert stream.bit_depth == 24  # Correct bit depth for atmos??
    assert stream.sample_rate == 192000  # Correct sample rate for atmos??
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.Atmos
    assert manifest.mime_type == MimeType.audio_eac3


@pytest.mark.skip(reason="MQA albums appears to fallback to LOSSLESS")
def test_track_quality_mqa(session):
    # TIDAL:
    #   For MQA: If you had an MQA track or album in your Collection – including in playlists –
    #   the track was automatically replaced by the highest quality FLAC version that has been distributed to TIDAL.
    # Ref: https://support.tidal.com/hc/en-us/articles/25876825185425-Audio-Format-Updates
    # Session should allow highest possible quality (but will fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    # U2 / Achtung Baby (Max quality: HI_RES MQA, 16bit/44100Hz)
    album = session.album("77640617")
    track = album.tracks()[0]
    assert track.audio_quality == "LOSSLESS"
    assert track.audio_modes == ["STEREO"]
    # assert track.is_mqa # for an MQA album, this value is expected to be true
    stream = track.get_stream()
    assert stream.is_mpd and not stream.is_bts
    assert stream.audio_quality == "LOSSLESS"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 16
    assert stream.sample_rate == 44100
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.FLAC
    assert manifest.mime_type == MimeType.audio_mp4


def test_track_quality_low96k(session):
    # Album is available in LOSSLESS, but we will explicitly request low 320k quality instead
    session.audio_quality = Quality.low_96k
    # D-A-D / A Prayer for the Loud   (Max quality: LOSSLESS FLAC, 16bit/44.1kHz)
    album = session.album("172358622")
    track = album.tracks()[0]
    assert track.audio_quality == "LOSSLESS"  # Available in LOSSLESS (or below)
    assert track.audio_modes == ["STEREO"]
    # Only LOSSLESS (or below) is available for this album
    assert not track.is_hi_res_lossless
    assert track.is_lossless
    stream = track.get_stream()
    assert (
        not stream.is_mpd and stream.is_bts
    )  # LOW/HIGH/LOSSLESS streams will use BTS, if OAuth authentication is used.
    assert stream.audio_quality == "LOW"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 16
    assert stream.sample_rate == 44100
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.MP4A
    assert (
        manifest.mime_type == MimeType.audio_mp4
    )  # All MPEG-DASH based streams use an 'audio_mp4' container


def test_track_quality_low320k(session):
    # Album is available in LOSSLESS, but we will explicitly request low 320k quality instead
    session.audio_quality = Quality.low_320k
    # D-A-D / A Prayer for the Loud   (Max quality: LOSSLESS FLAC, 16bit/44.1kHz)
    album = session.album("172358622")
    track = album.tracks()[0]
    assert track.audio_quality == "LOSSLESS"  # Available in LOSSLESS (or below)
    assert track.audio_modes == ["STEREO"]
    # Only LOSSLESS (or below) is available for this album
    assert not track.is_hi_res_lossless
    assert track.is_lossless
    stream = track.get_stream()
    assert not stream.is_mpd and stream.is_bts
    assert stream.audio_quality == "HIGH"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 16
    assert stream.sample_rate == 44100
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.MP4A
    assert (
        manifest.mime_type == MimeType.audio_mp4
    )  # All BTS (LOW/HIGH) based streams use an 'audio_mp4' container


def test_track_quality_lossless(session):
    # Session should allow highest possible quality (but will fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    # D-A-D / A Prayer for the Loud   (Max quality: LOSSLESS FLAC, 16bit/44.1kHz)
    album = session.album("172358622")
    track = album.tracks()[0]
    assert track.audio_quality == "LOSSLESS"
    assert track.audio_modes == ["STEREO"]
    # Only LOSSLESS is available for this album
    assert not track.is_hi_res_lossless
    assert track.is_lossless
    stream = track.get_stream()
    assert (
        not stream.is_mpd and stream.is_bts
    )  # LOW/HIGH/LOSSLESS streams will use BTS, if OAuth authentication is used.
    assert stream.audio_quality == "LOSSLESS"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 16
    assert stream.sample_rate == 44100
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.FLAC
    assert (
        manifest.mime_type == MimeType.audio_flac
    )  # All BTS (LOSSLESS) based streams use an 'audio_mp4' container


def test_track_quality_max(session):
    # Session should allow highest possible quality (but will fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    # Mark Knopfler, One Deep River: Reported as MAX (HI_RES_LOSSLESS, 16bit/48kHz)
    album = session.album("355473696")
    track = album.tracks()[0]
    assert track.audio_quality == "LOSSLESS"
    assert track.audio_modes == ["STEREO"]
    # Both HI_RES_LOSSLESS and LOSSLESS is available for this album
    assert track.is_hi_res_lossless
    assert track.is_lossless
    stream = track.get_stream()
    assert (
        stream.is_mpd and not stream.is_bts
    )  # HI_RES_LOSSLESS streams will use MPD, if OAuth authentication is used.
    assert stream.audio_quality == "HI_RES_LOSSLESS"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 16
    assert stream.sample_rate == 48000
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.FLAC
    assert (
        manifest.mime_type == MimeType.audio_mp4
    )  # All MPEG-DASH based streams use an 'audio_mp4' container


def test_track_quality_max_lossless(session):
    # Session should allow highest possible quality (but will fallback to highest available album quality)
    session.audio_quality = Quality.hi_res_lossless
    album = session.album("355473675")  # MAX (HI_RES_LOSSLESS, 24bit/192kHz)
    track = album.tracks()[0]
    # Both HI_RES_LOSSLESS and LOSSLESS is available for this album
    assert track.is_hi_res_lossless
    assert track.is_lossless
    stream = track.get_stream()
    assert (
        stream.is_mpd and not stream.is_bts
    )  # HI_RES_LOSSLESS streams will use MPD, if OAuth authentication is used.
    assert stream.audio_quality == "HI_RES_LOSSLESS"
    assert stream.audio_mode == "STEREO"
    assert stream.bit_depth == 24
    assert stream.sample_rate == 192000
    manifest = stream.get_stream_manifest()
    assert manifest.codecs == Codec.FLAC
    assert (
        manifest.mime_type == MimeType.audio_mp4
    )  # All MPEG-DASH based streams use an 'audio_mp4' container


def test_video(session):
    video = session.video(125506698)

    assert video.id == 125506698
    assert video.title == "Alone, Pt. II"
    assert video.name == video.title
    assert video.track_num == 0
    assert video.volume_num == 0
    assert video.release_date == datetime(2019, 12, 26, tzinfo=tz.tzutc())
    assert video.tidal_release_date == datetime(2019, 12, 27, 9, tzinfo=tz.tzutc())
    assert video.duration == 237
    assert video.video_quality == "MP4_1080P"
    assert video.type == "Music Video"
    assert video.album is None
    assert video.available is True
    assert video.explicit is False
    assert video.ad_supported_stream_ready is True  # adSupportedStreamReady
    assert video.ads_pre_paywall_only is True  # adsPrePaywallOnly
    assert video.ads_url is None  # adsUrl
    assert video.allow_streaming is True  # allowStreaming
    assert video.dj_ready is True  # djReady
    assert video.stem_ready is False  # stemReady
    assert video.stream_ready is True  # streamReady

    assert video.popularity == 21  # popularity
    assert video.image_id == "7f1160e3-bdc3-4764-810b-93194443913d"  # imageId
    assert video.image_path is None  # imagePath
    assert video.tidal_release_date == datetime(
        2019, 12, 27, 9, tzinfo=tz.tzutc()
    )  # streamStartDate
    assert video.vibrant_color == "#e2f2e5"  # vibrantColor

    assert video.artist.name == "Alan Walker"
    assert video.artist.id == 6159368
    assert video.artist.picture == "c46be937-9869-4454-8d80-ba6a6e23b6c6"
    artist_names = [artist.name for artist in video.artists]
    assert [artist in artist_names for artist in ["Alan Walker", "Ava Max"]]

    assert video.listen_url == "https://listen.tidal.com/artist/6159368/video/125506698"
    assert video.share_url == "https://tidal.com/browse/video/125506698"


def test_video_no_release_date(session):
    video = session.video(151050672)
    assert video.id == 151050672
    assert video.name == "Nachbarn"
    assert video.volume_num == 1
    assert video.track_num == 1
    assert video.release_date is None
    assert video.duration == 182
    assert video.available is True
    assert video.explicit is False
    assert video.type == "Music Video"
    assert video.album is None

    assert video.artist.name == "Harris & Ford"
    assert video.artists[0].name == "Harris & Ford"
    assert video.artists[1].name == "FiNCH"

    # Verify that we are clearing the release_date.
    videos = video.artists[1].get_videos()
    assert [None] == [
        video.release_date for video in videos if video.name == "Nachbarn"
    ]


def test_video_not_found(session):
    with pytest.raises(ObjectNotFound):
        session.video(12345678)


def test_video_url(session):
    # Test video URLs at all available qualities
    video = session.video(125506698)
    session.video_quality = VideoQuality.low
    url = video.get_url()
    assert "m3u8" in url
    verify_video_resolution(url, 640, 360)
    session.video_quality = VideoQuality.medium
    url = video.get_url()
    assert "m3u8" in url
    verify_video_resolution(url, 1280, 720)
    session.video_quality = VideoQuality.high
    url = video.get_url()
    assert "m3u8" in url
    verify_video_resolution(url, 1920, 1080)


def test_live_video(session):
    live = session.video(179076073)
    assert live.id == 179076073
    assert live.name == "Justine Skye"
    assert live.track_num == 1
    assert live.volume_num == 1
    assert live.release_date == datetime(2021, 4, 1, tzinfo=tz.tzutc())
    assert live.tidal_release_date == datetime(2021, 4, 1, 18, tzinfo=tz.tzutc())
    assert live.duration == 204
    assert live.video_quality == "MP4_1080P"
    assert live.available is True
    assert live.explicit is False
    assert live.type == "Live"
    assert live.album is None

    assert live.artist.name == "SESSIONS"
    assert live.artists[0].name == "SESSIONS"


def test_video_image(session):
    video = session.video(125506698)

    resolutions = [(160, 107), (480, 320), (750, 500), (1080, 720)]
    for width, height in resolutions:
        verify_image_resolution(session, video.image(width, height), width, height)

    with pytest.raises(ValueError):
        video.image(81, 21)

    with pytest.raises(AssertionError):
        verify_image_resolution(session, video.image(1080, 720), 1270, 1270)


def test_full_name_track_1(session):
    track = session.track(149119714)
    assert track.name == "Fibonacci Progressions (Keemiyo Remix)"
    assert track.version is None
    assert track.full_name == "Fibonacci Progressions (Keemiyo Remix)"


def test_full_name_track_2(session):
    track = session.track(78495659)
    assert track.name == "Bullitt"
    assert track.version == "Bonus Track"
    assert track.full_name == "Bullitt (Bonus Track)"


def test_full_name_track_3(session):
    track = session.track(98849340)
    assert track.name == "Magical place (feat. IOVA)"
    assert track.version == "Dj Dark & MD Dj Remix"
    assert track.full_name == "Magical place (feat. IOVA) (Dj Dark & MD Dj Remix)"


def test_track_media_metadata_tags(session):
    track = session.track(182912246)
    assert track.name == "All You Ever Wanted"
    assert track.media_metadata_tags == ["LOSSLESS", "HIRES_LOSSLESS"]


def test_get_track_radio_limit_default(session):
    track = session.track(182912246)
    similar_tracks = track.get_track_radio()
    assert len(similar_tracks) == 100


def test_get_track_radio_limit_25(session):
    track = session.track(182912246)
    similar_tracks = track.get_track_radio(limit=25)
    assert len(similar_tracks) == 25


def test_get_track_radio_limit_100(session):
    track = session.track(182912246)
    similar_tracks = track.get_track_radio(limit=100)
    assert len(similar_tracks) == 100


def test_get_radio_mix(session):
    track = session.track(12445712)
    radio = track.get_radio_mix()
    assert radio.id == "001c2cbc32b5b7c17f8c0aa55d9541"
    assert radio.title == "Happy Together"
    assert radio.sub_title == "The Turtles"
    assert radio.mix_type == MixType.track


def test_get_stream_bts(session):
    track = session.track(77646170)  # Beck: Sea Change, Track: The Golden Age
    # Set session as BTS type (i.e. low_320k/HIGH Quality)
    session.audio_quality = Quality.low_320k
    # Attempt to get stream and validate
    stream = track.get_stream()
    validate_stream(stream, False)
    # Get parsed stream manifest, audio resolutions
    manifest = stream.get_stream_manifest()
    validate_stream_manifest(manifest, False)
    audio_resolution = stream.get_audio_resolution()
    assert audio_resolution[0] == 16
    assert audio_resolution[1] == 44100


def test_get_stream_mpd(session):
    track = session.track(77646170)
    # Set session as MPD/DASH type (i.e. HI_RES_LOSSLESS Quality).
    session.audio_quality = Quality.hi_res_lossless
    # Attempt to get stream and validate
    stream = track.get_stream()
    validate_stream(stream, True)
    # Get parsed stream manifest
    manifest = stream.get_stream_manifest()
    validate_stream_manifest(manifest, True)


def test_manifest_element_count(session):
    # Certain tracks has only one element in their SegmentTimeline
    #   and must be handled slightly differently when parsing the stream manifest DashInfo
    track = session.track(281047832)
    # Set session as MPD/DASH type (i.e. HI_RES_LOSSLESS Quality).
    session.audio_quality = Quality.hi_res_lossless
    # Attempt to get stream
    stream = track.get_stream()
    # Get parsed stream manifest
    stream.get_stream_manifest()


def validate_stream(stream, is_hi_res_lossless: bool = False):
    assert stream.album_peak_amplitude == 1.0
    assert stream.album_replay_gain == -11.8
    assert stream.asset_presentation == "FULL"
    assert stream.audio_mode == AudioMode.stereo
    if not is_hi_res_lossless:
        assert stream.audio_quality == Quality.low_320k
        assert stream.is_bts == True
        assert stream.is_mpd == False
        assert stream.bit_depth == 16
        assert stream.sample_rate == 44100
        assert stream.manifest_mime_type == ManifestMimeType.BTS
        audio_resolution = stream.get_audio_resolution()
        assert audio_resolution[0] == 16
        assert audio_resolution[1] == 44100
    else:
        assert stream.audio_quality == Quality.hi_res_lossless
        assert stream.is_bts == False
        assert stream.is_mpd == True
        assert stream.bit_depth == 24
        assert stream.sample_rate == 192000  # HI_RES_LOSSLESS: 24bit/192kHz
        assert stream.manifest_mime_type == ManifestMimeType.MPD
        audio_resolution = stream.get_audio_resolution()
        assert audio_resolution[0] == 24
        assert audio_resolution[1] == 192000
    assert stream.track_id == 77646170
    assert stream.track_peak_amplitude == 1.0
    assert stream.track_replay_gain == -9.62


def validate_stream_manifest(manifest, is_hi_res_lossless: bool = False):
    if not is_hi_res_lossless:
        assert manifest.is_bts == True
        assert manifest.is_mpd == False
        assert manifest.codecs == Codec.MP4A
        assert manifest.dash_info is None
        assert manifest.encryption_key is None
        assert manifest.encryption_type == "NONE"
        assert manifest.file_extension == AudioExtensions.M4A
        assert manifest.is_encrypted == False
        assert manifest.manifest_mime_type == ManifestMimeType.BTS
        assert manifest.mime_type == MimeType.audio_mp4
        assert manifest.sample_rate == 44100
    else:
        assert manifest.is_bts == False
        assert manifest.is_mpd == True
        assert manifest.codecs == Codec.FLAC
        assert manifest.dash_info is not None
        assert manifest.encryption_key is None
        assert manifest.encryption_type == "NONE"
        assert manifest.file_extension == AudioExtensions.M4A
        assert manifest.is_encrypted == False
        assert manifest.manifest_mime_type == ManifestMimeType.MPD
        assert manifest.mime_type == MimeType.audio_mp4
        assert manifest.sample_rate == 192000
    # TODO Validate stream URL contents


def test_reset_session_quality(session):
    # HACK: Make sure to reset audio quality to default value for remaining tests
    session.audio_quality = Quality.default


def test_track_extension(session):
    track = session.track(65119559)
    # Set session as MPD/DASH type (i.e. HI_RES_LOSSLESS Quality).
    session.audio_quality = Quality.low_320k
    # Attempt to get stream and manifest
    stream = track.get_stream()
    manifest = stream.get_stream_manifest()
    # Assert extension
    assert manifest.file_extension == AudioExtensions.M4A
