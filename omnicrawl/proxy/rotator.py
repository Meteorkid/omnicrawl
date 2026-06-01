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
    """

    def __init__(
        self,
        proxies: list[str],
        strategy: str = "round_robin",  # round_robin / random / weighted
        weights: Optional[list[float]] = None,
    ):
        if not proxies:
            raise ValueError("代理列表不能为空")
        self._proxies = list(proxies)
        self._strategy = strategy
        self._weights = weights
        self._index = 0
        self._used_count: dict[str, int] = {p: 0 for p in proxies}

        if strategy == "weighted" and weights and len(weights) != len(proxies):
            raise ValueError("权重数量必须与代理数量一致")

    def next(self) -> str:
        """获取下一个代理"""
        if not self._proxies:
            raise RuntimeError("代理池为空，无法分配代理。请调用 add() 添加代理。")
        if self._strategy == "random":
            proxy = random.choice(self._proxies)
        elif self._strategy == "weighted":
            proxy = random.choices(self._proxies, weights=self._weights, k=1)[0]
        else:  # round_robin
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1

        self._used_count[proxy] = self._used_count.get(proxy, 0) + 1
        logger.debug(f"分配代理: {proxy}")
        return proxy

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
