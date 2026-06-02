"""WAF 绕过策略测试"""

import pytest
from omnicrawl.anti_detect.waf_bypass import WAFBypass, WAF_PROFILES
from omnicrawl.fetchers.base import FetchMode


class TestWAFBypass:
    def test_aliyun_waf_profile(self):
        bypass = WAFBypass("aliyun_waf")
        assert bypass.profile.name == "阿里云 WAF"
        assert bypass.get_recommended_mode() == FetchMode.CAMOUFOX
        assert bypass.get_min_delay() == 3.0

    def test_cloudflare_profile(self):
        bypass = WAFBypass("cloudflare")
        assert bypass.profile.name == "Cloudflare"
        assert bypass.get_recommended_mode() == FetchMode.STEALTH

    def test_generic_profile(self):
        bypass = WAFBypass("generic")
        assert bypass.get_recommended_mode() == FetchMode.AUTO

    def test_unknown_waf_fallback(self, caplog):
        bypass = WAFBypass("nonexistent_waf")
        assert bypass.profile.name == "通用"
        assert "未知 WAF 类型" in caplog.text

    def test_get_tls_fingerprint_returns_string(self):
        bypass = WAFBypass("aliyun_waf")
        fp = bypass.get_tls_fingerprint()
        assert isinstance(fp, str)
        assert len(fp) > 0

    def test_list_profiles(self):
        profiles = WAFBypass.list_profiles()
        assert "aliyun_waf" in profiles
        assert "cloudflare" in profiles
        assert "generic" in profiles
