"""
数据管道示例

功能：
- Pipeline 链式处理
- CleanPipeline（清洗）
- ValidatePipeline（验证）
- DedupPipeline（去重）
- JsonFilePipeline（存储）
"""

import asyncio
from omnicrawl import OmniClient
from omnicrawl.spider import Spider
from omnicrawl.spider.base import SpiderItem
from omnicrawl.spider.pipeline import (
    Pipeline,
    CleanPipeline,
    ValidatePipeline,
    DedupPipeline,
    JsonFilePipeline,
)
from omnicrawl.parser import HTMLParser


class ProductSpider(Spider):
    """爬取商品信息"""

    name = "product_spider"
    start_urls = [
        "https://example.com/products?page=1",
        "https://example.com/products?page=2",
    ]
    max_concurrent = 3
    download_delay = 1.5

    async def parse(self, response):
        parser = HTMLParser(response.html)

        # 解析商品列表
        items = parser.css_all(".product-card")
        for item in items:
            name = item.css_first(".product-name::text")
            price = item.css_first(".product-price::text")
            link = item.css_first("a::attr(href)")

            yield SpiderItem(
                data={
                    "name": name.strip() if name else "",
                    "price": price.strip() if price else "",
                    "url": link or response.url,
                    "source": "example.com",
                },
                url=response.url,
            )


async def main():
    # 1. 配置数据管道
    pipeline = Pipeline([
        # 清洗：去除空白、空值、截断长文本
        CleanPipeline(
            remove_empty=True,
            strip_whitespace=True,
            max_text_length=5000,
        ),
        # 验证：检查必填字段
        ValidatePipeline(required_fields=["name", "price"]),
        # 去重：按 URL 去重
        DedupPipeline(key_field="url"),
        # 存储：输出为 JSONL 文件
        JsonFilePipeline(output_dir="./output/products"),
    ])

    # 2. 运行 Spider + Pipeline
    spider = ProductSpider()

    print("开始爬取...")
    async with pipeline:
        async for item in spider.stream():
            await pipeline.process(item)

    # 3. 输出统计
    print(f"\n=== 管道统计 ===")
    print(f"处理: {pipeline.processed} 条")
    print(f"丢弃: {pipeline.dropped} 条")
    print(f"输出目录: ./output/products/")


if __name__ == "__main__":
    asyncio.run(main())
