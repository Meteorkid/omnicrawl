# 快速开始

## 最简用法

```python
import asyncio
from omnicrawl import OmniClient

async def main():
    async with OmniClient() as client:
        result = await client.get("https://example.com")
        print(f"状态码: {result.status_code}")
        print(f"Markdown: {result.markdown}")
        print(f"耗时: {result.elapsed:.2f}s")

asyncio.run(main())
```

## 批量抓取

```python
async with OmniClient() as client:
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    results = await client.batch(urls, concurrency=5)
    for r in results:
        print(f"{r.url} -> {r.status_code}")
```

## 指定抓取模式

```python
from omnicrawl import OmniClient, FetchMode

# HTTP 模式（最快，默认）
async with OmniClient(mode=FetchMode.HTTP) as client:
    result = await client.get("https://example.com")

# Browser 模式（支持 JS 渲染）
async with OmniClient(mode=FetchMode.BROWSER) as client:
    result = await client.get("https://spa-site.com")

# Camoufox 模式（反检测浏览器）
async with OmniClient(mode=FetchMode.CAMOUFOX) as client:
    result = await client.get("https://51job.com")

# AUTO 模式（自动选择，被封时自动降级）
async with OmniClient(mode=FetchMode.AUTO) as client:
    result = await client.get("https://example.com")
```

## 结构化数据提取

```python
from omnicrawl.parser import HTMLParser

async with OmniClient() as client:
    result = await client.get("https://news.ycombinator.com/")
    parser = HTMLParser(result.html)

    titles = parser.css_all(".titleline > a::text")
    links = parser.css_all(".titleline > a::attr(href)")

    for title, link in zip(titles, links):
        print(f"{title} -> {link}")
```
