"""Pipeline 数据管道测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnicrawl.spider.base import SpiderItem
from omnicrawl.spider.pipeline import (
    CleanPipeline,
    DedupPipeline,
    JsonFilePipeline,
    Pipeline,
    ValidatePipeline,
)


class TestCleanPipeline:
    @pytest.mark.asyncio
    async def test_strip_whitespace(self):
        item = SpiderItem(data={"title": "  hello  ", "desc": "  world  "})
        result = await CleanPipeline().process(item)
        assert result.data["title"] == "hello"
        assert result.data["desc"] == "world"

    @pytest.mark.asyncio
    async def test_remove_empty(self):
        item = SpiderItem(data={"title": "ok", "empty": "", "none_val": None})
        result = await CleanPipeline(remove_empty=True).process(item)
        assert "title" in result.data
        assert "empty" not in result.data
        assert "none_val" not in result.data

    @pytest.mark.asyncio
    async def test_keep_zero(self):
        item = SpiderItem(data={"count": 0, "name": "test"})
        result = await CleanPipeline(remove_empty=True).process(item)
        assert "count" in result.data

    @pytest.mark.asyncio
    async def test_max_text_length(self):
        item = SpiderItem(data={"text": "a" * 1000})
        result = await CleanPipeline(max_text_length=10).process(item)
        assert len(result.data["text"]) == 10

    @pytest.mark.asyncio
    async def test_all_empty_returns_none(self):
        item = SpiderItem(data={"a": "", "b": None})
        result = await CleanPipeline(remove_empty=True).process(item)
        assert result is None


class TestValidatePipeline:
    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        item = SpiderItem(data={"title": "ok", "url": "http://test.com"})
        result = await ValidatePipeline(required_fields=["title"]).process(item)
        assert result is not None

    @pytest.mark.asyncio
    async def test_required_field_missing(self):
        item = SpiderItem(data={"desc": "no title"})
        result = await ValidatePipeline(required_fields=["title"]).process(item)
        assert result is None

    @pytest.mark.asyncio
    async def test_required_field_empty(self):
        item = SpiderItem(data={"title": ""})
        result = await ValidatePipeline(required_fields=["title"]).process(item)
        assert result is None

    @pytest.mark.asyncio
    async def test_min_fields(self):
        item = SpiderItem(data={"only_one": "value"})
        result = await ValidatePipeline(min_fields=2).process(item)
        assert result is None

    @pytest.mark.asyncio
    async def test_min_fields_met(self):
        item = SpiderItem(data={"a": 1, "b": 2})
        result = await ValidatePipeline(min_fields=2).process(item)
        assert result is not None


class TestDedupPipeline:
    @pytest.mark.asyncio
    async def test_first_pass(self):
        pipeline = DedupPipeline()
        item = SpiderItem(data={"title": "unique"}, url="http://test.com/1")
        result = await pipeline.process(item)
        assert result is not None

    @pytest.mark.asyncio
    async def test_duplicate_rejected(self):
        pipeline = DedupPipeline()
        item1 = SpiderItem(data={"title": "same"}, url="http://test.com/1")
        item2 = SpiderItem(data={"title": "same"}, url="http://test.com/1")
        await pipeline.process(item1)
        result = await pipeline.process(item2)
        assert result is None

    @pytest.mark.asyncio
    async def test_key_field_dedup(self):
        pipeline = DedupPipeline(key_field="id")
        item1 = SpiderItem(data={"id": "123", "title": "A"})
        item2 = SpiderItem(data={"id": "123", "title": "B"})
        await pipeline.process(item1)
        result = await pipeline.process(item2)
        assert result is None

    @pytest.mark.asyncio
    async def test_reset(self):
        pipeline = DedupPipeline()
        item = SpiderItem(data={"title": "test"}, url="http://test.com/1")
        await pipeline.process(item)
        pipeline.reset()
        result = await pipeline.process(item)
        assert result is not None


class TestJsonFilePipeline:
    @pytest.mark.asyncio
    async def test_write_items(self, tmp_path):
        pipeline = JsonFilePipeline(output_dir=str(tmp_path), filename="test.jsonl")
        await pipeline.open()

        item = SpiderItem(data={"title": "Test"}, url="http://test.com")
        await pipeline.process(item)
        await pipeline.close()

        content = (tmp_path / "test.jsonl").read_text()
        record = json.loads(content.strip())
        assert record["data"]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_multiple_items(self, tmp_path):
        pipeline = JsonFilePipeline(output_dir=str(tmp_path), filename="test.jsonl")
        await pipeline.open()

        for i in range(3):
            item = SpiderItem(data={"index": i}, url=f"http://test.com/{i}")
            await pipeline.process(item)
        await pipeline.close()

        lines = (tmp_path / "test.jsonl").read_text().strip().split("\n")
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_creates_output_dir(self, tmp_path):
        output_dir = tmp_path / "nested" / "output"
        pipeline = JsonFilePipeline(output_dir=str(output_dir))
        await pipeline.open()
        await pipeline.close()
        assert output_dir.exists()


class TestPipeline:
    @pytest.mark.asyncio
    async def test_chained_processing(self):
        pipeline = Pipeline([
            CleanPipeline(),
            ValidatePipeline(required_fields=["title"]),
        ])
        await pipeline.open()

        # 有效数据通过
        item1 = SpiderItem(data={"title": "  Hello  "})
        result1 = await pipeline.process(item1)
        assert result1 is not None
        assert result1.data["title"] == "Hello"

        # 缺少 title 被丢弃
        item2 = SpiderItem(data={"desc": "no title"})
        result2 = await pipeline.process(item2)
        assert result2 is None

        await pipeline.close()
        assert pipeline.stats["processed"] == 1
        assert pipeline.stats["dropped"] == 1

    @pytest.mark.asyncio
    async def test_context_manager(self):
        pipeline = Pipeline([CleanPipeline()])
        async with pipeline:
            item = SpiderItem(data={"title": "  test  "})
            result = await pipeline.process(item)
            assert result is not None

    @pytest.mark.asyncio
    async def test_full_chain(self, tmp_path):
        pipeline = Pipeline([
            CleanPipeline(remove_empty=True),
            ValidatePipeline(required_fields=["title"]),
            DedupPipeline(key_field="title"),
            JsonFilePipeline(output_dir=str(tmp_path)),
        ])

        items = [
            SpiderItem(data={"title": "A", "desc": "ok"}, url="http://test.com/1"),
            SpiderItem(data={"title": "B", "desc": "ok"}, url="http://test.com/2"),
            SpiderItem(data={"title": "A", "desc": "dup"}, url="http://test.com/3"),  # 去重
            SpiderItem(data={"title": "", "desc": "no title"}, url="http://test.com/4"),  # 验证失败
        ]

        async with pipeline:
            results = []
            for item in items:
                r = await pipeline.process(item)
                if r:
                    results.append(r)

        assert len(results) == 2  # A 和 B 通过，A 的重复和空 title 被丢弃
        assert pipeline.stats["processed"] == 2
        assert pipeline.stats["dropped"] == 2
