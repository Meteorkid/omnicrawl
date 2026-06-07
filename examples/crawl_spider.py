"""
CrawlSpider 深度爬取示例

功能：
- 深度限制（max_depth）
- 链接过滤（follow/deny patterns）
- 同域限制
- 断点续爬（checkpoint）
"""

import asyncio
from omnicrawl.spider.base import CrawlSpider, SpiderItem
from omnicrawl.parser import HTMLParser


class ArticleCrawler(CrawlSpider):
    """爬取文章列表和详情页"""

    name = "article_crawler"
    start_urls = ["https://example-blog.com"]
    max_depth = 3
    follow_patterns = [r"/article/", r"/post/"]
    deny_patterns = [r"/login", r"/admin", r"/tag/"]
    same_domain = True
    checkpoint_file = "crawl_state.json"
    checkpoint_interval = 50

    async def parse(self, response):
        """解析页面，提取文章数据"""
        parser = HTMLParser(response.html)

        # 提取文章标题和内容
        title = parser.css_first("h1::text") or ""
        content = parser.css_first("article::text") or ""

        if title:
            yield SpiderItem(
                data={
                    "title": title.strip(),
                    "content": content[:500].strip(),
                    "url": response.url,
                },
                url=response.url,
            )


class NewsCrawler(CrawlSpider):
    """爬取新闻站点"""

    name = "news_crawler"
    start_urls = ["https://news.example.com"]
    max_depth = 2
    follow_patterns = [r"/\d{4}/\d{2}/"]  # 日期格式的新闻链接
    checkpoint_file = "news_state.json"

    async def parse(self, response):
        parser = HTMLParser(response.html)
        titles = parser.css_all("h2.headline::text")
        for title in titles:
            yield SpiderItem(data={"title": title.strip()}, url=response.url)


async def main():
    # 示例 1: 文章爬取
    crawler = ArticleCrawler()
    print("=== 文章爬取 ===")
    items = await crawler.run()
    print(f"爬取到 {len(items)} 篇文章")
    for item in items[:5]:
        print(f"  - {item.data.get('title', '无标题')}")

    # 示例 2: 流式输出
    print("\n=== 流式爬取 ===")
    crawler2 = NewsCrawler()
    count = 0
    async for item in crawler2.stream():
        count += 1
        print(f"  [{count}] {item.data.get('title', '无标题')}")
    print(f"共爬取 {count} 条")

    # 示例 3: 检查断点状态
    import json
    from pathlib import Path

    if Path("crawl_state.json").exists():
        with open("crawl_state.json") as f:
            state = json.load(f)
        print(f"\n断点状态: 已访问 {len(state.get('visited', []))} 个 URL")


if __name__ == "__main__":
    asyncio.run(main())
