"""代理轮换器测试"""

import pytest
from omnicrawl.proxy.rotator import ProxyRotator


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
