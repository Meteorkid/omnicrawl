"""Spider 单元测试（全部 mock，无真实浏览器）"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from omnicrawl.spider.base import Spider, SpiderItem, SpiderStats
from omnicrawl.spider.smart_spider import (
    ApiEndpoint, DiscoveryResult, NetworkCapture, SmartSpider,
)
from omnicrawl.fetchers.base import FetchMode, FetchResult


def make_result(url="http://test.com", html="<h1>hi</h1>", blocked=False):
    return FetchResult(
        url=url, status_code=200, html=html,
        headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1, blocked=blocked,
    )


# ===========================================================================
# 数据类
# ===========================================================================

class TestDataClasses:
    def test_spider_item(self):
        item = SpiderItem(data={"title": "test"}, url="http://x", markdown="# test")
        assert item.data == {"title": "test"}
        assert item.url == "http://x"
        assert item.markdown == "# test"

    def test_spider_stats_defaults(self):
        s = SpiderStats()
        assert s.requests == 0
        assert s.items == 0
        assert s.errors == 0
        assert s.blocked == 0

    def test_api_endpoint_stability_score(self):
        # 高频 JSON API
        ep = ApiEndpoint(url="http://api.com/data", frequency=10, response_type="json")
        assert ep.stability_score == 1.0  # capped at 1.0

    def test_api_endpoint_low_frequency(self):
        ep = ApiEndpoint(url="http://api.com/data", frequency=1, response_type="json")
        assert ep.stability_score == pytest.approx(0.3)  # (1/5) * 1.5 = 0.3

    def test_api_endpoint_html_type(self):
        ep = ApiEndpoint(url="http://api.com/data", frequency=10, response_type="html")
        assert ep.stability_score == 1.0  # min(10/5, 1.0) = 1.0, no 1.5x

    def test_discovery_result_best_endpoint_empty(self):
        dr = DiscoveryResult()
        assert dr.best_endpoint is None

    def test_discovery_result_best_endpoint(self):
        ep1 = ApiEndpoint(url="http://a.com", frequency=1, response_type="json")
        ep2 = ApiEndpoint(url="http://b.com", frequency=10, response_type="json")
        dr = DiscoveryResult(endpoints=[ep1, ep2])
        assert dr.best_endpoint.url == "http://b.com"

    def test_discovery_result_best_endpoint_single(self):
        ep = ApiEndpoint(url="http://a.com", frequency=5, response_type="json")
        dr = DiscoveryResult(endpoints=[ep])
        assert dr.best_endpoint is ep


# ===========================================================================
# NetworkCapture
# ===========================================================================

class TestNetworkCapture:
    def test_filter_xhr_fetch(self):
        nc = NetworkCapture()
        nc._requests = [
            {"url": "http://api.com/data", "resource_type": "xhr", "method": "GET", "headers": {}},
            {"url": "http://test.com/style.css", "resource_type": "stylesheet", "method": "GET", "headers": {}},
            {"url": "http://api.com/fetch", "resource_type": "fetch", "method": "GET", "headers": {}},
        ]
        result = nc.filter_xhr_fetch()
        assert len(result) == 2

    def test_is_likely_api_json_content(self):
        nc = NetworkCapture()
        assert nc._is_likely_api("http://api.com/data", "xhr", "application/json") is True

    def test_is_likely_api_url_pattern(self):
        nc = NetworkCapture()
        assert nc._is_likely_api("http://api.com/v1/users", "xhr") is True
        assert nc._is_likely_api("http://api.com/graphql", "fetch") is True

    def test_is_likely_api_static_rejected(self):
        nc = NetworkCapture()
        assert nc._is_likely_api("http://cdn.com/style.css", "xhr") is False

    def test_is_likely_api_non_xhr_rejected(self):
        nc = NetworkCapture()
        assert nc._is_likely_api("http://api.com/data", "document") is False

    def test_parse_request(self):
        nc = NetworkCapture()
        req = {
            "url": "http://api.com/v1/data?page=1&size=10",
            "method": "GET",
            "headers": {"Accept": "application/json", "Cookie": "secret"},
        }
        resp = {"content_type": "application/json"}
        ep = nc._parse_request(req, resp)
        assert ep is not None
        assert ep.url == "http://api.com/v1/data?page=1&size=10"
        assert ep.method == "GET"
        assert ep.response_type == "json"
        assert ep.params == {"page": "1", "size": "10"}
        # Cookie 应被过滤
        assert "cookie" not in {k.lower() for k in ep.headers}

    def test_parse_request_html_type(self):
        nc = NetworkCapture()
        req = {"url": "http://test.com", "method": "GET", "headers": {}}
        resp = {"content_type": "text/html"}
        ep = nc._parse_request(req, resp)
        assert ep.response_type == "html"

    def test_parse_request_text_type(self):
        nc = NetworkCapture()
        req = {"url": "http://test.com", "method": "GET", "headers": {}}
        resp = {"content_type": "text/plain"}
        ep = nc._parse_request(req, resp)
        assert ep.response_type == "text"

    def test_identify_apis(self):
        nc = NetworkCapture()
        nc._requests = [
            {"url": "http://api.com/v1/data", "resource_type": "xhr", "method": "GET", "headers": {}},
            {"url": "http://api.com/style.css", "resource_type": "stylesheet", "method": "GET", "headers": {}},
        ]
        nc._responses = {
            "http://api.com/v1/data": {"content_type": "application/json"},
        }
        apis = nc.identify_apis()
        assert len(apis) == 1
        assert apis[0].url == "http://api.com/v1/data"

    def test_identify_apis_merges_frequency(self):
        nc = NetworkCapture()
        nc._requests = [
            {"url": "http://api.com/v1/data?page=1", "resource_type": "xhr", "method": "GET", "headers": {}},
            {"url": "http://api.com/v1/data?page=2", "resource_type": "xhr", "method": "GET", "headers": {}},
        ]
        nc._responses = {
            "http://api.com/v1/data?page=1": {"content_type": "application/json"},
            "http://api.com/v1/data?page=2": {"content_type": "application/json"},
        }
        apis = nc.identify_apis()
        assert len(apis) == 1
        assert apis[0].frequency == 2  # 同一 base_url

    def test_stop_capture(self):
        nc = NetworkCapture()
        nc._requests = [{"url": "http://x"}]
        result = nc.stop_capture()
        assert result == [{"url": "http://x"}]

    def test_clear(self):
        nc = NetworkCapture()
        nc._requests = [{"url": "http://x"}]
        nc._responses = {"http://x": {}}
        nc.clear()
        assert len(nc._requests) == 0
        assert len(nc._responses) == 0


# ===========================================================================
# SmartSpider._is_safe_script
# ===========================================================================

class TestSafeScript:
    def test_safe_scroll(self):
        assert SmartSpider._is_safe_script("window.scrollTo(0, 1000)") is True

    def test_safe_query_selector(self):
        assert SmartSpider._is_safe_script("document.querySelector('.btn')") is True

    def test_safe_location_href(self):
        assert SmartSpider._is_safe_script("location.href = 'http://test.com'") is True

    def test_unsafe_eval(self):
        assert SmartSpider._is_safe_script("eval('alert(1)')") is False

    def test_unsafe_fetch(self):
        assert SmartSpider._is_safe_script("fetch('http://evil.com')") is False

    def test_unsafe_xmlhttprequest(self):
        assert SmartSpider._is_safe_script("new XMLHttpRequest()") is False

    def test_safe_history_push(self):
        assert SmartSpider._is_safe_script("history.pushState({}, '', '/new')") is True


# ===========================================================================
# SmartSpider._fetch_api
# ===========================================================================

def make_api_result(html="", text="", status=200, blocked=False):
    """创建用于 API 测试的 FetchResult"""
    r = FetchResult(
        url="http://test.com", status_code=status, html=html,
        headers={}, cookies={}, mode_used=FetchMode.HTTP, elapsed=0.1, blocked=blocked,
    )
    r.text = text
    return r


class TestFetchApi:
    @pytest.mark.asyncio
    async def test_fetch_json_success(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=make_api_result(text='{"key": "value"}'))

        endpoint = ApiEndpoint(url="http://api.com/data", response_type="json")
        result = await spider._fetch_api(endpoint, mock_client)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_fetch_non_json_returns_raw(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=make_api_result(text="plain text"))

        endpoint = ApiEndpoint(url="http://api.com/data", response_type="text")
        result = await spider._fetch_api(endpoint, mock_client)
        assert result == {"_raw": "plain text", "_url": "http://test.com"}

    @pytest.mark.asyncio
    async def test_fetch_failed_status(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=make_api_result(status=500))

        endpoint = ApiEndpoint(url="http://api.com/data")
        result = await spider._fetch_api(endpoint, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_timeout(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(side_effect=asyncio.TimeoutError())

        endpoint = ApiEndpoint(url="http://api.com/data")
        result = await spider._fetch_api(endpoint, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_exception(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(side_effect=Exception("network error"))

        endpoint = ApiEndpoint(url="http://api.com/data")
        result = await spider._fetch_api(endpoint, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_post_with_json_body(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=make_api_result(text='{"ok": true}'))

        endpoint = ApiEndpoint(
            url="http://api.com/data", method="POST",
            body='{"query": "test"}', response_type="json",
        )
        result = await spider._fetch_api(endpoint, mock_client)
        assert result == {"ok": True}
        call_kwargs = mock_client.fetch.call_args[1]
        assert call_kwargs["json"] == {"query": "test"}

    @pytest.mark.asyncio
    async def test_fetch_post_with_text_body(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.fetch = AsyncMock(return_value=make_api_result(text="ok"))

        endpoint = ApiEndpoint(
            url="http://api.com/data", method="POST",
            body="raw data", response_type="text",
        )
        await spider._fetch_api(endpoint, mock_client)
        call_kwargs = mock_client.fetch.call_args[1]
        assert call_kwargs["data"] == "raw data"


# ===========================================================================
# SmartSpider._dom_fallback
# ===========================================================================

class TestDomFallback:
    @pytest.mark.asyncio
    async def test_dom_fallback_basic(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result(html="<h1>Title</h1>"))

        items = await spider._dom_fallback("http://test.com", mock_client)
        assert len(items) == 1
        assert spider.stats.requests == 1

    @pytest.mark.asyncio
    async def test_dom_fallback_blocked(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result(blocked=True))

        items = await spider._dom_fallback("http://test.com", mock_client)
        assert spider.stats.blocked == 1

    @pytest.mark.asyncio
    async def test_dom_fallback_exception(self):
        spider = SmartSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("fail"))

        items = await spider._dom_fallback("http://test.com", mock_client)
        assert items == []
        assert spider.stats.errors == 1


# ===========================================================================
# Spider._process_url
# ===========================================================================

class TestProcessUrl:
    @pytest.mark.asyncio
    async def test_process_url_basic(self):
        class TestSpider(Spider):
            name = "test"
            async def parse(self, response):
                yield SpiderItem(data={"title": "test"}, url=response.url)

        spider = TestSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result())

        items = await spider._process_url(mock_client, "http://test.com")
        assert len(items) == 1
        assert spider.stats.requests == 1
        assert spider.stats.items == 1

    @pytest.mark.asyncio
    async def test_process_url_blocked(self):
        class TestSpider(Spider):
            name = "test"
            async def parse(self, response):
                yield SpiderItem(data={})

        spider = TestSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_result(blocked=True))

        items = await spider._process_url(mock_client, "http://test.com")
        assert spider.stats.blocked == 1

    @pytest.mark.asyncio
    async def test_process_url_exception(self):
        class TestSpider(Spider):
            name = "test"
            async def parse(self, response):
                yield SpiderItem(data={})

        spider = TestSpider()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("fail"))

        items = await spider._process_url(mock_client, "http://test.com")
        assert items == []
        assert spider.stats.errors == 1
