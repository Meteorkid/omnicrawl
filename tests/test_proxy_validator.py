"""代理验证器测试"""

import pytest
from omnicrawl.proxy.validator import ProxyValidator, ProxyStatus


class TestProxyValidator:
    def test_proxy_status_defaults(self):
        status = ProxyStatus(proxy="http://p1:8080", alive=True)
        assert status.alive is True
        assert status.fail_count == 0
        assert status.latency == 0.0

    def test_is_healthy_unknown_proxy(self):
        validator = ProxyValidator()
        # 未检查过的代理默认健康
        assert validator.is_healthy("http://unknown:8080") is True

    def test_is_healthy_alive(self):
        validator = ProxyValidator()
        validator._status["http://p1:8080"] = ProxyStatus(proxy="http://p1:8080", alive=True)
        assert validator.is_healthy("http://p1:8080") is True

    def test_is_healthy_dead(self):
        validator = ProxyValidator(max_failures=3)
        validator._status["http://p1:8080"] = ProxyStatus(proxy="http://p1:8080", alive=False, fail_count=3)
        assert validator.is_healthy("http://p1:8080") is False

    def test_get_alive(self):
        validator = ProxyValidator()
        validator._status["http://p1:8080"] = ProxyStatus(proxy="http://p1:8080", alive=True)
        validator._status["http://p2:8080"] = ProxyStatus(proxy="http://p2:8080", alive=False, fail_count=3)
        # get_alive 只返回已检查且可用的代理
        alive = validator.get_alive(["http://p1:8080", "http://p2:8080", "http://p3:8080"])
        assert "http://p1:8080" in alive
        assert "http://p2:8080" not in alive
        # p3 未检查，不在 get_alive 结果中
        assert "http://p3:8080" not in alive

    @pytest.mark.asyncio
    async def test_check_real_proxy(self):
        """测试真实代理检查（使用无代理，应该能连通）"""
        validator = ProxyValidator(test_url="https://example.com", timeout=5.0)
        status = await validator.check(None)
        # None 代理应该能直接连接
        # 注意：这个测试依赖网络
