"""Spider 基类 — 封装 Scrapling Spider，增加 LLM 输出支持"""

from __future__ import annotations

import asyncio
import json
from abc import abstractmethod
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional
from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.plugins.base import PluginManager
from omnicrawl.storage.base import StateStore
from omnicrawl.utils.logger import get_logger

logger = get_logger("spider")


@dataclass
class SpiderItem:
    """Spider 采集项"""
    data: dict
    url: str = ""
    markdown: str = ""  # LLM 友好的 Markdown


@dataclass
class SpiderStats:
    """Spider 统计"""
    requests: int = 0
    items: int = 0
    errors: int = 0
    blocked: int = 0


class Spider:
    """Spider 基类

    用法:
        class MySpider(Spider):
            name = "my_spider"
            start_urls = ["https://example.com"]

            async def parse(self, response: FetchResult):
                yield SpiderItem(
                    data={"title": response.markdown[:100]},
                    url=response.url,
                    markdown=response.markdown,
                )

        spider = MySpider()
        result = await spider.run()
    """

    name: str = "base_spider"
    start_urls: list[str] = field(default_factory=list)
    mode: FetchMode = FetchMode.AUTO
    max_concurrent: int = 4
    download_delay: float = 1.0

    def __init__(self):
        self.stats = SpiderStats()
        self._converter = MarkdownConverter()
        self.plugins = PluginManager()

    async def _process_url(self, client, url: str) -> list[SpiderItem]:
        """处理单个 URL，返回采集项列表"""
        # 插件钩子: on_request
        url = await self.plugins.trigger_request(url)
        if url is None:
            return []

        items = []
        try:
            result = await client.get(url)
            self.stats.requests += 1

            # 插件钩子: on_response
            result = await self.plugins.trigger_response(url, result)
            if result is None:
                return []

            if result.blocked:
                self.stats.blocked += 1
                logger.warning(f"被拦截: {url}")

            async for item in self.parse(result):
                if not item.markdown and result.html:
                    item.markdown = self._converter.convert(result.html)
                # 插件钩子: on_item
                item = await self.plugins.trigger_item(item)
                if item is not None:
                    items.append(item)
                    self.stats.items += 1

            if self.download_delay > 0:
                await asyncio.sleep(self.download_delay)
        except Exception as e:
            self.stats.errors += 1
            logger.error(f"处理失败: {url} - {e}")
            # 插件钩子: on_error
            await self.plugins.trigger_error(url, e)
        return items

    async def run(self) -> list[SpiderItem]:
        """运行 Spider，返回所有采集项"""
        from omnicrawl import OmniClient

        await self.plugins.trigger_start(self)
        all_items = []
        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def bounded_process(url: str) -> list[SpiderItem]:
                async with semaphore:
                    return await self._process_url(client, url)

            results = await asyncio.gather(
                *[bounded_process(url) for url in self.start_urls],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, list):
                    all_items.extend(result)

        logger.info(f"Spider 完成: {self.stats}")
        await self.plugins.trigger_finish(self, {"items": len(all_items)})
        return all_items

    async def stream(self) -> AsyncIterator[SpiderItem]:
        """流式输出采集项"""
        from omnicrawl import OmniClient

        await self.plugins.trigger_start(self)
        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)

            for url in self.start_urls:
                # 插件钩子: on_request
                url = await self.plugins.trigger_request(url)
                if url is None:
                    continue

                async with semaphore:
                    try:
                        result = await client.get(url)
                        self.stats.requests += 1

                        # 插件钩子: on_response
                        result = await self.plugins.trigger_response(url, result)
                        if result is None:
                            continue

                        async for item in self.parse(result):
                            if not item.markdown and result.html:
                                item.markdown = self._converter.convert(result.html)
                            # 插件钩子: on_item
                            item = await self.plugins.trigger_item(item)
                            if item is not None:
                                self.stats.items += 1
                                yield item

                        if self.download_delay > 0:
                            await asyncio.sleep(self.download_delay)
                    except Exception as e:
                        self.stats.errors += 1
                        logger.error(f"处理失败: {url} - {e}")
                        await self.plugins.trigger_error(url, e)

        await self.plugins.trigger_finish(self, {"items": self.stats.items})

    @abstractmethod
    async def parse(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
        """解析页面，yield SpiderItem 或新 URL"""
        ...
        yield  # 使成为 async generator


class CrawlSpider(Spider):
    """深度爬取 Spider — 支持链接跟踪、深度限制、断点续爬

    与 Spider 的区别：
    - 自动跟踪页面中的链接
    - 支持深度限制（max_depth）
    - URL 去重（visited set）
    - 断点续爬（checkpoint 文件）

    用法:
        class MyCrawler(CrawlSpider):
            name = "my_crawler"
            start_urls = ["https://example.com"]
            max_depth = 3
            follow_patterns = [r"/article/\\d+"]

            async def parse(self, response):
                yield SpiderItem(data={"title": response.markdown[:100]}, url=response.url)

        crawler = MyCrawler()
        result = await crawler.run()
    """

    max_depth: int = 3
    follow_patterns: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)
    same_domain: bool = True
    checkpoint_file: Optional[str] = None
    checkpoint_interval: int = 50  # 每 N 个 URL 保存一次断点

    def __init__(self, store: Optional[StateStore] = None):
        super().__init__()
        self._store = store
        self._local_visited: set[str] = set()
        self._local_queue: deque[tuple[str, int]] = deque()  # (url, depth)
        self._link_extractor = None
        self._store_prefix = f"crawl:{self.name}"

    # ── 访问集合操作（本地或分布式） ──

    async def _is_visited(self, url: str) -> bool:
        if self._store:
            return await self._store.sismember(f"{self._store_prefix}:visited", url)
        return url in self._local_visited

    async def _mark_visited(self, url: str) -> None:
        if self._store:
            await self._store.sadd(f"{self._store_prefix}:visited", url)
        else:
            self._local_visited.add(url)

    # ── 队列操作（本地或分布式） ──

    async def _queue_push(self, url: str, depth: int) -> None:
        payload = json.dumps([url, depth])
        if self._store:
            await self._store.lpush(f"{self._store_prefix}:queue", payload)
        else:
            self._local_queue.append((url, depth))

    async def _queue_pop(self) -> Optional[tuple[str, int]]:
        if self._store:
            raw = await self._store.rpop(f"{self._store_prefix}:queue")
            if raw is None:
                return None
            arr = json.loads(raw)
            return (arr[0], arr[1])
        if not self._local_queue:
            return None
        return self._local_queue.popleft()

    async def _queue_len(self) -> int:
        if self._store:
            return await self._store.llen(f"{self._store_prefix}:queue")
        return len(self._local_queue)

    async def _queue_extend(self, items: list[tuple[str, int]]) -> None:
        for url, depth in items:
            await self._queue_push(url, depth)

    def _get_link_extractor(self):
        """延迟创建链接提取器"""
        if self._link_extractor is None:
            from omnicrawl.spider.link_extractor import LinkExtractor
            self._link_extractor = LinkExtractor(
                allow_patterns=self.follow_patterns or None,
                deny_patterns=self.deny_patterns or None,
                same_domain=self.same_domain,
            )
        return self._link_extractor

    async def _process_url_with_depth(
        self, client, url: str, depth: int
    ) -> list[SpiderItem]:
        """处理 URL 并跟踪链接"""
        # 插件钩子: on_request
        url = await self.plugins.trigger_request(url)
        if url is None:
            return []

        if await self._is_visited(url):
            return []
        await self._mark_visited(url)

        items: list[SpiderItem] = []
        try:
            result = await client.get(url)
            self.stats.requests += 1

            # 插件钩子: on_response
            result = await self.plugins.trigger_response(url, result)
            if result is None:
                return []

            if result.blocked:
                self.stats.blocked += 1
                logger.warning("被拦截: %s", url)

            # 解析数据
            async for item in self.parse(result):
                if not item.markdown and result.html:
                    item.markdown = self._converter.convert(result.html)
                # 插件钩子: on_item
                item = await self.plugins.trigger_item(item)
                if item is not None:
                    items.append(item)
                    self.stats.items += 1

            # 跟踪链接（未达深度限制时）
            if depth < self.max_depth and result.html:
                extractor = self._get_link_extractor()
                links = extractor.extract(result.html, base_url=url)
                new_links = []
                for link in links:
                    if not await self._is_visited(link):
                        new_links.append((link, depth + 1))
                if new_links:
                    await self._queue_extend(new_links)
                logger.debug("深度 %d: 从 %s 发现 %d 个新链接", depth, url, len(new_links))

            if self.download_delay > 0:
                await asyncio.sleep(self.download_delay)

        except Exception as e:
            self.stats.errors += 1
            logger.error("处理失败: %s - %s", url, e)
            await self.plugins.trigger_error(url, e)

        return items

    def _save_checkpoint(self):
        """保存断点（store 模式下自动持久化，无需额外操作）"""
        if self._store:
            return  # store 已持久化
        if not self.checkpoint_file:
            return
        data = {
            "visited": list(self._local_visited),
            "queue": [[url, depth] for url, depth in self._local_queue],
            "stats": {
                "requests": self.stats.requests,
                "items": self.stats.items,
                "errors": self.stats.errors,
                "blocked": self.stats.blocked,
            },
        }
        path = Path(self.checkpoint_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.debug("断点已保存: %s (%d 已访问, %d 队列)", path, len(self._local_visited), len(self._local_queue))

    def _load_checkpoint(self) -> bool:
        """加载断点（store 模式下跳过，数据已在 store 中）"""
        if self._store:
            return False  # store 已持久化
        if not self.checkpoint_file:
            return False
        path = Path(self.checkpoint_file)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._local_visited = set(data.get("visited", []))
            self._local_queue = deque(
                (item[0], item[1]) for item in data.get("queue", [])
            )
            stats = data.get("stats", {})
            self.stats.requests = stats.get("requests", 0)
            self.stats.items = stats.get("items", 0)
            self.stats.errors = stats.get("errors", 0)
            self.stats.blocked = stats.get("blocked", 0)
            logger.info(
                "从断点恢复: %d 已访问, %d 队列中",
                len(self._local_visited), len(self._local_queue)
            )
            return True
        except Exception as e:
            logger.warning("加载断点失败: %s", e)
            return False

    async def run(self) -> list[SpiderItem]:
        """运行爬虫（BFS 深度优先）"""
        from omnicrawl import OmniClient

        await self.plugins.trigger_start(self)

        # 尝试从断点恢复
        self._load_checkpoint()

        # 初始化队列
        for url in self.start_urls:
            if not await self._is_visited(url):
                await self._queue_push(url, 0)

        all_items: list[SpiderItem] = []

        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)
            processed_since_checkpoint = 0

            while await self._queue_len() > 0:
                # 批量取 URL
                batch: list[tuple[str, int]] = []
                while len(batch) < self.max_concurrent:
                    item = await self._queue_pop()
                    if item is None:
                        break
                    url, depth = item
                    if not await self._is_visited(url):
                        batch.append((url, depth))

                if not batch:
                    break

                async def bounded_process(url: str, depth: int) -> list[SpiderItem]:
                    async with semaphore:
                        return await self._process_url_with_depth(client, url, depth)

                results = await asyncio.gather(
                    *[bounded_process(url, depth) for url, depth in batch],
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, list):
                        all_items.extend(result)

                processed_since_checkpoint += len(batch)
                if (self.checkpoint_file
                        and processed_since_checkpoint >= self.checkpoint_interval):
                    self._save_checkpoint()
                    processed_since_checkpoint = 0

        # 最终断点保存
        if self.checkpoint_file:
            self._save_checkpoint()

        visited = len(self._local_visited) if not self._store else -1
        logger.info("CrawlSpider 完成: %s (访问 %d 个 URL)", self.stats, visited)
        await self.plugins.trigger_finish(self, {"items": len(all_items), "visited": visited})
        return all_items

    async def stream(self) -> AsyncIterator[SpiderItem]:
        """流式运行爬虫"""
        from omnicrawl import OmniClient

        await self.plugins.trigger_start(self)
        self._load_checkpoint()

        for url in self.start_urls:
            if not await self._is_visited(url):
                await self._queue_push(url, 0)

        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)
            processed_since_checkpoint = 0

            while await self._queue_len() > 0:
                batch: list[tuple[str, int]] = []
                while len(batch) < self.max_concurrent:
                    item = await self._queue_pop()
                    if item is None:
                        break
                    url, depth = item
                    if not await self._is_visited(url):
                        batch.append((url, depth))

                if not batch:
                    break

                for url, depth in batch:
                    async with semaphore:
                        try:
                            items = await self._process_url_with_depth(client, url, depth)
                            for item in items:
                                yield item
                        except Exception as e:
                            self.stats.errors += 1
                            logger.error("流式处理失败: %s - %s", url, e)

                    processed_since_checkpoint += 1
                    if (self.checkpoint_file
                            and processed_since_checkpoint >= self.checkpoint_interval):
                        self._save_checkpoint()
                        processed_since_checkpoint = 0

        if self.checkpoint_file:
            self._save_checkpoint()

        await self.plugins.trigger_finish(self, {"items": self.stats.items})

    @property
    def visited_count(self) -> int:
        """已访问 URL 数量（仅本地模式准确）"""
        return len(self._local_visited)

    @property
    def queue_size(self) -> int:
        """队列中待处理 URL 数量（仅本地模式准确）"""
        return len(self._local_queue)

    @property
    def _visited(self) -> set[str]:
        """向后兼容：返回本地 visited set"""
        return self._local_visited

    @property
    def _queue(self) -> deque:
        """向后兼容：返回本地 queue"""
        return self._local_queue
