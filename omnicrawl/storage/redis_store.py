"""RedisStore — Redis 分布式状态存储。"""

from __future__ import annotations

from typing import Optional

from omnicrawl.storage.base import StateStore


class RedisStore(StateStore):
    """基于 Redis 的分布式存储。

    多个 worker 可共享同一 Redis 实例，实现分布式爬取。

    依赖：``pip install "omnicrawl[redis]"``

    Args:
        url: Redis 连接 URL，默认 ``redis://localhost:6379/0``
        prefix: 键前缀，避免命名冲突
    """

    def __init__(self, url: str = "redis://localhost:6379/0", prefix: str = "omnicrawl:") -> None:
        self._url = url
        self._prefix = prefix
        self._redis = None

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def _ensure_conn(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
            except ImportError:
                raise ImportError(
                    "Redis 后端需要 redis 包。请安装：pip install 'omnicrawl[redis]'"
                )
            self._redis = aioredis.from_url(self._url, decode_responses=True)

    # ── 通用 KV ──

    async def get(self, key: str) -> Optional[str]:
        await self._ensure_conn()
        return await self._redis.get(self._key(key))

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        await self._ensure_conn()
        await self._redis.set(self._key(key), value, ex=ex)

    async def delete(self, key: str) -> None:
        await self._ensure_conn()
        await self._redis.delete(self._key(key))

    # ── 集合 ──

    async def sadd(self, key: str, *values: str) -> int:
        await self._ensure_conn()
        return await self._redis.sadd(self._key(key), *values)

    async def smembers(self, key: str) -> set[str]:
        await self._ensure_conn()
        return await self._redis.smembers(self._key(key))

    async def sismember(self, key: str, value: str) -> bool:
        await self._ensure_conn()
        result = await self._redis.sismember(self._key(key), value)
        return bool(result)

    # ── 列表 ──

    async def lpush(self, key: str, *values: str) -> int:
        await self._ensure_conn()
        return await self._redis.lpush(self._key(key), *values)

    async def rpop(self, key: str) -> Optional[str]:
        await self._ensure_conn()
        return await self._redis.rpop(self._key(key))

    async def llen(self, key: str) -> int:
        await self._ensure_conn()
        return await self._redis.llen(self._key(key))

    # ── 哈希 ──

    async def hset(self, key: str, field: str, value: str) -> None:
        await self._ensure_conn()
        await self._redis.hset(self._key(key), field, value)

    async def hget(self, key: str, field: str) -> Optional[str]:
        await self._ensure_conn()
        return await self._redis.hget(self._key(key), field)

    async def hgetall(self, key: str) -> dict[str, str]:
        await self._ensure_conn()
        return await self._redis.hgetall(self._key(key))

    # ── 生命周期 ──

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except AttributeError:
                await self._redis.close()
            self._redis = None
