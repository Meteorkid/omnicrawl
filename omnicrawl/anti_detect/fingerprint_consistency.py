"""浏览器指纹一致性检查 — 确保所有指纹信号"讲同一个故事""

反爬系统会交叉验证 Canvas/WebGL/Font/Plugin/Navigator 等信号，
如果 Canvas 说 Chrome 120 on macOS 但 Plugin 数组暗示 Firefox，就会暴露。
本模块提供预定义的自洽身份，确保所有信号指向同一浏览器+操作系统组合。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Optional

from omnicrawl.utils.logger import get_logger

logger = get_logger("fingerprint_consistency")


@dataclass
class BrowserIdentity:
    """一个完整的浏览器身份，所有指纹信号必须一致

    核心原则：Canvas/WebGL/Font/Plugin/Navigator 等信号必须指向同一个
    浏览器+操作系统组合，否则反爬系统会检测到矛盾。
    """

    chrome_version: str  # e.g. "120", "136", "142"
    os: str  # "windows", "macos", "linux"
    platform: str  # "Win32", "MacIntel", "Linux x86_64"
    webgl_vendor: str  # "Google Inc. (Apple)", "Google Inc. (Intel)"
    webgl_renderer: str  # "ANGLE (Apple, Apple M1, ...)", "ANGLE (Intel, ...)"
    canvas_noise_seed: int  # Canvas 噪声种子，同一身份必须用同一个
    font_list: list[str] = field(default_factory=list)  # 该操作系统可用的字体列表
    plugin_list: list[str] = field(default_factory=list)  # 该浏览器版本的 Plugin 数组
    navigator_platform: str = ""  # navigator.platform 值
    user_agent: str = ""  # 完整 UA 字符串
    browser_name: str = ""  # "chrome", "firefox", "safari"

    def validate(self) -> list[str]:
        """检查所有信号是否自洽，返回不一致的描述列表（空=一致）"""
        errors: list[str] = []

        # --- OS 和 platform 是否匹配 ---
        os_platform_map = {
            "windows": "Win32",
            "macos": "MacIntel",
            "linux": "Linux x86_64",
        }
        expected_platform = os_platform_map.get(self.os)
        if expected_platform and self.platform != expected_platform:
            errors.append(
                f"platform 不匹配: OS={self.os} 期望 {expected_platform}，实际 {self.platform}"
            )

        if self.navigator_platform and self.navigator_platform != self.platform:
            errors.append(
                f"navigator_platform({self.navigator_platform}) 与 platform({self.platform}) 不一致"
            )

        # --- chrome_version 和 user_agent 是否匹配 ---
        if self.user_agent:
            if self.browser_name == "chrome":
                version = self.chrome_version
                if version and version != "0" and f"Chrome/{version}." not in self.user_agent:
                    errors.append(
                        f"UA 中未找到 Chrome/{version}，UA={self.user_agent[:80]}"
                    )
            elif self.browser_name == "firefox":
                if "Firefox/" not in self.user_agent:
                    errors.append(f"UA 中缺少 Firefox/ 标识，UA={self.user_agent[:80]}")
            elif self.browser_name == "safari":
                if "Safari/" not in self.user_agent:
                    errors.append(
                        f"UA 缺少 Safari/ 标识，UA={self.user_agent[:80]}"
                    )
                if "Chrome/" in self.user_agent:
                    errors.append(
                        f"Safari UA 不应包含 Chrome/，UA={self.user_agent[:80]}"
                    )

        # --- webgl_vendor 和 os/browser 是否匹配 ---
        if self.os == "macos":
            # macOS: Chrome 可能是 Google Inc. (Apple) 或 (Intel)，Safari 是 Apple，Firefox 是 Mozilla
            if self.browser_name == "chrome":
                if "Google Inc." not in self.webgl_vendor:
                    errors.append(
                        f"macOS Chrome 的 WebGL vendor 应包含 Google Inc.，实际: {self.webgl_vendor}"
                    )
            elif self.browser_name == "safari":
                if "Apple" not in self.webgl_vendor:
                    errors.append(
                        f"macOS Safari 的 WebGL vendor 应包含 Apple，实际: {self.webgl_vendor}"
                    )
            # Firefox on macOS 的 vendor 可以是 "Mozilla"，不报错
        elif self.os == "windows":
            # Windows: Chrome 是 Google Inc.，Firefox 是 Mozilla
            if self.browser_name == "chrome" and "Google Inc." not in self.webgl_vendor:
                errors.append(
                    f"Windows Chrome 的 WebGL vendor 应包含 Google Inc.，实际: {self.webgl_vendor}"
                )
        elif self.os == "linux":
            if self.browser_name == "chrome" and "Google Inc." not in self.webgl_vendor:
                errors.append(
                    f"Linux Chrome 的 WebGL vendor 应包含 Google Inc.，实际: {self.webgl_vendor}"
                )

        # --- font_list 和 os 是否匹配 ---
        if self.os == "macos":
            # macOS 一定有 Helvetica Neue
            mac_fonts = {"Helvetica Neue", "Menlo", "Monaco"}
            if not mac_fonts.intersection(set(self.font_list)):
                errors.append(
                    "macOS 字体列表缺少系统字体（Helvetica Neue / Menlo / Monaco）"
                )
        elif self.os == "windows":
            win_fonts = {"Segoe UI", "Consolas", "Arial"}
            if not win_fonts.intersection(set(self.font_list)):
                errors.append(
                    "Windows 字体列表缺少系统字体（Segoe UI / Consolas / Arial）"
                )
        elif self.os == "linux":
            linux_fonts = {"DejaVu Sans", "Liberation Sans", "Noto Sans"}
            if not linux_fonts.intersection(set(self.font_list)):
                errors.append(
                    "Linux 字体列表缺少系统字体（DejaVu Sans / Liberation Sans / Noto Sans）"
                )

        # --- plugin_list 和 browser 是否匹配 ---
        if self.browser_name == "chrome":
            chrome_plugins = {"Chrome PDF Viewer", "Chrome PDF Plugin"}
            if not chrome_plugins.intersection(set(self.plugin_list)):
                errors.append(
                    "Chrome 应包含 Chrome PDF Viewer / Chrome PDF Plugin，实际无"
                )
        elif self.browser_name == "firefox":
            firefox_plugins = {"PDF Viewer"}
            if not firefox_plugins.intersection(set(self.plugin_list)):
                errors.append("Firefox 应包含 PDF Viewer plugin，实际无")
            # Firefox 不应有 Native Client
            if "Native Client" in self.plugin_list:
                errors.append("Firefox 不应包含 Native Client plugin")

        # --- UA 中的 OS 标识和 self.os 是否匹配 ---
        if self.user_agent:
            ua_os_hints = {
                "windows": ["Windows NT", "Win64"],
                "macos": ["Macintosh", "Mac OS X"],
                "linux": ["Linux"],
            }
            hints = ua_os_hints.get(self.os, [])
            if hints and not any(h in self.user_agent for h in hints):
                errors.append(
                    f"UA 中缺少 OS={self.os} 的标识，UA={self.user_agent[:80]}"
                )

        return errors


# ---------------------------------------------------------------------------
# 预定义的浏览器身份配置（每个都是自洽的完整身份）
# ---------------------------------------------------------------------------

_FONT_MACOS = [
    "Helvetica Neue", "Arial", "SF Pro Display", "SF Pro Text",
    "Menlo", "Monaco", "Courier New", "Times New Roman",
    "Georgia", "PingFang SC", "PingFang TC", "Hiragino Sans GB",
    "Grantha MN", "Trebuchet MS",
]

_FONT_WINDOWS = [
    "Segoe UI", "Arial", "Calibri", "Cambria", "Consolas",
    "Courier New", "Georgia", "Tahoma", "Times New Roman",
    "Trebuchet MS", "Verdana", "Microsoft YaHei", "SimSun",
]

_FONT_LINUX = [
    "DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
    "Liberation Sans", "Liberation Serif", "Liberation Mono",
    "Noto Sans", "Noto Serif", "Ubuntu", "Cantarell",
    "Roboto", "Droid Sans Fallback",
]

_PLUGIN_CHROME = [
    "Chrome PDF Viewer", "Chrome PDF Plugin",
    "Chromium PDF Viewer", "Chromium PDF Plugin",
    "Native Client", "Native Client Executable",
    "PDF Viewer",
]

_PLUGIN_FIREFOX = [
    "PDF Viewer",
    "Firefox PDF.js",
]

_BUILTIN_IDENTITIES: dict[str, BrowserIdentity] = {
    # ---- Chrome on macOS (Apple Silicon) ----
    "chrome_macos_m1": BrowserIdentity(
        chrome_version="142",
        os="macos",
        platform="MacIntel",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
        canvas_noise_seed=42,
        font_list=_FONT_MACOS,
        plugin_list=_PLUGIN_CHROME,
        navigator_platform="MacIntel",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        browser_name="chrome",
    ),
    # ---- Chrome on macOS (Intel) ----
    "chrome_macos_intel": BrowserIdentity(
        chrome_version="136",
        os="macos",
        platform="MacIntel",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.1)",
        canvas_noise_seed=107,
        font_list=_FONT_MACOS,
        plugin_list=_PLUGIN_CHROME,
        navigator_platform="MacIntel",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        browser_name="chrome",
    ),
    # ---- Chrome on Windows ----
    "chrome_windows": BrowserIdentity(
        chrome_version="142",
        os="windows",
        platform="Win32",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        canvas_noise_seed=233,
        font_list=_FONT_WINDOWS,
        plugin_list=_PLUGIN_CHROME,
        navigator_platform="Win32",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        browser_name="chrome",
    ),
    # ---- Chrome on Linux ----
    "chrome_linux": BrowserIdentity(
        chrome_version="136",
        os="linux",
        platform="Linux x86_64",
        webgl_vendor="Google Inc. (Mesa)",
        webgl_renderer="ANGLE (Mesa, llvmpipe (LLVM 16.0.6, 256 bits), OpenGL 4.5)",
        canvas_noise_seed=789,
        font_list=_FONT_LINUX,
        plugin_list=_PLUGIN_CHROME,
        navigator_platform="Linux x86_64",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        browser_name="chrome",
    ),
    # ---- Safari on macOS ----
    "safari_macos": BrowserIdentity(
        chrome_version="0",
        os="macos",
        platform="MacIntel",
        webgl_vendor="Apple",
        webgl_renderer="Apple M1 Pro",
        canvas_noise_seed=512,
        font_list=_FONT_MACOS,
        plugin_list=[
            "WebKit Web Content",
            "Native Client",
            "PDF Viewer",
        ],
        navigator_platform="MacIntel",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.4 Safari/605.1.15"
        ),
        browser_name="safari",
    ),
    # ---- Firefox on macOS ----
    "firefox_macos": BrowserIdentity(
        chrome_version="0",
        os="macos",
        platform="MacIntel",
        webgl_vendor="Mozilla",
        webgl_renderer="Apple M1 Pro",
        canvas_noise_seed=999,
        font_list=_FONT_MACOS,
        plugin_list=_PLUGIN_FIREFOX,
        navigator_platform="MacIntel",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) "
            "Gecko/20100101 Firefox/127.0"
        ),
        browser_name="firefox",
    ),
    # ---- Firefox on Windows ----
    "firefox_windows": BrowserIdentity(
        chrome_version="0",
        os="windows",
        platform="Win32",
        webgl_vendor="Mozilla",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
        canvas_noise_seed=1024,
        font_list=_FONT_WINDOWS,
        plugin_list=_PLUGIN_FIREFOX,
        navigator_platform="Win32",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) "
            "Gecko/20100101 Firefox/127.0"
        ),
        browser_name="firefox",
    ),
}


class FingerprintConsistency:
    """指纹一致性管理器

    用法::

        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        errors = identity.validate()

        # 随机选一个 macOS Chrome 身份
        identity = fc.random_identity(os_filter="macos", browser_filter="chrome")

        # 生成 JS 注入代码
        js_overrides = fc.get_js_overrides(identity)
    """

    def __init__(self) -> None:
        self._identities: dict[str, BrowserIdentity] = {
            k: BrowserIdentity(
                chrome_version=v.chrome_version,
                os=v.os,
                platform=v.platform,
                webgl_vendor=v.webgl_vendor,
                webgl_renderer=v.webgl_renderer,
                canvas_noise_seed=v.canvas_noise_seed,
                font_list=list(v.font_list),
                plugin_list=list(v.plugin_list),
                navigator_platform=v.navigator_platform,
                user_agent=v.user_agent,
                browser_name=v.browser_name,
            )
            for k, v in _BUILTIN_IDENTITIES.items()
        }

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def get_identity(self, name: str) -> BrowserIdentity:
        """获取指定的浏览器身份，不存在时抛出 KeyError"""
        if name not in self._identities:
            available = ", ".join(sorted(self._identities.keys()))
            raise KeyError(f"未知身份 '{name}'，可用: {available}")
        return self._identities[name]

    def list_identities(
        self,
        os_filter: Optional[str] = None,
        browser_filter: Optional[str] = None,
    ) -> list[str]:
        """列出符合条件的身份名称"""
        return [
            name
            for name, ident in self._identities.items()
            if (os_filter is None or ident.os == os_filter)
            and (browser_filter is None or ident.browser_name == browser_filter)
        ]

    def random_identity(
        self,
        os_filter: Optional[str] = None,
        browser_filter: Optional[str] = None,
    ) -> BrowserIdentity:
        """随机选择一个自洽的浏览器身份，支持 OS 和浏览器过滤"""
        candidates = [
            ident
            for ident in self._identities.values()
            if (os_filter is None or ident.os == os_filter)
            and (browser_filter is None or ident.browser_name == browser_filter)
        ]
        if not candidates:
            raise ValueError(
                f"无匹配身份 (os={os_filter}, browser={browser_filter})，"
                f"可用: {list(self._identities.keys())}"
            )
        chosen = random.choice(candidates)
        logger.info(
            "随机选择身份: os=%s browser=%s",
            chosen.os,
            chosen.browser_name,
        )
        return chosen

    def register_identity(self, name: str, identity: BrowserIdentity) -> None:
        """注册自定义身份（运行时扩展用）"""
        errors = identity.validate()
        if errors:
            logger.warning("注册身份 '%s' 存在不一致: %s", name, errors)
        self._identities[name] = identity
        logger.info("注册身份: %s (os=%s, browser=%s)", name, identity.os, identity.browser_name)

    def validate_identity(self, identity: BrowserIdentity) -> list[str]:
        """显式验证一个身份的一致性"""
        return identity.validate()

    def validate_page_fingerprint(self, identity: BrowserIdentity, page_fingerprint: dict) -> list[str]:
        """验证页面实际暴露的指纹是否与身份一致

        Args:
            identity: 当前使用的 BrowserIdentity
            page_fingerprint: 从浏览器页面中提取的实际指纹值，支持的 key:
                - navigator_platform: str
                - navigator_user_agent: str
                - navigator_vendor: str
                - webgl_vendor: str
                - webgl_renderer: str
                - plugins: list[str]

        Returns:
            不一致描述列表，空列表表示一致
        """
        errors: list[str] = []

        # navigator.platform
        actual_platform = page_fingerprint.get("navigator_platform")
        if actual_platform and actual_platform != identity.platform:
            errors.append(
                f"navigator.platform 不匹配: 身份={identity.platform}, 实际={actual_platform}"
            )

        # navigator.userAgent
        actual_ua = page_fingerprint.get("navigator_user_agent")
        if actual_ua and actual_ua != identity.user_agent:
            # 允许 UA 有细微差异，只检查浏览器版本号
            if identity.browser_name == "chrome" and f"Chrome/{identity.chrome_version}." not in actual_ua:
                errors.append(
                    f"UA 版本不匹配: 期望 Chrome/{identity.chrome_version}, UA={actual_ua[:80]}"
                )
            elif identity.browser_name == "firefox" and "Firefox/" not in actual_ua:
                errors.append(f"UA 缺少 Firefox/ 标识, UA={actual_ua[:80]}")

        # WebGL vendor
        actual_webgl_vendor = page_fingerprint.get("webgl_vendor")
        if actual_webgl_vendor and actual_webgl_vendor != identity.webgl_vendor:
            errors.append(
                f"WebGL vendor 不匹配: 身份={identity.webgl_vendor}, 实际={actual_webgl_vendor}"
            )

        # WebGL renderer
        actual_webgl_renderer = page_fingerprint.get("webgl_renderer")
        if actual_webgl_renderer and actual_webgl_renderer != identity.webgl_renderer:
            errors.append(
                f"WebGL renderer 不匹配: 身份={identity.webgl_renderer}, 实际={actual_webgl_renderer}"
            )

        # Plugins
        actual_plugins = page_fingerprint.get("plugins")
        if isinstance(actual_plugins, list):
            actual_set = set(actual_plugins)
            expected_set = set(identity.plugin_list)
            # 只检查身份期望有但实际缺失的（允许实际多出）
            missing = expected_set - actual_set
            if missing:
                errors.append(f"Plugin 缺失: {missing}")

        return errors

    def get_js_overrides(self, identity: BrowserIdentity) -> dict[str, str]:
        """生成需要注入到浏览器页面的 JS 覆盖代码

        返回 {js_property: override_value} 的字典，值为可直接执行的 JS 表达式。
        """
        overrides: dict[str, str] = {}

        # --- Navigator 属性 ---
        # 使用 json.dumps() 安全转义，防止引号/反斜杠注入
        overrides["navigator.platform"] = json.dumps(identity.platform)
        overrides["navigator.userAgent"] = json.dumps(identity.user_agent)
        overrides["navigator.appVersion"] = json.dumps(identity.user_agent[8:])

        # navigator.vendor: Chrome/Safari 有值，Firefox 为空
        if identity.browser_name == "firefox":
            overrides["navigator.vendor"] = '""'
        elif identity.browser_name == "safari":
            overrides["navigator.vendor"] = json.dumps("Apple Computer, Inc.")
        else:
            overrides["navigator.vendor"] = json.dumps("Google Inc.")

        # navigator.language
        overrides["navigator.language"] = json.dumps("en-US")

        # --- Plugin 数组 ---
        plugin_js_items = ", ".join(
            f'{{name: {json.dumps(p)}, filename: "", description: ""}}'
            for p in identity.plugin_list
        )
        overrides["navigator.plugins"] = (
            f"(function() {{ "
            f"var arr = [{plugin_js_items}]; "
            f"arr.length = {len(identity.plugin_list)}; "
            f"return arr; }})()"
        )

        # --- WebGL 指纹 ---
        # 这些需要通过 WebGLRenderingContext 的 getter hook 注入
        overrides["webgl.vendor"] = json.dumps(identity.webgl_vendor)
        overrides["webgl.renderer"] = json.dumps(identity.webgl_renderer)

        # --- Canvas 指纹种子 ---
        overrides["canvas.noise_seed"] = str(identity.canvas_noise_seed)

        # --- 字体列表 ---
        font_list_js = ", ".join(json.dumps(f) for f in identity.font_list)
        overrides["fonts.list"] = f"[{font_list_js}]"

        logger.debug(
            "生成 %d 个 JS 覆盖项 (os=%s, browser=%s)",
            len(overrides),
            identity.os,
            identity.browser_name,
        )
        return overrides

    def get_canvas_noise_seed(self, identity: BrowserIdentity) -> int:
        """获取当前身份的 Canvas 噪声种子"""
        return identity.canvas_noise_seed

    def update_versions(self, version_map: dict[str, str]) -> None:
        """批量更新预定义身份的浏览器版本号

        当 Chrome 发布新版本后，调用此方法更新所有身份的版本号和 UA，
        保持指纹新鲜度。

        Args:
            version_map: {身份名: 新版本号}，如 {"chrome_macos_m1": "143"}

        示例::

            fc.update_versions({
                "chrome_macos_m1": "143",
                "chrome_windows": "143",
            })
        """
        for name, version in version_map.items():
            if name not in self._identities:
                logger.warning("update_versions: 未知身份 '%s'，跳过", name)
                continue
            ident = self._identities[name]
            old_version = ident.chrome_version
            ident.chrome_version = version
            # 更新 UA 中的版本号
            if ident.user_agent and old_version != "0":
                ident.user_agent = ident.user_agent.replace(
                    f"Chrome/{old_version}.", f"Chrome/{version}."
                )
            logger.info(
                "更新身份 '%s' 版本: %s → %s",
                name, old_version, version,
            )
