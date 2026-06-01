"""绕过 WAF 示例 — 针对阿里云 WAF / Cloudflare"""

import asyncio
from omnicrawl import OmniClient, FetchMode


async def bypass_aliyun_waf():
    """绕过阿里云 WAF 示例"""
    print("=== 阿里云 WAF 绕过 ===")

    async with OmniClient(
        mode=FetchMode.STEALTH,       # 使用最强反检测模式
        waf="aliyun_waf",             # 启用阿里云 WAF 策略
        fingerprint="chrome136",      # TLS 指纹
        # proxy_pool=["http://user:pass@proxy1:port"],  # 住宅代理
        min_delay=3.0,                # 最小延时 3 秒
    ) as client:
        result = await client.get("https://target-site.com")
        print(f"状态: {result.status_code}")
        print(f"被拦截: {result.blocked}")
        print(f"耗时: {result.elapsed:.2f}s")
        print(f"内容长度: {len(result.markdown)} 字符")


async def bypass_cloudflare():
    """绕过 Cloudflare 示例"""
    print("\n=== Cloudflare 绕过 ===")

    async with OmniClient(
        mode=FetchMode.STEALTH,
        waf="cloudflare",
    ) as client:
        result = await client.get("https://cloudflare-protected-site.com")
        print(f"状态: {result.status_code}")
        print(f"被拦截: {result.blocked}")


async def auto_fallback():
    """自动降级示例 — 从 HTTP 到 Browser 到 Stealth"""
    print("\n=== 自动降级 ===")

    async with OmniClient(
        mode=FetchMode.AUTO,  # 自动选择最佳模式
        max_retries=3,
    ) as client:
        result = await client.get("https://target-site.com")
        print(f"最终使用模式: {result.mode_used}")
        print(f"状态: {result.status_code}")


async def tls_fingerprint_rotation():
    """TLS 指纹轮换示例"""
    print("\n=== TLS 指纹轮换 ===")
    from omnicrawl.fingerprint.tls import TLSFingerprint

    fp = TLSFingerprint()
    fp.rotate(["chrome136", "safari180", "firefox135"])

    for i in range(5):
        fingerprint = fp.next()
        print(f"  请求 {i+1}: 使用指纹 {fingerprint}")


if __name__ == "__main__":
    asyncio.run(bypass_aliyun_waf())
    asyncio.run(bypass_cloudflare())
    asyncio.run(auto_fallback())
    asyncio.run(tls_fingerprint_rotation())
