"""ProxyScorer 代理质量评分测试"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from omnicrawl.proxy.scorer import ProxyScorer, ProxyStats


class TestProxyStats:
    def test_default_success_rate(self):
        stats = ProxyStats(proxy="http://p:8080")
        assert stats.success_rate == 1.0  # 未使用默认 100%

    def test_success_rate_calculation(self):
        stats = ProxyStats(proxy="http://p:8080", total_requests=10, success_count=7)
        assert stats.success_rate == 0.7

    def test_block_rate(self):
        stats = ProxyStats(proxy="http://p:8080", total_requests=10, block_count=3)
        assert stats.block_rate == 0.3

    def test_block_rate_no_requests(self):
        stats = ProxyStats(proxy="http://p:8080")
        assert stats.block_rate == 0.0


class TestProxyScorer:
    def test_unknown_proxy_gets_mid_score(self):
        scorer = ProxyScorer()
        assert scorer.get_score("http://unknown:8080") == 50.0

    def test_record_success(self):
        scorer = ProxyScorer()
        scorer.record_success("http://p:8080", latency=0.5)
        stats = scorer.get_stats("http://p:8080")
        assert stats.total_requests == 1
        assert stats.success_count == 1
        assert stats.consecutive_fails == 0
        assert stats.avg_latency > 0

    def test_record_failure(self):
        scorer = ProxyScorer()
        scorer.record_failure("http://p:8080", error="timeout")
        stats = scorer.get_stats("http://p:8080")
        assert stats.total_requests == 1
        assert stats.failure_count == 1
        assert stats.consecutive_fails == 1

    def test_record_blocked(self):
        scorer = ProxyScorer()
        scorer.record_blocked("http://p:8080")
        stats = scorer.get_stats("http://p:8080")
        assert stats.block_count == 1
        assert stats.last_blocked > 0

    def test_consecutive_fails_resets_on_success(self):
        scorer = ProxyScorer()
        scorer.record_failure("http://p:8080")
        scorer.record_failure("http://p:8080")
        assert scorer.get_stats("http://p:8080").consecutive_fails == 2
        scorer.record_success("http://p:8080", latency=0.3)
        assert scorer.get_stats("http://p:8080").consecutive_fails == 0

    def test_score_decreases_with_failures(self):
        scorer = ProxyScorer()
        scorer.record_success("http://p:8080", latency=0.5)
        score_before = scorer.get_score("http://p:8080")
        scorer.record_failure("http://p:8080")
        scorer.record_failure("http://p:8080")
        score_after = scorer.get_score("http://p:8080")
        assert score_after < score_before

    def test_score_decreases_with_blocks(self):
        scorer = ProxyScorer()
        scorer.record_success("http://p:8080", latency=0.5)
        score_before = scorer.get_score("http://p:8080")
        scorer.record_blocked("http://p:8080")
        score_after = scorer.get_score("http://p:8080")
        assert score_after < score_before

    def test_fast_proxy_scores_higher(self):
        scorer = ProxyScorer()
        scorer.record_success("http://fast:8080", latency=0.2)
        scorer.record_success("http://slow:8080", latency=4.0)
        assert scorer.get_score("http://fast:8080") > scorer.get_score("http://slow:8080")

    def test_score_bounded_0_100(self):
        scorer = ProxyScorer()
        # 大量失败应该不会低于 0
        for _ in range(20):
            scorer.record_failure("http://bad:8080")
        assert scorer.get_score("http://bad:8080") >= 0.0

        # 大量成功不会超过 100
        for _ in range(20):
            scorer.record_success("http://good:8080", latency=0.1)
        assert scorer.get_score("http://good:8080") <= 100.0

    def test_get_best(self):
        scorer = ProxyScorer()
        scorer.record_success("http://a:8080", latency=0.1)
        scorer.record_success("http://b:8080", latency=0.5)
        scorer.record_failure("http://c:8080")
        best = scorer.get_best(2)
        assert len(best) == 2
        assert best[0] == "http://a:8080"  # 最快的排第一

    def test_get_best_with_candidates(self):
        scorer = ProxyScorer()
        scorer.record_success("http://a:8080", latency=0.1)
        scorer.record_success("http://b:8080", latency=0.5)
        best = scorer.get_best(1, proxies=["http://b:8080"])
        assert best == ["http://b:8080"]

    def test_get_worst(self):
        scorer = ProxyScorer()
        scorer.record_success("http://good:8080", latency=0.1)
        scorer.record_failure("http://bad:8080")
        scorer.record_failure("http://bad:8080")
        worst = scorer.get_worst(1)
        assert worst == ["http://bad:8080"]

    def test_prune(self):
        scorer = ProxyScorer()
        scorer.record_success("http://good:8080", latency=0.1)
        for _ in range(10):
            scorer.record_failure("http://bad:8080")
        removed = scorer.prune(threshold=30.0)
        assert "http://bad:8080" in removed
        assert "http://bad:8080" not in scorer
        assert "http://good:8080" in scorer

    def test_prune_none_removed(self):
        scorer = ProxyScorer()
        scorer.record_success("http://good:8080", latency=0.1)
        removed = scorer.prune(threshold=10.0)
        assert removed == []

    def test_len(self):
        scorer = ProxyScorer()
        assert len(scorer) == 0
        scorer.record_success("http://a:8080", latency=0.1)
        assert len(scorer) == 1

    def test_contains(self):
        scorer = ProxyScorer()
        assert "http://a:8080" not in scorer
        scorer.record_success("http://a:8080", latency=0.1)
        assert "http://a:8080" in scorer

    def test_all_stats(self):
        scorer = ProxyScorer()
        scorer.record_success("http://a:8080", latency=0.1)
        scorer.record_failure("http://b:8080")
        stats = scorer.all_stats()
        assert len(stats) == 2
        assert "http://a:8080" in stats
        assert "http://b:8080" in stats

    def test_avg_latency_update(self):
        scorer = ProxyScorer()
        scorer.record_success("http://p:8080", latency=1.0)
        scorer.record_success("http://p:8080", latency=3.0)
        stats = scorer.get_stats("http://p:8080")
        # 增量更新：1.0 * 0.7 + 3.0 * 0.3 = 1.6
        assert abs(stats.avg_latency - 1.6) < 0.01

    def test_recent_block_penalty(self):
        scorer = ProxyScorer()
        scorer.record_success("http://p:8080", latency=0.1)
        score_before = scorer.get_score("http://p:8080")
        scorer.record_blocked("http://p:8080")
        # 刚被封，应该有额外惩罚
        score_after = scorer.get_score("http://p:8080")
        assert score_after < score_before - 5  # 至少扣了连续失败分 + 最近被封分

    def test_old_block_no_extra_penalty(self):
        scorer = ProxyScorer(recent_block_window=1.0)
        scorer.record_success("http://p:8080", latency=0.1)
        scorer.record_blocked("http://p:8080")
        # 模拟 1 秒前被封
        scorer._stats["http://p:8080"].last_blocked = time.time() - 2.0
        score = scorer.get_score("http://p:8080")
        # 不应有最近被封惩罚（只扣连续失败分）
        # 重新成功一次清除连续失败
        scorer.record_success("http://p:8080", latency=0.1)
        score_recovered = scorer.get_score("http://p:8080")
        assert score_recovered > score


class TestProxyRotatorScored:
    def test_scored_strategy_creates_scorer(self):
        from omnicrawl.proxy.rotator import ProxyRotator
        rotator = ProxyRotator(["http://a:8080", "http://b:8080"], strategy="scored")
        assert rotator.scorer is not None
        assert len(rotator.scorer) == 0

    def test_scored_strategy_with_custom_scorer(self):
        from omnicrawl.proxy.rotator import ProxyRotator
        scorer = ProxyScorer()
        rotator = ProxyRotator(["http://a:8080"], strategy="scored", scorer=scorer)
        assert rotator.scorer is scorer

    def test_scored_strategy_returns_proxy(self):
        from omnicrawl.proxy.rotator import ProxyRotator
        rotator = ProxyRotator(["http://a:8080", "http://b:8080"], strategy="scored")
        proxy = rotator.next()
        assert proxy in ["http://a:8080", "http://b:8080"]
