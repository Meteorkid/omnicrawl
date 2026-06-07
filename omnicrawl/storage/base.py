"""StateStore 抽象基类 — 统一内存和分布式存储接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class StateStore(ABC):
    """状态存储抽象接口。

    提供通用 KV、集合、列表、哈希操作，
    支持 MemoryStore（纯内存）和 RedisStore（分布式）两种后端。
    """

    # ── 通用 KV ──

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """获取值，不存在返回 None。"""

    @abstractmethod
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        """设置值。ex 为过期秒数（仅 Redis 有效）。"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除键。"""

    # ── 集合（用于 visited set / dedup） ──

    @abstractmethod
    async def sadd(self, key: str, *values: str) -> int:
        """向集合添加元素，返回实际新增数量。"""

    @abstractmethod
    async def smembers(self, key: str) -> set[str]:
        """获取集合所有成员。"""

    @abstractmethod
    async def sismember(self, key: str, value: str) -> bool:
        """检查元素是否在集合中。"""

    # ── 列表（用于 BFS 队列） ──

    @abstractmethod
    async def lpush(self, key: str, *values: str) -> int:
        """从左侧推入列表，返回列表长度。"""

    @abstractmethod
    async def rpop(self, key: str) -> Optional[str]:
        """从右侧弹出元素，空列表返回 None。"""

    @abstractmethod
    async def llen(self, key: str) -> int:
        """获取列表长度。"""

    # ── 哈希（用于 proxy stats / domain delays） ──

    @abstractmethod
    async def hset(self, key: str, field: str, value: str) -> None:
        """设置哈希字段。"""

    @abstractmethod
    async def hget(self, key: str, field: str) -> Optional[str]:
        """获取哈希字段值，不存在返回 None。"""

    @abstractmethod
    async def hgetall(self, key: str) -> dict[str, str]:
        """获取哈希所有字段和值。"""

    # ── 生命周期 ──

    async def close(self) -> None:
        """关闭连接。默认无操作。"""
