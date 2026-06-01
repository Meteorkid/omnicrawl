"""LLM 数据管道示例 — 将网页转为 LLM 友好格式"""

import asyncio
from omnicrawl import OmniClient
from omnicrawl.parser import HTMLParser
from omnicrawl.parser.markdown import MarkdownConverter


async def docs_to_markdown():
    """将文档站点转为 Markdown"""
    print("=== 文档 → Markdown ===")

    async with OmniClient() as client:
        result = await client.get("https://docs.python.org/3/tutorial/classes.html")
        print(f"状态: {result.status_code}")
        print(f"Token 数: {MarkdownConverter.token_count(result.markdown)}")
        print(f"Markdown (前 500 字):\n{result.markdown[:500]}")
        print("...")


async def batch_convert():
    """批量转换多个页面"""
    print("\n=== 批量转换 ===")

    urls = [
        "https://docs.python.org/3/tutorial/index.html",
        "https://docs.python.org/3/tutorial/introduction.html",
        "https://docs.python.org/3/tutorial/controlflow.html",
    ]

    async with OmniClient() as client:
        results = await client.batch(urls, concurrency=3)

        for r in results:
            tokens = MarkdownConverter.token_count(r.markdown)
            print(f"  {r.url.split('/')[-1]}: {tokens} tokens, {len(r.markdown)} chars")


async def extract_structured_data():
    """使用 CSS 选择器提取结构化数据"""
    print("\n=== 结构化数据提取 ===")

    from omnicrawl.parser import HTMLParser

    async with OmniClient() as client:
        result = await client.get("https://news.ycombinator.com/")
        parser = HTMLParser(result.html)

        # 提取标题和链接
        titles = parser.css_all(".titleline > a::text")
        links = parser.css_all(".titleline > a::attr(href)")

        print(f"  Hacker News 前 5 条:")
        for i, (title, link) in enumerate(zip(titles[:5], links[:5])):
            print(f"  {i+1}. {title}")
            print(f"     {link}")


if __name__ == "__main__":
    asyncio.run(docs_to_markdown())
    asyncio.run(batch_convert())
    asyncio.run(extract_structured_data())
