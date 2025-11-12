# Copyright (C) 2023- The Tidalapi Developers

from .album import Album  # noqa: F401
from .artist import Artist, Role  # noqa: F401
from .genre import Genre  # noqa: F401
from .media import Quality, Track, Video, VideoQuality  # noqa: F401
from .mix import Mix, MixV2  # noqa: F401
from .page import Page  # noqa: F401
from .playlist import Playlist, UserPlaylist  # noqa: F401
from .request import Requests  # noqa: F401
from .session import Config, Session  # noqa: F401
from .user import (  # noqa: F401
    Favorites,
    FetchedUser,
    LoggedInUser,
    PlaylistCreator,
    User,
)

__version__ = "0.8.9"
