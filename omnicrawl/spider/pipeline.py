"""数据管道 — 清洗、验证、存储

Pipeline 模式：Spider 产出的 SpiderItem 经过一系列 Pipeline 处理后输出。

用法:
    pipeline = Pipeline([
        CleanPipeline(),
        ValidatePipeline(required_fields=["title"]),
        JsonFilePipeline(output_dir="./output"),
    ])

    async for item in spider.stream():
        await pipeline.process(item)
    await pipeline.close()
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from omnicrawl.spider.base import SpiderItem
from omnicrawl.storage.base import StateStore
from omnicrawl.utils.logger import get_logger

logger = get_logger("pipeline")


class PipelineBase(ABC):
    """管道基类"""

    @abstractmethod
    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        """处理数据项，返回处理后的项或 None（丢弃）"""
        ...

    async def open(self) -> None:
        """管道打开（初始化资源）"""
        pass

    async def close(self) -> None:
        """管道关闭（释放资源）"""
        pass


class CleanPipeline(PipelineBase):
    """清洗管道 — 去除空白、规范化字段"""

    def __init__(
        self,
        strip_whitespace: bool = True,
        remove_empty: bool = True,
        max_text_length: Optional[int] = None,
    ):
        self._strip = strip_whitespace
        self._remove_empty = remove_empty
        self._max_len = max_text_length

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        cleaned_data = {}
        for k, v in item.data.items():
            if isinstance(v, str):
                if self._strip:
                    v = v.strip()
                if self._max_len and len(v) > self._max_len:
                    v = v[:self._max_len]
            if self._remove_empty and not v and v != 0:
                continue
            cleaned_data[k] = v

        if self._remove_empty and not cleaned_data:
            return None

        item.data = cleaned_data
        return item


class ValidatePipeline(PipelineBase):
    """验证管道 — 检查必需字段"""

    def __init__(
        self,
        required_fields: Optional[list[str]] = None,
        min_fields: int = 1,
    ):
        self._required = required_fields or []
        self._min_fields = min_fields

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        # 检查必需字段
        for field in self._required:
            if field not in item.data or not item.data[field]:
                logger.debug("丢弃缺少字段 '%s' 的数据项", field)
                return None

        # 检查最少字段数
        if len(item.data) < self._min_fields:
            logger.debug("丢弃字段数不足的数据项 (%d < %d)", len(item.data), self._min_fields)
            return None

        return item


class DedupPipeline(PipelineBase):
    """去重管道 — 基于 URL 或自定义 key 去重"""

    def __init__(self, key_field: Optional[str] = None):
        self._key_field = key_field
        self._seen: set[str] = set()

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        if self._key_field and self._key_field in item.data:
            key = str(item.data[self._key_field])
        else:
            key = item.url or str(item.data)

        if key in self._seen:
            return None
        self._seen.add(key)
        return item

    def reset(self):
        self._seen.clear()


class RedisDedupPipeline(PipelineBase):
    """分布式去重管道 — 基于 StateStore 的集合去重。

    多个 worker 共享同一个 store，实现跨进程去重。

    Args:
        store: StateStore 实例（MemoryStore 或 RedisStore）
        key_field: 用作去重 key 的字段名，默认按 URL 去重
        prefix: store 中集合的键名前缀
    """

    def __init__(
        self,
        store: StateStore,
        key_field: Optional[str] = None,
        prefix: str = "dedup",
    ):
        self._store = store
        self._key_field = key_field
        self._prefix = prefix

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        if self._key_field and self._key_field in item.data:
            key = str(item.data[self._key_field])
        else:
            key = item.url or str(item.data)

        is_dup = await self._store.sismember(self._prefix, key)
        if is_dup:
            return None
        await self._store.sadd(self._prefix, key)
        return item


class JsonFilePipeline(PipelineBase):
    """JSON 文件存储管道"""

    def __init__(
        self,
        output_dir: str = "./output",
        filename: str = "items.jsonl",
        indent: bool = False,
    ):
        self._output_dir = Path(output_dir)
        self._filename = filename
        self._indent = indent
        self._file = None
        self._count = 0

    async def open(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._output_dir / self._filename
        self._file = open(filepath, "w", encoding="utf-8")
        logger.info("数据将写入: %s", filepath)

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        if self._file is None:
            await self.open()

        record = {
            "url": item.url,
            "data": item.data,
        }
        if item.markdown:
            record["markdown"] = item.markdown[:500]

        line = json.dumps(record, ensure_ascii=False)
        self._file.write(line + "\n")
        self._count += 1
        return item

    async def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
            logger.info("已写入 %d 条数据", self._count)


class Pipeline:
    """管道编排器 — 按顺序执行多个管道"""

    def __init__(self, stages: list[PipelineBase]):
        self._stages = stages
        self._total_processed = 0
        self._total_dropped = 0

    async def open(self) -> None:
        for stage in self._stages:
            await stage.open()

    async def process(self, item: SpiderItem) -> Optional[SpiderItem]:
        """依次通过所有管道处理"""
        current = item
        for stage in self._stages:
            if current is None:
                break
            current = await stage.process(current)

        if current is not None:
            self._total_processed += 1
        else:
            self._total_dropped += 1
        return current

    async def close(self) -> None:
        for stage in self._stages:
            await stage.close()
        logger.info("管道处理完成: 通过 %d, 丢弃 %d", self._total_processed, self._total_dropped)

    @property
    def processed(self) -> int:
        """已处理数据项数"""
        return self._total_processed

    @property
    def dropped(self) -> int:
        """已丢弃数据项数"""
        return self._total_dropped

    @property
    def stats(self) -> dict:
        return {
            "processed": self._total_processed,
            "dropped": self._total_dropped,
        }

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()
