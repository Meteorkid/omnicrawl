"""查询缓存 — 跳过已知空结果，节省请求配额

灵感来自猎聘爬虫的"空结果记忆"优化：
- 记录 (url, params) 返回空的组合
- 下次相同请求直接跳过，避免浪费请求配额
- TTL 过期后重新尝试（反爬策略可能变化）
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Optional

from omnicrawl.utils.logger import get_logger

logger = get_logger("cache")

__all__ = ["QueryCache"]


class QueryCache:
    """查询结果缓存（线程安全，TTL 过期）

    用法:
        cache = QueryCache(ttl=3600)  # 1 小时过期

        # 请求前检查
        key = cache.make_key("https://api.example.com/search", {"q": "python"})
        if cache.is_known_empty(key):
            print("跳过已知空结果")
            return

        # 请求后记录空结果
        if not results:
            cache.record_empty(key)
    """

    def __init__(self, ttl: float = 3600.0, max_size: int = 10000):
        """
        Args:
            ttl: 缓存过期时间（秒），默认 1 小时
            max_size: 最大缓存条目数（防内存溢出）
        """
        self._ttl = ttl
        self._max_size = max_size
        self._cache: dict[str, float] = {}  # key -> expire_time
        self._lock = threading.Lock()

    def make_key(self, url: str, params: Optional[dict] = None) -> str:
        """生成缓存 key（URL + 参数的哈希）"""
        raw = url
        if params:
            raw += "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def is_known_empty(self, key: str) -> bool:
        """检查是否在 TTL 内已知返回空"""
        with self._lock:
            expire = self._cache.get(key)
            if expire is None:
                return False
            if time.time() > expire:
                # 已过期，删除
                del self._cache[key]
                return False
            return True

    def record_empty(self, key: str) -> None:
        """记录空结果"""
        with self._lock:
            # FIFO 淘汰：先删过期条目，仍满则删最早过期的一半
            if len(self._cache) >= self._max_size:
                self._evict()

            self._cache[key] = time.time() + self._ttl
            logger.debug("记录空结果: %s (缓存 %d 条)", key[:12], len(self._cache))

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def _evict(self) -> None:
        """淘汰过期 + 最早的条目（锁内调用）"""
        now = time.time()
        # 先删过期的
        expired = [k for k, v in self._cache.items() if v <= now]
        for k in expired:
            del self._cache[k]

        # 还是太多，删最早的一半
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k])
            to_remove = sorted_keys[: len(sorted_keys) // 2]
            for k in to_remove:
                del self._cache[k]

    @property
    def size(self) -> int:
        """当前缓存条目数"""
        with self._lock:
            return len(self._cache)
