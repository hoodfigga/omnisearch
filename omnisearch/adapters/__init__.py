from omnisearch.adapters.base import BaseSourceAdapter
from omnisearch.adapters.youtube import YouTubeAdapter
from omnisearch.adapters.vimeo import VimeoAdapter
from omnisearch.adapters.dailymotion import DailymotionAdapter
from omnisearch.adapters.internet_archive import InternetArchiveAdapter
from omnisearch.adapters.peertube import PeerTubeAdapter
from omnisearch.adapters.mrss import MRSSAdapter
from omnisearch.adapters.generic_web import GenericWebAdapter
from omnisearch.adapters.open_web import OpenWebDiscoveryAdapter
from omnisearch.adapters.adult_web import AdultVideoNetworkAdapter
from omnisearch.adapters.file_hosts import FileHostingAdapter

__all__ = [
    "BaseSourceAdapter",
    "YouTubeAdapter",
    "VimeoAdapter",
    "DailymotionAdapter",
    "InternetArchiveAdapter",
    "PeerTubeAdapter",
    "MRSSAdapter",
    "GenericWebAdapter",
    "OpenWebDiscoveryAdapter",
    "AdultVideoNetworkAdapter",
    "FileHostingAdapter",
]
