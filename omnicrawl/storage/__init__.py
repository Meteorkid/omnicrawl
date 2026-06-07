"""存储后端 — 支持内存和 Redis 两种状态存储。"""

from omnicrawl.storage.base import StateStore
from omnicrawl.storage.memory import MemoryStore

__all__ = ["StateStore", "MemoryStore"]


def create_store(backend: str = "memory", **kwargs) -> StateStore:
    """工厂函数：根据后端名称创建 StateStore。

    Args:
        backend: "memory" 或 "redis"
        **kwargs: 传递给具体实现的参数（如 url, prefix）
    """
    if backend == "memory":
        return MemoryStore()
    elif backend == "redis":
        from omnicrawl.storage.redis_store import RedisStore

        return RedisStore(**kwargs)
    else:
        raise ValueError(f"未知存储后端: {backend}，可选: memory, redis")
