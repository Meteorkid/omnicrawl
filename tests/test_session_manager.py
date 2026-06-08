"""SessionManager 单元测试（全部 mock，无真实浏览器）"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from omnicrawl.session.manager import SessionManager, BrowserHandle, Session
from omnicrawl.fetchers.base import FetchMode


# ===========================================================================
# BrowserHandle / Session 数据类
# ===========================================================================

class TestDataClasses:
    def test_browser_handle_defaults(self):
        bh = BrowserHandle(id="1", name="test", mode=FetchMode.HTTP)
        assert bh.id == "1"
        assert bh.name == "test"
        assert bh.mode == FetchMode.HTTP
        assert bh.desc == ""
        assert bh.proxy is None
        assert bh._browser is None
        assert bh._sessions == {}
        assert bh._cookies == {}

    def test_session_defaults(self):
        s = Session(name="s1", browser_id="b1")
        assert s.name == "s1"
        assert s.browser_id == "b1"
        assert s._page is None
        assert s._cookies == {}


# ===========================================================================
# create_browser
# ===========================================================================

class TestCreateBrowser:
    @pytest.mark.asyncio
    async def test_create_basic(self):
        mgr = SessionManager()
        bh = await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        assert bh.name == "main"
        assert bh.mode == FetchMode.CAMOUFOX
        assert bh.id  # uuid 非空

    @pytest.mark.asyncio
    async def test_create_with_desc_and_proxy(self):
        mgr = SessionManager()
        bh = await mgr.create_browser(
            "51job", mode=FetchMode.CAMOUFOX,
            desc="51job 登录态", proxy="http://p1:8080",
        )
        assert bh.desc == "51job 登录态"
        assert bh.proxy == "http://p1:8080"

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_existing(self):
        mgr = SessionManager()
        bh1 = await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        bh2 = await mgr.create_browser("main", mode=FetchMode.STEALTH)
        assert bh1 is bh2  # 同一个实例
        assert bh1.mode == FetchMode.CAMOUFOX  # 保留第一次的模式

    @pytest.mark.asyncio
    async def test_create_multiple(self):
        mgr = SessionManager()
        await mgr.create_browser("a", mode=FetchMode.HTTP)
        await mgr.create_browser("b", mode=FetchMode.BROWSER)
        assert len(mgr.list_browsers()) == 2


# ===========================================================================
# open_session
# ===========================================================================

class TestOpenSession:
    @pytest.mark.asyncio
    async def test_open_basic(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "search")
        assert session.name == "search"
        assert session.browser_id == mgr._browsers["main"].id

    @pytest.mark.asyncio
    async def test_open_auto_name(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main")
        assert session.name.startswith("main_")

    @pytest.mark.asyncio
    async def test_open_duplicate_returns_existing(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        s1 = await mgr.open_session("main", "search")
        s2 = await mgr.open_session("main", "search")
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_open_nonexistent_browser_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError, match="不存在"):
            await mgr.open_session("nope")

    @pytest.mark.asyncio
    async def test_open_on_http_mode_raises(self):
        mgr = SessionManager()
        await mgr.create_browser("http", mode=FetchMode.HTTP)
        with pytest.raises(ValueError, match="HTTP 模式"):
            await mgr.open_session("http", "test")

    @pytest.mark.asyncio
    async def test_open_multiple_sessions(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        await mgr.open_session("main", "s1")
        await mgr.open_session("main", "s2")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2


# ===========================================================================
# close_session
# ===========================================================================

class TestCloseSession:
    @pytest.mark.asyncio
    async def test_close_existing(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        await mgr.open_session("main", "search")
        await mgr.close_session("search")
        assert len(mgr.list_sessions()) == 0

    @pytest.mark.asyncio
    async def test_close_nonexistent_warns(self):
        mgr = SessionManager()
        # 不应抛异常
        await mgr.close_session("nope")

    @pytest.mark.asyncio
    async def test_close_preserves_cookies(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "search")
        session._cookies = {"token": "abc123"}
        await mgr.close_session("search")
        browser = mgr._browsers["main"]
        assert browser._cookies == {"token": "abc123"}

    @pytest.mark.asyncio
    async def test_close_calls_page_close(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "search")
        mock_page = AsyncMock()
        session._page = mock_page
        await mgr.close_session("search")
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_page_exception_handled(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "search")
        mock_page = AsyncMock()
        mock_page.close.side_effect = Exception("page crash")
        session._page = mock_page
        # 不应抛异常
        await mgr.close_session("search")


# ===========================================================================
# close_browser
# ===========================================================================

class TestCloseBrowser:
    @pytest.mark.asyncio
    async def test_close_browser_removes_it(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        await mgr.close_browser("main")
        assert len(mgr.list_browsers()) == 0

    @pytest.mark.asyncio
    async def test_close_browser_with_sessions(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        await mgr.open_session("main", "s1")
        await mgr.open_session("main", "s2")
        await mgr.close_browser("main")
        assert len(mgr.list_browsers()) == 0
        assert len(mgr.list_sessions()) == 0

    @pytest.mark.asyncio
    async def test_close_nonexistent_browser_warns(self):
        mgr = SessionManager()
        # 不应抛异常
        await mgr.close_browser("nope")

    @pytest.mark.asyncio
    async def test_close_browser_closes_instance(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        mock_browser = AsyncMock()
        mgr._browsers["main"]._browser = mock_browser
        await mgr.close_browser("main")
        mock_browser.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_browser_instance_exception_handled(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        mock_browser = AsyncMock()
        mock_browser.close.side_effect = Exception("crash")
        mgr._browsers["main"]._browser = mock_browser
        # 不应抛异常
        await mgr.close_browser("main")


# ===========================================================================
# find_browser
# ===========================================================================

class TestFindBrowser:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX, desc="51job 登录态浏览器")
        result = mgr.find_browser("51job")
        assert result is not None
        assert result.name == "main"

    @pytest.mark.asyncio
    async def test_word_match(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX, desc="淘宝 登录 购物")
        # "淘宝" 和 "购物" 分别命中 desc 中的词
        result = mgr.find_browser("淘宝 购物")
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_match(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX, desc="51job")
        result = mgr.find_browser("淘宝")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_manager(self):
        mgr = SessionManager()
        assert mgr.find_browser("anything") is None

    @pytest.mark.asyncio
    async def test_best_match_selected(self):
        mgr = SessionManager()
        await mgr.create_browser("a", mode=FetchMode.CAMOUFOX, desc="51job 搜索")
        await mgr.create_browser("b", mode=FetchMode.CAMOUFOX, desc="51job 登录态 浏览器 搜索")
        # "51job 登录态 浏览器" 分词后 3 个词，"a" 匹配 1 个，"b" 匹配 2 个
        result = mgr.find_browser("51job 登录态 浏览器")
        assert result.name == "b"


# ===========================================================================
# append_desc
# ===========================================================================

class TestAppendDesc:
    @pytest.mark.asyncio
    async def test_append_to_empty(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        mgr.append_desc("main", "登录成功")
        assert mgr._browsers["main"].desc == "登录成功"

    @pytest.mark.asyncio
    async def test_append_to_existing(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX, desc="51job")
        mgr.append_desc("main", "登录成功")
        assert mgr._browsers["main"].desc == "51job | 登录成功"

    @pytest.mark.asyncio
    async def test_append_nonexistent_warns(self):
        mgr = SessionManager()
        # 不应抛异常
        mgr.append_desc("nope", "info")


# ===========================================================================
# list / close_all
# ===========================================================================

class TestListAndCloseAll:
    @pytest.mark.asyncio
    async def test_list_browsers(self):
        mgr = SessionManager()
        await mgr.create_browser("a", mode=FetchMode.HTTP)
        await mgr.create_browser("b", mode=FetchMode.BROWSER)
        browsers = mgr.list_browsers()
        assert len(browsers) == 2

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        mgr = SessionManager()
        await mgr.create_browser("a", mode=FetchMode.CAMOUFOX)
        await mgr.open_session("a", "s1")
        await mgr.open_session("a", "s2")
        assert len(mgr.list_sessions()) == 2

    @pytest.mark.asyncio
    async def test_close_all(self):
        mgr = SessionManager()
        await mgr.create_browser("a", mode=FetchMode.CAMOUFOX)
        await mgr.create_browser("b", mode=FetchMode.CAMOUFOX)
        await mgr.close_all()
        assert len(mgr.list_browsers()) == 0

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with SessionManager() as mgr:
            await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        # 退出后应该全部关闭
        assert len(mgr.list_browsers()) == 0


# ===========================================================================
# _reap_expired_sessions
# ===========================================================================

class TestReapExpired:
    @pytest.mark.asyncio
    async def test_reaps_expired(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "old")
        session.last_used = time.time() - mgr.SESSION_TTL - 1  # 已过期
        await mgr._reap_expired_sessions()
        assert len(mgr.list_sessions()) == 0

    @pytest.mark.asyncio
    async def test_keeps_fresh(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        await mgr.open_session("main", "fresh")
        await mgr._reap_expired_sessions()
        assert len(mgr.list_sessions()) == 1

    @pytest.mark.asyncio
    async def test_reap_closes_page(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "old")
        mock_page = AsyncMock()
        session._page = mock_page
        session.last_used = time.time() - mgr.SESSION_TTL - 1
        await mgr._reap_expired_sessions()
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_reap_page_exception_handled(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        session = await mgr.open_session("main", "old")
        mock_page = AsyncMock()
        mock_page.close.side_effect = Exception("crash")
        session._page = mock_page
        session.last_used = time.time() - mgr.SESSION_TTL - 1
        # 不应抛异常
        await mgr._reap_expired_sessions()


# ===========================================================================
# Session 轮换
# ===========================================================================

class TestSessionRotation:
    def test_should_rotate_by_count(self):
        s = Session(name="s1", browser_id="b1", _max_requests=10)
        for _ in range(10):
            s.tick()
        assert s.should_rotate() is True

    def test_should_rotate_by_age(self):
        s = Session(name="s1", browser_id="b1", _max_age=0)
        assert s.should_rotate() is True

    def test_should_not_rotate_fresh(self):
        s = Session(name="s1", browser_id="b1", _max_requests=100, _max_age=3600)
        assert s.should_rotate() is False

    def test_tick_increments_count(self):
        s = Session(name="s1", browser_id="b1")
        assert s._request_count == 0
        s.tick()
        s.tick()
        assert s._request_count == 2

    @pytest.mark.asyncio
    async def test_rotate_session_basic(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        old_session = await mgr.open_session("main", "search")
        old_session._cookies = {"token": "abc"}
        old_session._request_count = 50

        new_session = await mgr.rotate_session("main", "search")

        assert new_session is not old_session
        assert new_session._request_count == 0
        assert new_session.name == "search"
        # cookie 应保留到浏览器
        assert mgr._browsers["main"]._cookies == {"token": "abc"}

    @pytest.mark.asyncio
    async def test_rotate_closes_old_page(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        old_session = await mgr.open_session("main", "search")
        mock_page = AsyncMock()
        old_session._page = mock_page

        await mgr.rotate_session("main", "search")
        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_session_creates_new(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        new_session = await mgr.rotate_session("main", "new_search")
        assert new_session.name == "new_search"
        assert len(mgr.list_sessions()) == 1

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_browser_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError, match="不存在"):
            await mgr.rotate_session("nope", "s1")

    @pytest.mark.asyncio
    async def test_rotate_page_exception_handled(self):
        mgr = SessionManager()
        await mgr.create_browser("main", mode=FetchMode.CAMOUFOX)
        old_session = await mgr.open_session("main", "search")
        mock_page = AsyncMock()
        mock_page.close.side_effect = Exception("crash")
        old_session._page = mock_page
        # 不应抛异常
        new_session = await mgr.rotate_session("main", "search")
        assert new_session._request_count == 0
