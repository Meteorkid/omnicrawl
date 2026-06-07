# WAF 绕过

## 阿里云 WAF

### TLS 指纹检测（大部分站点）

```python
async with OmniClient(
    waf="aliyun_waf",
    fingerprint="chrome136",
    proxy_pool=["http://user:pass@residential:port"],
    min_delay=3.0,
) as client:
    result = await client.get("https://protected-site.com")
```

### JS 环境检测（51job 等强反爬站点）

```python
async with OmniClient(
    mode=FetchMode.CAMOUFOX,
    waf="aliyun_waf",
    proxy_pool=["http://user:pass@residential:port"],
    min_delay=3.0,
) as client:
    result = await client.get("https://51job.com")
```

## Cloudflare

```python
async with OmniClient(
    waf="cloudflare",
    mode=FetchMode.STEALTH,
) as client:
    result = await client.get("https://cloudflare-site.com")
```

## 代理选择

| 代理类型 | 有效性 | 成本 | 推荐场景 |
|----------|--------|------|----------|
| 住宅代理 | ⭐⭐⭐⭐⭐ | 高 | 阿里云/Cloudflare |
| 移动代理 | ⭐⭐⭐⭐⭐ | 高 | 高安全性目标 |
| ISP 代理 | ⭐⭐⭐⭐ | 中 | 一般反爬 |
| 机房代理 | ⭐⭐ | 低 | 无 WAF 站点 |

## TLS 指纹轮换

```python
from omnicrawl.fingerprint.tls import TLSFingerprint

fp = TLSFingerprint()
fp.rotate(["chrome136", "chrome142", "safari180", "firefox135"])
```

## 验证码处理

OmniCrawl 支持多级验证码处理：

1. **OCR 自动识别**（简单验证码）
2. **2captcha API**（reCAPTCHA / hCaptcha / Turnstile）
3. **手动兜底**（浏览器弹窗，等待人工输入）

```python
from omnicrawl.anti_detect.captcha_solver import CaptchaSolver

solver = CaptchaSolver(twocaptcha_api_key="your-key")
result = await solver.solve_from_page(page, "https://example.com")
```
