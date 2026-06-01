"""Spider 基类 — 封装 Scrapling Spider，增加 LLM 输出支持"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional
from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.parser.markdown import MarkdownConverter
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

    async def _process_url(self, client, url: str) -> list[SpiderItem]:
        """处理单个 URL，返回采集项列表"""
        items = []
        try:
            result = await client.get(url)
            self.stats.requests += 1

            if result.blocked:
                self.stats.blocked += 1
                logger.warning(f"被拦截: {url}")

            async for item in self.parse(result):
                if not item.markdown and result.html:
                    item.markdown = self._converter.convert(result.html)
                items.append(item)
                self.stats.items += 1

            if self.download_delay > 0:
                await asyncio.sleep(self.download_delay)
        except Exception as e:
            self.stats.errors += 1
            logger.error(f"处理失败: {url} - {e}")
        return items

    async def run(self) -> list[SpiderItem]:
        """运行 Spider，返回所有采集项"""
        from omnicrawl import OmniClient

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
        return all_items

    async def stream(self) -> AsyncIterator[SpiderItem]:
        """流式输出采集项"""
        from omnicrawl import OmniClient

        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)

            for url in self.start_urls:
                async with semaphore:
                    try:
                        result = await client.get(url)
                        self.stats.requests += 1

                        async for item in self.parse(result):
                            if not item.markdown and result.html:
                                item.markdown = self._converter.convert(result.html)
                            self.stats.items += 1
                            yield item

                        if self.download_delay > 0:
                            await asyncio.sleep(self.download_delay)
                    except Exception as e:
                        self.stats.errors += 1
                        logger.error(f"处理失败: {url} - {e}")

    @abstractmethod
    async def parse(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
        """解析页面，yield SpiderItem 或新 URL"""
        ...
        yield  # 使成为 async generator
