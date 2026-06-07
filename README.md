# OmniCrawl 🕷️

**无所不能的爬虫框架** — 整合 Scrapling + curl_cffi + Playwright，绕过 WAF，LLM 友好输出。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-491%20passed-brightgreen.svg)](#测试)
[![PyPI](https://img.shields.io/pypi/v/omnicrawl-core.svg)](https://pypi.org/project/omnicrawl-core/)

---

## 📖 目录

- [为什么需要 OmniCrawl](#为什么需要-omnicrawl)
- [核心特性](#核心特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [API 参考](#api-参考)
- [WAF 绕过实战](#waf-绕过实战)
- [架构设计](#架构设计)
- [测试](#测试)
- [项目结构](#项目结构)
- [依赖说明](#依赖说明)
- [License](#license)

---

## 为什么需要 OmniCrawl

现有的爬虫库各有局限：

| 库 | 问题 |
|---|---|
| `requests` | TLS 指纹暴露，被 WAF 秒封 |
| `httpx` | 同上，HTTP/2 指纹也暴露 |
| `Selenium` | 自动化痕迹明显，资源消耗大 |
| `Playwright` | 无内置爬虫逻辑，无反检测 |
| `Scrapling` | 功能强大但 API 复杂 |

**OmniCrawl 的定位**：把这些库的最佳能力整合到一个统一 API 中，自动选择最优方案。

### 实测对比

| 方案 | example.com | 百度 | 淘宝 | 京东 | 51job |
|------|-------------|------|------|------|-------|
| `requests` | ❌ 被封 | ❌ 被封 | ❌ 被封 | ❌ 被封 | ❌ 被封 |
| **curl_cffi** | ✅ 0.6s | ✅ 0.1s | ✅ 0.1s | ✅ 0.1s | ❌ WAF 验证页 |
| Scrapling Stealthy | ✅ 2.0s | ❌ 超时 | ❌ 超时 | ❌ 超时 | ❌ bug |
| **Camoufox** | ✅ 14.8s | - | - | - | ✅ 绕过 JS 检测 |

> 结论：
> - curl_cffi 解决 90% 的场景（TLS 指纹检测）
> - Camoufox 解决 JS 环境检测（51job 等强反爬站点）
> - 自动降级：curl_cffi 被封 → 自动切换 Camoufox

---

## 核心特性

| 特性 | 说明 |
|------|------|
| 🔒 **TLS 指纹伪装** | 37+ 浏览器指纹（Chrome/Safari/Firefox/Edge/Tor），绕过 JA3/JA4 检测 |
| 🛡️ **WAF 绕过** | 阿里云 WAF、Cloudflare、Akamai 等专用策略配置 |
| 🦊 **Camoufox** | Firefox 原生反检测浏览器，绕过 JS 环境检测（51job 等强反爬站点） |
| 🔄 **自动降级** | HTTP → Browser → Camoufox → Stealth，被封时自动切换 |
| 🌐 **代理轮换** | 支持轮询/随机/加权策略，内置代理健康检查 |
| ⏱️ **智能限速** | 基于域名的自适应延时，被封自动退避，成功自动恢复 |
| 📝 **LLM 输出** | 自动去除导航/广告/脚本，输出干净 Markdown，Token 计数 |
| 🕷️ **Spider 框架** | 类 Scrapy 架构，支持并发控制、流式输出 |
| 🔄 **失败重试** | 指数退避重试，每次重试自动轮换 TLS 指纹 |

---

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install omnicrawl-core
```

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/Meteorkid/omnicrawl.git
cd omnicrawl

# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装（基础版，包含 curl_cffi + Scrapling）
pip install -e .

# 安装浏览器（Browser/Stealth 模式需要）
playwright install chromium
patchright install chromium

# 安装 Camoufox（51job 等强反爬站点需要）
pip install -e ".[camoufox]"
camoufox fetch
```

### 环境要求

- Python >= 3.10
- macOS / Linux / Windows

---

## 快速开始

### 1. 最简用法

```python
import asyncio
from omnicrawl import OmniClient

async def main():
    async with OmniClient() as client:
        result = await client.get("https://example.com")
        print(f"状态码: {result.status_code}")    # 200
        print(f"Markdown: {result.markdown}")      # 干净的 Markdown
        print(f"纯文本: {result.text}")            # 去除 HTML 的纯文本
        print(f"耗时: {result.elapsed:.2f}s")      # 0.60s

asyncio.run(main())
```

### 2. 批量抓取

```python
async with OmniClient() as client:
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    results = await client.batch(urls, concurrency=5)
    for r in results:
        print(f"{r.url} -> {r.status_code} ({r.elapsed:.2f}s)")
```

### 3. 指定抓取模式

```python
from omnicrawl import OmniClient, FetchMode

# HTTP 模式（最快，默认）
async with OmniClient(mode=FetchMode.HTTP) as client:
    result = await client.get("https://example.com")

# Browser 模式（支持 JS 渲染）
async with OmniClient(mode=FetchMode.BROWSER) as client:
    result = await client.get("https://spa-site.com")

# Camoufox 模式（反检测浏览器，绕过 JS 环境检测）
async with OmniClient(mode=FetchMode.CAMOUFOX) as client:
    result = await client.get("https://51job.com")

# Stealth 模式（Cloudflare Turnstile 绕过）
async with OmniClient(mode=FetchMode.STEALTH) as client:
    result = await client.get("https://cloudflare-site.com")

# AUTO 模式（自动选择，被封时自动降级）
async with OmniClient(mode=FetchMode.AUTO) as client:
    result = await client.get("https://example.com")
```

### 4. 绕过 WAF

```python
async with OmniClient(
    waf="aliyun_waf",                    # 阿里云 WAF 策略
    fingerprint="chrome136",             # TLS 指纹
    proxy_pool=["http://user:pass@residential:port"],  # 住宅代理
    min_delay=3.0,                       # 最小请求间隔
    max_retries=2,                       # 失败重试次数
) as client:
    result = await client.get("https://protected-site.com")
    print(result.markdown)
```

### 5. Spider 框架

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
        # 解析页面，yield 采集项
        from omnicrawl.parser import HTMLParser
        parser = HTMLParser(response.html)
        titles = parser.css_all(".titleline > a::text")
        for title in titles:
            yield SpiderItem(data={"title": title}, url=response.url)

# 运行
spider = MySpider()
items = await spider.run()
print(f"采集到 {len(items)} 条数据")

# 流式输出
async for item in spider.stream():
    print(item.data)
```

### 6. 结构化数据提取

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

### 7. LLM 数据管道

```python
from omnicrawl.parser.markdown import MarkdownConverter

async with OmniClient() as client:
    result = await client.get("https://docs.python.org/3/tutorial/classes.html")

    # 自动去除导航/广告/脚本
    clean_markdown = result.markdown

    # Token 计数
    tokens = MarkdownConverter.token_count(clean_markdown)
    print(f"Token 数: {tokens}")  # 比原始 HTML 节省 60-90%
```

---

## API 参考

### OmniClient

```python
OmniClient(
    mode: FetchMode = FetchMode.AUTO,  # 抓取模式
    fingerprint: str = "chrome",       # TLS 指纹
    proxy_pool: list[str] = None,      # 代理池
    waf: str = None,                   # WAF 类型 (aliyun_waf/cloudflare/akamai/generic)
    min_delay: float = 1.0,            # 最小请求间隔（秒）
    max_retries: int = 2,              # 失败重试次数
    auto_fallback: bool = True,        # 是否自动降级
)
```

#### 方法

| 方法 | 说明 |
|------|------|
| `await client.get(url, **kwargs)` | 抓取单个 URL |
| `await client.batch(urls, concurrency=5)` | 批量抓取 |
| `await client.close()` | 关闭所有连接 |

#### FetchResult

```python
result.url           # 最终 URL（可能有重定向）
result.status_code   # HTTP 状态码
result.html          # 原始 HTML
result.markdown      # LLM 友好的 Markdown
result.text          # 纯文本
result.headers       # 响应头
result.cookies       # Cookies
result.mode_used     # 实际使用的抓取模式
result.elapsed       # 耗时（秒）
result.blocked       # 是否被 WAF 拦截
result.ok            # 是否成功 (2xx 且未被拦截)
```

### FetchMode

| 模式 | 底层 | 速度 | JS 支持 | 反检测 | 适用场景 |
|------|------|------|---------|--------|----------|
| `HTTP` | curl_cffi | ⚡ 最快 | ❌ | ⭐⭐⭐ | 静态页面、API |
| `BROWSER` | Playwright | 🐢 中等 | ✅ | ⭐⭐ | JS 渲染页面 |
| `CAMOUFOX` | Camoufox | 🐢 较慢 | ✅ | ⭐⭐⭐⭐⭐ | 51job、阿里云 WAF（JS 环境检测） |
| `STEALTH` | Scrapling | 🐢 较慢 | ✅ | ⭐⭐⭐⭐ | Cloudflare Turnstile |
| `AUTO` | 自动选择 | - | - | - | 通用（推荐） |

### TLSFingerprint

```python
from omnicrawl.fingerprint.tls import TLSFingerprint

fp = TLSFingerprint()
fp.set("chrome136")                              # 固定指纹
fp.random()                                      # 随机选择
fp.rotate(["chrome136", "safari180", "firefox135"])  # 轮换列表
fp.next()                                        # 轮换到下一个
fp.get()                                         # 获取当前指纹
fp.list_available()                              # 列出所有可用指纹
```

支持的指纹：`chrome99`-`chrome146`, `safari153`-`safari2601`, `firefox133`-`firefox147`, `edge99`-`edge101`, `tor145`

### ProxyRotator

```python
from omnicrawl.proxy.rotator import ProxyRotator

rotator = ProxyRotator(
    proxies=["http://p1:8080", "http://p2:8080"],
    strategy="round_robin",  # round_robin / random / weighted
    weights=[3, 1],          # weighted 模式的权重
)

proxy = rotator.next()    # 获取下一个代理
rotator.add("http://p3:8080")     # 添加代理
rotator.remove("http://p1:8080")  # 移除代理
rotator.stats                      # 使用统计
```

### ProxyValidator

```python
from omnicrawl.proxy.validator import ProxyValidator

validator = ProxyValidator(
    test_url="https://httpbin.org/ip",  # 测试 URL
    timeout=10.0,                       # 超时
    max_failures=3,                     # 最大连续失败次数
)

# 检查单个代理
status = await validator.check("http://proxy:8080")
print(f"可用: {status.alive}, 延迟: {status.latency:.2f}s")

# 批量检查
results = await validator.check_all(["http://p1:8080", "http://p2:8080"])
alive = [r for r in results if r.alive]

# 判断代理是否健康
validator.is_healthy("http://proxy:8080")  # True/False
```

### RateLimiter

```python
from omnicrawl.anti_detect.rate_limiter import RateLimiter

limiter = RateLimiter(
    min_delay=1.0,       # 最小延时
    max_delay=10.0,      # 最大延时
    backoff_factor=2.0,  # 退避系数
)

await limiter.wait("https://example.com/page")  # 等待限速
limiter.report_blocked("https://example.com/page")   # 报告被封（延时增加）
limiter.report_success("https://example.com/page")   # 报告成功（延时恢复）
```

### WAFBypass

```python
from omnicrawl.anti_detect.waf_bypass import WAFBypass

bypass = WAFBypass("aliyun_waf")
bypass.get_recommended_mode()    # FetchMode.STEALTH
bypass.get_tls_fingerprint()     # "chrome136" 等
bypass.get_min_delay()           # 3.0
bypass.list_profiles()           # 所有 WAF 配置
```

### MarkdownConverter

```python
from omnicrawl.parser.markdown import MarkdownConverter

converter = MarkdownConverter(
    remove_tags=["script", "style", "nav"],  # 要移除的标签
    strip_images=False,                       # 是否移除图片
    strip_links=False,                        # 是否移除链接
)

md = converter.convert(html)
tokens = MarkdownConverter.token_count(md)
```

### HTMLParser

```python
from omnicrawl.parser.html_parser import HTMLParser

parser = HTMLParser(html)
parser.css_first("h1::text")              # 第一个 h1 的文本
parser.css_first("a::attr(href)")         # 第一个 a 的 href
parser.css_all("p::text")                 # 所有 p 的文本列表
parser.title()                            # 页面标题
parser.links()                            # 所有链接
parser.text()                             # 纯文本
parser.meta("description")                # meta 标签
```

---

## WAF 绕过实战

### 阿里云 WAF

阿里云 WAF 有两种检测方式：

**方式一：TLS 指纹检测**（大部分站点）→ curl_cffi 解决

```python
async with OmniClient(
    waf="aliyun_waf",
    fingerprint="chrome136",
    proxy_pool=["http://user:pass@residential:port"],
    min_delay=3.0,
) as client:
    result = await client.get("https://target.com")
```

**方式二：JS 环境检测**（51job 等强反爬站点）→ 需要 Camoufox

```python
async with OmniClient(
    mode=FetchMode.CAMOUFOX,
    waf="aliyun_waf",
    proxy_pool=["http://user:pass@residential:port"],
    min_delay=3.0,
) as client:
    result = await client.get("https://51job.com")
```

> **为什么 Camoufox 能绕过？**
> Camoufox 是 Firefox 的原生修改版，指纹注入发生在浏览器引擎内部（非 JS 注入）。
> 阿里云 WAF 检测 `navigator.webdriver`、`window.chrome`、Canvas/WebGL 指纹等，
> Camoufox 在这些检测面前表现得和真实 Firefox 一模一样。

### Cloudflare

Cloudflare 有 JS 挑战（Turnstile），需要浏览器模式：

```python
async with OmniClient(
    waf="cloudflare",
    mode=FetchMode.STEALTH,
) as client:
    result = await client.get("https://cloudflare-site.com")
```

### 代理选择指南

| 代理类型 | 对 WAF 有效性 | 成本 | 推荐场景 |
|----------|--------------|------|----------|
| **住宅代理** | ⭐⭐⭐⭐⭐ | 高 | 阿里云/Cloudflare |
| **移动代理** | ⭐⭐⭐⭐⭐ | 高 | 高安全性目标 |
| **ISP 代理** | ⭐⭐⭐⭐ | 中 | 一般反爬 |
| **机房代理** | ⭐⭐ | 低 | 无 WAF 站点 |

### TLS 指纹轮换

```python
from omnicrawl.fingerprint.tls import TLSFingerprint

fp = TLSFingerprint()
fp.rotate(["chrome136", "chrome142", "safari180", "firefox135"])

# 每次请求轮换指纹
async with AsyncSession(impersonate=fp.next()) as s:
    resp = await s.get(url)
```

---

## 架构设计

```
请求 → OmniClient
        │
        ├─ RateLimiter (智能限速: 域名隔离, 自适应延时)
        │
        ├─ ProxyRotator (代理轮换: 轮询/随机/加权)
        │
        ├─ TLSFingerprint (指纹伪装: 37+ 浏览器指纹)
        │
        └─ _fetch_with_retry (重试: 指数退避, 指纹轮换)
            │
            └─ _fetch_with_fallback (降级: HTTP → Browser → Camoufox → Stealth)
                │
                ├─ HttpFetcher      [curl_cffi]   0.1-0.6s, 最快
                ├─ BrowserFetcher   [Playwright]  1-5s, JS 渲染
                ├─ CamoufoxFetcher  [Camoufox]    5-15s, Firefox 反检测
                └─ StealthFetcher   [Scrapling]   2-30s, Cloudflare 绕过
                        │
                        ├─ 自动检测被封 (HTTP 403/429)
                        ├─ 自动切换更隐蔽的方案
                        └─ MarkdownConverter (LLM 输出)
```

### 降级流程

```
AUTO 模式:
  1. HttpFetcher (curl_cffi, 最快, TLS 指纹伪装)
     ↓ 被封 (403/429)?
  2. BrowserFetcher (Playwright, JS 渲染)
     ↓ 被封?
  3. CamoufoxFetcher (Firefox 反检测, 绕过 JS 环境检测) ← 51job 等强反爬
     ↓ 被封?
  4. StealthFetcher (Scrapling, Cloudflare Turnstile)
     ↓ 还是失败?
  5. 轮换 TLS 指纹 + 代理, 重试 (最多 max_retries 次)
```

---

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_client.py -v
pytest tests/test_fingerprint.py -v

# 运行并显示覆盖率
pytest tests/ -v --tb=short
```

### 测试覆盖

| 模块 | 测试数 | 覆盖内容 |
|------|--------|----------|
| `test_fingerprint.py` | 6 | TLS 指纹设置、轮换、随机 |
| `test_proxy.py` | 25 | 代理轮换、验证、评分、scored 策略 |
| `test_rate_limiter.py` | 5 | 限速、退避、恢复、域名隔离 |
| `test_waf_bypass.py` | 6 | WAF 策略配置、未知类型降级 |
| `test_parser.py` | 14 | Markdown 转换、HTML 解析、Token 计数 |
| `test_client.py` | 17 | OmniClient 集成、批量抓取、FetchResult |
| `test_client_unit.py` | 178 | Client 单元测试（session/fetch/fallback） |
| `test_cli.py` | 34 | CLI 命令、配置解析、预设 |
| `test_config.py` | 22 | TOML 配置、环境变量、合并 |
| `test_proxy_scorer.py` | 27 | 代理评分、统计、prune |
| `test_anti_detect.py` | 62 | 验证码检测/处理、指纹一致性、WAF 绕过 |
| `test_link_extractor.py` | 14 | 链接提取、过滤、去重 |
| `test_pipeline.py` | 20 | 数据管道（Clean/Validate/Dedup/JsonFile） |
| `test_crawl_spider.py` | 15 | 深度爬取、断点续爬、链接跟踪 |
| `test_smart_spider.py` | 26 | SmartSpider 编排 |
| **总计** | **491** | ✅ 全部通过 |

---

## 项目结构

```
omnicrawl/
├── omnicrawl/                  # 源代码
│   ├── __init__.py             # 包入口
│   ├── client.py               # OmniClient 统一入口
│   ├── cli.py                  # CLI 入口（typer）
│   ├── config.py               # TOML 配置
│   ├── fetchers/               # 抓取器
│   │   ├── base.py             # 基类 (FetchMode, FetchResult)
│   │   ├── http_fetcher.py     # curl_cffi (最快)
│   │   ├── browser_fetcher.py  # Playwright (JS 渲染)
│   │   ├── camoufox_fetcher.py # Camoufox (反检测浏览器)
│   │   └── stealth_fetcher.py  # Scrapling (Cloudflare 绕过)
│   ├── fingerprint/            # 指纹管理
│   │   └── tls.py              # TLS 指纹 (37+ 浏览器)
│   ├── proxy/                  # 代理管理
│   │   ├── rotator.py          # 代理轮换器
│   │   ├── validator.py        # 代理健康检查
│   │   └── scorer.py           # 代理质量评分
│   ├── anti_detect/            # 反检测
│   │   ├── rate_limiter.py     # 智能限速
│   │   ├── waf_bypass.py       # WAF 策略引擎
│   │   ├── captcha_detector.py # 验证码检测
│   │   ├── captcha_solver.py   # 验证码处理
│   │   └── fingerprint_consistency.py  # 指纹一致性
│   ├── parser/                 # 数据解析
│   │   ├── html_parser.py      # HTML 解析 (CSS/XPath)
│   │   └── markdown.py         # HTML → Markdown
│   ├── spider/                 # Spider 框架
│   │   ├── base.py             # Spider + CrawlSpider
│   │   ├── link_extractor.py   # 链接发现
│   │   └── pipeline.py         # 数据管道
│   └── utils/                  # 工具
│       └── logger.py           # 日志
├── tests/                      # 测试 (491 个用例)
├── examples/                   # 示例
│   ├── basic_scrape.py         # 基础爬取
│   ├── bypass_waf.py           # WAF 绕过
│   ├── llm_pipeline.py         # LLM 数据管道
│   ├── spider_example.py       # Spider 框架
│   ├── crawl_spider.py         # CrawlSpider 深度爬取
│   ├── data_pipeline.py        # 数据管道
│   └── cli_usage.sh            # CLI 使用示例
├── docs/                       # mkdocs 文档
├── .github/workflows/          # CI/CD
├── pyproject.toml              # 项目配置
├── CONTRIBUTING.md             # 贡献指南
├── CHANGELOG.md                # 变更日志
└── README.md                   # 本文档
```

---

## 依赖说明

| 库 | 版本 | 用途 |
|----|------|------|
| `curl_cffi` | >= 0.15 | TLS 指纹伪装（核心，37+ 浏览器指纹） |
| `scrapling` | >= 0.3 | 反反爬框架（Cloudflare 绕过、浏览器指纹防护） |
| `camoufox` | >= 0.4 | Firefox 反检测浏览器（51job、阿里云 WAF JS 环境检测） |
| `playwright` | >= 1.40 | 浏览器自动化（JS 渲染） |
| `patchright` | >= 1.40 | Scrapling 的隐身浏览器引擎 |
| `selectolax` | >= 0.3 | 高性能 HTML 解析 |
| `markdownify` | >= 0.11 | HTML → Markdown 转换 |
| `tiktoken` | >= 0.5 | Token 计数（GPT 系列模型） |
| `browserforge` | >= 1.0 | 浏览器指纹数据 |
| `msgspec` | >= 0.18 | Scrapling 依赖 |

---

## 常见问题

### Q: curl_cffi 和 requests 有什么区别？

`requests` 使用 Python 标准库的 TLS 实现，其 JA3 指纹与真实浏览器完全不同，会被 WAF 立即识别。`curl_cffi` 底层使用修改版的 libcurl，可以精确模拟 Chrome/Safari/Firefox 的 TLS 握手行为。

### Q: 什么时候用 Camoufox 模式？

当目标站点**检测浏览器 JS 环境**（如 51job）时。这些站点不仅检查 TLS 指纹，还会检查 `navigator.webdriver`、Canvas/WebGL 指纹等。Camoufox 是 Firefox 的原生修改版，指纹注入在引擎内部完成，检测不到自动化。

### Q: 什么时候用 Stealth 模式？

当目标站点使用 **Cloudflare Turnstile** 验证时。Scrapling 的 StealthyFetcher 内置 Turnstile 解决方案。

### Q: 代理从哪来？

推荐使用住宅代理服务：
- [Bright Data](https://brightdata.com/) — 最大代理池
- [Oxylabs](https://oxylabs.io/) — 企业级
- [Smartproxy](https://smartproxy.com/) — 性价比高
- [芝麻代理](https://zhimaruanji.com/) — 国内住宅代理

### Q: 如何调试？

```bash
# 开启 DEBUG 日志
OMNICRAWL_LOG_LEVEL=DEBUG python your_script.py
```

### Q: 如何贡献？

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: 添加某功能'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## License

MIT License - 详见 [LICENSE](LICENSE) 文件
