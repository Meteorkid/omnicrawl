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

    用法:
        converter = MarkdownConverter()
        md = converter.convert(html)
        print(converter.token_count(md))
    """

    def __init__(
        self,
        remove_tags: Optional[list[str]] = None,
        remove_patterns: Optional[list[str]] = None,
        strip_links: bool = False,
        strip_images: bool = False,
    ):
        self._remove_tags = remove_tags or REMOVE_TAGS
        self._remove_patterns = remove_patterns or REMOVE_PATTERNS
        self._strip_links = strip_links
        self._strip_images = strip_images

    def convert(self, html: str) -> str:
        """将 HTML 转换为干净的 Markdown"""
        try:
            from selectolax.parser import HTMLParser as SelectolaxParser
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
