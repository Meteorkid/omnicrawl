# 安装

## 基础安装

```bash
pip install omnicrawl
```

## 可选依赖

```bash
# Camoufox（51job 等强反爬站点需要）
pip install "omnicrawl[camoufox]"
camoufox fetch

# 开发依赖（测试 + 覆盖率）
pip install "omnicrawl[dev]"

# 文档构建
pip install "omnicrawl[docs]"
```

## 浏览器安装

```bash
# Playwright（Browser 模式需要）
playwright install chromium

# Patchright（Stealth 模式需要）
patchright install chromium
```

## 环境要求

- Python >= 3.10
- macOS / Linux / Windows

## 从源码安装

```bash
git clone https://github.com/Meteorkid/omnicrawl.git
cd omnicrawl
pip install -e ".[dev]"
```

## 验证安装

```bash
omnicrawl version
```
