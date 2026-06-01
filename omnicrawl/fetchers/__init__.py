"""抓取器模块"""

from omnicrawl.fetchers.base import FetchMode, FetchResult, BaseFetcher
from omnicrawl.fetchers.http_fetcher import HttpFetcher
from omnicrawl.fetchers.browser_fetcher import BrowserFetcher
from omnicrawl.fetchers.camoufox_fetcher import CamoufoxFetcher
from omnicrawl.fetchers.stealth_fetcher import StealthFetcher

__all__ = [
    "FetchMode", "FetchResult", "BaseFetcher",
    "HttpFetcher", "BrowserFetcher", "CamoufoxFetcher", "StealthFetcher",
]
