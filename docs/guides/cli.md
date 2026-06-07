# CLI 命令行

OmniCrawl 提供命令行接口，无需写代码即可使用。

## 安装

安装后自动注册 `omnicrawl` 命令：

```bash
pip install omnicrawl
```

## 命令列表

### fetch — 抓取单个 URL

```bash
omnicrawl fetch https://example.com
omnicrawl fetch https://example.com --format markdown
omnicrawl fetch https://example.com --mode camoufox --waf aliyun_waf
omnicrawl fetch https://example.com --proxy http://p:8080
omnicrawl fetch https://example.com --fingerprint chrome136
omnicrawl fetch https://example.com -H "User-Agent: Custom/1.0" -H "Accept-Language: zh-CN"
omnicrawl fetch https://example.com --preset stealth
omnicrawl fetch https://example.com --output result.json
```

### batch — 批量抓取

```bash
omnicrawl batch urls.txt
omnicrawl batch urls.txt --concurrency 10 --format json
omnicrawl batch urls.txt --preset 51job --output results/
```

### convert — 转换文件格式

```bash
omnicrawl convert input.html --from html --to markdown
omnicrawl convert input.html --from html --to text
```

### version — 版本信息

```bash
omnicrawl version
```

### config — 配置管理

```bash
omnicrawl config              # 查看当前配置
omnicrawl config --preset stealth  # 查看预设
```

## 配置文件

在项目根目录创建 `omnicrawl.toml`：

```toml
[default]
fingerprint = "chrome136"
min_delay = 1.0
format = "markdown"

[presets.stealth]
mode = "stealth"
waf = "cloudflare"
fingerprint = "chrome142"
min_delay = 3.0

[presets.51job]
mode = "camoufox"
waf = "aliyun_waf"
min_delay = 5.0
```

### 配置优先级

CLI 参数 > 预设 > [default] > 环境变量

## 环境变量

所有配置都可以通过 `OMNICRAWL_` 前缀的环境变量设置：

```bash
export OMNICRAWL_FINGERPRINT=chrome136
export OMNICRAWL_MIN_DELAY=2.0
export OMNICRAWL_PROXY=http://p:8080
```
