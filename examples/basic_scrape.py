"""基础爬取示例"""

import asyncio
from omnicrawl import OmniClient, FetchMode


async def main():
    # 1. 最简用法
    async with OmniClient() as client:
        result = await client.get("https://httpbin.org/get")
        print(f"状态: {result.status_code}")
        print(f"模式: {result.mode_used}")
        print(f"耗时: {result.elapsed:.2f}s")
        print(f"Markdown (前 200 字): {result.markdown[:200]}")
        print()

    # 2. 指定模式
    async with OmniClient(mode=FetchMode.STEALTH) as client:
        result = await client.get("https://example.com")
        print(f"状态: {result.status_code}")
        print(f"标题: {result.markdown[:100]}")
        print()

    # 3. 批量抓取
    async with OmniClient() as client:
        urls = [
            "https://httpbin.org/get",
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
        ]
        results = await client.batch(urls, concurrency=3)
        for r in results:
            print(f"  {r.url} -> {r.status_code} ({r.elapsed:.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())
