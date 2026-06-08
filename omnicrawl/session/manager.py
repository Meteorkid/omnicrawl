"""Session 管理器 — 统一的浏览器生命周期和 Session 管理

灵感来自 BrowserAct 的"浏览器=身份，Session=工作区"模型。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from omnicrawl.fetchers.base import FetchMode
from omnicrawl.utils.logger import get_logger

logger = get_logger("session")

__all__ = ["BrowserHandle", "Session", "SessionManager"]


@dataclass
class BrowserHandle:
    """浏览器句柄 — 代表一个持久的浏览器身份"""
    id: str                          # 唯一 ID
    name: str                        # 人类可读名称
    mode: FetchMode                  # 抓取模式
    desc: str = ""                   # 语义描述（用于任务匹配）
    proxy: Optional[str] = None      # 绑定的代理
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    _browser: object = field(default=None, repr=False)  # 底层浏览器实例
    _sessions: dict = field(default_factory=dict)        # {session_name: Session}
    _cookies: dict = field(default_factory=dict)         # 持久化 cookie


@dataclass
class Session:
    """工作区 Session — 一个浏览器内的独立工作单元"""
    name: str
    browser_id: str
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    _request_count: int = 0             # 已发请求计数
    _max_requests: int = 100            # 最大请求数（超过则轮换）
    _max_age: float = 1800.0            # 最长存活时间（秒，默认 30 分钟）
    _page: object = field(default=None, repr=False)
    _cookies: dict = field(default_factory=dict)

    def should_rotate(self) -> bool:
        """判断是否需要轮换（按请求计数或存活时间）"""
        if self._request_count >= self._max_requests:
            return True
        if time.time() - self.created_at > self._max_age:
            return True
        return False

    def tick(self):
        """请求计数 +1，更新最后使用时间"""
        self._request_count += 1
        self.last_used = time.time()


class SessionManager:
    """统一的 Session 生命周期管理器

    核心概念：
    - 浏览器 = 身份（独立指纹 + IP + Cookie）
    - Session = 工作区（同浏览器可多 session 共享登录态）
    - desc = 语义记忆（按自然语言描述匹配浏览器）

    用法:
        manager = SessionManager()

        # 创建浏览器
        browser = await manager.create_browser("main", desc="51job 登录态浏览器", mode=FetchMode.CAMOUFOX)

        # 打开 session
        session = await manager.open_session("main", "search_job")

        # 在 session 中操作（返回底层的 page 对象）
        page = session.page
        await page.goto("https://www.51job.com")

        # 关闭 session（cookie 保留到浏览器）
        await manager.close_session("search_job")

        # 按 desc 匹配浏览器
        browser = manager.find_browser("51job")

        # 追加经验
        manager.append_desc("main", "登录成功，使用手机号+验证码")
    """

    # Session 自动回收时间（秒）
    SESSION_TTL = 8 * 3600  # 8 小时

    def __init__(self):
        self._browsers: dict[str, BrowserHandle] = {}
        self._lock = asyncio.Lock()

    async def create_browser(
        self,
        name: str,
        mode: FetchMode,
        desc: str = "",
        proxy: Optional[str] = None,
        **kwargs,
    ) -> BrowserHandle:
        """创建一个新的浏览器身份"""
        async with self._lock:
            if name in self._browsers:
                logger.warning(f"浏览器 '{name}' 已存在，返回已有实例")
                return self._browsers[name]

            browser = BrowserHandle(
                id=str(uuid.uuid4()),
                name=name,
                mode=mode,
                desc=desc,
                proxy=proxy,
            )
            self._browsers[name] = browser
            logger.info(f"创建浏览器: {name} [{mode.value}] desc={desc!r}")
            return browser

    async def open_session(
        self,
        browser_name: str,
        session_name: Optional[str] = None,
    ) -> Session:
        """在同一浏览器中打开新的工作区 Session"""
        async with self._lock:
            await self._reap_expired_sessions()

            if browser_name not in self._browsers:
                raise KeyError(f"浏览器 '{browser_name}' 不存在")

            browser = self._browsers[browser_name]

            # HTTP 模式下不支持 session（无浏览器实例）
            if browser.mode == FetchMode.HTTP:
                raise ValueError(
                    f"浏览器 '{browser_name}' 使用 HTTP 模式，不支持 session。"
                    f"请使用 FetchMode.BROWSER / CAMOUFOX / STEALTH 模式"
                )

            if session_name is None:
                session_name = f"{browser_name}_{uuid.uuid4().hex[:8]}"
            elif session_name in browser._sessions:
                logger.warning(f"Session '{session_name}' 已存在于浏览器 '{browser_name}'，返回已有实例")
                return browser._sessions[session_name]

            session = Session(
                name=session_name,
                browser_id=browser.id,
            )
            browser._sessions[session_name] = session
            browser.last_used = time.time()
            logger.info(f"打开 Session: {session_name} @ 浏览器 {browser_name}")
            return session

    async def close_session(self, session_name: str):
        """关闭 Session，cookie 保留到浏览器"""
        page_to_close = None

        async with self._lock:
            for browser in self._browsers.values():
                if session_name in browser._sessions:
                    session = browser._sessions.pop(session_name)

                    # 将 session 的 cookie 保存到浏览器
                    if session._cookies:
                        browser._cookies.update(session._cookies)
                        logger.debug(f"Session '{session_name}' 的 {len(session._cookies)} 个 cookie 已保存到浏览器 '{browser.name}'")

                    page_to_close = session._page
                    logger.info(f"关闭 Session: {session_name}")
                    break
            else:
                logger.warning(f"Session '{session_name}' 不存在，跳过关闭")
                return

        # 锁外执行 IO 操作
        if page_to_close is not None:
            try:
                await page_to_close.close()
            except Exception as e:
                logger.debug("页面关闭异常: %s", e)

    async def rotate_session(self, browser_name: str, session_name: str) -> Session:
        """轮换 Session — 关闭旧的，打开新的（防指纹关联）

        轮换时机：
        - 请求数达到 _max_requests
        - 存活时间超过 _max_age

        轮换后：
        - 关闭旧 page（cookie 保留到浏览器）
        - 创建新 Session（同名替换）
        - 重置请求计数
        """
        page_to_close = None
        new_session = None

        async with self._lock:
            if browser_name not in self._browsers:
                raise KeyError(f"浏览器 '{browser_name}' 不存在")

            browser = self._browsers[browser_name]
            old_session = browser._sessions.get(session_name)

            if old_session is None:
                # session 不存在，直接创建新的（避免递归调用 open_session 死锁）
                new_session = Session(
                    name=session_name,
                    browser_id=browser.id,
                )
                browser._sessions[session_name] = new_session
                browser.last_used = time.time()
                logger.info("Session '%s' 不存在，创建新的", session_name)
                return new_session

            # 保存 cookie、准备关闭 page
            if old_session._cookies:
                browser._cookies.update(old_session._cookies)
            page_to_close = old_session._page

            # 创建新 Session（同名替换）
            new_session = Session(
                name=session_name,
                browser_id=browser.id,
            )
            browser._sessions[session_name] = new_session
            browser.last_used = time.time()

            logger.info(
                "♻️ Session 已轮换: %s @ %s (请求数=%d, 存活=%.0fs)",
                session_name, browser_name,
                old_session._request_count,
                time.time() - old_session.created_at,
            )

        # 锁外执行 IO 操作
        if page_to_close is not None:
            try:
                await page_to_close.close()
            except Exception as e:
                logger.debug("轮换时页面关闭异常: %s", e)

        return new_session

    async def close_browser(self, browser_name: str):
        """关闭浏览器及其所有 Session"""
        pages_to_close = []
        browser_instance = None

        async with self._lock:
            if browser_name not in self._browsers:
                logger.warning(f"浏览器 '{browser_name}' 不存在，跳过关闭")
                return

            browser = self._browsers.pop(browser_name)

            # 收集需要关闭的 page
            for session in browser._sessions.values():
                if session._page is not None:
                    pages_to_close.append(session._page)

            browser_instance = browser._browser

        # 锁外执行 IO 操作
        for page in pages_to_close:
            try:
                await page.close()
            except Exception as e:
                logger.debug("页面关闭异常: %s", e)

        # 关闭底层浏览器实例
        if browser_instance is not None:
            try:
                if hasattr(browser_instance, "close"):
                    await browser_instance.close()
            except Exception as e:
                logger.warning(f"关闭浏览器 '{browser_name}' 实例异常: {e}")

        logger.info(f"关闭浏览器: {browser_name} (含 {len(pages_to_close)} 个 page)")

    def find_browser(self, task_desc: str) -> Optional[BrowserHandle]:
        """按 desc 语义匹配浏览器

        匹配策略：
        1. 优先精确子串匹配（score=1000）
        2. 回退到分词匹配（按空格分割 task_desc，统计命中的词数）
        """
        task_lower = task_desc.lower()
        best_match: Optional[BrowserHandle] = None
        best_score = 0

        for browser in self._browsers.values():
            score = self._match_score(task_lower, browser.desc.lower())
            if score > best_score:
                best_score = score
                best_match = browser

        if best_match:
            logger.debug(f"按 '{task_desc}' 匹配到浏览器 '{best_match.name}' (score={best_score})")
        else:
            logger.debug(f"按 '{task_desc}' 未匹配到任何浏览器")
        return best_match

    @staticmethod
    def _match_score(query: str, desc: str) -> int:
        """计算 query 与 desc 的匹配分数

        Returns:
            0 = 无匹配, >0 = 命中分数
        """
        # 精确子串匹配：权重远高于分词
        if query in desc:
            return 1000
        # 分词匹配：统计命中的词数
        return sum(1 for word in query.split() if word in desc)

    def append_desc(self, browser_name: str, info: str):
        """追加经验到浏览器 desc"""
        if browser_name not in self._browsers:
            logger.warning(f"浏览器 '{browser_name}' 不存在，无法追加描述")
            return

        browser = self._browsers[browser_name]
        if browser.desc:
            browser.desc += f" | {info}"
        else:
            browser.desc = info
        logger.debug(f"浏览器 '{browser_name}' desc 更新: {browser.desc}")

    def list_browsers(self) -> list[BrowserHandle]:
        """列出所有浏览器"""
        return list(self._browsers.values())

    def list_sessions(self) -> list[Session]:
        """列出所有活跃 session"""
        sessions = []
        for browser in self._browsers.values():
            sessions.extend(browser._sessions.values())
        return sessions

    async def _ensure_browser_instance(self, browser: BrowserHandle):
        """确保底层浏览器实例已创建（懒加载）"""
        async with self._lock:
            if browser._browser is not None:
                return

            logger.info(f"懒加载浏览器实例: {browser.name} [{browser.mode.value}]")

            if browser.mode == FetchMode.BROWSER:
                from omnicrawl.fetchers.browser_fetcher import BrowserFetcher
                fetcher = BrowserFetcher()
                await fetcher._ensure_browser()
                browser._browser = fetcher

            elif browser.mode == FetchMode.CAMOUFOX:
                from omnicrawl.fetchers.camoufox_fetcher import CamoufoxFetcher
                fetcher = CamoufoxFetcher(proxy=browser.proxy)
                await fetcher._ensure_browser()
                browser._browser = fetcher

            elif browser.mode == FetchMode.STEALTH:
                from omnicrawl.fetchers.stealth_fetcher import StealthFetcher
                fetcher = StealthFetcher()
                browser._browser = fetcher

            elif browser.mode == FetchMode.HTTP:
                logger.info(f"浏览器 '{browser.name}' 使用 HTTP 模式，跳过浏览器实例创建")

            else:
                logger.warning(f"浏览器 '{browser.name}' 使用未知模式 {browser.mode.value}，跳过实例创建")

    async def _reap_expired_sessions(self):
        """回收过期 session（调用方需持有 self._lock）"""
        now = time.time()
        pages_to_close = []

        for browser in self._browsers.values():
            expired = [
                name for name, s in browser._sessions.items()
                if now - s.last_used > self.SESSION_TTL
            ]
            for session_name in expired:
                session = browser._sessions.pop(session_name, None)
                if session and session._page is not None:
                    pages_to_close.append(session._page)
                    logger.info(f"回收过期 Session: {session_name}")

        # page.close() 是 IO，但回收是低频操作，此处直接 await
        # 若需优化可收集后在锁外关闭，但会增加复杂度
        for page in pages_to_close:
            try:
                await page.close()
            except Exception as e:
                logger.debug("页面关闭异常: %s", e)

    async def close_all(self):
        """关闭所有浏览器和 session"""
        browser_names = list(self._browsers.keys())
        for name in browser_names:
            await self.close_browser(name)
        logger.info("已关闭所有浏览器")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close_all()
