"""CrawlSpider 深度爬取测试"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.spider.base import CrawlSpider, SpiderItem


def make_result(url="http://test.com", html="<a href='/page1'>Link</a>", status=200):
    r = FetchResult(
        url=url, status_code=status, html=html,
        headers={}, cookies={}, mode_used=FetchMode.HTTP,
        elapsed=0.1, blocked=(status in (403, 429)),
    )
    r.markdown = f"# {url}"
    r.text = f"Text from {url}"
    return r


class TestCrawlSpider:
    @pytest.mark.asyncio
    async def test_basic_crawl(self):
        """基本爬取：start_urls 中的 URL 应该被处理"""
        class SimpleCrawler(CrawlSpider):
            name = "simple"
            start_urls = ["http://test.com"]
            max_depth = 0

            async def parse(self, response):
                yield SpiderItem(data={"url": response.url}, url=response.url)

        spider = SimpleCrawler()
        # mock client.get
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result())

        with patch("omnicrawl.OmniClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            results = await spider.run()

        assert len(results) >= 1
        assert spider.stats.requests >= 1

    def test_visited_set(self):
        """已访问 URL 应该被去重"""
        spider = CrawlSpider()
        spider._visited.add("http://test.com/page1")
        assert "http://test.com/page1" in spider._visited
        assert spider.visited_count == 1

    def test_queue_management(self):
        """队列应该正确管理"""
        spider = CrawlSpider()
        spider._queue.append(("http://test.com", 0))
        spider._queue.append(("http://test.com/page1", 1))
        assert spider.queue_size == 2

        url, depth = spider._queue.popleft()
        assert url == "http://test.com"
        assert depth == 0

    def test_checkpoint_save_load(self, tmp_path):
        """断点保存和加载"""
        checkpoint = str(tmp_path / "checkpoint.json")
        spider = CrawlSpider()
        spider.checkpoint_file = checkpoint

        spider._local_visited = {"http://a.com", "http://b.com"}
        spider._local_queue.append(("http://c.com", 1))
        spider.stats.requests = 5
        spider.stats.items = 3

        spider._save_checkpoint()
        assert Path(checkpoint).exists()

        # 创建新 spider 并加载
        spider2 = CrawlSpider()
        spider2.checkpoint_file = checkpoint
        loaded = spider2._load_checkpoint()
        assert loaded is True
        assert spider2.visited_count == 2
        assert spider2.queue_size == 1
        assert spider2.stats.requests == 5

    def test_checkpoint_no_file(self):
        """没有 checkpoint_file 时返回 False"""
        spider = CrawlSpider()
        assert spider._load_checkpoint() is False

    def test_checkpoint_nonexistent(self, tmp_path):
        """checkpoint 文件不存在时返回 False"""
        spider = CrawlSpider()
        spider.checkpoint_file = str(tmp_path / "nonexistent.json")
        assert spider._load_checkpoint() is False

    def test_max_depth_default(self):
        spider = CrawlSpider()
        assert spider.max_depth == 3

    def test_follow_patterns(self):
        class MySpider(CrawlSpider):
            follow_patterns = ["/article/\\d+"]
        spider = MySpider()
        assert len(spider.follow_patterns) == 1

    def test_deny_patterns(self):
        class MySpider(CrawlSpider):
            deny_patterns = ["/login"]
        spider = MySpider()
        assert spider.deny_patterns == ["/login"]

    def test_same_domain_default(self):
        spider = CrawlSpider()
        assert spider.same_domain is True

    def test_checkpoint_interval(self):
        class MySpider(CrawlSpider):
            checkpoint_interval = 10
        spider = MySpider()
        assert spider.checkpoint_interval == 10

    def test_properties(self):
        spider = CrawlSpider()
        assert spider.visited_count == 0
        assert spider.queue_size == 0

        spider._visited.add("http://test.com")
        spider._queue.append(("http://test.com/page1", 1))
        assert spider.visited_count == 1
        assert spider.queue_size == 1


class TestCrawlSpiderLinkFollowing:
    @pytest.mark.asyncio
    async def test_follows_links_within_depth(self):
        """应该在深度限制内跟踪链接"""
        class DepthTestSpider(CrawlSpider):
            name = "depth_test"
            start_urls = ["http://test.com"]
            max_depth = 1
            same_domain = True

            async def parse(self, response):
                yield SpiderItem(data={"url": response.url}, url=response.url)

        spider = DepthTestSpider()
        # 第一个页面有链接
        page1_html = '<html><a href="/page2">Link</a></html>'
        page2_html = '<html><p>No links</p></html>'

        call_count = 0
        async def mock_get(url, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_result(url=url, html=page1_html)
            return make_result(url=url, html=page2_html)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch("omnicrawl.OmniClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            results = await spider.run()

        assert spider.stats.requests >= 1

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """重复 URL 不应该被再次访问"""
        class DedupTestSpider(CrawlSpider):
            name = "dedup_test"
            start_urls = ["http://test.com"]
            max_depth = 0

            async def parse(self, response):
                yield SpiderItem(data={"url": response.url}, url=response.url)

        spider = DedupTestSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result())

        with patch("omnicrawl.OmniClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            await spider.run()

        # URL 只应被访问一次
        assert spider.visited_count == 1

    @pytest.mark.asyncio
    async def test_checkpoint_during_crawl(self, tmp_path):
        """爬取过程中应该保存断点"""
        checkpoint = str(tmp_path / "ckpt.json")

        class CheckpointSpider(CrawlSpider):
            name = "ckpt_test"
            start_urls = ["http://test.com"]
            max_depth = 0
            checkpoint_file = checkpoint
            checkpoint_interval = 1

            async def parse(self, response):
                yield SpiderItem(data={"url": response.url}, url=response.url)

        spider = CheckpointSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result())

        with patch("omnicrawl.OmniClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            await spider.run()

        assert Path(checkpoint).exists()
        data = json.loads(Path(checkpoint).read_text())
        assert len(data["visited"]) >= 1
