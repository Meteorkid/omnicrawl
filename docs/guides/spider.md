# Spider 爬虫框架

## 基础 Spider

```python
from omnicrawl.spider import Spider
from omnicrawl.spider.base import SpiderItem
from omnicrawl.fetchers.base import FetchResult

class MySpider(Spider):
    name = "my_spider"
    start_urls = ["https://news.ycombinator.com/"]
    max_concurrent = 4
    download_delay = 1.0

    async def parse(self, response: FetchResult):
        from omnicrawl.parser import HTMLParser
        parser = HTMLParser(response.html)
        titles = parser.css_all(".titleline > a::text")
        for title in titles:
            yield SpiderItem(data={"title": title}, url=response.url)

# 运行
spider = MySpider()
items = await spider.run()

# 流式输出
async for item in spider.stream():
    print(item.data)
```

## CrawlSpider（深度爬取）

```python
from omnicrawl.spider.base import CrawlSpider, SpiderItem

class ArticleCrawler(CrawlSpider):
    name = "article_crawler"
    start_urls = ["https://example.com"]
    max_depth = 3                    # 最大跟踪深度
    follow_patterns = [r"/article/"] # 只跟踪文章链接
    deny_patterns = [r"/login"]      # 排除登录页
    same_domain = True               # 仅跟踪同域链接
    checkpoint_file = "state.json"   # 断点续爬

    async def parse(self, response):
        from omnicrawl.parser import HTMLParser
        parser = HTMLParser(response.html)
        yield SpiderItem(
            data={
                "title": parser.css_first("h1::text") or "",
                "url": response.url,
            },
            url=response.url,
        )
```

### 链接发现

`CrawlSpider` 内置 `LinkExtractor`，支持：

- `follow_patterns` — 正则白名单
- `deny_patterns` — 正则黑名单
- `same_domain` — 仅跟踪同域链接
- 自动排除静态资源（.css, .js, .png 等）
- 自动去除 fragment（#section）和 query（?param=value）

### 断点续爬

设置 `checkpoint_file` 后，每处理 N 个 URL 自动保存状态。重新运行时自动加载断点，跳过已访问的 URL。

## 数据管道

```python
from omnicrawl.spider.pipeline import (
    Pipeline, CleanPipeline, ValidatePipeline,
    DedupPipeline, JsonFilePipeline,
)

pipeline = Pipeline([
    CleanPipeline(remove_empty=True, max_text_length=10000),
    ValidatePipeline(required_fields=["title"]),
    DedupPipeline(key_field="url"),
    JsonFilePipeline(output_dir="./output"),
])

async with pipeline:
    async for item in spider.stream():
        await pipeline.process(item)

print(f"处理: {pipeline.processed}, 丢弃: {pipeline.dropped}")
```

### 自定义 Pipeline

```python
from omnicrawl.spider.pipeline import PipelineBase

class DatabasePipeline(PipelineBase):
    async def open(self):
        self.db = await connect_db()

    async def process(self, item):
        await self.db.insert(item.data)
        return item

    async def close(self):
        await self.db.disconnect()
```
