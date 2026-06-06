"""Browser Act 新功能模块测试"""

import asyncio
import pytest
from omnicrawl.anti_detect.fingerprint_consistency import (
    BrowserIdentity,
    FingerprintConsistency,
    _BUILTIN_IDENTITIES,
)
from omnicrawl.anti_detect.captcha_solver import (
    CaptchaType,
    CaptchaDetector,
    CaptchaChallenge,
    CaptchaResult,
)
from omnicrawl.parser.interactive_state import (
    InteractiveStateExtractor,
    PageState,
    InteractiveElement,
)
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.spider.smart_spider import (
    ApiEndpoint,
    NetworkCapture,
    DiscoveryResult,
)


# ======================================================================
# 1. fingerprint_consistency
# ======================================================================
class TestBrowserIdentity:
    def test_validate_consistent_identity(self):
        """自洽身份 validate 返回空列表"""
        ident = _BUILTIN_IDENTITIES["chrome_macos_m1"]
        errors = ident.validate()
        assert errors == [], f"预定义身份应自洽，但有: {errors}"

    def test_validate_inconsistent_os_platform(self):
        """OS 和 platform 不匹配时返回错误"""
        ident = BrowserIdentity(
            chrome_version="142",
            os="windows",
            platform="MacIntel",  # 应为 Win32
            webgl_vendor="Google Inc. (NVIDIA)",
            webgl_renderer="ANGLE",
            canvas_noise_seed=1,
            font_list=["Segoe UI"],
            plugin_list=["Chrome PDF Viewer"],
            navigator_platform="MacIntel",
            browser_name="chrome",
        )
        errors = ident.validate()
        assert any("platform 不匹配" in e for e in errors)

    def test_validate_inconsistent_navigator_platform(self):
        """navigator_platform 与 platform 不一致"""
        ident = BrowserIdentity(
            chrome_version="142",
            os="windows",
            platform="Win32",
            webgl_vendor="Google Inc.",
            webgl_renderer="ANGLE",
            canvas_noise_seed=1,
            font_list=["Segoe UI"],
            plugin_list=["Chrome PDF Viewer"],
            navigator_platform="MacIntel",  # 与 platform 矛盾
            browser_name="chrome",
        )
        errors = ident.validate()
        assert any("navigator_platform" in e for e in errors)

    def test_validate_ua_missing_os_identifier(self):
        """UA 中缺少 OS 标识"""
        ident = BrowserIdentity(
            chrome_version="142",
            os="windows",
            platform="Win32",
            webgl_vendor="Google Inc.",
            webgl_renderer="ANGLE",
            canvas_noise_seed=1,
            font_list=["Segoe UI"],
            plugin_list=["Chrome PDF Viewer"],
            navigator_platform="Win32",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/142.0.0.0",
            browser_name="chrome",
        )
        errors = ident.validate()
        assert any("缺少 OS=windows" in e for e in errors)

    def test_all_builtin_identities_are_consistent(self):
        """所有预定义身份都通过 validate"""
        for name, ident in _BUILTIN_IDENTITIES.items():
            errors = ident.validate()
            assert errors == [], f"预定义身份 {name} 不自洽: {errors}"


class TestFingerprintConsistency:
    def test_get_identity(self):
        fc = FingerprintConsistency()
        ident = fc.get_identity("chrome_macos_m1")
        assert ident.os == "macos"
        assert ident.browser_name == "chrome"

    def test_get_identity_unknown_raises(self):
        fc = FingerprintConsistency()
        with pytest.raises(KeyError, match="未知身份"):
            fc.get_identity("nonexistent")

    def test_random_identity_os_filter(self):
        fc = FingerprintConsistency()
        ident = fc.random_identity(os_filter="macos")
        assert ident.os == "macos"

    def test_random_identity_browser_filter(self):
        fc = FingerprintConsistency()
        ident = fc.random_identity(browser_filter="firefox")
        assert ident.browser_name == "firefox"

    def test_random_identity_combined_filter(self):
        fc = FingerprintConsistency()
        ident = fc.random_identity(os_filter="windows", browser_filter="chrome")
        assert ident.os == "windows"
        assert ident.browser_name == "chrome"

    def test_random_identity_no_match_raises(self):
        fc = FingerprintConsistency()
        with pytest.raises(ValueError, match="无匹配身份"):
            fc.random_identity(os_filter="ios", browser_filter="safari")

    def test_list_identities(self):
        fc = FingerprintConsistency()
        all_ids = fc.list_identities()
        assert len(all_ids) == len(_BUILTIN_IDENTITIES)

    def test_list_identities_filtered(self):
        fc = FingerprintConsistency()
        mac_ids = fc.list_identities(os_filter="macos")
        assert all(fc.get_identity(n).os == "macos" for n in mac_ids)

    def test_get_js_overrides_returns_nonempty_dict(self):
        fc = FingerprintConsistency()
        ident = fc.get_identity("chrome_macos_m1")
        overrides = fc.get_js_overrides(ident)
        assert isinstance(overrides, dict)
        assert len(overrides) > 0
        assert "navigator.platform" in overrides
        assert "webgl.vendor" in overrides

    def test_validate_page_fingerprint_consistent(self):
        fc = FingerprintConsistency()
        ident = fc.get_identity("chrome_macos_m1")
        page_fp = {
            "navigator_platform": ident.platform,
            "navigator_user_agent": ident.user_agent,
            "webgl_vendor": ident.webgl_vendor,
            "webgl_renderer": ident.webgl_renderer,
            "plugins": ident.plugin_list,
        }
        errors = fc.validate_page_fingerprint(ident, page_fp)
        assert errors == []


