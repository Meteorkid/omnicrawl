"""OmniCrawl — 无所不能的爬虫框架

整合 Scrapling + curl_cffi + Camoufox + Playwright，绕过 WAF，LLM 友好输出。

快速开始:
    from omnicrawl import OmniClient

    client = OmniClient()
    response = await client.get("https://example.com")
    print(response.markdown)
"""

from omnicrawl.client import OmniClient
from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.proxy.rotator import ProxyRotator
from omnicrawl.proxy.validator import ProxyValidator
from omnicrawl.fingerprint.tls import TLSFingerprint
from omnicrawl.anti_detect.waf_bypass import WAFBypass
from omnicrawl.anti_detect.rate_limiter import RateLimiter
from omnicrawl.anti_detect.fingerprint_consistency import FingerprintConsistency, BrowserIdentity
from omnicrawl.anti_detect.captcha_solver import CaptchaSolver, CaptchaDetector, CaptchaType
from omnicrawl.session.manager import SessionManager, BrowserHandle, Session
from omnicrawl.parser.html_parser import HTMLParser
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.parser.interactive_state import InteractiveStateExtractor, PageState, InteractiveElement
from omnicrawl.spider.smart_spider import SmartSpider, ApiEndpoint, NetworkCapture

__version__ = "0.2.0"
__all__ = [
    # Core
    "OmniClient",
    "FetchMode",
    "FetchResult",
    # Proxy
    "ProxyRotator",
    "ProxyValidator",
    # Fingerprint
    "TLSFingerprint",
    "FingerprintConsistency",
    "BrowserIdentity",
    # Anti-detect
    "WAFBypass",
    "RateLimiter",
    "CaptchaSolver",
    "CaptchaDetector",
    "CaptchaType",
    # Session
    "SessionManager",
    "BrowserHandle",
    "Session",
    # Parser
    "HTMLParser",
    "MarkdownConverter",
    "InteractiveStateExtractor",
    "PageState",
    "InteractiveElement",
    # Spider
    "SmartSpider",
    "ApiEndpoint",
    "NetworkCapture",
]
