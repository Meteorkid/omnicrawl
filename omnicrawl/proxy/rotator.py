"""代理轮换器"""

from __future__ import annotations

import random
import threading
import time
from typing import Optional, Callable
from omnicrawl.utils.logger import get_logger

logger = get_logger("proxy")


class TokenBucket:
    """线程安全的令牌桶限速器

    每个代理一个桶，控制单代理请求速率。

    用法:
        bucket = TokenBucket(rate_per_minute=30)
        if bucket.acquire():  # 非阻塞
            # 可以发请求
        wait = bucket.wait_time()  # 需要等多久
    """

    def __init__(self, rate_per_minute: int):
        self.rate = rate_per_minute / 60.0  # tokens/second
        self.burst = max(rate_per_minute / 10, 1)  # burst = ~10% of rate
        self.tokens = self.burst
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """尝试获取一个令牌，立即返回是否成功"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def wait_time(self) -> float:
        """获取需要等待的秒数（0=立即可用）"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                return 0.0
            return (1 - self.tokens) / self.rate


class ProxyRotator:
    """代理轮换器

    注意：本类非线程安全，仅限 asyncio 单协程使用。

    用法:
        rotator = ProxyRotator([
            "http://proxy1:8080",
            "http://user:pass@proxy2:8080",
        ])
        proxy = rotator.next()  # 获取下一个代理

    支持自定义轮换策略:
        rotator = ProxyRotator(proxies, strategy="random")
        rotator = ProxyRotator(proxies, strategy="weighted", weights=[3, 1])
        rotator = ProxyRotator(proxies, strategy="scored", scorer=scorer)

    支持 per-proxy 限速:
        rotator = ProxyRotator(proxies, rate_per_minute=30)
        proxy = rotator.next_available()  # 只分配有令牌的代理
    """

    def __init__(
        self,
        proxies: list[str],
        strategy: str = "round_robin",  # round_robin / random / weighted / scored
        weights: Optional[list[float]] = None,
        scorer: Optional[object] = None,  # ProxyScorer 实例
        rate_per_minute: int = 0,  # 每代理每分钟最大请求数（0=不限速）
    ):
        if not proxies:
            raise ValueError("代理列表不能为空")
        self._proxies = list(proxies)
        self._strategy = strategy
        self._weights = weights
        self._scorer = scorer
        self._index = 0
        self._available_index = 0  # next_available 专用索引
        self._used_count: dict[str, int] = {p: 0 for p in proxies}
        self._rate_per_minute = rate_per_minute

        # 每代理独立令牌桶
        self._buckets: dict[str, TokenBucket] = {}
        if rate_per_minute > 0:
            for p in proxies:
                self._buckets[p] = TokenBucket(rate_per_minute)

        if strategy == "weighted" and weights and len(weights) != len(proxies):
            raise ValueError("权重数量必须与代理数量一致")
        if strategy == "scored" and scorer is None:
            from omnicrawl.proxy.scorer import ProxyScorer
            self._scorer = ProxyScorer()

    def next(self) -> str:
        """获取下一个代理（忽略限速，强制分配）"""
        if not self._proxies:
            raise RuntimeError("代理池为空，无法分配代理。请调用 add() 添加代理。")
        if self._strategy == "random":
            proxy = random.choice(self._proxies)
        elif self._strategy == "weighted":
            proxy = random.choices(self._proxies, weights=self._weights, k=1)[0]
        elif self._strategy == "scored":
            proxy = self._next_by_score()
        else:  # round_robin
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1

        self._used_count[proxy] = self._used_count.get(proxy, 0) + 1
        logger.debug(f"分配代理: {proxy}")
        return proxy

    def next_available(self) -> Optional[str]:
        """获取下一个有可用令牌的代理（限速模式下优先使用）

        Returns:
            有令牌的代理 URL，或 None（所有代理都在限速冷却中）
        """
        if not self._proxies or not self._buckets:
            return self.next() if self._proxies else None

        # 收集有令牌的代理
        available = [p for p in self._proxies if p in self._buckets and self._buckets[p].acquire()]
        if not available:
            return None

        # 从可用代理中按策略选择
        if self._strategy == "random":
            proxy = random.choice(available)
        elif self._strategy == "weighted":
            # 过滤对应权重
            avail_weights = [self._weights[self._proxies.index(p)] for p in available]
            proxy = random.choices(available, weights=avail_weights, k=1)[0]
        elif self._strategy == "scored":
            scores = [(p, self._scorer.get_score(p) if self._scorer else 50.0) for p in available]
            proxy = max(scores, key=lambda x: x[1])[0]
        else:  # round_robin
            proxy = available[self._available_index % len(available)]
            self._available_index += 1

        self._used_count[proxy] = self._used_count.get(proxy, 0) + 1
        logger.debug(f"分配代理（限速模式）: {proxy}")
        return proxy

    def get_wait_time(self, proxy: str) -> float:
        """获取指定代理的令牌等待时间"""
        bucket = self._buckets.get(proxy)
        if bucket is None:
            return 0.0
        return bucket.wait_time()

    def _next_by_score(self) -> str:
        """按评分加权选择代理（评分越高被选中概率越大）"""
        scorer = self._scorer
        scores = []
        for p in self._proxies:
            s = scorer.get_score(p) if scorer else 50.0
            scores.append(max(s, 1.0))  # 最低 1 分，避免全 0

        # 按评分加权随机选择
        return random.choices(self._proxies, weights=scores, k=1)[0]

    @property
    def scorer(self):
        """获取评分器"""
        return self._scorer

    def remove(self, proxy: str) -> None:
        """移除失效代理"""
        if proxy in self._proxies:
            self._proxies.remove(proxy)
            self._used_count.pop(proxy, None)
            self._buckets.pop(proxy, None)
            logger.info(f"移除代理: {proxy}")

    def add(self, proxy: str) -> None:
        """添加新代理"""
        if proxy not in self._proxies:
            self._proxies.append(proxy)
            self._used_count[proxy] = 0
            if self._rate_per_minute > 0:
                self._buckets[proxy] = TokenBucket(self._rate_per_minute)

    @property
    def count(self) -> int:
        return len(self._proxies)

    @property
    def stats(self) -> dict[str, int]:
        """各代理使用次数"""
        return dict(self._used_count)

    def __len__(self) -> int:
        return len(self._proxies)

    def __repr__(self) -> str:
        return f"<ProxyRotator {len(self._proxies)} proxies, strategy={self._strategy}>"
