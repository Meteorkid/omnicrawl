"""OmniCrawl — 无所不能的爬虫框架

整合 Scrapling + curl_cffi + Camoufox + Playwright，绕过 WAF，LLM 友好输出。

快速开始:
    from omnicrawl import OmniClient

    client = OmniClient()
    response = await client.get("https://example.com")
    print(response.markdown)
"""

__version__ = "0.2.0"

# 延迟导入：首次访问时才 import，避免顶层加载全部模块
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Core
    "OmniClient": ("omnicrawl.client", "OmniClient"),
    "FetchMode": ("omnicrawl.fetchers.base", "FetchMode"),
    "FetchResult": ("omnicrawl.fetchers.base", "FetchResult"),
    # Proxy
    "ProxyRotator": ("omnicrawl.proxy.rotator", "ProxyRotator"),
    "ProxyValidator": ("omnicrawl.proxy.validator", "ProxyValidator"),
    "ProxyScorer": ("omnicrawl.proxy.scorer", "ProxyScorer"),
    "ProxyStats": ("omnicrawl.proxy.scorer", "ProxyStats"),
    # Fingerprint
    "TLSFingerprint": ("omnicrawl.fingerprint.tls", "TLSFingerprint"),
    "FingerprintConsistency": ("omnicrawl.anti_detect.fingerprint_consistency", "FingerprintConsistency"),
    "BrowserIdentity": ("omnicrawl.anti_detect.fingerprint_consistency", "BrowserIdentity"),
    # Anti-detect
    "WAFBypass": ("omnicrawl.anti_detect.waf_bypass", "WAFBypass"),
    "RateLimiter": ("omnicrawl.anti_detect.rate_limiter", "RateLimiter"),
    "CaptchaSolver": ("omnicrawl.anti_detect.captcha_solver", "CaptchaSolver"),
    "CaptchaDetector": ("omnicrawl.anti_detect.captcha_solver", "CaptchaDetector"),
    "CaptchaType": ("omnicrawl.anti_detect.captcha_solver", "CaptchaType"),
    # Session
    "SessionManager": ("omnicrawl.session.manager", "SessionManager"),
    "BrowserHandle": ("omnicrawl.session.manager", "BrowserHandle"),
    "Session": ("omnicrawl.session.manager", "Session"),
    # Parser
    "HTMLParser": ("omnicrawl.parser.html_parser", "HTMLParser"),
    "MarkdownConverter": ("omnicrawl.parser.markdown", "MarkdownConverter"),
    "InteractiveStateExtractor": ("omnicrawl.parser.interactive_state", "InteractiveStateExtractor"),
    "PageState": ("omnicrawl.parser.interactive_state", "PageState"),
    "InteractiveElement": ("omnicrawl.parser.interactive_state", "InteractiveElement"),
    # Spider
    "Spider": ("omnicrawl.spider.base", "Spider"),
    "CrawlSpider": ("omnicrawl.spider.base", "CrawlSpider"),
    "SpiderItem": ("omnicrawl.spider.base", "SpiderItem"),
    "SpiderStats": ("omnicrawl.spider.base", "SpiderStats"),
    "SmartSpider": ("omnicrawl.spider.smart_spider", "SmartSpider"),
    "ApiEndpoint": ("omnicrawl.spider.smart_spider", "ApiEndpoint"),
    "NetworkCapture": ("omnicrawl.spider.smart_spider", "NetworkCapture"),
    "LinkExtractor": ("omnicrawl.spider.link_extractor", "LinkExtractor"),
    "Pipeline": ("omnicrawl.spider.pipeline", "Pipeline"),
    "CleanPipeline": ("omnicrawl.spider.pipeline", "CleanPipeline"),
    "ValidatePipeline": ("omnicrawl.spider.pipeline", "ValidatePipeline"),
    "DedupPipeline": ("omnicrawl.spider.pipeline", "DedupPipeline"),
    "RedisDedupPipeline": ("omnicrawl.spider.pipeline", "RedisDedupPipeline"),
    "JsonFilePipeline": ("omnicrawl.spider.pipeline", "JsonFilePipeline"),
    # Storage
    "StateStore": ("omnicrawl.storage", "StateStore"),
    "MemoryStore": ("omnicrawl.storage", "MemoryStore"),
    # Plugins
    "Plugin": ("omnicrawl.plugins", "Plugin"),
    "PluginManager": ("omnicrawl.plugins", "PluginManager"),
    "LoggingPlugin": ("omnicrawl.plugins", "LoggingPlugin"),
    "StatsPlugin": ("omnicrawl.plugins", "StatsPlugin"),
    "FilterPlugin": ("omnicrawl.plugins", "FilterPlugin"),
    "TransformPlugin": ("omnicrawl.plugins", "TransformPlugin"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module 'omnicrawl' has no attribute {name!r}")
