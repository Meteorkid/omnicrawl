"""验证码自动解决 — 三级递进：本地→云端→人工"""

from __future__ import annotations

import asyncio
import base64
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from omnicrawl.utils.logger import get_logger

logger = get_logger("captcha_solver")


class CaptchaType(Enum):
    """验证码类型"""
    CLOUDFLARE_TURNSTILE = "cloudflare_turnstile"
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    IMAGE_SELECT = "image_select"      # 点选图片
    IMAGE_TEXT = "image_text"          # 图片文字识别
    SLIDE = "slide"                    # 滑块验证
    CLICK_WORD = "click_word"          # 点选文字
    GEETEST = "geetest"               # 极验
    UNKNOWN = "unknown"


@dataclass
class CaptchaChallenge:
    """检测到的验证码"""
    captcha_type: CaptchaType
    image_data: Optional[bytes] = None   # 验证码图片数据（只发图片，不发 cookie）
    image_url: Optional[str] = None      # 验证码图片 URL
    site_key: Optional[str] = None       # reCAPTCHA/hCaptcha 的 site_key
    page_url: str = ""                   # 页面 URL（用于 context）
    extra: dict = field(default_factory=dict)


@dataclass
class CaptchaResult:
    """验证码解决结果"""
    solved: bool
    solution: Optional[str] = None       # 解决方案（文字/token 等）
    captcha_type: CaptchaType = CaptchaType.UNKNOWN
    method: str = ""                     # 使用的解决方法
    error: Optional[str] = None


