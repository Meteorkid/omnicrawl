# OmniCrawl 🕷️

**无所不能的爬虫框架** — 整合 Scrapling + curl_cffi + Playwright，绕过 WAF，LLM 友好输出。

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔒 **TLS 指纹伪装** | 37+ 浏览器指纹（Chrome/Safari/Firefox/Edge），绕过 JA3/JA4 检测 |
| 🛡️ **WAF 绕过** | 阿里云 WAF、Cloudflare、Akamai 等专用策略 |
| 🔄 **自动降级** | HTTP → Browser → Stealth，被封自动切换 |
| 🌐 **代理轮换** | 住宅/机房/移动代理，支持轮询/随机/加权策略 |
| ⏱️ **智能限速** | 基于域名的自适应延时，被封自动退避 |
| 📝 **LLM 输出** | 自动转 Markdown，去除噪音，Token 友好 |
| 🕷️ **Spider 框架** | 类 Scrapy 架构，支持并发、流式输出 |

## 📦 安装

```bash
cd omnicrawl
pip install -e .
playwright install chromium  # 首次使用需要安装浏览器
```

## 🚀 快速开始

### 基础用法

```python
import asyncio
from omnicrawl import OmniClient

async def main():
    async with OmniClient() as client:
        result = await client.get("https://example.com")
        print(result.status_code)   # 200
        print(result.markdown)      # LLM 友好的 Markdown
        print(result.text)          # 纯文本

asyncio.run(main())
```

### 绕过阿里云 WAF

```python
from omnicrawl import OmniClient, FetchMode

async with OmniClient(
    mode=FetchMode.STEALTH,
    waf="aliyun_waf",
    fingerprint="chrome136",
    proxy_pool=["http://user:pass@proxy:port"],
    min_delay=3.0,
) as client:
    result = await client.get("https://protected-site.com")
    print(result.markdown)
```

### 批量抓取

```python
async with OmniClient() as client:
    urls = ["https://site1.com", "https://site2.com", "https://site3.com"]
    results = await client.batch(urls, concurrency=5)
    for r in results:
        print(f"{r.url} -> {r.status_code} ({r.elapsed:.2f}s)")
```

### Spider 框架

```python
from omnicrawl.spider import Spider
from omnicrawl.spider.base import SpiderItem

class MySpider(Spider):
    name = "my_spider"
    start_urls = ["https://example.com/page1", "https://example.com/page2"]
    mode = FetchMode.AUTO

    async def parse(self, response):
        # 提取数据
        yield SpiderItem(
            data={"title": "示例", "content": response.markdown[:200]},
            url=response.url,
            markdown=response.markdown,
        )

# 运行
spider = MySpider()
items = await spider.run()
```

## 🏗️ 架构

```
请求 → OmniClient
        │
        ├─ 模式选择 (AUTO/HTTP/BROWSER/STEALTH)
        │
        ├─ RateLimiter (智能限速)
        │
        ├─ ProxyRotator (代理轮换)
        │
        ├─ TLSFingerprint (指纹伪装)
        │
        └─ Fetcher (抓取器)
            ├─ HttpFetcher      [curl_cffi, 最快]
            ├─ BrowserFetcher   [Playwright, JS 渲染]
            └─ StealthFetcher   [Scrapling, 最强反检测]
                    │
                    ├─ 自动降级 (被封时切换)
                    │
                    └─ MarkdownConverter (LLM 输出)
```

## 📚 示例

| 文件 | 说明 |
|------|------|
| `examples/basic_scrape.py` | 基础爬取、批量抓取 |
| `examples/bypass_waf.py` | 阿里云 WAF / Cloudflare 绕过 |
| `examples/llm_pipeline.py` | LLM 数据管道、结构化提取 |
| `examples/spider_example.py` | Spider 框架使用 |

## 🔧 WAF 绕过策略

### 阿里云 WAF

```python
client = OmniClient(
    waf="aliyun_waf",           # 预设策略
    fingerprint="chrome136",    # TLS 指纹
    proxy_pool=["..."],         # 住宅代理
    min_delay=3.0,              # 最小延时
)
```

### Cloudflare

```python
client = OmniClient(
    waf="cloudflare",
    mode=FetchMode.STEALTH,     # StealthyFetcher 自动处理 Turnstile
)
```

### 自定义策略

```python
from omnicrawl.fingerprint.tls import TLSFingerprint
from omnicrawl.proxy.rotator import ProxyRotator

# 指纹轮换
fp = TLSFingerprint()
fp.rotate(["chrome136", "safari180", "firefox135"])

# 代理轮换
proxy = ProxyRotator(
    proxies=["http://p1:8080", "http://p2:8080"],
    strategy="weighted",
    weights=[3, 1],  # p1 权重 3，p2 权重 1
)
```

## 📊 依赖

| 库 | 用途 |
|----|------|
| `curl_cffi` | TLS 指纹伪装（37+ 浏览器指纹） |
| `scrapling` | 反反爬框架（Cloudflare 绕过、指纹防护） |
| `playwright` | 浏览器自动化（JS 渲染） |
| `selectolax` | 高性能 HTML 解析 |
| `markdownify` | HTML → Markdown 转换 |
| `tiktoken` | Token 计数 |

## 📄 License

MIT
