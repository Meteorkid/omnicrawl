"""链接发现和过滤 — 从 HTML 中提取、过滤、规范化链接"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse, ParseResult

from omnicrawl.parser.html_parser import HTMLParser
from omnicrawl.utils.logger import get_logger

logger = get_logger("link_extractor")


class LinkExtractor:
    """链接提取器 — 从 HTML 中发现并过滤链接

    用法:
        extractor = LinkExtractor(
            allow_patterns=[r"/article/\d+"],
            deny_patterns=[r"/login", r"/logout"],
            same_domain=True,
        )
        links = extractor.extract(html, base_url="https://example.com")
    """

    def __init__(
        self,
        allow_patterns: Optional[list[str]] = None,
        deny_patterns: Optional[list[str]] = None,
        same_domain: bool = True,
        strip_fragment: bool = True,
        strip_query: bool = False,
        max_links: int = 200,
    ):
        self._allow = [re.compile(p) for p in (allow_patterns or [])]
        self._deny = [re.compile(p) for p in (deny_patterns or [])]
        self._same_domain = same_domain
        self._strip_fragment = strip_fragment
        self._strip_query = strip_query
        self._max_links = max_links
        self._base_domain: Optional[str] = None

    def extract(self, html: str, base_url: str = "") -> list[str]:
        """从 HTML 中提取并过滤链接

        Args:
            html: HTML 内容
            base_url: 基础 URL（用于解析相对链接）

        Returns:
            去重后的链接列表
        """
        if base_url:
            parsed = urlparse(base_url)
            self._base_domain = parsed.netloc

        parser = HTMLParser(html)
        raw_links = parser.links()

        seen: set[str] = set()
        result: list[str] = []

        for href in raw_links:
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # 解析相对链接
            if base_url:
                href = urljoin(base_url, href)

            # 规范化
            href = self._normalize(href)
            if not href:
                continue

            # 去重
            if href in seen:
                continue
            seen.add(href)

            # 过滤
            if not self._should_follow(href):
                continue

            result.append(href)

            if len(result) >= self._max_links:
                break

        logger.debug("从 HTML 中提取 %d 个链接（原始 %d）", len(result), len(raw_links))
        return result

    def _normalize(self, url: str) -> str:
        """规范化 URL"""
        try:
            parsed = urlparse(url)
        except Exception:
            return ""

        # 只接受 http/https
        if parsed.scheme not in ("http", "https"):
            return ""

        # 去掉 fragment 和/或 query
        fragment = "" if self._strip_fragment else parsed.fragment
        query = "" if self._strip_query else parsed.query

        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, query, fragment,
        ))

    def _should_follow(self, url: str) -> bool:
        """判断是否应该跟踪此链接"""
        parsed = urlparse(url)

        # 同域限制
        if self._same_domain and self._base_domain:
            if parsed.netloc != self._base_domain:
                return False

        # deny 模式
        for pattern in self._deny:
            if pattern.search(url):
                return False

        # allow 模式（如果指定了 allow，则必须匹配至少一个）
        if self._allow:
            if not any(p.search(url) for p in self._allow):
                return False

        # 排除静态资源
        if re.search(r"\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|mp4|mp3|zip|pdf)(\?|$)", url, re.IGNORECASE):
            return False

        return True
