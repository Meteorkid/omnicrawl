"""Spider 爬虫框架"""

from omnicrawl.spider.base import Spider
from omnicrawl.spider.smart_spider import (
    SmartSpider,
    ApiEndpoint,
    DiscoveryResult,
    NetworkCapture,
)

__all__ = [
    "Spider",
    "SmartSpider",
    "ApiEndpoint",
    "DiscoveryResult",
    "NetworkCapture",
]
