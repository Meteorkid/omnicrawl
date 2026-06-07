"""代理轮换器"""

from __future__ import annotations

import random
from typing import Optional, Callable
from omnicrawl.utils.logger import get_logger

logger = get_logger("proxy")


class ProxyRotator:
    """代理轮换器

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
    """

    def __init__(
        self,
        proxies: list[str],
        strategy: str = "round_robin",  # round_robin / random / weighted / scored
        weights: Optional[list[float]] = None,
        scorer: Optional[object] = None,  # ProxyScorer 实例
    ):
        if not proxies:
            raise ValueError("代理列表不能为空")
        self._proxies = list(proxies)
        self._strategy = strategy
        self._weights = weights
        self._scorer = scorer
        self._index = 0
        self._used_count: dict[str, int] = {p: 0 for p in proxies}

        if strategy == "weighted" and weights and len(weights) != len(proxies):
            raise ValueError("权重数量必须与代理数量一致")
        if strategy == "scored" and scorer is None:
            from omnicrawl.proxy.scorer import ProxyScorer
            self._scorer = ProxyScorer()

    def next(self) -> str:
        """获取下一个代理"""
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
            logger.info(f"移除代理: {proxy}")

    def add(self, proxy: str) -> None:
        """添加新代理"""
        if proxy not in self._proxies:
            self._proxies.append(proxy)
            self._used_count[proxy] = 0

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
