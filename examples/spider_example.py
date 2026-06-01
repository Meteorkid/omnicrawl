"""Spider 框架示例"""

import asyncio
from typing import AsyncIterator
from omnicrawl import FetchMode
from omnicrawl.spider import Spider
from omnicrawl.spider.base import SpiderItem
from omnicrawl.fetchers.base import FetchResult
from omnicrawl.parser import HTMLParser


class HackerNewsSpider(Spider):
    """爬取 Hacker News 标题"""

    name = "hackernews"
    start_urls = ["https://news.ycombinator.com/"]
    mode = FetchMode.HTTP
    max_concurrent = 2
    download_delay = 0.5

    async def parse(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
        parser = HTMLParser(response.html)
        titles = parser.css_all(".titleline > a::text")
        links = parser.css_all(".titleline > a::attr(href)")

        for title, link in zip(titles, links):
            yield SpiderItem(
                data={"title": title, "url": link},
                url=response.url,
            )


async def main():
    print("=== Spider 示例: Hacker News ===\n")

    spider = HackerNewsSpider()

    # 方式 1: 运行并获取所有结果
    items = await spider.run()
    print(f"采集到 {len(items)} 条数据:")
    for i, item in enumerate(items[:10]):
        print(f"  {i+1}. {item.data['title']}")
        print(f"     {item.data['url']}")
    print(f"\n统计: {spider.stats}")

    # 方式 2: 流式输出
    print("\n=== 流式输出 ===")
    spider2 = HackerNewsSpider()
    async for item in spider2.stream():
        print(f"  → {item.data['title']}")


if __name__ == "__main__":
    asyncio.run(main())
