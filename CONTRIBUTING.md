# 贡献指南

感谢你对 OmniCrawl 的关注！

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/Meteorkid/omnicrawl.git
cd omnicrawl

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -e ".[dev]"

# 安装浏览器（可选）
playwright install chromium
patchright install chromium
```

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_client.py -v

# 运行并显示覆盖率
pytest tests/ -v --cov=omnicrawl --cov-report=term-missing
```

## 代码规范

- Python 3.10+，使用类型提示
- 代码风格遵循 ruff（`ruff check` + `ruff format`）
- 注释只写必要的（公共 API、复杂逻辑、业务规则）
- 命名表达业务含义，避免泛化名

## 提交规范

```
<类型>: <简短描述>

<详细说明（可选）>
```

类型：
- `feat` — 新功能
- `fix` — Bug 修复
- `refactor` — 重构
- `test` — 测试
- `docs` — 文档
- `chore` — 构建/工具

## PR 流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: 添加某功能'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

### PR 要求

- 测试通过（`pytest tests/`）
- 无 linter 错误（`ruff check`）
- 新功能需附带测试
- 更新相关文档

## 架构概述

```
omnicrawl/
├── client.py           # OmniClient 统一入口
├── config.py           # TOML 配置
├── cli.py              # CLI 入口
├── fetchers/           # 抓取器（HTTP/Browser/Camoufox/Stealth）
├── fingerprint/        # TLS/浏览器指纹
├── proxy/              # 代理轮换/验证/评分
├── anti_detect/        # 反检测（限速/WAF/验证码/指纹一致性）
├── parser/             # HTML/Markdown 解析
├── spider/             # Spider 框架（爬虫/管道/链接提取）
└── utils/              # 工具（日志）
```

## 问题反馈

- Bug 报告：使用 Issue 模板
- 功能建议：Discussion 区
- 安全问题：邮件联系（见 README）

## License

贡献的代码将按照 MIT License 发布。
