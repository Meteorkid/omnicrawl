# OmniCrawl Agent 指南

## 核心原则
- 不要猜测，先读代码再改
- 改完必须跑测试：`.venv/bin/pytest tests/ -v`
- 新模块必须写测试
- commit 用中文，push 前确认

## 模块职责
| 模块 | 职责 | 别碰 |
|------|------|------|
| client.py | 统一入口、降级逻辑 | 别在里面写抓取细节 |
| fetchers/ | 各抓取器实现 | 别互相引用 |
| anti_detect/ | WAF 策略、限速 | 别依赖 fetcher |
| parser/ | 数据解析 | 别依赖 client |
| spider/ | 爬虫框架 | 别直接用 fetcher，用 client |

## 测试规则
- 新增/修改模块 → 必须补充测试
- 测试文件命名：`tests/test_<模块名>.py`
- 异步测试用 `@pytest.mark.asyncio`
- 运行：`.venv/bin/pytest tests/ -v --tb=short`

## 常见坑
- Camoufox 每次 fetch 会启动新浏览器，批量抓取很慢
- StealthyFetcher 在国内站点容易超时
- 代理 URL 可能包含凭据，日志要脱敏
- `FetchMode.AUTO` + `waf` 参数 → 自动使用 WAF 推荐模式
