"""代理模块测试 — ProxyRotator + ProxyValidator"""

import pytest
from unittest.mock import AsyncMock, patch

from omnicrawl.proxy.rotator import ProxyRotator
from omnicrawl.proxy.validator import ProxyStatus, ProxyValidator


class TestProxyRotator:
    def test_round_robin(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080", "http://p3:8080"])
        assert rotator.next() == "http://p1:8080"
        assert rotator.next() == "http://p2:8080"
        assert rotator.next() == "http://p3:8080"
        assert rotator.next() == "http://p1:8080"  # 循环

    def test_random_strategy(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"], strategy="random")
        results = {rotator.next() for _ in range(100)}
        # 随机策略应该能命中多个代理
        assert len(results) >= 1

    def test_weighted_strategy(self):
        rotator = ProxyRotator(
            ["http://p1:8080", "http://p2:8080"],
            strategy="weighted",
            weights=[9, 1],
        )
        results = [rotator.next() for _ in range(1000)]
        p1_count = results.count("http://p1:8080")
        # p1 权重 9，应该大约是 p2 的 9 倍
        assert p1_count > 700

    def test_empty_pool_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            ProxyRotator([])

    def test_weighted_wrong_length(self):
        with pytest.raises(ValueError, match="权重数量"):
            ProxyRotator(["http://p1:8080"], strategy="weighted", weights=[1, 2])

    def test_remove_and_next(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"])
        rotator.remove("http://p1:8080")
        assert rotator.next() == "http://p2:8080"
        rotator.remove("http://p2:8080")
        with pytest.raises(RuntimeError, match="代理池为空"):
            rotator.next()

    def test_add(self):
        rotator = ProxyRotator(["http://p1:8080"])
        rotator.add("http://p2:8080")
        assert rotator.count == 2

    def test_stats(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"])
        rotator.next()
        rotator.next()
        rotator.next()
        stats = rotator.stats
        assert stats["http://p1:8080"] == 2
        assert stats["http://p2:8080"] == 1

    def test_len(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"])
        assert len(rotator) == 2

    def test_single_proxy_round_robin(self):
        rotator = ProxyRotator(["http://only:8080"])
        for _ in range(5):
            assert rotator.next() == "http://only:8080"

    def test_add_duplicate(self):
        rotator = ProxyRotator(["http://p1:8080"])
        rotator.add("http://p1:8080")
        assert rotator.count == 1

    def test_remove_nonexistent(self):
        rotator = ProxyRotator(["http://p1:8080"])
        rotator.remove("http://notexist:8080")
        assert rotator.count == 1

    def test_repr(self):
        rotator = ProxyRotator(["http://p1:8080"])
        assert "1 proxies" in repr(rotator)

    def test_weighted_zero_weight(self):
        rotator = ProxyRotator(
            ["http://p1:8080", "http://p2:8080"],
            strategy="weighted",
            weights=[10, 0],
        )
        for _ in range(10):
            assert rotator.next() == "http://p1:8080"

    def test_scored_strategy_creates_scorer(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"], strategy="scored")
        assert rotator.scorer is not None

    def test_scored_strategy_returns_proxy(self):
        rotator = ProxyRotator(["http://p1:8080", "http://p2:8080"], strategy="scored")
        proxy = rotator.next()
        assert proxy in ["http://p1:8080", "http://p2:8080"]


# ════════════════════════════════════════════════════════════════════════
# ProxyValidator
# ════════════════════════════════════════════════════════════════════════


class TestProxyValidator:
    def test_is_healthy_unknown_proxy(self):
        validator = ProxyValidator()
        assert validator.is_healthy("http://unknown:8080") is True

    def test_is_healthy_alive_proxy(self):
        validator = ProxyValidator()
        validator._status["http://p:8080"] = ProxyStatus(proxy="http://p:8080", alive=True)
        assert validator.is_healthy("http://p:8080") is True

    def test_is_healthy_dead_proxy(self):
        validator = ProxyValidator()
        validator._status["http://p:8080"] = ProxyStatus(
            proxy="http://p:8080", alive=False, fail_count=5
        )
        assert validator.is_healthy("http://p:8080") is False

    def test_is_healthy_max_failures(self):
        validator = ProxyValidator(max_failures=3)
        validator._status["http://p:8080"] = ProxyStatus(
            proxy="http://p:8080", alive=True, fail_count=3
        )
        assert validator.is_healthy("http://p:8080") is False

    def test_get_status_unknown(self):
        validator = ProxyValidator()
        assert validator.get_status("http://unknown:8080") is None

    def test_get_alive(self):
        validator = ProxyValidator()
        validator._status["http://a:8080"] = ProxyStatus(proxy="http://a:8080", alive=True)
        validator._status["http://b:8080"] = ProxyStatus(proxy="http://b:8080", alive=False, fail_count=5)
        alive = validator.get_alive(["http://a:8080", "http://b:8080", "http://c:8080"])
        assert "http://a:8080" in alive
        assert "http://b:8080" not in alive
        assert "http://c:8080" not in alive

    @pytest.mark.asyncio
    async def test_check_success(self):
        validator = ProxyValidator()
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("curl_cffi.requests.AsyncSession", return_value=mock_session):
            status = await validator.check("http://proxy:8080")

        assert status.alive is True
        assert status.latency >= 0

    @pytest.mark.asyncio
    async def test_check_failure(self):
        validator = ProxyValidator()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("curl_cffi.requests.AsyncSession", return_value=mock_session):
            status = await validator.check("http://proxy:8080")

        assert status.alive is False
        assert "connection refused" in status.error

    def test_proxy_status_defaults(self):
        status = ProxyStatus(proxy="http://p:8080", alive=False)
        assert status.alive is False
        assert status.latency == 0.0
        assert status.fail_count == 0
        assert status.error == ""
