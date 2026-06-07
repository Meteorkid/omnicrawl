"""抓取器基类和通用数据结构"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omnicrawl.parser.interactive_state import PageState


__all__ = ["FetchMode", "FetchResult", "BaseFetcher"]


class FetchMode(Enum):
    """抓取模式"""
    HTTP = "http"          # 纯 HTTP（curl_cffi，最快）
    BROWSER = "browser"    # 浏览器（Playwright，支持 JS）
    CAMOUFOX = "camoufox"  # 反检测浏览器（Firefox 原生修改，绕过 JS 环境检测）
    STEALTH = "stealth"    # 隐身（Scrapling StealthyFetcher）
    AUTO = "auto"          # 自动选择最佳模式


@dataclass
class FetchResult:
    """抓取结果"""
    url: str
    status_code: int
    html: str
    headers: dict
    cookies: dict
    mode_used: FetchMode  # 实际使用的模式
    elapsed: float        # 耗时（秒）
    blocked: bool = False # 是否被 WAF 拦截
    markdown: str = ""    # LLM 友好的 Markdown
    text: str = ""        # 纯文本
    _content: Optional[bytes] = field(default=None, repr=False)
    _interactive_state: Optional[PageState] = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400 and not self.blocked

    @property
    def interactive_state(self):
        """获取索引式交互状态（Agent 友好）

        Returns:
            PageState，调用 .to_state_text() 获取文本输出
        """
        if self._interactive_state is None and self.html:
            from omnicrawl.parser.interactive_state import InteractiveStateExtractor
            extractor = InteractiveStateExtractor()
            self._interactive_state = extractor.extract(self.html, url=self.url)
        return self._interactive_state

    def __repr__(self) -> str:
        return f"<FetchResult {self.status_code} [{self.mode_used.value}] {self.url[:60]}>"


class BaseFetcher(ABC):
    """抓取器基类"""

    mode: FetchMode

    @abstractmethod
    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResult:
        """执行抓取"""
        ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
