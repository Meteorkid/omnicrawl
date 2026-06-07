"""RedisDedupPipeline 测试 — 使用 MemoryStore 验证分布式去重。"""

import pytest
from omnicrawl.storage.memory import MemoryStore
from omnicrawl.spider.base import SpiderItem
from omnicrawl.spider.pipeline import RedisDedupPipeline, Pipeline


@pytest.fixture
def store():
    return MemoryStore()


class TestRedisDedupPipeline:
    @pytest.mark.asyncio
    async def test_first_pass(self, store):
        pipe = RedisDedupPipeline(store=store)
        item = SpiderItem(data={"title": "test"}, url="https://example.com/1")
        result = await pipe.process(item)
        assert result is item

    @pytest.mark.asyncio
    async def test_duplicate_rejected(self, store):
        pipe = RedisDedupPipeline(store=store)
        item1 = SpiderItem(data={"title": "test"}, url="https://example.com/1")
        item2 = SpiderItem(data={"title": "test2"}, url="https://example.com/1")

        assert await pipe.process(item1) is not None
        assert await pipe.process(item2) is None

    @pytest.mark.asyncio
    async def test_different_urls_pass(self, store):
        pipe = RedisDedupPipeline(store=store)
        item1 = SpiderItem(data={"title": "a"}, url="https://example.com/1")
        item2 = SpiderItem(data={"title": "b"}, url="https://example.com/2")

        assert await pipe.process(item1) is not None
        assert await pipe.process(item2) is not None

    @pytest.mark.asyncio
    async def test_key_field(self, store):
        pipe = RedisDedupPipeline(store=store, key_field="id")
        item1 = SpiderItem(data={"id": "abc", "title": "a"}, url="https://a.com")
        item2 = SpiderItem(data={"id": "abc", "title": "b"}, url="https://b.com")

        assert await pipe.process(item1) is not None
        assert await pipe.process(item2) is None  # same id

    @pytest.mark.asyncio
    async def test_custom_prefix(self, store):
        pipe = RedisDedupPipeline(store=store, prefix="my_dedup")
        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        await pipe.process(item)

        # 数据应在自定义前缀下
        assert await store.sismember("my_dedup", "https://example.com")

    @pytest.mark.asyncio
    async def test_shared_store_across_pipelines(self, store):
        """两个 pipeline 共享同一个 store，实现跨 pipeline 去重"""
        pipe1 = RedisDedupPipeline(store=store, prefix="shared")
        pipe2 = RedisDedupPipeline(store=store, prefix="shared")

        item1 = SpiderItem(data={"title": "a"}, url="https://example.com")
        item2 = SpiderItem(data={"title": "b"}, url="https://example.com")

        assert await pipe1.process(item1) is not None
        assert await pipe2.process(item2) is None  # 去重

    @pytest.mark.asyncio
    async def test_in_pipeline_chain(self, store):
        """测试在 Pipeline 链中使用"""
        from omnicrawl.spider.pipeline import CleanPipeline, ValidatePipeline

        pipeline = Pipeline([
            CleanPipeline(remove_empty=True),
            ValidatePipeline(required_fields=["title"]),
            RedisDedupPipeline(store=store, key_field="url"),
        ])

        item1 = SpiderItem(data={"title": "test"}, url="https://example.com")
        item2 = SpiderItem(data={"title": "test"}, url="https://example.com")

        result1 = await pipeline.process(item1)
        assert result1 is not None
        assert pipeline.processed == 1

        result2 = await pipeline.process(item2)
        assert result2 is None
        assert pipeline.dropped == 1


class TestPipelineProperties:
    @pytest.mark.asyncio
    async def test_processed_dropped(self):
        from omnicrawl.spider.pipeline import ValidatePipeline

        pipeline = Pipeline([ValidatePipeline(required_fields=["title"])])

        good = SpiderItem(data={"title": "ok"}, url="https://a.com")
        bad = SpiderItem(data={"other": "val"}, url="https://b.com")

        await pipeline.process(good)
        await pipeline.process(bad)

        assert pipeline.processed == 1
        assert pipeline.dropped == 1
