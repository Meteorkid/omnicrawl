"""StateStore 测试 — MemoryStore + RedisStore（fakeredis）。"""

import pytest
from omnicrawl.storage.base import StateStore
from omnicrawl.storage.memory import MemoryStore
from omnicrawl.storage import create_store


# ── 工厂函数 ──

class TestCreateStore:
    def test_create_memory(self):
        store = create_store("memory")
        assert isinstance(store, MemoryStore)

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="未知存储后端"):
            create_store("unknown")

    def test_create_redis_missing_dep(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "redis.asyncio", None)
        store = create_store("redis")
        with pytest.raises(ImportError, match="redis 包"):
            import asyncio
            asyncio.run(store.get("key"))


# ── MemoryStore 通用测试 ──

@pytest.fixture
def store():
    return MemoryStore()


class TestKV:
    @pytest.mark.asyncio
    async def test_get_missing(self, store):
        assert await store.get("nope") is None

    @pytest.mark.asyncio
    async def test_set_get(self, store):
        await store.set("key", "value")
        assert await store.get("key") == "value"

    @pytest.mark.asyncio
    async def test_set_overwrite(self, store):
        await store.set("key", "v1")
        await store.set("key", "v2")
        assert await store.get("key") == "v2"

    @pytest.mark.asyncio
    async def test_delete(self, store):
        await store.set("key", "value")
        await store.delete("key")
        assert await store.get("key") is None

    @pytest.mark.asyncio
    async def test_delete_missing(self, store):
        await store.delete("nope")  # 不抛异常


class TestSet:
    @pytest.mark.asyncio
    async def test_sadd_new(self, store):
        count = await store.sadd("s", "a", "b", "c")
        assert count == 3

    @pytest.mark.asyncio
    async def test_sadd_duplicate(self, store):
        await store.sadd("s", "a", "b")
        count = await store.sadd("s", "b", "c")
        assert count == 1  # 只有 c 是新增

    @pytest.mark.asyncio
    async def test_smembers(self, store):
        await store.sadd("s", "a", "b")
        members = await store.smembers("s")
        assert members == {"a", "b"}

    @pytest.mark.asyncio
    async def test_smembers_empty(self, store):
        assert await store.smembers("nope") == set()

    @pytest.mark.asyncio
    async def test_sismember(self, store):
        await store.sadd("s", "a")
        assert await store.sismember("s", "a") is True
        assert await store.sismember("s", "b") is False

    @pytest.mark.asyncio
    async def test_sismember_missing_key(self, store):
        assert await store.sismember("nope", "a") is False


class TestList:
    @pytest.mark.asyncio
    async def test_lpush_rpop(self, store):
        await store.lpush("q", "a", "b", "c")
        assert await store.rpop("q") == "a"  # FIFO
        assert await store.rpop("q") == "b"
        assert await store.rpop("q") == "c"
        assert await store.rpop("q") is None

    @pytest.mark.asyncio
    async def test_llen(self, store):
        await store.lpush("q", "a", "b")
        assert await store.llen("q") == 2

    @pytest.mark.asyncio
    async def test_llen_empty(self, store):
        assert await store.llen("nope") == 0

    @pytest.mark.asyncio
    async def test_rpop_empty(self, store):
        assert await store.rpop("nope") is None


class TestHash:
    @pytest.mark.asyncio
    async def test_hset_hget(self, store):
        await store.hset("h", "field", "value")
        assert await store.hget("h", "field") == "value"

    @pytest.mark.asyncio
    async def test_hget_missing(self, store):
        assert await store.hget("h", "nope") is None
        assert await store.hget("nope", "nope") is None

    @pytest.mark.asyncio
    async def test_hgetall(self, store):
        await store.hset("h", "a", "1")
        await store.hset("h", "b", "2")
        result = await store.hgetall("h")
        assert result == {"a": "1", "b": "2"}

    @pytest.mark.asyncio
    async def test_hgetall_empty(self, store):
        assert await store.hgetall("nope") == {}


class TestDeleteCascade:
    @pytest.mark.asyncio
    async def test_delete_clears_all_types(self, store):
        await store.set("k", "v")
        await store.sadd("k", "a")
        await store.lpush("k", "b")
        await store.hset("k", "f", "v")
        await store.delete("k")
        assert await store.get("k") is None
        assert await store.smembers("k") == set()
        assert await store.llen("k") == 0
        assert await store.hgetall("k") == {}


class TestIsStateStore:
    def test_memory_is_state_store(self):
        assert isinstance(MemoryStore(), StateStore)


# ── RedisStore 测试（fakeredis） ──

@pytest.fixture
def redis_store():
    try:
        import fakeredis.aioredis
    except ImportError:
        pytest.skip("fakeredis 未安装")

    from omnicrawl.storage.redis_store import RedisStore

    store = RedisStore.__new__(RedisStore)
    store._url = "redis://localhost"
    store._prefix = "test:"
    store._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return store


class TestRedisStore:
    @pytest.mark.asyncio
    async def test_kv(self, redis_store):
        await redis_store.set("key", "value")
        assert await redis_store.get("key") == "value"
        await redis_store.delete("key")
        assert await redis_store.get("key") is None

    @pytest.mark.asyncio
    async def test_set_ops(self, redis_store):
        await redis_store.sadd("s", "a", "b")
        assert await redis_store.sismember("s", "a") is True
        assert await redis_store.sismember("s", "c") is False
        members = await redis_store.smembers("s")
        assert members == {"a", "b"}

    @pytest.mark.asyncio
    async def test_list_ops(self, redis_store):
        await redis_store.lpush("q", "a", "b")
        assert await redis_store.llen("q") == 2
        assert await redis_store.rpop("q") == "a"
        assert await redis_store.rpop("q") == "b"
        assert await redis_store.rpop("q") is None

    @pytest.mark.asyncio
    async def test_hash_ops(self, redis_store):
        await redis_store.hset("h", "f1", "v1")
        await redis_store.hset("h", "f2", "v2")
        assert await redis_store.hget("h", "f1") == "v1"
        result = await redis_store.hgetall("h")
        assert result == {"f1": "v1", "f2": "v2"}

    @pytest.mark.asyncio
    async def test_prefix_isolation(self, redis_store):
        await redis_store.set("key", "value")
        raw = await redis_store._redis.get("test:key")
        assert raw == "value"

    @pytest.mark.asyncio
    async def test_close(self, redis_store):
        await redis_store.set("key", "value")
        await redis_store.close()
        assert redis_store._redis is None
