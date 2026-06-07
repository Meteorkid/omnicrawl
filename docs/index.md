# OmniCrawl 🕷️

**无所不能的爬虫框架** — 整合 Scrapling + curl_cffi + Playwright，绕过 WAF，LLM 友好输出。

## 为什么选择 OmniCrawl？

| 库 | 问题 |
|---|---|
| `requests` | TLS 指纹暴露，被 WAF 秒封 |
| `httpx` | 同上，HTTP/2 指纹也暴露 |
| `Selenium` | 自动化痕迹明显，资源消耗大 |
| `Playwright` | 无内置爬虫逻辑，无反检测 |
| **OmniCrawl** | ✅ 统一 API，自动选择最优方案 |

## 核心特性

- **🔒 TLS 指纹伪装** — 37+ 浏览器指纹，绕过 JA3/JA4 检测
- **🛡️ WAF 绕过** — 阿里云 WAF、Cloudflare、Akamai 专用策略
- **🦊 Camoufox** — Firefox 原生反检测浏览器
- **🔄 自动降级** — HTTP → Browser → Camoufox → Stealth
- **🌐 代理轮换** — 轮询/随机/加权策略
- **📝 LLM 输出** — 干净 Markdown + Token 计数
- **🕷️ Spider 框架** — 深度限制、去重、断点续爬
- **⚙️ CLI** — 命令行直接使用

## 快速体验

```bash
pip install omnicrawl
```

```python
import asyncio
from omnicrawl import OmniClient

async def main():
    async with OmniClient() as client:
        result = await client.get("https://example.com")
        print(result.markdown)  # 干净的 Markdown

asyncio.run(main())
```

## 适用场景

- **数据采集** — 绕过 WAF 抓取目标站点
- **LLM 数据管道** — 网页转干净 Markdown
- **竞品监控** — 定期抓取价格/库存变化
- **SEO 分析** — 批量抓取页面结构
