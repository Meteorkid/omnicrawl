# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-06-08

### Added

- **Session 轮换** — 请求计数+存活时间追踪，自动轮换防指纹关联（`should_rotate()` + `rotate_session()`）
- **Per-proxy 令牌桶限速** — 每代理独立速率控制（`TokenBucket` + `next_available()`）
- **空结果缓存** — 记录空 URL，TTL 内跳过重复请求（`QueryCache` + `query_cache_ttl` 参数）

### Fixed

- `rotate_session`/`close_session`/`close_browser` 锁内 await 重构为"锁内收集→锁外 IO"模式
- `ProxyRotator.remove()` 同步清理令牌桶
- 缓存 key 纳入请求参数（method/data/json），避免 POST 不同 body 同 key
- 空结果缓存跳过 status 200/301/302，避免 SPA 空页面误缓存

## [0.2.0] - 2026-06-07

### Added

- **StateStore 抽象** — 统一内存和分布式存储接口（KV/集合/列表/哈希）
- **RedisStore** — Redis 分布式后端，多 worker 共享状态
- **分布式 CrawlSpider** — `store` 参数，visited/queue 委托给 StateStore
- **RedisDedupPipeline** — 跨进程去重
- **插件系统** — Plugin ABC（6 钩子）+ PluginManager + 内置插件
- **内置插件** — LoggingPlugin, StatsPlugin, FilterPlugin, TransformPlugin
- **配置扩展** — `[storage]` 节（backend/redis_url/key_prefix）
- **文档站点** — mkdocs-material + mkdocstrings
- **CI/CD** — GitHub Actions（test/publish/docs 三个 workflow）
- **贡献指南** — CONTRIBUTING.md

## [0.1.0] - 2026-06-05

### Added

- **OmniClient** — 统一抓取入口，支持 HTTP/Browser/Camoufox/Stealth/AUTO 模式
- **TLS 指纹伪装** — 37+ 浏览器指纹（Chrome/Safari/Firefox/Edge/Tor）
- **WAF 绕过** — 阿里云 WAF、Cloudflare、Akamai 专用策略
- **Camoufox 集成** — Firefox 原生反检测浏览器
- **代理管理** — 轮询/随机/加权/评分策略，健康检查
- **智能限速** — 域名隔离，自适应延时，退避恢复
- **验证码处理** — OCR + 2captcha + 手动兜底
- **指纹一致性** — 8 个预定义浏览器身份，交叉验证
- **Spider 框架** — BFS 深度爬取，链接发现，断点续爬
- **数据管道** — Clean/Validate/Dedup/JsonFile Pipeline
- **CLI** — typer 命令行：fetch/batch/convert/version/config
- **TOML 配置** — 预设系统，环境变量支持
- **HTML 解析** — CSS/XPath 选择器，Markdown 输出
- **Token 计数** — tiktoken 集成
