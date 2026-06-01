"""WAF 绕过策略引擎"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from omnicrawl.fetchers.base import FetchMode
from omnicrawl.utils.logger import get_logger

logger = get_logger("waf_bypass")


@dataclass
class WAFProfile:
    """WAF 特征配置"""
    name: str
    description: str
    recommended_mode: FetchMode
    tls_fingerprints: list[str] = field(default_factory=list)
    needs_js: bool = False
    min_delay: float = 2.0
    proxy_required: bool = False


# 预定义的 WAF 配置
WAF_PROFILES: dict[str, WAFProfile] = {
    "aliyun_waf": WAFProfile(
        name="阿里云 WAF",
        description="阿里云 Web 应用防火墙，TLS 指纹 + JS 挑战 + IP 信誉。需要 Camoufox 绕过 JS 环境检测",
        recommended_mode=FetchMode.CAMOUFOX,
        tls_fingerprints=["chrome136", "chrome142", "safari180"],
        needs_js=True,
        min_delay=3.0,
        proxy_required=True,
    ),
    "cloudflare": WAFProfile(
        name="Cloudflare",
        description="Cloudflare WAF + Turnstile 验证",
        recommended_mode=FetchMode.STEALTH,
        tls_fingerprints=["chrome136", "chrome142"],
        needs_js=True,
        min_delay=2.0,
        proxy_required=False,
    ),
    "akamai": WAFProfile(
        name="Akamai",
        description="Akamai Bot Manager，HTTP/2 指纹检测",
        recommended_mode=FetchMode.HTTP,
        tls_fingerprints=["chrome136", "safari180", "firefox135"],
        needs_js=False,
        min_delay=1.5,
        proxy_required=True,
    ),
    "generic": WAFProfile(
        name="通用",
        description="无特定 WAF 或未知 WAF",
        recommended_mode=FetchMode.AUTO,
        tls_fingerprints=["chrome"],
        needs_js=False,
        min_delay=1.0,
        proxy_required=False,
    ),
}


class WAFBypass:
    """WAF 绕过策略管理器

    用法:
        bypass = WAFBypass("aliyun_waf")
        config = bypass.get_config()
        # config 包含推荐的抓取模式、TLS 指纹、延时等
    """

    def __init__(self, waf_type: str = "generic"):
        self._profile = WAF_PROFILES.get(waf_type)
        if self._profile is None:
            logger.warning(f"未知 WAF 类型 '{waf_type}'，使用通用配置。可用: {list(WAF_PROFILES.keys())}")
            self._profile = WAF_PROFILES["generic"]

    @property
    def profile(self) -> WAFProfile:
        return self._profile

    def get_recommended_mode(self) -> FetchMode:
        """获取推荐的抓取模式"""
        return self._profile.recommended_mode

    def get_tls_fingerprint(self) -> str:
        """获取推荐的 TLS 指纹（随机选择一个）"""
        import random
        if self._profile.tls_fingerprints:
            return random.choice(self._profile.tls_fingerprints)
        return "chrome"

    def get_min_delay(self) -> float:
        """获取最小请求延时"""
        return self._profile.min_delay

    @staticmethod
    def list_profiles() -> dict[str, str]:
        """列出所有 WAF 配置"""
        return {k: v.description for k, v in WAF_PROFILES.items()}
