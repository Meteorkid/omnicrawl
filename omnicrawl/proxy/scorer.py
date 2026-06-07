"""代理质量评分器 — 基于历史表现动态评分

评分维度：
- 延迟（越低越好）
- 成功率（越高越好）
- 被封率（越低越好）
- 连续失败次数（惩罚因子）

用法:
    scorer = ProxyScorer()
    scorer.record_success("http://proxy:8080", latency=0.5)
    scorer.record_failure("http://proxy:8080", error="timeout")
    scorer.record_blocked("http://proxy:8080")

    best = scorer.get_best(3)  # 获取评分最高的 3 个代理
    score = scorer.get_score("http://proxy:8080")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from omnicrawl.utils.logger import get_logger

logger = get_logger("proxy_scorer")


@dataclass
class ProxyStats:
    """代理统计数据"""
    proxy: str
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    block_count: int = 0          # 被 WAF 拦截次数
    consecutive_fails: int = 0    # 连续失败次数
    avg_latency: float = 0.0      # 平均延迟（秒）
    last_used: float = 0.0        # 最后使用时间
    last_blocked: float = 0.0     # 最后被封时间
    first_seen: float = 0.0       # 首次使用时间

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0  # 未使用过的代理默认成功率 100%
        return self.success_count / self.total_requests

    @property
    def block_rate(self) -> float:
        """被封率"""
        if self.total_requests == 0:
            return 0.0
        return self.block_count / self.total_requests


# 评分权重
_WEIGHT_LATENCY = 0.3
_WEIGHT_SUCCESS = 0.4
_WEIGHT_BLOCK = 0.3
_PENALTY_CONSECUTIVE_FAIL = 5.0   # 每次连续失败扣 5 分
_PENALTY_RECENT_BLOCK = 10.0      # 最近被封额外扣分


class ProxyScorer:
    """代理质量评分器

    评分公式:
        score = w1 * latency_score + w2 * success_rate * 100 + w3 * (1 - block_rate) * 100
                - penalty_consecutive_fails - penalty_recent_block

    其中:
        latency_score = max(0, 100 - avg_latency * 20)  # 5s 延迟得 0 分
        penalty_consecutive_fails = consecutive_fails * 5
        penalty_recent_block = 10 if 最近 5 分钟内被封 else 0
    """

    def __init__(
        self,
        weight_latency: float = _WEIGHT_LATENCY,
        weight_success: float = _WEIGHT_SUCCESS,
        weight_block: float = _WEIGHT_BLOCK,
        recent_block_window: float = 300.0,  # 5 分钟
    ):
        self._stats: dict[str, ProxyStats] = {}
        self._weight_latency = weight_latency
        self._weight_success = weight_success
        self._weight_block = weight_block
        self._recent_block_window = recent_block_window

    def _get_or_create(self, proxy: str) -> ProxyStats:
        """获取或创建代理统计"""
        if proxy not in self._stats:
            self._stats[proxy] = ProxyStats(proxy=proxy, first_seen=time.time())
        return self._stats[proxy]

    def record_success(self, proxy: str, latency: float = 0.0) -> None:
        """记录成功的请求"""
        stats = self._get_or_create(proxy)
        stats.total_requests += 1
        stats.success_count += 1
        stats.consecutive_fails = 0
        stats.last_used = time.time()
        # 增量更新平均延迟
        if stats.avg_latency == 0:
            stats.avg_latency = latency
        else:
            stats.avg_latency = stats.avg_latency * 0.7 + latency * 0.3
        logger.debug("记录成功: %s (%.2fs, score=%.1f)", proxy, latency, self.get_score(proxy))

    def record_failure(self, proxy: str, error: str = "") -> None:
        """记录失败的请求"""
        stats = self._get_or_create(proxy)
        stats.total_requests += 1
        stats.failure_count += 1
        stats.consecutive_fails += 1
        stats.last_used = time.time()
        logger.debug("记录失败: %s (%s, 连续失败 %d)", proxy, error, stats.consecutive_fails)

    def record_blocked(self, proxy: str) -> None:
        """记录被 WAF 拦截"""
        stats = self._get_or_create(proxy)
        stats.total_requests += 1
        stats.block_count += 1
        stats.consecutive_fails += 1
        stats.last_used = time.time()
        stats.last_blocked = time.time()
        logger.debug("记录被封: %s (总被封 %d)", proxy, stats.block_count)

    def get_score(self, proxy: str) -> float:
        """获取代理综合评分 (0-100)"""
        stats = self._stats.get(proxy)
        if stats is None:
            return 50.0  # 未知代理给中间分

        # 延迟评分：5s 以上得 0 分
        latency_score = max(0.0, 100.0 - stats.avg_latency * 20.0)

        # 成功率评分
        success_score = stats.success_rate * 100.0

        # 被封率评分
        block_score = (1.0 - stats.block_rate) * 100.0

        # 综合评分
        score = (
            self._weight_latency * latency_score
            + self._weight_success * success_score
            + self._weight_block * block_score
        )

        # 连续失败惩罚
        score -= stats.consecutive_fails * _PENALTY_CONSECUTIVE_FAIL

        # 最近被封惩罚
        if stats.last_blocked > 0:
            time_since_block = time.time() - stats.last_blocked
            if time_since_block < self._recent_block_window:
                score -= _PENALTY_RECENT_BLOCK

        return max(0.0, min(100.0, score))

    def get_stats(self, proxy: str) -> ProxyStats:
        """获取代理详细统计"""
        return self._get_or_create(proxy)

    def get_best(self, n: int = 5, proxies: list[str] | None = None) -> list[str]:
        """获取评分最高的 N 个代理

        Args:
            n: 返回数量
            proxies: 候选代理列表，None 则使用所有已知代理

        Returns:
            按评分降序排列的代理列表
        """
        candidates = proxies or list(self._stats.keys())
        scored = [(p, self.get_score(p)) for p in candidates if p in self._stats]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:n]]

    def get_worst(self, n: int = 5) -> list[str]:
        """获取评分最低的 N 个代理"""
        scored = [(p, self.get_score(p)) for p in self._stats]
        scored.sort(key=lambda x: x[1])
        return [p for p, _ in scored[:n]]

    def prune(self, threshold: float = 20.0) -> list[str]:
        """移除低分代理

        Args:
            threshold: 低于此分数的代理将被移除

        Returns:
            被移除的代理列表
        """
        to_remove = [p for p in self._stats if self.get_score(p) < threshold]
        for p in to_remove:
            del self._stats[p]
            logger.info("移除低分代理: %s", p)
        return to_remove

    def all_stats(self) -> dict[str, ProxyStats]:
        """获取所有代理统计"""
        return dict(self._stats)

    def __len__(self) -> int:
        return len(self._stats)

    def __contains__(self, proxy: str) -> bool:
        return proxy in self._stats