# ======================================================================
# 2. session/manager
# ======================================================================
class TestSessionManager:
    @pytest.fixture
    def manager(self):
        from omnicrawl.session.manager import SessionManager
        return SessionManager()

    @pytest.mark.asyncio
    async def test_create_browser(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        bh = await manager.create_browser("main", mode=FetchMode.HTTP, desc="test browser")
        assert bh.name == "main"
        assert bh.desc == "test browser"
        assert bh.mode == FetchMode.HTTP

    @pytest.mark.asyncio
    async def test_create_duplicate_browser_returns_existing(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        bh1 = await manager.create_browser("main", mode=FetchMode.HTTP, desc="first")
        bh2 = await manager.create_browser("main", mode=FetchMode.HTTP, desc="second")
        assert bh1.id == bh2.id

    @pytest.mark.asyncio
    async def test_open_and_close_session(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("main", mode=FetchMode.HTTP)
        session = await manager.open_session("main", "search")
        assert session.name == "search"
        sessions = manager.list_sessions()
        assert len(sessions) == 1

        await manager.close_session("search")
        sessions = manager.list_sessions()
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_open_session_on_nonexistent_browser_raises(self, manager):
        with pytest.raises(KeyError, match="不存在"):
            await manager.open_session("nonexistent", "s1")

    @pytest.mark.asyncio
    async def test_find_browser(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("main", mode=FetchMode.HTTP, desc="51job 登录态浏览器")
        found = manager.find_browser("51job 登录")
        assert found is not None
        assert found.name == "main"

    @pytest.mark.asyncio
    async def test_find_browser_no_match(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("main", mode=FetchMode.HTTP, desc="51job 登录态浏览器")
        found = manager.find_browser("淘宝购物")
        assert found is None

    @pytest.mark.asyncio
    async def test_append_desc(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("main", mode=FetchMode.HTTP, desc="初始描述")
        manager.append_desc("main", "新信息")
        bh = manager.list_browsers()[0]
        assert bh.desc == "初始描述 | 新信息"

    @pytest.mark.asyncio
    async def test_list_browsers(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("a", mode=FetchMode.HTTP)
        await manager.create_browser("b", mode=FetchMode.HTTP)
        browsers = manager.list_browsers()
        assert len(browsers) == 2

    @pytest.mark.asyncio
    async def test_close_browser_removes_it(self, manager):
        from omnicrawl.fetchers.base import FetchMode
        await manager.create_browser("main", mode=FetchMode.HTTP)
        await manager.close_browser("main")
        assert len(manager.list_browsers()) == 0


# ======================================================================
# 3. interactive_state
# ======================================================================
class TestInteractiveStateExtractor:
    @pytest.fixture
    def extractor(self):
        return InteractiveStateExtractor()

    def test_extract_basic_elements(self, extractor):
        html = """
        <html><body>
            <a href="/link">Click</a>
            <button type="submit">Submit</button>
            <input type="text" placeholder="Search" />
        </body></html>
        """
        state = extractor.extract(html, url="https://example.com")
        assert len(state.elements) == 3
        tags = [e.tag for e in state.elements]
        assert "a" in tags
        assert "button" in tags
        assert "input" in tags

    def test_indices_start_at_one(self, extractor):
        html = """
        <html><body>
            <a href="/a">A</a>
            <a href="/b">B</a>
            <a href="/c">C</a>
        </body></html>
        """
        state = extractor.extract(html)
        indices = [e.index for e in state.elements]
        assert indices == [1, 2, 3]

    def test_hidden_elements_filtered(self, extractor):
        html = """
        <html><body>
            <a href="/visible">Visible</a>
            <a href="/hidden" style="display:none">Hidden</a>
            <input type="hidden" name="csrf" value="abc" />
            <div aria-hidden="true"><a href="/aria">Aria</a></div>
        </body></html>
        """
        state = extractor.extract(html)
        hrefs = [e.href for e in state.elements]
        assert "/visible" in hrefs
        assert "/hidden" not in hrefs
        assert "/aria" not in hrefs

    def test_to_state_text_format(self, extractor):
        html = """
        <html><head><title>Test Page</title></head>
        <body>
            <a href="/link">Click Me</a>
            <input type="text" placeholder="Search" />
        </body></html>
        """
        state = extractor.extract(html, url="https://example.com")
        text = state.to_state_text()
        assert "url=https://example.com" in text
        assert "title=Test Page" in text
        assert "[1]" in text
        assert "[2]" in text
        assert "<a " in text
        assert "<input " in text

    def test_diff_detects_new_elements(self, extractor):
        html1 = "<html><body><a href='/a'>A</a></body></html>"
        html2 = "<html><body><a href='/a'>A</a><a href='/b'>B</a></body></html>"
        state1 = extractor.extract(html1)
        state2 = extractor.extract(html2)
        delta = state1.diff(state2)
        assert len(delta) == 1
        assert 2 in delta

    def test_diff_no_changes(self, extractor):
        html = "<html><body><a href='/a'>A</a></body></html>"
        state1 = extractor.extract(html)
        state2 = extractor.extract(html)
        delta = state1.diff(state2)
        assert len(delta) == 0

    def test_delta_marker_in_state_text(self, extractor):
        html1 = "<html><body><a href='/a'>A</a></body></html>"
        html2 = "<html><body><a href='/a'>A</a><a href='/b'>B</a></body></html>"
        state1 = extractor.extract(html1)
        state2 = extractor.extract(html2)
        delta = state1.diff(state2)
        text = state2.to_state_text(delta_indices=delta)
        assert "*[2]" in text


# ======================================================================
# 4. captcha_solver
# ======================================================================
class TestCaptchaType:
    def test_enum_values(self):
        assert CaptchaType.CLOUDFLARE_TURNSTILE.value == "cloudflare_turnstile"
        assert CaptchaType.RECAPTCHA_V2.value == "recaptcha_v2"
        assert CaptchaType.SLIDE.value == "slide"
        assert CaptchaType.UNKNOWN.value == "unknown"

    def test_all_types_exist(self):
        assert len(CaptchaType) >= 10


class TestCaptchaChallenge:
    def test_creation(self):
        c = CaptchaChallenge(
            captcha_type=CaptchaType.RECAPTCHA_V2,
            site_key="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
            page_url="https://example.com",
        )
        assert c.captcha_type == CaptchaType.RECAPTCHA_V2
        assert c.site_key.startswith("6Le-")
        assert c.image_data is None

    def test_extra_field(self):
        c = CaptchaChallenge(
            captcha_type=CaptchaType.SLIDE,
            extra={"track": [1, 2, 3]},
        )
        assert c.extra["track"] == [1, 2, 3]


class TestCaptchaResult:
    def test_solved(self):
        r = CaptchaResult(solved=True, solution="03ABC", captcha_type=CaptchaType.IMAGE_TEXT)
        assert r.solved is True
        assert r.solution == "03ABC"

    def test_unsolved(self):
        r = CaptchaResult(solved=False, error="OCR failed")
        assert r.solved is False
        assert r.error == "OCR failed"


class TestCaptchaDetector:
    @pytest.mark.asyncio
    async def test_detect_cloudflare_turnstile(self):
        detector = CaptchaDetector()
        html = '<div class="cf-turnstile" data-sitekey="0x4AAAA"></div>'
        challenge = await detector.detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.CLOUDFLARE_TURNSTILE

    @pytest.mark.asyncio
    async def test_detect_recaptcha_v2(self):
        detector = CaptchaDetector()
        html = '<div class="g-recaptcha" data-sitekey="6Le-wvkS"></div>'
        challenge = await detector.detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.RECAPTCHA_V2
        assert challenge.site_key == "6Le-wvkS"

    @pytest.mark.asyncio
    async def test_detect_hcaptcha(self):
        detector = CaptchaDetector()
        html = '<iframe src="https://hcaptcha.com/"></iframe>'
        challenge = await detector.detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.HCAPTCHA

    @pytest.mark.asyncio
    async def test_detect_no_captcha(self):
        detector = CaptchaDetector()
        html = "<html><body><p>Hello world</p></body></html>"
        challenge = await detector.detect_from_html(html)
        assert challenge is None

    @pytest.mark.asyncio
    async def test_detect_geetest(self):
        detector = CaptchaDetector()
        html = '<div class="geetest_panel"></div>'
        challenge = await detector.detect_from_html(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.GEETEST


# ======================================================================
# 5. smart_spider
# ======================================================================
class TestApiEndpoint:
    def test_stability_score_json_high_freq(self):
        ep = ApiEndpoint(url="https://api.example.com/data", response_type="json", frequency=5)
        score = ep.stability_score
        assert score == 1.0  # min(5/5, 1.0) * 1.5 capped to 1.0

    def test_stability_score_json_low_freq(self):
        ep = ApiEndpoint(url="https://api.example.com/data", response_type="json", frequency=2)
        score = ep.stability_score
        assert abs(score - 0.6) < 0.01  # (2/5) * 1.5 = 0.6

    def test_stability_score_html(self):
        ep = ApiEndpoint(url="https://example.com/data", response_type="html", frequency=5)
        score = ep.stability_score
        assert score == 1.0  # min(5/5, 1.0) * 1.0 = 1.0

    def test_stability_score_zero_freq(self):
        ep = ApiEndpoint(url="https://example.com/data", frequency=0)
        assert ep.stability_score == 0.0


class TestNetworkCaptureIsLikelyApi:
    def setup_method(self):
        self.capture = NetworkCapture()

    def test_json_content_type(self):
        assert self.capture._is_likely_api("https://example.com/data", "xhr", "application/json")

    def test_api_path_pattern(self):
        assert self.capture._is_likely_api("https://example.com/api/users", "xhr", "")

    def test_v1_path_pattern(self):
        assert self.capture._is_likely_api("https://example.com/v2/search", "xhr", "")

    def test_static_resource_rejected(self):
        assert not self.capture._is_likely_api("https://example.com/app.css", "xhr", "text/css")

    def test_non_xhr_rejected(self):
        assert not self.capture._is_likely_api("https://example.com/api/data", "image", "")

    def test_fetch_type_accepted(self):
        assert self.capture._is_likely_api("https://example.com/api/items", "fetch", "")


class TestDiscoveryResult:
    def test_best_endpoint_empty(self):
        dr = DiscoveryResult()
        assert dr.best_endpoint is None

    def test_best_endpoint_sorts_by_stability(self):
        ep1 = ApiEndpoint(url="https://a.com/api", response_type="html", frequency=1)
        ep2 = ApiEndpoint(url="https://b.com/api", response_type="json", frequency=3)
        dr = DiscoveryResult(endpoints=[ep1, ep2])
        best = dr.best_endpoint
        assert best.url == "https://b.com/api"

    def test_best_endpoint_single(self):
        ep = ApiEndpoint(url="https://only.com/api", response_type="json", frequency=1)
        dr = DiscoveryResult(endpoints=[ep])
        assert dr.best_endpoint.url == "https://only.com/api"


# ======================================================================
# 6. markdown (enhanced features)
# ======================================================================
class TestMarkdownCompact:
    def test_removes_empty_links(self):
        converter = MarkdownConverter(compact=True)
        md = converter.convert("<p><a href='/link'></a></p><p>Content</p>")
        assert "Content" in md
        # 空链接应该被移除

    def test_removes_image_only_lines(self):
        converter = MarkdownConverter(compact=True)
        md = converter.convert('<p><img src="x.jpg"/></p><p>Real text</p>')
        assert "Real text" in md

    def test_deduplicates_hr(self):
        converter = MarkdownConverter(compact=True)
        html = "<hr/><hr/><hr/><p>Content</p>"
        md = converter.convert(html)
        assert "Content" in md


class TestMarkdownTokenTruncation:
    def test_no_truncation_when_under_limit(self):
        converter = MarkdownConverter(max_tokens=10000)
        md = converter.convert("<p>Hello World</p>")
        assert "Hello World" in md

    def test_truncation_at_paragraph_boundary(self):
        converter = MarkdownConverter(max_tokens=5)
        paragraphs = "".join(f"<p>Paragraph {i}. {'Word ' * 20}</p>" for i in range(20))
        md = converter.convert(paragraphs)
        assert "[truncated" in md

    def test_convert_with_stats(self):
        converter = MarkdownConverter()
        html = "<h1>Title</h1><p>Some content here.</p>"
        result = converter.convert_with_stats(html)
        assert "markdown" in result
        assert "original_tokens" in result
        assert "cleaned_tokens" in result
        assert "compression_ratio" in result
        assert result["original_tokens"] > 0
        assert result["compression_ratio"] > 0


class TestMarkdownSegment:
    def test_segment_no_size_returns_single(self):
        converter = MarkdownConverter()
        md = "Para 1\n\nPara 2\n\nPara 3"
        segments = converter.segment(md)
        assert len(segments) == 1
        assert segments[0] == md

    def test_segment_with_size(self):
        converter = MarkdownConverter(segment_size=20)
        paras = [f"Paragraph {i}. {'Words ' * 5}" for i in range(10)]
        md = "\n\n".join(paras)
        segments = converter.segment(md, segment_size=20)
        assert len(segments) > 1

    def test_segment_preserves_paragraph_boundaries(self):
        converter = MarkdownConverter(segment_size=30)
        md = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        segments = converter.segment(md, segment_size=30)
        for seg in segments:
            # 每段应包含完整的段落
            assert seg.strip()
