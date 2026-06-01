"""OmniClient 集成测试"""

import pytest
import asyncio
from omnicrawl import OmniClient, FetchMode
from omnicrawl.fetchers.base import FetchResult


class TestOmniClientInit:
    def test_default_mode(self):
        client = OmniClient()
        assert client._mode == FetchMode.AUTO

    def test_custom_mode(self):
        client = OmniClient(mode=FetchMode.STEALTH)
        assert client._mode == FetchMode.STEALTH

    def test_with_proxy_pool(self):
        client = OmniClient(proxy_pool=["http://p1:8080"])
        assert client._proxy_rotator is not None
        assert client._proxy_rotator.count == 1

    def test_with_waf(self):
        client = OmniClient(waf="aliyun_waf")
        assert client._waf is not None

    def test_context_manager(self):
        async def test():
            async with OmniClient() as client:
                assert client is not None
        asyncio.run(test())


class TestOmniClientFetch:
    @pytest.mark.asyncio
    async def test_http_fetch(self):
        async with OmniClient(mode=FetchMode.HTTP) as client:
            result = await client.get("https://example.com")
            assert result.status_code == 200
            assert result.mode_used == FetchMode.HTTP
            assert len(result.markdown) > 0
            assert result.elapsed > 0

    @pytest.mark.asyncio
    async def test_auto_fetch(self):
        async with OmniClient(mode=FetchMode.AUTO) as client:
            result = await client.get("https://example.com")
            assert result.status_code == 200
            # AUTO 模式应该选择 HTTP（最快）
            assert result.mode_used == FetchMode.HTTP

    @pytest.mark.asyncio
    async def test_batch(self):
        async with OmniClient(mode=FetchMode.HTTP) as client:
            results = await client.batch(
                ["https://example.com", "https://example.com"],
                concurrency=2,
            )
            assert len(results) == 2
            for r in results:
                assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_batch_error_handling(self):
        async with OmniClient(mode=FetchMode.HTTP) as client:
            results = await client.batch(
                ["https://example.com", "https://invalid-domain-xyz.com"],
                concurrency=2,
            )
            # 失败的 URL 应该被跳过，成功的仍然返回
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_markdown_conversion(self):
        async with OmniClient(mode=FetchMode.HTTP) as client:
            result = await client.get("https://example.com")
            assert "Example Domain" in result.markdown

    @pytest.mark.asyncio
    async def test_text_extraction(self):
        async with OmniClient(mode=FetchMode.HTTP) as client:
            result = await client.get("https://example.com")
            assert "Example Domain" in result.text


class TestFetchResult:
    def test_ok_true(self):
        r = FetchResult(url="http://x", status_code=200, html="", headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1)
        assert r.ok is True

    def test_ok_false_blocked(self):
        r = FetchResult(url="http://x", status_code=200, html="", headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1, blocked=True)
        assert r.ok is False

    def test_ok_false_status(self):
        r = FetchResult(url="http://x", status_code=403, html="", headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1)
        assert r.ok is False
