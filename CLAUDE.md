# OmniCrawl 项目配置

## 项目概述
Python 异步爬虫框架，整合 curl_cffi + Playwright + Camoufox + Scrapling，支持 WAF 绕过和 LLM 友好输出。

## 技术栈
- Python 3.10+，异步架构（asyncio）
- 依赖：curl_cffi、scrapling、camoufox、playwright、selectolax、markdownify、tiktoken
- 测试：pytest + pytest-asyncio

## 代码规范
- 类型提示必须完整（`from __future__ import annotations`）
- 所有 public 方法需 docstring
- 日志使用 `omnicrawl.utils.logger.get_logger`
- 异常不静默吞掉，至少 logger.error

## 常用命令
```bash
# 测试
/Users/meteor/omnicrawl/.venv/bin/pytest /Users/meteor/omnicrawl/tests/ -v

# 安装
/Users/meteor/omnicrawl/.venv/bin/pip install -e ".[camoufox]"

# 运行示例
/Users/meteor/omnicrawl/.venv/bin/python examples/basic_scrape.py
```

## 项目结构
- `omnicrawl/client.py` — OmniClient 统一入口
- `omnicrawl/fetchers/` — 四种抓取器（HTTP/Browser/Camoufox/Stealth）
- `omnicrawl/fingerprint/` — TLS 指纹管理
- `omnicrawl/proxy/` — 代理轮换 + 验证
- `omnicrawl/anti_detect/` — WAF 策略 + 限速
- `omnicrawl/parser/` — Markdown + HTML 解析
- `omnicrawl/spider/` — Spider 框架
- `tests/` — 65 个测试用例

## MCP 优先级
- 网页内容获取：优先用 `mcp__firecrawl__firecrawl_scrape` 或 `mcp__fetch__fetch_markdown`
- 搜索：优先用 `mcp__firecrawl__firecrawl_search`
- GitHub 操作：优先用 `mcp__github__*`
- 文件操作：优先用 `mcp__filesystem__*`
- 浏览器交互：优先用 `mcp__playwright__*`

## Git 规范
- commit 用中文
- 分支：main
- 完成后询问用户是否 commit/push
