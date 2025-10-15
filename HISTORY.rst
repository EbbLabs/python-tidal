.. :changelog:

History
=======

v0.8.8
--------
* Bugfix: OAuth Client ID, secret updated - tehkillerbee_

v0.8.7
--------
* OAuth Client ID, secret updated - tehkillerbee_
* Bugfix: `albums_paginated` using `get_artists_count` instead of `get_albums_count` - rafrombrc_
* TooManyRequests now includes the retry_after header in its data. - semohr_
* Added a central error class (TidalAPIError) to allow for unified error handling. - semohr_

v0.8.6
------
* Bugfix: Use get_*_count in workers to get the actual number of items. (Fixes #360) - tehkillerbee_
* Feature: Add support for get<track, album, artist, playlist>count(), Workers: Use get_*_count to get the actual number of items. - tehkillerbee_
* Feature: Get playlist tracks, items count. Get playlist tracks paginated. - tehkillerbee_
* Only return warning if page itemtype (v2) is not implemented (Fixes: #362) - tehkillerbee_
* Add legacy home endpoint for backwards compatibility - tehkillerbee_

v0.8.5
------
* Cleanup: Removed deprecated function(s). - tehkillerbee_
* Feature: MixV2: Add support for parsing mixes originating from PageCategoryV2. - tehkillerbee_
* Feature: Get home page using new v2 endpoint. Add support for PageCategoryV2 - tehkillerbee_, Nokse22_
* Feature: Add pagination workers from mopidy-tidal - tehkillerbee_, BlackLight_
* Fix(playlist): Improve v2 endpoint usage. - tehkillerbee_
* fix(playlist): More robust handling of the passed objects. - BlackLight_

v0.8.4
------
* Album: Add UPC barcode, genre URL for tidal tracks - tehkillerbee_
* Remove Python 2 cruft - C0rn3j_
* Adhere to typing standards and mark Python current versions as supported - C0rn3j_
* Add Track.get_radio_mix and Artist.get_radio_mix to get radio as Mix - tehkillerbee_, Nokse22_
* Consistent use of path file open - tehkillerbee_
* CI: Fix branch syntax, bump action and python versions to current, fix indent - C0rn3j_
* Implement sorting for remaining favourites + playlists nilathedragon_
* Feature: Switch to v2 endpoint for playlist get/add/delete. tehkillerbee_
* Add support for album, track, artist batch additions. Add support for add/delete mixes and radios to favorites. (Fixes #336, #337, #339) tehkillerbee_
* Test: List ordering when getting tracks, items, playlist, mixes tehkillerbee_
* Test: Add, remove favorite mix. Add remove artist, album, playlist, track (multiple at a time) tehkillerbee_
* Feature: Get origin album cover by tehkillerbee_
* Fix: Validate returned tracks (isrc) and skip invalid results tehkillerbee_

v0.8.3
------
* Extended file extension detection to properly detect M4A files. - exislow_
* Tests: Updated unit test(s) - tehkillerbee_

v0.8.2
------
* Fixed wrong determination of file extensions for stream metadata. - exislow_
* Moved LinkLogin and futures to login_oauth. - exislow_
* Added/updated docstrings for auth methods. - exislow_
* Methods for device authorization have been renamed considered private. - exislow_

v0.8.1
------
* Typings: get_urls() returned value shall be `[str]`. - exislow_
* Remove MQA legacy code leftovers, HIRES naming inconsistency  - exislow_
* Tests: Updated unit test(s) - tehkillerbee_

v0.8.0
------
* BREAKING: MQA, Sony 360 audio no longer supported July 24th 2024; removed references to these formats. - tehkillerbee_
* Bugfix: Logical loop of is_encrypted / encryption_key - TooYoungTooSimp_
* Tests: Added additional playlist, folder tests. - tehkillerbee_
* Feature: Add support for playlist merging. - tehkillerbee_
* Added trn to playlist object for convenience. - tehkillerbee_
* Set limits from argument in all relevant methods. - tehkillerbee_
* Feature: Use v2 endpoint for playlist creation. - tehkillerbee_
* Feature: Add support for playlist folders (#181) - tehkillerbee_
* Feature: Add track to user playlist, user tracks from ISRC (#96) - tehkillerbee_
* Feature: Add optional fn_print to Session::login_session_file - GioF71_
* Feature: Add support for moving playlist items (#116) - tehkillerbee_
* Feature: Allow adding items multiple times to the same playlist - tehkillerbee_
* Feature: Add support for adding items to a playlists at a specific position (#116) - tehkillerbee_
* Feature: Set UserPlaylist public/private. Add method for getting public user playlists. - tehkillerbee_
* Feature: Remove multiple items from UserPlaylist. (Fixes #259) - tehkillerbee_
* Remove deprecated username/pass login method (Fixes #279) - tehkillerbee_
* Populate the track/items.album attributes from the parent Album object. Updated tests (Fixes #281) - tehkillerbee_
* Added clarifications to video_url method. Check video URLs for all available video qualities (Fixes #257) - tehkillerbee_
* Tests: Fix all tests that previously failed. - tehkillerbee_
* Use enum to specify default audio / video quality - tehkillerbee_
* Bugfix: Recent TIDAL changes resulted in missing Mix not causing a ObjectNotFound exception. - tehkillerbee_
* Bugfix: Ensure manifest.codecs always uses a Codec type for both MPD and BTS. - tehkillerbee_
* Added additional tests to verify stream formats (Relates to #252) - tehkillerbee_
* BREAKING: Fix naming of getters to align with python naming convention and avoid confusion (Fixes #255) - tehkillerbee_
* Bugfix: Use correct internal type int for relevant IDs (Fixes #260) - tehkillerbee_
* Bugfix: Fix linting for audio_modes. Update tests (Fixes #261) - tehkillerbee_
* Feat.: Provide "Share Link", "Listen link" as an attribute to album/artist/media/playlist/. Update relevant tests (Fixes #266) - tehkillerbee_
* Allow switching authentication method oauth/pkce for tests. Default: oauth - tehkillerbee_
* Tests: Added track stream tests (BTS, MPD) - tehkillerbee_
* Bugfix: Always use last element in segment timeline. (Fixes #273) - tehkillerbee_
* Add method to get detailed request error response if an error occurred during request. - tehkillerbee_
* Tests: Add tests tests for ISRC, barcode methods and cleanup exception handling. - tehkillerbee_
* Feat.: Add support to get tracks by ISRC. - tehkillerbee_, M4TH1EU_
* Feat.: Add support to get albums by Barcode ID (UPC). - tehkillerbee_, M4TH1EU_
* Feat.: Add support for a custom base url in `request()` and `basic_request()` to use the new openapi. - M4TH1EU_

v0.7.6
------
* Fix: Set token type correctly for OAuth/PKCE authentication - tehkillerbee_
* Revert to using enums with str support for relevant classes - tehkillerbee_, exislow_
* Removed return types from method names for consistency, added deprecation warnings - exislow_

v0.7.5
------
* Fix: Use wide image when no square picture is available. - tehkillerbee_
* Feat.: Added HiRes page. - tehkillerbee_
* Feat.: Handle missing Stream fields gracefully. Get stream audio resolution (bit depth, rate) as tuple. - tehkillerbee_
* Feat.: Added misc helper functions for audio mode, get available audio mode for media. - tehkillerbee_
* Feat.: Added misc. fields to album. Get audio resolution for album + individual tracks. - tehkillerbee_
* Feat.: Added MPEG-DASH to HLS stream parsing, Added MPEG-DASH stream example. - tehkillerbee_
* Set default artist IMG if missing. Use default album IMG URI instead of direct URL. - tehkillerbee_
* Bugfix: Make sure is_pkce state is set when pkce_login_url() is used directly. - tehkillerbee_
* Tests: Added misc tests for ObjectNotFound - tehkillerbee_
* Error handling: Handle TooManyRequests exceptions gracefully. - tehkillerbee_
* Error handling: Handle ObjectNotFound exceptions gracefully.  - tehkillerbee_
* Tests: Fix misc tests broken by Tidal. - tehkillerbee_
* Bugfix: Fix pkce token refresh. - tehkillerbee_
* Bugfix: Load/store PKCE state from file using wrong client_id. - tehkillerbee_
* Feat.: Improved error handling (Missing albums, missing lyrics, missing track url etc.). - tehkillerbee_
* Bugfix: Page Recursion into Categories. - quodrum-glas_

v0.7.4
------
* Load/store OAuth/PKCE session to file - tehkillerbee_
* Add PKCE login for HiRes - exislow_, arnesongit_
* Include request response on error. Print as warning - tehkillerbee_
* Fix tests - tehkillerbee_
* Bugfixes (artist.get_similar) - tehkillerbee_
* Favourite mixes refactoring - jozefKruszynski_
* Add typings for Playlist, UserPlaylist, Pages - arusahni_
* Update favorites.tracks to accept order and orderDirection params - Jimmyscene_

v0.7.3
------
* Official support for HI_RES FLAC quality - tehkillerbee_
* Add helper functions to set audio/video quality for current session - tehkillerbee_
* Added missing WELCOME_MIX MixType - tehkillerbee_
* Various image bugfixes - tehkillerbee_
* Add "for_you" page - tehkillerbee_
* Various test, poetry bugfixes - 2e0byo_
* Add typings for Artists and Users - arusahni_
* Add media metadata - jozefKruszynski_
* Add option to limit track radio length - jozefKruszynski_
* Downgrade minimum required version of requests JoshMock_



v0.7.2
------
* (BREAKING!) Drop support for python3.8 and older
* Improved tests - 2e0byo_
* Add type to album object - jozefKruszynski_
* Add mix images and tests - jozefKruszynski_
* Add mypy and fix immediate typing errors - arusahni_
* New attribute to media.Track() class: 'full_name' - WilliamGuisan_
* Fix Track.stream() method - ssnailed_
* Fixed key error for gender when parsing user json - mkaufhol_
* Drop (almost) all user data we don't use. - 2e0byo_
* Add typing for media, genres, mixes, and albums - arusahni_
* Replace TypedDict and NamedTuple with dataclasses - arusahni_
* Fix circular Imports and Typing - PretzelVector_

v0.7.1
------
* Quick fix for "got key error 'picture'" error. - BlackLight_
* Bring back Radio support - bjesus_
* Added function for multiple deletions at once bloedboemmel_
* Use UTC instead of local time for expiry_time lutzbuerkle_

v0.7.0
------

* (BREAKING!) Removed obsolete parameter session_id from load_oauth_session - lutzbuerkle_
* (BREAKING!) Drop support for python2.7 - morguldir_
* (BREAKING!) Change the architecture of the library to allow for using more files, see the migration guide - morguldir_
* Add support for tidal pages (e.g. home, videos and explore in the web ui) - morguldir_
* Add support for parsing mixes and retrieving the media - morguldir_
* Get rid of the old genre and mood support, you can now find them in the pages instead - morguldir_
* Update almost all of the json parsing and classes to include more fields - morguldir_
* Add complete docstrings to many of the functions - morguldir_
* Tests now cover almost all of the code - morguldir_
* Pylint scores are now much higher - morguldir_
* Add option to retrieve master quality tracks (I can't test this, but I believe it works as of writing) - morguldir_
* Add a few documentation pages explaining the basics - morguldir_
* Add support for modifying playlists - morguldir_
* Add a parameter to always fetch the track album if it's not provided - divadsn_
* Add function to retrieve the year and date from either the release data or the stream start date - divadsn_
* Improve the performance of the internal get_items() function by using extend - BlackLight_
* Properly deal with the api returning non-json results - BlackLight_
* Add support for retrieving the reviews of an album - retired-guy_


v0.6.10
-------
* Update the client secret - 1nikolas_
* Use a track url endpoint compatible with the new secret - morguldir_

v0.6.9
------

* Update the client secret - morguldir_
* Fix token_refresh() not correctly including the client secret - morguldir_

v0.6.8
------

* Support OAuth login through login_oauth_simple() and login_oauth() - morguldir_
* Support loading an OAuth session through load_oauth_session() - morguldir_
* Include more info when a request fails - morguldir_

v0.6.7
------

* Fix wimp images not resolving - ktnrg45_
* Made the favorite playlists function also return created playlists - morguldir_

v0.6.6
------

* Update api token and slightly obfuscate it - morguldir_

v0.6.5
------

* Update api token - morguldir_

v0.6.4
------

* Add parameter to search() allowing for more results (up to 300) - morguldir_
* Fix get_track_url() not returning anything - morguldir_

v0.6.3
------

* Fix quality options using enum names instead of values - morguldir_
* Handle situations where tidal doesn't set the version tag - morguldir_

v0.6.2
------

* Update lossless token - morguldir_
* Always use the same api token - morguldir_
* Include additional info when logging fails - morguldir_
* Make user_id and country_code optional when using load_session() - morguldir_
* Add version tag for Track - Husky22_
* Switch to netlify for documentation - morguldir_

.. _morguldir: https://github.com/morguldir
.. _Husky22: https://github.com/Husky22
.. _ktnrg45: https://github.com/ktnrg45
.. _1nikolas: https://github.com/1nikolas
.. _divadsn: https://github.com/divadsn
.. _BlackLight: https://github.com/BlackLight
.. _lutzbuerkle: https://github.com/lutzbuerkle
.. _retired-guy: https://github.com/retired-guy
.. _bjesus: https://github.com/bjesus
.. _bloedboemmel: https://github.com/bloedboemmel
.. _2e0byo: https://github.com/2e0byo
.. _jozefKruszynski: https://github.com/jozefKruszynski
.. _arusahni: https://github.com/arusahni
.. _WilliamGuisan: https://github.com/WilliamGuisan
.. _ssnailed: https://github.com/ssnailed
.. _mkaufhol: https://github.com/mkaufhol
.. _PretzelVector: https://github.com/PretzelVector
.. _tehkillerbee: https://github.com/tehkillerbee
.. _JoshMock: https://github.com/JoshMock
.. _exislow: https://github.com/exislow
.. _arnesongit: https://github.com/arnesongit
.. _Jimmyscene: https://github.com/Jimmyscene
.. _quodrum-glas: https://github.com/quodrum-glas
.. _M4TH1EU: https://github.com/M4TH1EU
.. _GioF71: https://github.com/GioF71
.. _TooYoungTooSimp: https://github.com/TooYoungTooSimp
.. _C0rn3j: https://github.com/C0rn3j
.. _Nokse22: https://github.com/Nokse22
.. _nilathedragon: https://github.com/nilathedragon
.. _semohr: https://github.com/semohr
.. _rafrombrc: https://github.com/rafrombrc

