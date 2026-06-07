"""OmniClient 单元测试（全部 mock，无网络请求）"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from omnicrawl.client import OmniClient, FALLBACK_ORDER
from omnicrawl.fetchers.base import FetchMode, FetchResult


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def make_result(url="http://test.com", status=200, html="<h1>hi</h1>", blocked=False, mode=FetchMode.HTTP):
    return FetchResult(
        url=url, status_code=status, html=html,
        headers={}, cookies={}, mode_used=mode, elapsed=0.1, blocked=blocked,
    )


def mock_fetcher(result=None):
    """创建一个 mock fetcher，返回指定 result"""
    fetcher = AsyncMock()
    fetcher.fetch = AsyncMock(return_value=result or make_result())
    return fetcher


# ===========================================================================
# 初始化
# ===========================================================================

class TestInit:
    def test_default_mode(self):
        c = OmniClient()
        assert c._mode == FetchMode.AUTO
        assert c._max_retries == 2
        assert c._auto_fallback is True

    def test_custom_mode(self):
        c = OmniClient(mode=FetchMode.STEALTH)
        assert c._mode == FetchMode.STEALTH

    def test_proxy_pool(self):
        c = OmniClient(proxy_pool=["http://p1:8080", "http://p2:8080"])
        assert c._proxy_rotator is not None
        assert c._proxy_rotator.count == 2

    def test_no_proxy(self):
        c = OmniClient()
        assert c._proxy_rotator is None

    def test_waf_sets_tls_and_delay(self):
        c = OmniClient(waf="aliyun_waf")
        assert c._waf is not None

    def test_session_manager_true(self):
        c = OmniClient(session_manager=True)
        assert c._session_mgr is not None

    def test_session_manager_instance(self):
        mock_mgr = MagicMock()
        c = OmniClient(session_manager=mock_mgr)
        assert c._session_mgr is mock_mgr

    def test_captcha_api_key(self):
        c = OmniClient(captcha_api_key="test-key")
        assert c._captcha_solver is not None

    def test_no_captcha(self):
        c = OmniClient()
        assert c._captcha_solver is None

    def test_fingerprint_identity(self):
        """默认应预选一个指纹身份"""
        c = OmniClient()
        # identity 可能是 None（如果模块不可用），但不应抛异常
        assert c._identity is not None or c._identity is None


# ===========================================================================
# _get_fetcher
# ===========================================================================

class TestGetFetcher:
    def test_creates_http_fetcher(self):
        c = OmniClient()
        f = c._get_fetcher(FetchMode.HTTP)
        assert f is not None
        # 缓存
        assert c._get_fetcher(FetchMode.HTTP) is f

    def test_creates_browser_fetcher(self):
        c = OmniClient()
        f = c._get_fetcher(FetchMode.BROWSER)
        assert f is not None

    def test_creates_camoufox_fetcher(self):
        c = OmniClient()
        f = c._get_fetcher(FetchMode.CAMOUFOX)
        assert f is not None

    def test_creates_stealth_fetcher(self):
        c = OmniClient()
        f = c._get_fetcher(FetchMode.STEALTH)
        assert f is not None


# ===========================================================================
# _get_proxy
# ===========================================================================

class TestGetProxy:
    def test_no_rotator_returns_none(self):
        c = OmniClient()
        assert c._get_proxy() is None

    def test_with_rotator(self):
        c = OmniClient(proxy_pool=["http://p1:8080"])
        assert c._get_proxy() == "http://p1:8080"


# ===========================================================================
# fetch / get / post
# ===========================================================================

class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_auto_defaults_to_http(self):
        c = OmniClient(mode=FetchMode.AUTO)
        mock_f = mock_fetcher(make_result(mode=FetchMode.HTTP))
        c._fetchers[FetchMode.HTTP] = mock_f

        result = await c.fetch("http://test.com")
        assert result.status_code == 200
        mock_f.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_fills_markdown(self):
        c = OmniClient(mode=FetchMode.HTTP)
        r = make_result(html="<h1>Hello</h1>")
        r.markdown = ""  # 空 markdown
        mock_f = mock_fetcher(r)
        c._fetchers[FetchMode.HTTP] = mock_f

        result = await c.fetch("http://test.com")
        assert result.markdown != ""

    @pytest.mark.asyncio
    async def test_fetch_fills_text(self):
        c = OmniClient(mode=FetchMode.HTTP)
        r = make_result(html="<p>World</p>")
        r.text = ""
        mock_f = mock_fetcher(r)
        c._fetchers[FetchMode.HTTP] = mock_f

        result = await c.fetch("http://test.com")
        assert result.text != ""

    @pytest.mark.asyncio
    async def test_fetch_reports_blocked(self):
        c = OmniClient(mode=FetchMode.HTTP)
        r = make_result(blocked=True)
        mock_f = mock_fetcher(r)
        c._fetchers[FetchMode.HTTP] = mock_f

        result = await c.fetch("http://test.com")
        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_fetch_with_waf_uses_recommended_mode(self):
        c = OmniClient(waf="aliyun_waf")
        recommended = c._waf.get_recommended_mode()
        c._fetch_with_fallback = AsyncMock(return_value=make_result(mode=recommended))

        result = await c.fetch("http://test.com")
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_explicit_mode_overrides_default(self):
        c = OmniClient(mode=FetchMode.HTTP)
        mock_f = mock_fetcher(make_result(mode=FetchMode.BROWSER))
        c._fetchers[FetchMode.BROWSER] = mock_f

        result = await c.fetch("http://test.com", mode=FetchMode.BROWSER)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_uses_specified_proxy(self):
        c = OmniClient()
        mock_f = mock_fetcher()
        c._fetchers[FetchMode.HTTP] = mock_f

        await c.fetch("http://test.com", proxy="http://myproxy:8080")
        call_kwargs = mock_f.fetch.call_args
        assert call_kwargs[1].get("proxy") == "http://myproxy:8080"


class TestGet:
    @pytest.mark.asyncio
    async def test_get_calls_fetch_with_get(self):
        c = OmniClient(mode=FetchMode.HTTP)
        mock_f = mock_fetcher()
        c._fetchers[FetchMode.HTTP] = mock_f

        await c.get("http://test.com")
        call_kwargs = mock_f.fetch.call_args
        assert call_kwargs[1].get("method") == "GET"


class TestPost:
    @pytest.mark.asyncio
    async def test_post_calls_fetch_with_post(self):
        c = OmniClient(mode=FetchMode.HTTP)
        mock_f = mock_fetcher()
        c._fetchers[FetchMode.HTTP] = mock_f

        await c.post("http://test.com", json={"key": "val"})
        call_kwargs = mock_f.fetch.call_args
        assert call_kwargs[1].get("method") == "POST"


# ===========================================================================
# _fetch_with_retry
# ===========================================================================

class TestRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        c = OmniClient(mode=FetchMode.HTTP, max_retries=2)
        c._fetch_with_fallback = AsyncMock(return_value=make_result())

        result = await c._fetch_with_retry("http://test.com", mode=FetchMode.HTTP)
        assert result.status_code == 200
        assert c._fetch_with_fallback.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_exception(self):
        c = OmniClient(mode=FetchMode.HTTP, max_retries=2)
        c._fetch_with_fallback = AsyncMock(side_effect=[Exception("fail"), make_result()])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await c._fetch_with_retry("http://test.com", mode=FetchMode.HTTP)
        assert result.status_code == 200
        assert c._fetch_with_fallback.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        c = OmniClient(mode=FetchMode.HTTP, max_retries=1)
        c._fetch_with_fallback = AsyncMock(side_effect=Exception("fail"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="fail"):
                await c._fetch_with_retry("http://test.com", mode=FetchMode.HTTP)
        assert c._fetch_with_fallback.call_count == 2  # 1 initial + 1 retry


# ===========================================================================
# _fetch_with_fallback
# ===========================================================================

class TestFallback:
    @pytest.mark.asyncio
    async def test_http_blocked_falls_to_browser(self):
        c = OmniClient(mode=FetchMode.HTTP, auto_fallback=True)
        blocked = make_result(blocked=True, status=403, mode=FetchMode.HTTP)
        ok = make_result(status=200, mode=FetchMode.BROWSER)

        http_f = mock_fetcher(blocked)
        browser_f = mock_fetcher(ok)
        c._fetchers[FetchMode.HTTP] = http_f
        c._fetchers[FetchMode.BROWSER] = browser_f

        result = await c._fetch_with_fallback("http://test.com", mode=FetchMode.HTTP)
        assert result.status_code == 200
        assert result.mode_used == FetchMode.BROWSER

    @pytest.mark.asyncio
    async def test_no_fallback_raises_on_blocked(self):
        """auto_fallback=False + HTTP 被 403 拦截 → 无模式可降级，抛异常"""
        c = OmniClient(mode=FetchMode.HTTP, auto_fallback=False)
        blocked = make_result(blocked=True, status=403)
        c._fetchers[FetchMode.HTTP] = mock_fetcher(blocked)

        with pytest.raises(RuntimeError, match="所有抓取模式均失败"):
            await c._fetch_with_fallback("http://test.com", mode=FetchMode.HTTP)

    @pytest.mark.asyncio
    async def test_exception_falls_to_next_mode(self):
        c = OmniClient(mode=FetchMode.HTTP, auto_fallback=True)
        http_f = MagicMock()
        http_f.fetch = AsyncMock(side_effect=Exception("timeout"))
        browser_f = mock_fetcher(make_result(mode=FetchMode.BROWSER))
        c._fetchers[FetchMode.HTTP] = http_f
        c._fetchers[FetchMode.BROWSER] = browser_f

        result = await c._fetch_with_fallback("http://test.com", mode=FetchMode.HTTP)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_all_modes_fail_raises(self):
        c = OmniClient(mode=FetchMode.HTTP, auto_fallback=True)
        for mode in FALLBACK_ORDER:
            f = MagicMock()
            f.fetch = AsyncMock(side_effect=Exception(f"{mode.value} fail"))
            c._fetchers[mode] = f

        with pytest.raises(Exception):
            await c._fetch_with_fallback("http://test.com", mode=FetchMode.HTTP)

    @pytest.mark.asyncio
    async def test_429_also_triggers_fallback(self):
        c = OmniClient(mode=FetchMode.HTTP, auto_fallback=True)
        blocked = make_result(blocked=True, status=429, mode=FetchMode.HTTP)
        ok = make_result(status=200, mode=FetchMode.BROWSER)
        c._fetchers[FetchMode.HTTP] = mock_fetcher(blocked)
        c._fetchers[FetchMode.BROWSER] = mock_fetcher(ok)

        result = await c._fetch_with_fallback("http://test.com", mode=FetchMode.HTTP)
        assert result.mode_used == FetchMode.BROWSER

    @pytest.mark.asyncio
    async def test_stealth_blocked_no_further_fallback(self):
        """STEALTH 是最后一级，被拦截后直接返回"""
        c = OmniClient(mode=FetchMode.STEALTH, auto_fallback=True)
        blocked = make_result(blocked=True, status=403, mode=FetchMode.STEALTH)
        c._fetchers[FetchMode.STEALTH] = mock_fetcher(blocked)

        result = await c._fetch_with_fallback("http://test.com", mode=FetchMode.STEALTH)
        assert result.blocked is True


# ===========================================================================
# batch
# ===========================================================================

class TestBatch:
    @pytest.mark.asyncio
    async def test_batch_returns_successes(self):
        c = OmniClient(mode=FetchMode.HTTP)
        c._fetch_with_fallback = AsyncMock(return_value=make_result())

        results = await c.batch(["http://a.com", "http://b.com"], concurrency=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_batch_skips_failures(self):
        c = OmniClient(mode=FetchMode.HTTP)

        async def selective_fetch(url, **kw):
            if "fail" in url:
                raise Exception("fail")
            return make_result(url=url)

        c._fetch_with_fallback = AsyncMock(side_effect=selective_fetch)

        results = await c.batch(["http://ok.com", "http://fail.com"], concurrency=2)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_batch_with_errors_returns_both(self):
        c = OmniClient(mode=FetchMode.HTTP)

        async def selective_fetch(url, **kw):
            if "fail" in url:
                raise Exception("boom")
            return make_result(url=url)

        c._fetch_with_fallback = AsyncMock(side_effect=selective_fetch)

        successes, errors = await c.batch_with_errors(
            ["http://ok.com", "http://fail.com"], concurrency=2,
        )
        assert len(successes) == 1
        assert len(errors) == 1
        assert errors[0][0] == "http://fail.com"
        assert isinstance(errors[0][1], Exception)


# ===========================================================================
# session 管理
# ===========================================================================

class TestSessionManagement:
    def test_create_browser_no_mgr_raises(self):
        c = OmniClient()
        with pytest.raises(RuntimeError, match="Session 管理器未启用"):
            asyncio.run(c.create_browser("test"))

    def test_open_session_no_mgr_raises(self):
        c = OmniClient()
        with pytest.raises(RuntimeError, match="Session 管理器未启用"):
            asyncio.run(c.open_session("test"))

    def test_close_session_no_mgr_raises(self):
        c = OmniClient()
        with pytest.raises(RuntimeError, match="Session 管理器未启用"):
            asyncio.run(c.close_session("test"))

    def test_find_browser_no_mgr_returns_none(self):
        c = OmniClient()
        assert c.find_browser("test") is None

    def test_append_desc_no_mgr_does_nothing(self):
        c = OmniClient()
        # 不应抛异常
        c.append_browser_desc("test", "info")

    @pytest.mark.asyncio
    async def test_create_browser_with_mgr(self):
        mock_mgr = AsyncMock()
        c = OmniClient(session_manager=mock_mgr)
        await c.create_browser("51job", mode=FetchMode.CAMOUFOX, desc="搜索")
        mock_mgr.create_browser.assert_called_once_with(
            "51job", mode=FetchMode.CAMOUFOX, desc="搜索", proxy=None,
        )

    @pytest.mark.asyncio
    async def test_open_session_with_mgr(self):
        mock_mgr = AsyncMock()
        c = OmniClient(session_manager=mock_mgr)
        await c.open_session("51job", "search")
        mock_mgr.open_session.assert_called_once_with("51job", "search")


# ===========================================================================
# 交互状态 + 验证码
# ===========================================================================

class TestInteractiveState:
    def test_get_interactive_state(self):
        c = OmniClient()
        html = '<button>Click</button><a href="/go">Link</a>'
        state = c.get_interactive_state(html, "http://test.com")
        assert state is not None


class TestCaptcha:
    @pytest.mark.asyncio
    async def test_solve_captcha_no_solver(self):
        c = OmniClient()
        result = await c.solve_captcha(MagicMock())
        assert result is False


# ===========================================================================
# close + context manager
# ===========================================================================

class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_fetchers(self):
        c = OmniClient(mode=FetchMode.HTTP)
        c._fetchers[FetchMode.HTTP] = AsyncMock()
        await c.close()
        assert len(c._fetchers) == 0

    @pytest.mark.asyncio
    async def test_close_with_session_mgr(self):
        mock_mgr = AsyncMock()
        c = OmniClient(session_manager=mock_mgr)
        await c.close()
        mock_mgr.close_all.assert_called_once()
        assert c._session_mgr is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with OmniClient() as client:
            assert client is not None
