"""分布式 CrawlSpider 测试 — 使用 MemoryStore 验证 store 集成。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from omnicrawl.storage.memory import MemoryStore
from omnicrawl.spider.base import CrawlSpider, SpiderItem
from omnicrawl.fetchers.base import FetchResult


@pytest.fixture
def store():
    return MemoryStore()


class SimpleCrawler(CrawlSpider):
    name = "simple"
    start_urls = ["https://example.com"]
    max_depth = 1

    async def parse(self, response):
        yield SpiderItem(data={"title": "test"}, url=response.url)


class TestDistributedCrawlSpider:
    @pytest.mark.asyncio
    async def test_store_injection(self, store):
        spider = SimpleCrawler(store=store)
        assert spider._store is store

    @pytest.mark.asyncio
    async def test_no_store_default(self):
        spider = SimpleCrawler()
        assert spider._store is None

    @pytest.mark.asyncio
    async def test_visited_via_store(self, store):
        spider = SimpleCrawler(store=store)
        assert not await spider._is_visited("https://example.com")
        await spider._mark_visited("https://example.com")
        assert await spider._is_visited("https://example.com")

    @pytest.mark.asyncio
    async def test_visited_local(self):
        spider = SimpleCrawler()
        assert not await spider._is_visited("https://example.com")
        await spider._mark_visited("https://example.com")
        assert await spider._is_visited("https://example.com")

    @pytest.mark.asyncio
    async def test_queue_via_store(self, store):
        spider = SimpleCrawler(store=store)
        await spider._queue_push("https://a.com", 0)
        await spider._queue_push("https://b.com", 1)
        assert await spider._queue_len() == 2

        item = await spider._queue_pop()
        assert item == ("https://a.com", 0)  # FIFO
        item = await spider._queue_pop()
        assert item == ("https://b.com", 1)
        assert await spider._queue_pop() is None

    @pytest.mark.asyncio
    async def test_queue_local(self):
        spider = SimpleCrawler()
        await spider._queue_push("https://a.com", 0)
        assert await spider._queue_len() == 1
        item = await spider._queue_pop()
        assert item == ("https://a.com", 0)

    @pytest.mark.asyncio
    async def test_queue_empty_pop(self, store):
        spider = SimpleCrawler(store=store)
        assert await spider._queue_pop() is None

    @pytest.mark.asyncio
    async def test_queue_extend(self, store):
        spider = SimpleCrawler(store=store)
        await spider._queue_extend([("https://a.com", 0), ("https://b.com", 1)])
        assert await spider._queue_len() == 2

    @pytest.mark.asyncio
    async def test_store_prefix(self, store):
        spider = SimpleCrawler(store=store)
        await spider._mark_visited("https://example.com")
        # 数据应存在带前缀的 key 中
        assert await store.sismember("crawl:simple:visited", "https://example.com")

    @pytest.mark.asyncio
    async def test_checkpoint_noop_with_store(self, store, tmp_path):
        spider = SimpleCrawler(store=store)
        spider.checkpoint_file = str(tmp_path / "state.json")
        spider._save_checkpoint()  # 不应写文件
        assert not (tmp_path / "state.json").exists()

    @pytest.mark.asyncio
    async def test_checkpoint_load_noop_with_store(self, store):
        spider = SimpleCrawler(store=store)
        result = spider._load_checkpoint()
        assert result is False

    @pytest.mark.asyncio
    async def test_crawl_with_store(self, store):
        """测试使用 store 的完整爬取流程"""
        mock_result = FetchResult(
            url="https://example.com",
            status_code=200,
            html="<html><a href='/page2'>link</a></html>",
            markdown="# Test",
            text="Test",
            headers={},
            cookies={},
            mode_used="http",
            elapsed=0.1,
        )

        with patch("omnicrawl.OmniClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_result)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            spider = SimpleCrawler(store=store)
            spider.max_depth = 0  # 不跟踪链接
            items = await spider.run()

            assert len(items) == 1
            assert items[0].data["title"] == "test"
            # 验证 store 中有 visited 记录
            assert await store.sismember("crawl:simple:visited", "https://example.com")
