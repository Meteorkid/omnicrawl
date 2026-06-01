"""智能限速器测试"""

import asyncio
import time
import pytest
from omnicrawl.anti_detect.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_wait_basic(self):
        limiter = RateLimiter(min_delay=0.1)
        start = time.time()
        await limiter.wait("https://example.com/page1")
        await limiter.wait("https://example.com/page2")
        elapsed = time.time() - start
        # 第二次请求应该被限速
        assert elapsed >= 0.08  # 允许少量误差

    @pytest.mark.asyncio
    async def test_different_domains_independent(self):
        limiter = RateLimiter(min_delay=0.5)
        start = time.time()
        await limiter.wait("https://site1.com/page")
        await limiter.wait("https://site2.com/page")  # 不同域名，不等待
        elapsed = time.time() - start
        # 不同域名不应该互相限速
        assert elapsed < 0.3

    def test_report_blocked(self):
        limiter = RateLimiter(min_delay=1.0, max_delay=10.0, backoff_factor=2.0)
        limiter.report_blocked("https://example.com/page")
        assert limiter._domain_delays["example.com"] == 2.0
        limiter.report_blocked("https://example.com/page")
        assert limiter._domain_delays["example.com"] == 4.0

    def test_report_success(self):
        limiter = RateLimiter(min_delay=1.0, backoff_factor=2.0)
        limiter.report_blocked("https://example.com/page")
        limiter.report_blocked("https://example.com/page")
        assert limiter._domain_delays["example.com"] == 4.0
        limiter.report_success("https://example.com/page")
        assert limiter._domain_delays["example.com"] == 2.0

    def test_report_success_clamp_at_min(self):
        limiter = RateLimiter(min_delay=1.0, backoff_factor=2.0)
        limiter.report_success("https://example.com/page")
        # 不应该低于 min_delay
        delay = limiter._domain_delays.get("example.com", limiter._min_delay)
        assert delay >= 1.0
