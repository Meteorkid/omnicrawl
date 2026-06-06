"""HTML → Markdown 转换器（LLM 友好输出）"""

from __future__ import annotations

import re
from typing import Optional

# 需要移除的标签（导航、广告、脚本等）
REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "svg", "canvas",
]

# 需要移除的 class/id 关键词
REMOVE_PATTERNS = [
    "sidebar", "advertisement", "ad-", "cookie", "popup",
    "modal", "banner", "social", "share", "comment",
    "related", "recommend", "breadcrumb", "pagination",
]


class MarkdownConverter:
    """HTML → 干净 Markdown 转换器

    特点：
    - 移除导航、广告、脚本等噪音
    - 保留正文内容
    - Token 友好（比原始 HTML 节省 60-90%）
    - 支持紧凑模式、token 截断、分段输出

    用法:
        converter = MarkdownConverter()
        md = converter.convert(html)
        print(converter.token_count(md))

        # 带统计信息
        result = converter.convert_with_stats(html)
        print(result["compression_ratio"])
    """

    def __init__(
        self,
        remove_tags: Optional[list[str]] = None,
        remove_patterns: Optional[list[str]] = None,
        strip_links: bool = False,
        strip_images: bool = False,
        compact: bool = False,
        max_tokens: Optional[int] = None,
        segment_size: Optional[int] = None,
    ):
        self._remove_tags = remove_tags or REMOVE_TAGS
        self._remove_patterns = remove_patterns or REMOVE_PATTERNS
        self._strip_links = strip_links
        self._strip_images = strip_images
        self._compact = compact
        self._max_tokens = max_tokens
        self._segment_size = segment_size

    def convert(self, html: str) -> str:
        """将 HTML 转换为干净的 Markdown（增强版）"""
        md_text = self._raw_convert(html)

        if self._compact:
            md_text = self._apply_compact(md_text)

        if self._max_tokens is not None:
            md_text, _ = self._apply_token_limit(md_text, self._max_tokens)

        return md_text

    def _raw_convert(self, html: str) -> str:
        """执行原始 HTML → Markdown 转换（不含后处理）"""
        try:
            return self._convert_selectolax(html)
        except ImportError:
            return self._convert_markdownify(html)

    def _convert_selectolax(self, html: str) -> str:
        """使用 selectolax 高性能解析"""
        from selectolax.parser import HTMLParser as SelectolaxParser

        tree = SelectolaxParser(html)

        # 移除噪音标签
        for tag in self._remove_tags:
            for node in tree.tags(tag):
                node.decompose()

        # 移除噪音 class/id
        for node in tree.css("*"):
            classes = " ".join(node.attributes.get("class", "").split())
            id_attr = node.attributes.get("id", "")
            combined = f"{classes} {id_attr}".lower()
            if any(p in combined for p in self._remove_patterns):
                node.decompose()

        # 获取清理后的 HTML
        cleaned_html = tree.body.html if tree.body else str(tree)

        # 转换为 Markdown
        return self._convert_markdownify(cleaned_html)

    def _convert_markdownify(self, html: str) -> str:
        """使用 markdownify 转换"""
        from markdownify import markdownify as md

        strip_tags = []
        if self._strip_images:
            strip_tags.append("img")
        if self._strip_links:
            strip_tags.append("a")
        kwargs = {"strip": strip_tags} if strip_tags else {}

        md_text = md(html, **kwargs)

        # 清理多余空行
        md_text = re.sub(r"\n{3,}", "\n\n", md_text)
        return md_text.strip()

    def _apply_compact(self, markdown: str) -> str:
        """应用紧凑模式：只保留 Agent 关心的结构化内容

        移除：
        - 空链接 `[](url)`
        - 只有图片无文字的段落（如 `![](image.jpg)`）
        - 重复的分隔线
        - 纯装饰性文本（空段落、纯空白）
        保留：标题、正文段落、列表、表格、代码块
        """
        lines = markdown.split("\n")
        result: list[str] = []
        prev_was_hr = False

        for line in lines:
            stripped = line.strip()

            # 跳过空行（但保留单个换行用于段落分隔）
            if stripped == "":
                # 保留段落间隔
                if result and result[-1] != "":
                    result.append("")
                continue

            # 移除空链接 `[](url)`
            if re.match(r"^\[\]\([^)]*\)\s*$", stripped):
                continue

            # 移除只有图片无文字的行（图片无 alt text）
            if re.match(r"^!\[\]\([^)]*\)\s*$", stripped):
                continue

            # 移除连续重复的分隔线
            if re.match(r"^[-*_]{3,}\s*$", stripped):
                if prev_was_hr:
                    continue
                prev_was_hr = True
                result.append(stripped)
                continue

            prev_was_hr = False
            result.append(line)

        # 清理尾部空行
        while result and result[-1] == "":
            result.pop()

        return "\n".join(result)

    def _apply_token_limit(self, markdown: str, max_tokens: int) -> tuple[str, bool]:
        """截断到指定 token 数，按段落边界截断

        Returns:
            (截断后的文本, 是否发生了截断)
        """
        current_tokens = self.token_count(markdown)
        if current_tokens <= max_tokens:
            return markdown, False

        # 按段落分割
        paragraphs = re.split(r"\n\n+", markdown)
        truncated_parts: list[str] = []
        used_tokens = 0

        for para in paragraphs:
            para_tokens = self.token_count(para)
            # 加上段落间的换行开销
            sep_tokens = self.token_count("\n\n") if truncated_parts else 0
            if used_tokens + sep_tokens + para_tokens > max_tokens:
                break
            truncated_parts.append(para)
            used_tokens += sep_tokens + para_tokens

        truncated = "\n\n".join(truncated_parts)
        truncated += f"\n\n[truncated at {max_tokens} tokens]"
        return truncated, True

    def segment(
        self, markdown: str, segment_size: Optional[int] = None
    ) -> list[str]:
        """将 Markdown 按段落边界分段

        每段尽量接近 segment_size token 但不超过。
        段之间保留轻微重叠（上一段最后一个段落作为下一段的上下文）。

        Args:
            markdown: 要分段的 Markdown 文本
            segment_size: 每段最大 token 数，默认使用实例设置

        Returns:
            分段后的文本列表
        """
        size = segment_size or self._segment_size
        if size is None:
            return [markdown]

        paragraphs = re.split(r"\n\n+", markdown)
        segments: list[str] = []
        current_segment: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.token_count(para)
            sep_tokens = self.token_count("\n\n") if current_segment else 0

            if current_tokens + sep_tokens + para_tokens > size and current_segment:
                # 当前段已满，保存并开始新段
                segments.append("\n\n".join(current_segment))

                # 重叠：将当前段最后一个段落作为新段的开头
                overlap = [current_segment[-1]]
                overlap_tokens = self.token_count(current_segment[-1])

                current_segment = overlap
                current_tokens = overlap_tokens

            current_segment.append(para)
            current_tokens += sep_tokens + para_tokens

        # 追加最后一段
        if current_segment:
            segments.append("\n\n".join(current_segment))

        return segments

    def convert_with_stats(self, html: str) -> dict:
        """带统计信息的转换

        Returns:
            {
                "markdown": str,
                "original_tokens": int,
                "cleaned_tokens": int,
                "compression_ratio": float,
                "truncated": bool,
                "segments": list[str] | None,
            }
        """
        # 计算原始 HTML token 数
        original_tokens = self.token_count(html)

        # 执行转换
        raw_md = self._raw_convert(html)
        raw_tokens = self.token_count(raw_md)

        # 应用 compact
        if self._compact:
            raw_md = self._apply_compact(raw_md)

        # 应用截断
        truncated = False
        if self._max_tokens is not None:
            raw_md, truncated = self._apply_token_limit(raw_md, self._max_tokens)

        cleaned_tokens = self.token_count(raw_md)

        # 分段
        segments = None
        if self._segment_size is not None:
            segments = self.segment(raw_md)

        # 压缩比：清理后 / 原始（越小越好）
        compression_ratio = cleaned_tokens / original_tokens if original_tokens > 0 else 0.0

        return {
            "markdown": raw_md,
            "original_tokens": original_tokens,
            "cleaned_tokens": cleaned_tokens,
            "compression_ratio": compression_ratio,
            "truncated": truncated,
            "segments": segments,
        }

    @staticmethod
    def token_count(text: str, model: str = "gpt-4o") -> int:
        """计算 Token 数量"""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(model)
            return len(enc.encode(text))
        except (ImportError, Exception):
            # 粗略估算：1 中文字 ≈ 2 token，1 英文词 ≈ 1.3 token
            cn_chars = len(re.findall(r"[一-鿿]", text))
            en_words = len(re.findall(r"[a-zA-Z]+", text))
            return cn_chars * 2 + int(en_words * 1.3)
