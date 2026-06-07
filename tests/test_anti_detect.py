"""反检测模块测试 — captcha_solver, fingerprint_consistency, waf_bypass, rate_limiter"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnicrawl.anti_detect.captcha_solver import (
    CaptchaChallenge,
    CaptchaDetector,
    CaptchaResult,
    CaptchaSolver,
    CaptchaType,
    CloudSolver,
    LocalSolver,
)
from omnicrawl.anti_detect.fingerprint_consistency import (
    BrowserIdentity,
    FingerprintConsistency,
)
from omnicrawl.anti_detect.waf_bypass import WAFBypass, WAF_PROFILES
from omnicrawl.anti_detect.rate_limiter import RateLimiter


# ════════════════════════════════════════════════════════════════════════
# CaptchaDetector
# ════════════════════════════════════════════════════════════════════════


class TestCaptchaDetector:
    @pytest.mark.asyncio
    async def test_detect_from_html_turnstile(self):
        html = '<div class="cf-turnstile" data-sitekey="xxx"></div>'
        challenge = await CaptchaDetector().detect_from_html(html, url="http://test.com")
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.CLOUDFLARE_TURNSTILE
        assert challenge.page_url == "http://test.com"

    @pytest.mark.asyncio
    async def test_detect_from_html_recaptcha_v2(self):
        html = '<div class="g-recaptcha" data-sitekey="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-"></div>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.RECAPTCHA_V2
        assert challenge.site_key == "6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-"

    @pytest.mark.asyncio
    async def test_detect_from_html_recaptcha_v3(self):
        # 只包含 v3 特有的 render= 模式，不包含 google.com/recaptcha（会被 v2 先匹配）
        html = '<script src="https://www.recaptcha.net/recaptcha/api.js?render=6Ld-wvkS"></script>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.RECAPTCHA_V3

    @pytest.mark.asyncio
    async def test_detect_from_html_hcaptcha(self):
        html = '<div class="h-captcha" data-sitekey="10000000-ffff-ffff-ffff-000000000001"></div>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.HCAPTCHA

    @pytest.mark.asyncio
    async def test_detect_from_html_geetest(self):
        html = '<div class="geetest_panel">captcha</div>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.GEETEST

    @pytest.mark.asyncio
    async def test_detect_from_html_slide(self):
        html = '<div class="slide-verify">slide</div>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.SLIDE

    @pytest.mark.asyncio
    async def test_detect_from_html_no_captcha(self):
        html = "<html><body><h1>Hello</h1></body></html>"
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is None

    @pytest.mark.asyncio
    async def test_detect_from_html_turnstile_sitekey(self):
        html = '<div class="cf-turnstile" sitekey="0x4AAAA..."></div>'
        challenge = await CaptchaDetector().detect_from_html(html)
        assert challenge is not None
        assert challenge.site_key == "0x4AAAA..."

    @pytest.mark.asyncio
    async def test_detect_page_no_captcha(self):
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        result = await CaptchaDetector().detect(page)
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_page_found_captcha(self):
        element = AsyncMock()
        page = AsyncMock()
        # Turnstile 3 个选择器都不匹配，reCAPTCHA_v2 第一个匹配
        page.query_selector = AsyncMock(side_effect=[None, None, None, element])
        page.url = "http://test.com"
        page.evaluate = AsyncMock(return_value="site-key-123")
        result = await CaptchaDetector().detect(page)
        assert result is not None
        assert result.captcha_type == CaptchaType.RECAPTCHA_V2


# ════════════════════════════════════════════════════════════════════════
# LocalSolver
# ════════════════════════════════════════════════════════════════════════


class TestLocalSolver:
    @pytest.mark.asyncio
    async def test_solve_unsupported_type(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE)
        result = await LocalSolver().solve(challenge)
        assert not result.solved
        assert "仅支持图片" in result.error

    @pytest.mark.asyncio
    async def test_solve_no_image_data(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT)
        result = await LocalSolver().solve(challenge)
        assert not result.solved
        assert "无验证码图片" in result.error

    @pytest.mark.asyncio
    async def test_solve_ocr_not_installed(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT, image_data=b"fake")
        solver = LocalSolver()
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = await solver.solve(challenge)
        assert not result.solved


# ════════════════════════════════════════════════════════════════════════
# CloudSolver
# ════════════════════════════════════════════════════════════════════════


class TestCloudSolver:
    @pytest.mark.asyncio
    async def test_solve_no_api_key(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2, site_key="key")
        result = await CloudSolver().solve(challenge)
        assert not result.solved
        assert "API Key" in result.error

    @pytest.mark.asyncio
    async def test_solve_turnstile_no_sitekey(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE)
        result = await CloudSolver(api_key="test-key").solve(challenge)
        assert not result.solved
        assert "site_key" in result.error

    @pytest.mark.asyncio
    async def test_solve_recaptcha_no_sitekey(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2)
        result = await CloudSolver(api_key="test-key").solve(challenge)
        assert not result.solved
        assert "site_key" in result.error

    @pytest.mark.asyncio
    async def test_solve_hcaptcha_no_sitekey(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.HCAPTCHA)
        result = await CloudSolver(api_key="test-key").solve(challenge)
        assert not result.solved
        assert "site_key" in result.error

    @pytest.mark.asyncio
    async def test_solve_image_no_data(self):
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT)
        result = await CloudSolver(api_key="test-key").solve(challenge)
        assert not result.solved


# ════════════════════════════════════════════════════════════════════════
# CaptchaSolver
# ════════════════════════════════════════════════════════════════════════


class TestCaptchaSolver:
    @pytest.mark.asyncio
    async def test_solve_challenge_local_first(self):
        solver = CaptchaSolver(enable_cloud=False)
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT, image_data=b"fake")
        # mock LocalSolver to return success
        solver._local_solver = AsyncMock()
        solver._local_solver.solve = AsyncMock(return_value=CaptchaResult(
            solved=True, solution="abc123", method="local_ocr"
        ))
        result = await solver.solve_challenge(challenge)
        assert result.solved
        assert result.solution == "abc123"

    @pytest.mark.asyncio
    async def test_solve_challenge_cascade_to_cloud(self):
        solver = CaptchaSolver()
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT, image_data=b"fake")
        # local fails
        solver._local_solver = AsyncMock()
        solver._local_solver.solve = AsyncMock(return_value=CaptchaResult(solved=False, error="fail"))
        # cloud succeeds
        solver._cloud_solver = AsyncMock()
        solver._cloud_solver.solve = AsyncMock(return_value=CaptchaResult(
            solved=True, solution="token", method="cloud"
        ))
        result = await solver.solve_challenge(challenge)
        assert result.solved
        assert result.solution == "token"

    @pytest.mark.asyncio
    async def test_solve_challenge_all_fail(self):
        solver = CaptchaSolver()
        challenge = CaptchaChallenge(captcha_type=CaptchaType.IMAGE_TEXT, image_data=b"fake")
        solver._local_solver = AsyncMock()
        solver._local_solver.solve = AsyncMock(return_value=CaptchaResult(solved=False, error="fail"))
        solver._cloud_solver = AsyncMock()
        solver._cloud_solver.solve = AsyncMock(return_value=CaptchaResult(solved=False, error="fail"))
        result = await solver.solve_challenge(challenge)
        assert not result.solved
        assert "自动解决失败" in result.error

    @pytest.mark.asyncio
    async def test_solve_on_page_no_captcha(self):
        solver = CaptchaSolver()
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        result = await solver.solve_on_page(page)
        assert not result.solved
        assert "未检测到" in result.error

    @pytest.mark.asyncio
    async def test_inject_token(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=True)
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2)
        result = await CaptchaSolver._inject_token(page, challenge, "my-token")
        assert result is True

    @pytest.mark.asyncio
    async def test_inject_token_no_token(self):
        page = AsyncMock()
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2)
        result = await CaptchaSolver._inject_token(page, challenge, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_inject_text(self):
        element = AsyncMock()
        element.is_visible = AsyncMock(return_value=True)
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=element)
        result = await CaptchaSolver._inject_text(page, "1234")
        assert result is True
        element.fill.assert_called_once_with("1234")

    @pytest.mark.asyncio
    async def test_inject_text_no_element(self):
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        result = await CaptchaSolver._inject_text(page, "1234")
        assert result is False


# ════════════════════════════════════════════════════════════════════════
# FingerprintConsistency
# ════════════════════════════════════════════════════════════════════════


class TestBrowserIdentity:
    def test_consistent_identity(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        errors = identity.validate()
        assert errors == []

    def test_platform_mismatch(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.platform = "Win32"  # 故意不匹配
        errors = identity.validate()
        assert any("platform" in e for e in errors)

    def test_ua_version_mismatch(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.user_agent = identity.user_agent.replace("Chrome/142", "Chrome/99")
        errors = identity.validate()
        assert any("Chrome/142" in e for e in errors)

    def test_webgl_vendor_mismatch(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.webgl_vendor = "Mozilla"
        errors = identity.validate()
        assert any("WebGL vendor" in e for e in errors)

    def test_font_list_missing_system_font(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.font_list = ["Arial"]  # 缺少 macOS 系统字体
        errors = identity.validate()
        assert any("字体" in e for e in errors)

    def test_chrome_missing_plugins(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.plugin_list = []
        errors = identity.validate()
        assert any("Chrome PDF" in e for e in errors)

    def test_firefox_native_client_error(self):
        identity = FingerprintConsistency().get_identity("firefox_macos")
        identity.plugin_list = ["Native Client"]
        errors = identity.validate()
        assert any("Native Client" in e for e in errors)

    def test_ua_os_mismatch(self):
        identity = FingerprintConsistency().get_identity("chrome_macos_m1")
        identity.user_agent = "Mozilla/5.0 (Windows NT 10.0) Chrome/142.0.0.0"
        errors = identity.validate()
        assert any("OS" in e for e in errors)


class TestFingerprintConsistency:
    def test_get_identity(self):
        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        assert identity.os == "macos"
        assert identity.browser_name == "chrome"

    def test_get_identity_not_found(self):
        fc = FingerprintConsistency()
        with pytest.raises(KeyError, match="未知身份"):
            fc.get_identity("nonexistent")

    def test_list_identities(self):
        fc = FingerprintConsistency()
        all_ids = fc.list_identities()
        assert len(all_ids) >= 7  # 至少 7 个预定义身份

    def test_list_identities_filter_os(self):
        fc = FingerprintConsistency()
        mac_ids = fc.list_identities(os_filter="macos")
        assert all("macos" in name for name in mac_ids)

    def test_list_identities_filter_browser(self):
        fc = FingerprintConsistency()
        chrome_ids = fc.list_identities(browser_filter="chrome")
        assert all("chrome" in name for name in chrome_ids)

    def test_random_identity(self):
        fc = FingerprintConsistency()
        identity = fc.random_identity()
        assert isinstance(identity, BrowserIdentity)

    def test_random_identity_with_filter(self):
        fc = FingerprintConsistency()
        identity = fc.random_identity(os_filter="macos", browser_filter="chrome")
        assert identity.os == "macos"
        assert identity.browser_name == "chrome"

    def test_random_identity_no_match(self):
        fc = FingerprintConsistency()
        with pytest.raises(ValueError, match="无匹配身份"):
            fc.random_identity(os_filter="android")

    def test_register_identity(self):
        fc = FingerprintConsistency()
        custom = BrowserIdentity(
            chrome_version="100", os="macos", platform="MacIntel",
            webgl_vendor="Google Inc. (Apple)", webgl_renderer="ANGLE (Apple, M1)",
            canvas_noise_seed=123, font_list=["Helvetica Neue"],
            plugin_list=["Chrome PDF Viewer"], navigator_platform="MacIntel",
            user_agent="Mozilla/5.0 (Macintosh) Chrome/100.0.0.0 Safari/537.36",
            browser_name="chrome",
        )
        fc.register_identity("custom_100", custom)
        assert fc.get_identity("custom_100").chrome_version == "100"

    def test_register_identity_warns_on_inconsistency(self):
        fc = FingerprintConsistency()
        bad = BrowserIdentity(
            chrome_version="100", os="macos", platform="Win32",  # 不匹配
            webgl_vendor="Google Inc.", webgl_renderer="test",
            canvas_noise_seed=1,
        )
        fc.register_identity("bad", bad)
        assert fc.get_identity("bad").platform == "Win32"  # 仍然注册了

    def test_validate_page_fingerprint(self):
        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        page_fp = {
            "navigator_platform": "MacIntel",
            "navigator_user_agent": identity.user_agent,
            "webgl_vendor": identity.webgl_vendor,
            "webgl_renderer": identity.webgl_renderer,
        }
        errors = fc.validate_page_fingerprint(identity, page_fp)
        assert errors == []

    def test_validate_page_fingerprint_mismatch(self):
        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        page_fp = {
            "navigator_platform": "Win32",
            "webgl_vendor": "Wrong Vendor",
        }
        errors = fc.validate_page_fingerprint(identity, page_fp)
        assert len(errors) >= 2

    def test_get_js_overrides(self):
        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        overrides = fc.get_js_overrides(identity)
        assert "navigator.platform" in overrides
        assert "navigator.userAgent" in overrides
        assert "navigator.plugins" in overrides
        assert "webgl.vendor" in overrides
        assert "canvas.noise_seed" in overrides
        assert "MacIntel" in overrides["navigator.platform"]

    def test_update_versions(self):
        fc = FingerprintConsistency()
        old_ua = fc.get_identity("chrome_macos_m1").user_agent
        fc.update_versions({"chrome_macos_m1": "999"})
        new_identity = fc.get_identity("chrome_macos_m1")
        assert new_identity.chrome_version == "999"
        assert "Chrome/999" in new_identity.user_agent
        assert "Chrome/142" not in new_identity.user_agent

    def test_update_versions_unknown_identity(self):
        fc = FingerprintConsistency()
        # 不应抛异常，只记录 warning
        fc.update_versions({"nonexistent": "999"})


# ════════════════════════════════════════════════════════════════════════
# WAFBypass
# ════════════════════════════════════════════════════════════════════════


class TestWAFBypass:
    def test_known_waf(self):
        bypass = WAFBypass("aliyun_waf")
        assert bypass.profile.name == "阿里云 WAF"

    def test_unknown_waf_falls_back(self):
        bypass = WAFBypass("unknown_waf")
        assert bypass.profile.name == "通用"

    def test_get_recommended_mode(self):
        bypass = WAFBypass("aliyun_waf")
        from omnicrawl.fetchers.base import FetchMode
        assert bypass.get_recommended_mode() == FetchMode.CAMOUFOX

    def test_get_tls_fingerprint(self):
        bypass = WAFBypass("aliyun_waf")
        fp = bypass.get_tls_fingerprint()
        assert fp in ["chrome136", "chrome142", "safari180"]

    def test_get_min_delay(self):
        bypass = WAFBypass("aliyun_waf")
        assert bypass.get_min_delay() == 3.0

    def test_list_profiles(self):
        profiles = WAFBypass.list_profiles()
        assert "aliyun_waf" in profiles
        assert "cloudflare" in profiles
        assert "akamai" in profiles

    def test_all_profiles_valid(self):
        for name, profile in WAF_PROFILES.items():
            assert profile.name
            assert profile.description
            assert profile.min_delay > 0


# ════════════════════════════════════════════════════════════════════════
# RateLimiter
# ════════════════════════════════════════════════════════════════════════


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_wait_first_request(self):
        limiter = RateLimiter(min_delay=0.01)
        await limiter.wait("http://test.com/page")
        # 第一次请求应该不需要等待

    @pytest.mark.asyncio
    async def test_wait_respects_delay(self):
        limiter = RateLimiter(min_delay=0.05)
        await limiter.wait("http://test.com/page")
        start = time.time()
        await limiter.wait("http://test.com/page2")
        elapsed = time.time() - start
        assert elapsed >= 0.04  # 大约等 50ms

    def test_report_blocked_increases_delay(self):
        limiter = RateLimiter(min_delay=1.0, backoff_factor=2.0)
        limiter.report_blocked("http://test.com/page")
        domain = "test.com"
        assert limiter._domain_delays[domain] == 2.0  # 1.0 * 2^1
        limiter.report_blocked("http://test.com/page2")
        assert limiter._domain_delays[domain] == 4.0  # 1.0 * 2^2

    def test_report_success_recovers_delay(self):
        limiter = RateLimiter(min_delay=1.0, backoff_factor=2.0)
        limiter.report_blocked("http://test.com/page")
        limiter.report_blocked("http://test.com/page")
        assert limiter._domain_delays["test.com"] == 4.0
        limiter.report_success("http://test.com/page")
        assert limiter._domain_delays["test.com"] == 2.0  # 4.0 / 2

    def test_report_success_no_effect_when_not_blocked(self):
        limiter = RateLimiter(min_delay=1.0)
        limiter.report_success("http://test.com/page")
        # 不应报错，delay 保持默认

    def test_different_domains_independent(self):
        limiter = RateLimiter(min_delay=1.0, backoff_factor=2.0)
        limiter.report_blocked("http://a.com/page")
        assert "b.com" not in limiter._domain_delays