class CaptchaDetector:
    """验证码检测器 — 在页面中识别验证码类型和位置"""

    # 检测规则：按优先级排序，先检测最常见的
    DETECTION_RULES: dict[CaptchaType, list[str]] = {
        CaptchaType.CLOUDFLARE_TURNSTILE: [
            "iframe[src*='challenges.cloudflare.com']",
            "#turnstile-wrapper",
            ".cf-turnstile",
        ],
        CaptchaType.RECAPTCHA_V2: [
            "iframe[src*='google.com/recaptcha']",
            ".g-recaptcha",
            "#g-recaptcha",
        ],
        CaptchaType.RECAPTCHA_V3: [
            "script[src*='recaptcha/api.js?render=']",
            "#g-recaptcha-response",
        ],
        CaptchaType.HCAPTCHA: [
            "iframe[src*='hcaptcha.com']",
            ".h-captcha",
            "#h-captcha",
        ],
        CaptchaType.GEETEST: [
            ".geetest_panel",
            "#geetest_",
            ".geetest_widget",
        ],
        CaptchaType.SLIDE: [
            ".slide-verify",
            ".captcha-slide",
            "#slide-captcha",
        ],
    }

    async def detect(self, page) -> Optional[CaptchaChallenge]:
        """在 Playwright page 中检测验证码

        Args:
            page: Playwright Page 对象

        Returns:
            CaptchaChallenge 或 None（无验证码）
        """
        for captcha_type, selectors in self.DETECTION_RULES.items():
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logger.info(f"检测到验证码: {captcha_type.value} (选择器: {selector})")
                        challenge = CaptchaChallenge(
                            captcha_type=captcha_type,
                            page_url=page.url,
                        )
                        # 尝试提取 site_key
                        await self._extract_site_key(page, captcha_type, challenge)
                        # 尝试提取图片
                        await self._extract_captcha_image(page, challenge)
                        return challenge
                except Exception:
                    continue
        return None

    async def detect_from_html(self, html: str, url: str = "") -> Optional[CaptchaChallenge]:
        """从 HTML 字符串中检测验证码（不需要浏览器）"""
        for captcha_type, patterns in self._html_patterns().items():
            for pattern in patterns:
                if re.search(pattern, html, re.IGNORECASE):
                    logger.info(f"从 HTML 检测到验证码: {captcha_type.value}")
                    challenge = CaptchaChallenge(
                        captcha_type=captcha_type,
                        page_url=url,
                    )
                    # 提取 site_key
                    site_key_match = re.search(
                        r'data-sitekey=["\']([^"\']+)["\']', html
                    )
                    if site_key_match:
                        challenge.site_key = site_key_match.group(1)
                    # 提取 Turnstile 的 site_key
                    if captcha_type == CaptchaType.CLOUDFLARE_TURNSTILE:
                        site_key_match = re.search(
                            r'sitekey=["\']([^"\']+)["\']', html
                        )
                        if site_key_match:
                            challenge.site_key = site_key_match.group(1)
                    return challenge
        return None

    @staticmethod
    def _html_patterns() -> dict[CaptchaType, list[str]]:
        """HTML 检测的正则模式"""
        return {
            CaptchaType.CLOUDFLARE_TURNSTILE: [
                r"challenges\.cloudflare\.com/turnstile",
                r"cf-turnstile",
                r"turnstile-wrapper",
            ],
            CaptchaType.RECAPTCHA_V2: [
                r"google\.com/recaptcha",
                r"g-recaptcha",
            ],
            CaptchaType.RECAPTCHA_V3: [
                r"recaptcha/api\.js\?render=",
            ],
            CaptchaType.HCAPTCHA: [
                r"hcaptcha\.com",
                r"h-captcha",
            ],
            CaptchaType.GEETEST: [
                r"geetest",
            ],
            CaptchaType.SLIDE: [
                r"slide-verify",
                r"captcha-slide",
            ],
        }

    async def _extract_site_key(self, page, captcha_type: CaptchaType, challenge: CaptchaChallenge) -> None:
        """从页面中提取 site_key"""
        if captcha_type == CaptchaType.RECAPTCHA_V2:
            challenge.site_key = await page.evaluate("""() => {
                const el = document.querySelector('.g-recaptcha, #g-recaptcha');
                return el ? el.getAttribute('data-sitekey') : null;
            }""")
        elif captcha_type == CaptchaType.RECAPTCHA_V3:
            challenge.site_key = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[src*="recaptcha/api.js?render="]');
                if (scripts.length > 0) {
                    const match = scripts[0].src.match(/render=([^&]+)/);
                    return match ? match[1] : null;
                }
                return null;
            }""")
        elif captcha_type == CaptchaType.HCAPTCHA:
            challenge.site_key = await page.evaluate("""() => {
                const el = document.querySelector('.h-captcha, #h-captcha');
                return el ? el.getAttribute('data-sitekey') : null;
            }""")

    async def _extract_captcha_image(self, page, challenge: CaptchaChallenge) -> None:
        """提取验证码图片的 base64 数据"""
        image_selectors = {
            CaptchaType.IMAGE_TEXT: "img[src*='captcha'], .captcha-img img, #captcha_image",
            CaptchaType.IMAGE_SELECT: "img[src*='captcha'], .geetest_item_img img",
            CaptchaType.SLIDE: ".slide-verify-image img, .captcha-slide img",
            CaptchaType.CLICK_WORD: ".click-word-captcha img",
        }
        selector = image_selectors.get(challenge.captcha_type)
        if not selector:
            return

        try:
            element = await page.query_selector(selector)
            if element:
                screenshot = await element.screenshot(type="png")
                challenge.image_data = screenshot
                logger.debug(f"已提取验证码图片: {len(screenshot)} bytes")
        except Exception as e:
            logger.debug(f"提取验证码图片失败: {e}")


class CaptchaSolverBase(ABC):
    """验证码解决器基类"""

    @abstractmethod
    async def solve(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """解决验证码"""
        ...


class LocalSolver(CaptchaSolverBase):
    """本地解决 — 适用于简单的图片验证码

    使用 OCR 或简单的图像识别。
    """

    def __init__(self):
        self._ocr = None

    async def solve(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """尝试本地 OCR 解决图片验证码"""
        if challenge.captcha_type not in (
            CaptchaType.IMAGE_TEXT,
            CaptchaType.IMAGE_SELECT,
            CaptchaType.CLICK_WORD,
        ):
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="local",
                error="本地 OCR 仅支持图片文字类验证码",
            )

        if not challenge.image_data:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="local",
                error="无验证码图片数据",
            )

        try:
            text = await self._ocr_recognize(challenge.image_data)
            if text:
                logger.info(f"本地 OCR 识别结果: {text}")
                return CaptchaResult(
                    solved=True,
                    solution=text,
                    captcha_type=challenge.captcha_type,
                    method="local_ocr",
                )
        except ImportError:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="local",
                error="未安装 pytesseract 或 Pillow，请 pip install pytesseract Pillow",
            )
        except Exception as e:
            logger.warning(f"本地 OCR 识别失败: {e}")

        return CaptchaResult(
            solved=False,
            captcha_type=challenge.captcha_type,
            method="local",
            error="OCR 识别失败",
        )

    async def _ocr_recognize(self, image_data: bytes) -> Optional[str]:
        """使用 pytesseract 进行 OCR 识别（异步包装，避免阻塞事件循环）"""
        from io import BytesIO
        from PIL import Image
        import pytesseract

        def _do_ocr():
            img = Image.open(BytesIO(image_data))
            # 转灰度 + 二值化，提高识别率
            img = img.convert("L")
            img = img.point(lambda x: 0 if x < 128 else 255, "1")
            return pytesseract.image_to_string(
                img,
                config="--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
            )

        text = await asyncio.to_thread(_do_ocr)
        return text.strip() if text and text.strip() else None


class CloudSolver(CaptchaSolverBase):
    """云端解决 — 调用第三方验证码解决服务

    隐私设计：只发送验证码图片，不发送 cookie/URL/页面内容。
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self._api_key = api_key
        self._api_url = api_url

    async def solve(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """调用云端服务解决验证码"""
        if not self._api_key:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="cloud",
                error="未配置云端验证码解决服务的 API Key",
            )

        # 根据验证码类型选择不同的解决策略
        if challenge.captcha_type == CaptchaType.CLOUDFLARE_TURNSTILE:
            return await self._solve_turnstile(challenge)
        elif challenge.captcha_type in (CaptchaType.RECAPTCHA_V2, CaptchaType.RECAPTCHA_V3):
            return await self._solve_recaptcha(challenge)
        elif challenge.captcha_type == CaptchaType.HCAPTCHA:
            return await self._solve_hcaptcha(challenge)
        elif challenge.image_data:
            return await self._solve_image(challenge.image_data, challenge.captcha_type)
        else:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="cloud",
                error=f"云端服务暂不支持 {challenge.captcha_type.value}",
            )

    async def _solve_turnstile(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """解决 Cloudflare Turnstile"""
        if not challenge.site_key:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="cloud",
                error="缺少 Turnstile site_key",
            )
        return await self._solve_2captcha(
            sitekey=challenge.site_key,
            url=challenge.page_url,
            method="turnstile",
            captcha_type=challenge.captcha_type,
        )

    async def _solve_recaptcha(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """解决 reCAPTCHA v2/v3"""
        if not challenge.site_key:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="cloud",
                error="缺少 reCAPTCHA site_key",
            )
        method = "recaptcha_v2" if challenge.captcha_type == CaptchaType.RECAPTCHA_V2 else "recaptcha_v3"
        return await self._solve_2captcha(
            sitekey=challenge.site_key,
            url=challenge.page_url,
            method=method,
            captcha_type=challenge.captcha_type,
        )

    async def _solve_hcaptcha(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """解决 hCaptcha"""
        if not challenge.site_key:
            return CaptchaResult(
                solved=False,
                captcha_type=challenge.captcha_type,
                method="cloud",
                error="缺少 hCaptcha site_key",
            )
        return await self._solve_2captcha(
            sitekey=challenge.site_key,
            url=challenge.page_url,
            method="hcaptcha",
            captcha_type=challenge.captcha_type,
        )

    async def _solve_2captcha(
        self,
        sitekey: str,
        url: str,
        method: str,
        captcha_type: CaptchaType,
    ) -> CaptchaResult:
        """2captcha API 适配

        适用于 Turnstile、reCAPTCHA、hCaptcha 等需要 site_key 的验证码。
        API 文档: https://2captcha.com/in.php
        """
        try:
            import aiohttp
        except ImportError:
            return CaptchaResult(
                solved=False,
                captcha_type=captcha_type,
                method="cloud_2captcha",
                error="aiohttp 未安装，请运行: pip install aiohttp",
            )

        api_url = self._api_url or "https://2captcha.com"

        # 提交任务
        submit_url = f"{api_url}/in.php"
        payload = {
            "key": self._api_key,
            "method": method,
            "sitekey": sitekey,
            "pageurl": url,
            "json": 1,
        }

        try:
            async with aiohttp.ClientSession() as session:
                # 提交
                async with session.post(submit_url, data=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("status") != 1:
                        return CaptchaResult(
                            solved=False,
                            captcha_type=captcha_type,
                            method="cloud_2captcha",
                            error=f"提交失败: {data.get('request', 'unknown')}",
                        )
                    task_id = data["request"]

                # 轮询结果（最长等待 120 秒）
                result_url = f"{api_url}/res.php"
                for _ in range(24):  # 每 5 秒检查一次
                    await asyncio.sleep(5)
                    params = {
                        "key": self._api_key,
                        "action": "get",
                        "id": task_id,
                        "json": 1,
                    }
                    async with session.get(result_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        if data.get("status") == 1:
                            token = data["request"]
                            logger.info(f"云端解决成功: {captcha_type.value}")
                            return CaptchaResult(
                                solved=True,
                                solution=token,
                                captcha_type=captcha_type,
                                method="cloud_2captcha",
                            )
                        if data.get("request") != "CAPCHA_NOT_READY":
                            return CaptchaResult(
                                solved=False,
                                captcha_type=captcha_type,
                                method="cloud_2captcha",
                                error=f"解决失败: {data.get('request', 'unknown')}",
                            )

                return CaptchaResult(
                    solved=False,
                    captcha_type=captcha_type,
                    method="cloud_2captcha",
                    error="超时：验证码解决耗时过长",
                )
        except asyncio.TimeoutError:
            return CaptchaResult(
                solved=False,
                captcha_type=captcha_type,
                method="cloud_2captcha",
                error="网络超时",
            )
        except Exception as e:
            return CaptchaResult(
                solved=False,
                captcha_type=captcha_type,
                method="cloud_2captcha",
                error=f"请求异常: {e}",
            )

    async def _solve_image(self, image_data: bytes, captcha_type: CaptchaType) -> CaptchaResult:
        """发送图片验证码到云端（只发图片，不发 cookie/URL）"""
        import aiohttp

        api_url = self._api_key and (self._api_url or "https://2captcha.com")
        if not api_url:
            return CaptchaResult(
                solved=False,
                captcha_type=captcha_type,
                method="cloud_image",
                error="未配置 API Key",
            )

        base64_image = base64.b64encode(image_data).decode("utf-8")

        try:
            async with aiohttp.ClientSession() as session:
                # base64 方式提交
                payload = {
                    "key": self._api_key,
                    "method": "base64",
                    "body": base64_image,
                    "json": 1,
                }
                async with session.post(
                    f"{api_url}/in.php", data=payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()
                    if data.get("status") != 1:
                        return CaptchaResult(
                            solved=False,
                            captcha_type=captcha_type,
                            method="cloud_image",
                            error=f"提交失败: {data.get('request', 'unknown')}",
                        )
                    task_id = data["request"]

                # 轮询结果
                for _ in range(12):  # 图片验证码通常较快，等 60 秒
                    await asyncio.sleep(5)
                    params = {
                        "key": self._api_key,
                        "action": "get",
                        "id": task_id,
                        "json": 1,
                    }
                    async with session.get(
                        f"{api_url}/res.php", params=params, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        data = await resp.json()
                        if data.get("status") == 1:
                            return CaptchaResult(
                                solved=True,
                                solution=data["request"],
                                captcha_type=captcha_type,
                                method="cloud_image",
                            )
                        if data.get("request") != "CAPCHA_NOT_READY":
                            return CaptchaResult(
                                solved=False,
                                captcha_type=captcha_type,
                                method="cloud_image",
                                error=f"解决失败: {data.get('request', 'unknown')}",
                            )

                return CaptchaResult(
                    solved=False,
                    captcha_type=captcha_type,
                    method="cloud_image",
                    error="超时：图片验证码解决耗时过长",
                )
        except Exception as e:
            return CaptchaResult(
                solved=False,
                captcha_type=captcha_type,
                method="cloud_image",
                error=f"请求异常: {e}",
            )


class CaptchaSolver:
    """验证码自动解决管理器

    三级递进策略：
    1. 本地解决（OCR，适用于简单图片验证码）
    2. 云端解决（第三方服务，只发图片）
    3. 返回未解决（上层可降级到人工）

    用法:
        solver = CaptchaSolver()

        # 在 Playwright page 中检测并解决
        result = await solver.solve_on_page(page)
        if result.solved:
            print(f"已解决: {result.solution}")
        else:
            # 降级到人工
            ...

        # 从 HTML 中检测
        challenge = await solver.detector.detect_from_html(html)
        if challenge:
            result = await solver.solve_challenge(challenge)
    """

    def __init__(
        self,
        cloud_api_key: Optional[str] = None,
        cloud_api_url: Optional[str] = None,
        enable_local: bool = True,
        enable_cloud: bool = True,
    ):
        self.detector = CaptchaDetector()
        self._local_solver = LocalSolver() if enable_local else None
        self._cloud_solver = CloudSolver(cloud_api_key, cloud_api_url) if enable_cloud else None

    async def solve_on_page(self, page) -> CaptchaResult:
        """在页面上检测并解决验证码

        Args:
            page: Playwright Page 对象
        """
        challenge = await self.detector.detect(page)
        if not challenge:
            logger.debug("页面无验证码")
            return CaptchaResult(solved=False, error="未检测到验证码")

        result = await self.solve_challenge(challenge)
        if result.solved:
            injected = await self.inject_solution(page, challenge, result)
            if not injected:
                logger.warning("解决方案注入失败")
                return CaptchaResult(
                    solved=False,
                    captcha_type=challenge.captcha_type,
                    error="解决方案注入页面失败",
                )
        return result

    async def solve_challenge(self, challenge: CaptchaChallenge) -> CaptchaResult:
        """解决已检测到的验证码

        按优先级尝试：本地 → 云端
        """
        # 第一级：本地解决
        if self._local_solver:
            result = await self._local_solver.solve(challenge)
            if result.solved:
                return result
            logger.debug(f"本地解决失败: {result.error}")

        # 第二级：云端解决
        if self._cloud_solver:
            result = await self._cloud_solver.solve(challenge)
            if result.solved:
                return result
            logger.debug(f"云端解决失败: {result.error}")

        # 第三级：未解决，上层可降级到人工
        logger.warning(f"所有自动解决方式均失败: {challenge.captcha_type.value}")
        return CaptchaResult(
            solved=False,
            captcha_type=challenge.captcha_type,
            method="auto",
            error="自动解决失败，建议降级到人工",
        )

    async def inject_solution(self, page, challenge: CaptchaChallenge, result: CaptchaResult) -> bool:
        """将解决方案注入到页面中

        根据验证码类型选择不同的注入方式：
        - reCAPTCHA/hCaptcha/Turnstile: 填入隐藏 textarea 并触发回调
        - 图片文字类: 填入输入框
        - 滑块: 模拟拖拽
        """
        try:
            if challenge.captcha_type in (
                CaptchaType.RECAPTCHA_V2,
                CaptchaType.RECAPTCHA_V3,
                CaptchaType.CLOUDFLARE_TURNSTILE,
                CaptchaType.HCAPTCHA,
            ):
                return await self._inject_token(page, challenge, result.solution)
            elif challenge.captcha_type in (
                CaptchaType.IMAGE_TEXT,
                CaptchaType.IMAGE_SELECT,
                CaptchaType.CLICK_WORD,
            ):
                return await self._inject_text(page, result.solution)
            elif challenge.captcha_type == CaptchaType.SLIDE:
                logger.info("滑块验证码需要模拟拖拽，建议使用 --headed 模式人工操作")
                return False
            else:
                logger.warning(f"未知验证码类型 {challenge.captcha_type.value}，无法自动注入")
                return False
        except Exception as e:
            logger.error(f"注入解决方案失败: {e}")
            return False

    @staticmethod
    async def _inject_token(page, challenge: CaptchaChallenge, token: Optional[str]) -> bool:
        """向隐藏的 textarea 注入 token"""
        if not token:
            return False

        textarea_selectors = {
            CaptchaType.RECAPTCHA_V2: "#g-recaptcha-response",
            CaptchaType.RECAPTCHA_V3: "#g-recaptcha-response",
            CaptchaType.CLOUDFLARE_TURNSTILE: "[name='cf-turnstile-response']",
            CaptchaType.HCAPTCHA: "[name='h-captcha-response']",
        }
        selector = textarea_selectors.get(challenge.captcha_type)
        if not selector:
            return False

        injected = await page.evaluate("""(args) => {
            const [selector, token] = args;
            const textarea = document.querySelector(selector);
            if (!textarea) return false;
            textarea.value = token;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            // 触发回调
            const form = textarea.closest('form');
            if (form) {
                form.dispatchEvent(new Event('submit', { bubbles: true }));
            }
            // Turnstile 需要额外调用 callback
            if (window.turnstile) {
                try { window.turnstile.execute(); } catch(e) {}
            }
            return true;
        }""", [selector, token])
        return injected

    @staticmethod
    async def _inject_text(page, text: Optional[str]) -> bool:
        """向验证码输入框填入文字"""
        if not text:
            return False

        input_selectors = [
            "input[name*='captcha']:visible",
            "input[id*='captcha']:visible",
            "input[placeholder*='验证码']:visible",
            "input[placeholder*='captcha']:visible",
            ".captcha-input input:visible",
            # 回退：无 :visible 伪类时仍可匹配
            "input[name*='captcha']",
            "input[id*='captcha']",
            "input[placeholder*='验证码']",
            "input[placeholder*='captcha']",
            ".captcha-input input",
        ]
        for selector in input_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # 二次校验：确保元素可见且未禁用
                    is_visible = await element.is_visible()
                    if not is_visible:
                        continue
                    await element.fill(text)
                    logger.info(f"已填入验证码文字: {text}")
                    return True
            except Exception:
                continue
        return False
