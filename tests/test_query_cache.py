"""QueryCache 单元测试"""

import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from omnicrawl.utils.cache import QueryCache


class TestQueryCache:
    def test_make_key_deterministic(self):
        cache = QueryCache()
        k1 = cache.make_key("https://example.com", {"q": "python"})
        k2 = cache.make_key("https://example.com", {"q": "python"})
        assert k1 == k2

    def test_make_key_different_params(self):
        cache = QueryCache()
        k1 = cache.make_key("https://example.com", {"q": "python"})
        k2 = cache.make_key("https://example.com", {"q": "java"})
        assert k1 != k2

    def test_make_key_no_params(self):
        cache = QueryCache()
        k = cache.make_key("https://example.com")
        assert isinstance(k, str)
        assert len(k) == 32  # md5 hex

    def test_record_and_check(self):
        cache = QueryCache(ttl=60)
        key = "test_key"
        assert cache.is_known_empty(key) is False
        cache.record_empty(key)
        assert cache.is_known_empty(key) is True

    def test_ttl_expiry(self):
        cache = QueryCache(ttl=0)  # 立即过期
        key = "test_key"
        cache.record_empty(key)
        # TTL=0 意味着记录后立即过期
        assert cache.is_known_empty(key) is False

    def test_max_size_eviction(self):
        cache = QueryCache(ttl=3600, max_size=5)
        for i in range(10):
            cache.record_empty(f"key_{i}")
        assert cache.size <= 5

    def test_clear(self):
        cache = QueryCache(ttl=60)
        cache.record_empty("key1")
        cache.record_empty("key2")
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_size_property(self):
        cache = QueryCache(ttl=60)
        assert cache.size == 0
        cache.record_empty("k1")
        assert cache.size == 1


class TestClientQueryCache:
    """测试 Client 集成"""

    @pytest.mark.asyncio
    async def test_cache_skip_empty_result(self):
        """第二次请求相同空 URL 应被跳过"""
        from omnicrawl.client import OmniClient
        from omnicrawl.fetchers.base import FetchResult, FetchMode

        client = OmniClient(query_cache_ttl=60)
        # Mock markdown 转换器避免空 html 处理报错
        client._converter = MagicMock()
        client._converter.convert.return_value = ""

        # Mock fetcher 返回空结果
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch.return_value = FetchResult(
            url="https://empty.com", html="", status_code=404,
            headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1,
        )

        # Patch _get_fetcher 返回 mock
        original_get_fetcher = client._get_fetcher
        def _mock_get_fetcher(mode):
            return mock_fetcher
        client._get_fetcher = _mock_get_fetcher

        # 第一次请求
        result1 = await client.fetch("https://empty.com")
        assert result1.html == ""
        assert mock_fetcher.fetch.call_count == 1

        # 第二次请求应被缓存跳过
        result2 = await client.fetch("https://empty.com")
        assert result2.status_code == 0
        assert "缓存" in result2.text
        # fetcher 不应被再次调用
        assert mock_fetcher.fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_no_cache_when_disabled(self):
        """query_cache_ttl=0 时不应使用缓存"""
        from omnicrawl.client import OmniClient

        client = OmniClient(query_cache_ttl=0)
        assert client._query_cache is None
