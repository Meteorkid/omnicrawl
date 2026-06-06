"""SmartSpider — API 优先发现的智能爬虫

核心思路：优先抓 XHR/fetch 网络请求找到隐藏的 API 端点，DOM 作为兜底。
API 比 DOM 稳定 10 倍——前端改版不会影响数据接口。

灵感来源：BrowserAct skill-forge 优先抓 XHR/fetch 网络请求发现 API 端点。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional
from urllib.parse import urlparse, parse_qs

from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.spider.base import Spider, SpiderItem, SpiderStats
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.utils.logger import get_logger

logger = get_logger("smart_spider")


@dataclass
class ApiEndpoint:
    """发现的 API 端点"""
    url: str
    method: str = "GET"
    params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    body: Optional[str] = None
    response_type: str = "json"   # json, html, text
    frequency: int = 1            # 被观察到的次数
    source_action: str = ""       # 触发该 API 的用户操作（如"点击翻页"）

    @property
    def stability_score(self) -> float:
        """稳定性评分（基于频率和响应类型）"""
        score = min(self.frequency / 5.0, 1.0)
        if self.response_type == "json":
            score *= 1.5  # JSON API 更稳定
        return min(score, 1.0)


@dataclass
class DiscoveryResult:
    """API 发现结果"""
    endpoints: list[ApiEndpoint] = field(default_factory=list)
    dom_fallback: bool = False    # 是否降级到 DOM 提取
    page_url: str = ""

    @property
    def best_endpoint(self) -> Optional[ApiEndpoint]:
        """返回最佳 API 端点（按稳定性评分排序）"""
        if not self.endpoints:
            return None
        return sorted(self.endpoints, key=lambda e: e.stability_score, reverse=True)[0]


class NetworkCapture:
    """网络请求捕获器 — 监控 XHR/fetch 请求

    通过 Playwright page 的 request/response 事件捕获所有网络请求，
    过滤出 XHR/fetch 类型，识别其中的 API 端点。

    用法:
        capture = NetworkCapture()
        await capture.start_capture(page)
        # ... 执行一些页面操作 ...
        apis = capture.identify_apis()
    """

    def __init__(self, max_requests: int = 500):
        self._requests: list[dict] = []
        self._responses: dict[str, dict] = {}  # url -> response info
        self._max_requests = max_requests
        self._request_handlers: list = []
        self._response_handlers: list = []
        self._api_patterns: list[str] = [
            r"/api/",
            r"/v\d+/",
            r"\.json",
            r"/graphql",
            r"/rest/",
            r"/data/",
            r"/query",
            r"/search",
            r"/list",
            r"/get",
            r"/fetch",
            r"/ajax",
        ]
        # 排除的静态资源类型
        self._static_types = {
            "image", "stylesheet", "font", "media",
            "manifest", "other",
        }

    async def start_capture(self, page) -> None:
        """开始捕获网络请求（Playwright page）

        Args:
            page: Playwright async page 对象
        """
        async def on_request(request):
            try:
                entry = {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "headers": dict(request.headers) if request.headers else {},
                }
                if request.method == "POST" and request.post_data:
                    entry["body"] = request.post_data
                if len(self._requests) < self._max_requests:
                    self._requests.append(entry)
            except Exception as e:
                logger.debug(f"捕获请求异常: {e}")

        async def on_response(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "")
                entry = {
                    "url": url,
                    "status": response.status,
                    "content_type": content_type,
                    "headers": dict(response.headers) if response.headers else {},
                }
                # 尝试获取响应体（仅对小体积 JSON）
                if "json" in content_type:
                    try:
                        body = await response.text()
                        if len(body) < 1024 * 100:  # < 100KB
                            entry["body"] = body
                        else:
                            logger.debug("响应体过大 (%d bytes)，跳过存储: %s", len(body), url)
                    except Exception:
                        pass
                self._responses[url] = entry
            except Exception as e:
                logger.debug(f"捕获响应异常: {e}")

        self._request_handlers.append(on_request)
        self._response_handlers.append(on_response)
        page.on("request", on_request)
        page.on("response", on_response)

    def stop_capture(self) -> list[dict]:
        """停止捕获并返回所有请求"""
        return list(self._requests)

    def filter_xhr_fetch(self) -> list[dict]:
        """过滤出 XHR/fetch 请求

        Returns:
            仅包含 XHR 和 fetch 类型请求的列表
        """
        return [
            req for req in self._requests
            if req["resource_type"] in ("xhr", "fetch")
        ]

    def identify_apis(self) -> list[ApiEndpoint]:
        """识别 API 端点（基于 URL 模式和响应类型）

        综合 URL 模式匹配和 resource_type 过滤来判断哪些请求是数据 API。
        对同一 URL 的多次出现会累加 frequency。

        Returns:
            识别出的 ApiEndpoint 列表
        """
        xhr_requests = self.filter_xhr_fetch()
        endpoint_map: dict[str, ApiEndpoint] = {}

        for req in xhr_requests:
            url = req["url"]
            # 去掉 query string 做 key，合并相同端点
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            if base_url in endpoint_map:
                endpoint_map[base_url].frequency += 1
                continue

            # 检查响应信息
            resp_info = self._responses.get(url, {})
            content_type = resp_info.get("content_type", "")

            if self._is_likely_api(url, req["resource_type"], content_type):
                endpoint = self._parse_request(req, resp_info)
                if endpoint:
                    endpoint_map[base_url] = endpoint

        return list(endpoint_map.values())

    def _is_likely_api(
        self, url: str, resource_type: str, content_type: str = ""
    ) -> bool:
        """判断是否可能是数据 API

        综合 resource_type、URL 模式、content-type 来判断。
        """
        # resource_type 必须是 xhr 或 fetch
        if resource_type not in ("xhr", "fetch"):
            return False

        # JSON 响应直接通过
        if "json" in content_type:
            return True

        # URL 匹配已知 API 模式
        for pattern in self._api_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # 排除明显的静态资源 URL
        if re.search(r"\.(css|js|png|jpg|gif|svg|ico|woff|ttf|mp4|mp3)(\?|$)", url, re.IGNORECASE):
            return False

        return False

    def _parse_request(
        self, request_data: dict, resp_info: dict
    ) -> Optional[ApiEndpoint]:
        """将原始请求数据解析为 ApiEndpoint"""
        url = request_data["url"]
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        # 将 list 值展开为单值（如果只有一个元素）
        flat_params = {
            k: v[0] if len(v) == 1 else v
            for k, v in params.items()
        }

        content_type = resp_info.get("content_type", "")
        if "json" in content_type:
            response_type = "json"
        elif "html" in content_type:
            response_type = "html"
        else:
            response_type = "text"

        # 过滤掉敏感 header（cookie、authorization 等）
        safe_headers = {
            k: v for k, v in request_data.get("headers", {}).items()
            if k.lower() not in ("cookie", "authorization", "x-csrf-token")
        }

        return ApiEndpoint(
            url=url,
            method=request_data.get("method", "GET"),
            params=flat_params,
            headers=safe_headers,
            body=request_data.get("body"),
            response_type=response_type,
        )

    def clear(self):
        """清空所有捕获的数据"""
        self._requests.clear()
        self._responses.clear()


class SmartSpider(Spider):
    """API 优先发现的智能爬虫

    工作流程：
    1. 用浏览器打开页面
    2. 捕获网络请求，发现 XHR/fetch API 端点
    3. 如果找到 API -> 直接调用 API（更稳定、更快、更省 token）
    4. 如果没找到 -> 降级到 DOM 提取

    用法:
        class MySmartSpider(SmartSpider):
            name = "my_spider"
            start_urls = ["https://example.com/list"]

            # 定义触发 API 发现的操作（如翻页、搜索）
            discovery_actions = [
                {"type": "click", "selector": ".next-page"},
                {"type": "wait", "ms": 2000},
            ]

            async def parse_api(self, endpoint: ApiEndpoint, data: dict) -> AsyncIterator[SpiderItem]:
                yield SpiderItem(data=data)

            async def parse_dom(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
                yield SpiderItem(data={"title": "..."})

        spider = MySmartSpider()
        result = await spider.run()
    """

    # API 发现配置
    discovery_enabled: bool = True
    discovery_actions: list[dict] = field(default_factory=list)
    api_timeout: float = 10.0
    max_capture_time: float = 15.0  # 最大捕获时间（秒）

    def __init__(self):
        super().__init__()
        self._network_capture = NetworkCapture()
        self._discovered_apis: dict[str, DiscoveryResult] = {}
        self._discovery_fetcher = None

    async def _discover_api(self, page, url: str) -> DiscoveryResult:
        """在页面上执行 API 发现

        打开页面，执行 discovery_actions，捕获网络请求，
        从中识别 API 端点。

        Args:
            page: Playwright page 对象
            url: 目标页面 URL

        Returns:
            DiscoveryResult 包含发现的 API 端点列表
        """
        self._network_capture.clear()

        try:
            await self._network_capture.start_capture(page)
            await page.goto(url, wait_until="domcontentloaded", timeout=int(self.api_timeout * 1000))

            # 执行发现操作
            for action in self.discovery_actions:
                await self._execute_action(page, action)

            # 等待一段时间让 XHR/fetch 请求完成
            await asyncio.sleep(2.0)

            # 识别 API 端点
            endpoints = self._network_capture.identify_apis()
            logger.info(f"[{self.name}] 在 {url} 发现 {len(endpoints)} 个 API 端点")

            result = DiscoveryResult(
                endpoints=endpoints,
                dom_fallback=len(endpoints) == 0,
                page_url=url,
            )
            self._discovered_apis[url] = result
            return result

        except Exception as e:
            logger.error(f"[{self.name}] API 发现失败: {url} - {e}")
            return DiscoveryResult(dom_fallback=True, page_url=url)

    async def _execute_action(self, page, action: dict):
        """执行一个发现操作（click, wait, scroll, input 等）

        Args:
            page: Playwright page 对象
            action: 操作描述字典，支持以下类型：
                - {"type": "click", "selector": "button.next"}
                - {"type": "wait", "ms": 2000}
                - {"type": "scroll", "direction": "down"}
                - {"type": "input", "selector": "input.search", "text": "keyword"}
                - {"type": "evaluate", "script": "window.scrollTo(0, 1000)"}
        """
        action_type = action.get("type", "")
        try:
            if action_type == "click":
                selector = action["selector"]
                timeout = action.get("timeout", 5000)
                await page.click(selector, timeout=timeout)

            elif action_type == "wait":
                ms = action.get("ms", 1000)
                await asyncio.sleep(ms / 1000.0)

            elif action_type == "scroll":
                direction = action.get("direction", "down")
                pixels = action.get("pixels", 500)
                delta = pixels if direction == "down" else -pixels
                await page.mouse.wheel(0, delta)

            elif action_type == "input":
                selector = action["selector"]
                text = action["text"]
                await page.fill(selector, text)

            elif action_type == "evaluate":
                script = action["script"]
                # 安全校验：只允许白名单内的 JS 模式
                if not self._is_safe_script(script):
                    logger.warning(f"[{self.name}] 拒绝不安全的 evaluate 脚本: {script[:80]}...")
                    return
                await page.evaluate(script)

            elif action_type == "wait_for_selector":
                selector = action["selector"]
                timeout = action.get("timeout", 5000)
                await page.wait_for_selector(selector, timeout=timeout)

            else:
                logger.warning(f"[{self.name}] 未知操作类型: {action_type}")

        except Exception as e:
            logger.warning(f"[{self.name}] 执行操作失败 ({action_type}): {e}")

    # 允许的 JS 模式白名单（安全的 DOM/窗口操作）
    _SAFE_SCRIPT_PATTERNS = (
        "window.scrollTo",
        "window.scrollBy",
        "document.querySelector",
        "document.querySelectorAll",
        "document.getElementById",
        "document.getElementsByClassName",
        "document.getElementsByTagName",
        "history.pushState",
        "history.replaceState",
        "location.href",
    )

    @staticmethod
    def _is_safe_script(script: str) -> bool:
        """校验 evaluate 脚本是否在白名单内"""
        script_stripped = script.strip()
        # 允许纯函数调用模式
        for pattern in SmartSpider._SAFE_SCRIPT_PATTERNS:
            if script_stripped.startswith(pattern):
                return True
        # 允许简单的属性赋值（如 location.href = ...）
        if script_stripped.startswith("location.") and "=" in script_stripped:
            return True
        return False

    async def _fetch_api(self, endpoint: ApiEndpoint, client) -> Optional[dict]:
        """直接调用发现的 API

        Args:
            endpoint: API 端点信息
            client: OmniClient 实例

        Returns:
            解析后的响应数据，失败返回 None
        """
        try:
            kwargs: dict = {
                "method": endpoint.method,
                "timeout": self.api_timeout,
            }
            if endpoint.headers:
                kwargs["headers"] = endpoint.headers

            if endpoint.method == "POST" and endpoint.body:
                # 尝试 JSON 解析 body
                try:
                    kwargs["json"] = json.loads(endpoint.body)
                except (json.JSONDecodeError, TypeError):
                    kwargs["data"] = endpoint.body

            result = await client.fetch(endpoint.url, **kwargs)

            if not result.ok:
                logger.warning(
                    f"[{self.name}] API 请求失败: {endpoint.url} "
                    f"HTTP {result.status_code}"
                )
                return None

            # 尝试 JSON 解析
            if result.text:
                try:
                    return json.loads(result.text)
                except (json.JSONDecodeError, TypeError):
                    pass

            # 非 JSON 响应，返回原始文本包装
            return {"_raw": result.text, "_url": result.url}

        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] API 超时: {endpoint.url}")
            return None
        except Exception as e:
            logger.error(f"[{self.name}] API 调用异常: {endpoint.url} - {e}")
            return None

    async def parse(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
        """智能解析：优先 API，降级 DOM

        这是主入口方法。SmartSpider 不直接从 HTML 解析，
        而是先尝试发现 API，如果发现则直接调用 API 获取数据。
        """
        # SmartSpider 的 parse 不从 HTML 提取数据
        # 实际的数据提取在 run/stream 中通过 _smart_process_url 完成
        # 这里直接返回空，作为安全兜底
        return
        yield  # type: ignore[misc]  # pragma: no cover

    async def parse_api(
        self, endpoint: ApiEndpoint, data: dict
    ) -> AsyncIterator[SpiderItem]:
        """解析 API 响应（子类重写）

        Args:
            endpoint: API 端点信息
            data: API 返回的 JSON 数据

        Yields:
            SpiderItem 数据项
        """
        yield SpiderItem(data=data, url=endpoint.url)

    async def parse_dom(self, response: FetchResult) -> AsyncIterator[SpiderItem]:
        """DOM 兜底解析（子类重写）

        当没有发现可用 API 时，降级到从 DOM 提取数据。

        Args:
            response: FetchResult 包含 HTML

        Yields:
            SpiderItem 数据项
        """
        yield SpiderItem(
            data={"markdown": response.markdown[:500]},
            url=response.url,
        )

    async def _smart_process_url(self, client, url: str) -> list[SpiderItem]:
        """智能处理单个 URL：API 优先，DOM 兜底

        Args:
            client: OmniClient 实例
            url: 目标 URL

        Returns:
            采集到的 SpiderItem 列表
        """
        items: list[SpiderItem] = []

        # 如果 API 发现被禁用，直接走 DOM 路径
        if not self.discovery_enabled:
            return await self._dom_fallback(url, client)

        # 尝试用浏览器进行 API 发现
        discovery_result = await self._browser_discover(client, url)

        if discovery_result and discovery_result.endpoints:
            # 发现了 API 端点，逐个调用
            for endpoint in discovery_result.endpoints:
                if endpoint.stability_score < 0.2:
                    logger.debug(
                        f"[{self.name}] 跳过低稳定性 API: {endpoint.url} "
                        f"(score={endpoint.stability_score:.2f})"
                    )
                    continue

                data = await self._fetch_api(endpoint, client)
                if data is not None:
                    async for item in self.parse_api(endpoint, data):
                        self.stats.items += 1
                        items.append(item)
                    self.stats.requests += 1

            if items:
                logger.info(
                    f"[{self.name}] 通过 API 获取 {len(items)} 条数据 "
                    f"({url})"
                )
                return items

        # 没有发现 API 或 API 调用失败，降级到 DOM
        logger.info(f"[{self.name}] 未发现 API，降级到 DOM 解析: {url}")
        return await self._dom_fallback(url, client)

    async def _browser_discover(
        self, client, url: str
    ) -> Optional[DiscoveryResult]:
        """通过浏览器进行 API 发现

        尝试获取一个 Playwright page 对象来捕获网络请求。
        如果当前模式不支持浏览器（如纯 HTTP），则跳过发现。
        复用同一个 BrowserFetcher 实例，避免每次创建新浏览器。

        Args:
            client: OmniClient 实例
            url: 目标 URL

        Returns:
            DiscoveryResult 或 None（无法使用浏览器时）
        """
        from omnicrawl.fetchers.browser_fetcher import BrowserFetcher

        if self._discovery_fetcher is None:
            self._discovery_fetcher = BrowserFetcher()

        fetcher = self._discovery_fetcher
        try:
            context, page = await fetcher.create_page(
                viewport={"width": 1920, "height": 1080}
            )
            try:
                return await self._discover_api(page, url)
            finally:
                await context.close()
        except ImportError:
            logger.warning(
                f"[{self.name}] Playwright 未安装，跳过 API 发现"
            )
            return None
        except Exception as e:
            logger.warning(
                f"[{self.name}] 浏览器 API 发现失败: {e}"
            )
            return None

    async def _dom_fallback(self, url: str, client=None) -> list[SpiderItem]:
        """DOM 降级处理：用父类的 _process_url 获取页面再解析

        Args:
            url: 目标 URL
            client: 已有的 OmniClient 实例（复用），为 None 时新建

        Returns:
            采集到的 SpiderItem 列表
        """
        from omnicrawl import OmniClient

        items: list[SpiderItem] = []
        try:
            if client is None:
                client = OmniClient(mode=self.mode)
            result = await client.get(url)
            self.stats.requests += 1
            if result.blocked:
                self.stats.blocked += 1

            async for item in self.parse_dom(result):
                if not item.markdown and result.html:
                    item.markdown = self._converter.convert(result.html)
                self.stats.items += 1
                items.append(item)
        except Exception as e:
            self.stats.errors += 1
            logger.error(f"[{self.name}] DOM 降级失败: {url} - {e}")

        return items

    async def run(self) -> list[SpiderItem]:
        """运行爬虫（智能 API 优先模式）

        Returns:
            所有采集到的 SpiderItem 列表
        """
        from omnicrawl import OmniClient

        all_items: list[SpiderItem] = []
        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def bounded_process(url: str) -> list[SpiderItem]:
                async with semaphore:
                    return await self._smart_process_url(client, url)

            results = await asyncio.gather(
                *[bounded_process(url) for url in self.start_urls],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, list):
                    all_items.extend(result)

        return all_items

    async def stream(self) -> AsyncIterator[SpiderItem]:
        """流式运行爬虫（智能 API 优先模式）

        Yields:
            采集到的 SpiderItem
        """
        from omnicrawl import OmniClient

        async with OmniClient(mode=self.mode) as client:
            semaphore = asyncio.Semaphore(self.max_concurrent)
            for url in self.start_urls:
                async with semaphore:
                    try:
                        items = await self._smart_process_url(client, url)
                        for item in items:
                            yield item
                        if self.download_delay > 0:
                            await asyncio.sleep(self.download_delay)
                    except Exception as e:
                        self.stats.errors += 1
                        logger.error(f"[{self.name}] 流式处理失败: {url} - {e}")
