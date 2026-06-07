"""MemoryStore — 纯内存状态存储，默认后端。"""

from __future__ import annotations

from typing import Optional

from omnicrawl.storage.base import StateStore


class MemoryStore(StateStore):
    """基于 Python dict/set/list 的内存存储。

    所有数据存储在进程内存中，进程退出即丢失。
    适用于单机场景和测试。
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._sets: dict[str, set[str]] = {}
        self._lists: dict[str, list[str]] = {}
        self._hashes: dict[str, dict[str, str]] = {}

    # ── 通用 KV ──

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._sets.pop(key, None)
        self._lists.pop(key, None)
        self._hashes.pop(key, None)

    # ── 集合 ──

    async def sadd(self, key: str, *values: str) -> int:
        s = self._sets.setdefault(key, set())
        before = len(s)
        s.update(values)
        return len(s) - before

    async def smembers(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    async def sismember(self, key: str, value: str) -> bool:
        return value in self._sets.get(key, set())

    # ── 列表 ──

    async def lpush(self, key: str, *values: str) -> int:
        lst = self._lists.setdefault(key, [])
        for v in values:
            lst.insert(0, v)
        return len(lst)

    async def rpop(self, key: str) -> Optional[str]:
        lst = self._lists.get(key)
        if not lst:
            return None
        return lst.pop()

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    # ── 哈希 ──

    async def hset(self, key: str, field: str, value: str) -> None:
        self._hashes.setdefault(key, {})[field] = value

    async def hget(self, key: str, field: str) -> Optional[str]:
        return self._hashes.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))
