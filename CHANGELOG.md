# Changelog

All notable changes to this project will be documented in this file.

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
