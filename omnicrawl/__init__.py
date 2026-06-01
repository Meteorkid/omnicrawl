"""OmniCrawl — 无所不能的爬虫框架

整合 Scrapling + curl_cffi + Playwright，绕过 WAF，LLM 友好输出。

快速开始:
    from omnicrawl import OmniClient

    client = OmniClient()
    response = await client.get("https://example.com")
    print(response.markdown)
"""

from omnicrawl.client import OmniClient
from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.proxy.rotator import ProxyRotator

__version__ = "0.1.0"
__all__ = ["OmniClient", "FetchMode", "FetchResult", "ProxyRotator"]
