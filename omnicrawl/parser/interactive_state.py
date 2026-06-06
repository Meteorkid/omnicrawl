"""索引式交互状态 — 面向 Agent 的页面交互元素提取

灵感来自 BrowserAct 的 state 命令，只提取可交互元素并分配索引号。
Agent 用 click(3) 操作，不需要 CSS 选择器，大幅降低 token 消耗。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional
from selectolax.parser import HTMLParser as SelectolaxParser, Node
from omnicrawl.utils.logger import get_logger

logger = get_logger("interactive_state")


# 可交互的 HTML 标签
INTERACTIVE_TAGS = {
    "a", "button", "input", "textarea", "select", "option",
    "details", "summary", "label",
}

# 有内容含义的标签（即使不可交互也值得提取文本）
CONTENT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "td", "th", "li", "span"}


@dataclass
class InteractiveElement:
    """一个可交互元素"""
    index: int                    # 全局索引号
    tag: str                      # HTML 标签名
    element_type: str = ""        # input type, button type 等
    text: str = ""                # 显示文本
    placeholder: str = ""         # placeholder
    href: str = ""                # 链接目标
    id: str = ""                  # 元素 id
    classes: str = ""             # class 属性
    name: str = ""                # name 属性
    value: str = ""               # value 属性
    disabled: bool = False        # 是否禁用
    visible: bool = True          # 是否可见（aria-hidden, display:none 等）
    depth: int = 0                # DOM 深度（用于缩进显示）
    children_text: str = ""       # 子元素文本（用于 button/a 等有内容的元素）
    hash: str = ""                # 元素指纹（用于增量检测）

    def to_state_line(self, delta: bool = False) -> str:
        """转换为 state 格式的单行输出"""
        prefix = "*[" if delta else "["
        indent = "  " * self.depth
        attrs = []
        if self.element_type:
            attrs.append(f"type={self.element_type}")
        if self.placeholder:
            attrs.append(f'placeholder="{self.placeholder}"')
        if self.id:
            attrs.append(f"id={self.id}")
        if self.name:
            attrs.append(f"name={self.name}")

        attr_str = " ".join(attrs)
        text_part = ""
        if self.children_text:
            text_part = f" {self.children_text}"
        elif self.text:
            text_part = f" {self.text}"

        return f"{indent}{prefix}{self.index}]<{self.tag} {attr_str} />{text_part}"


@dataclass
class PageState:
    """页面交互状态快照"""
    url: str = ""
    title: str = ""
    elements: list[InteractiveElement] = field(default_factory=list)
    _hash_map: dict[int, str] = field(default_factory=dict)  # index -> hash

    def to_state_text(self, delta_indices: Optional[set[int]] = None) -> str:
        """转换为 Agent 友好的 state 文本

        Args:
            delta_indices: 变化的元素索引集合，这些元素前加 * 标记
        """
        lines = []
        if self.url:
            lines.append(f"url={self.url}")
        if self.title:
            lines.append(f"title={self.title}")
        lines.append("")

        for elem in self.elements:
            is_delta = delta_indices and elem.index in delta_indices
            lines.append(elem.to_state_line(delta=is_delta))

        return "\n".join(lines)

    def diff(self, other: PageState) -> set[int]:
        """与另一个状态比较，返回变化的元素索引集合

        比较逻辑：
        1. 先按 hash 过滤掉完全相同的元素
        2. 对于 hash 变化的元素，检查是否只是索引变了（位置移动）
        3. 返回真正发生变化的元素在 other 中的索引
        """
        old_hashes = {elem.hash: elem.index for elem in self.elements if elem.hash}
        new_hashes = {elem.hash: elem.index for elem in other.elements if elem.hash}

        changed_indices: set[int] = set()
        for elem in other.elements:
            if not elem.hash:
                # 没有 hash 的元素视为变化
                changed_indices.add(elem.index)
                continue
            if elem.hash not in old_hashes:
                # 新出现的元素
                changed_indices.add(elem.index)

        return changed_indices


class InteractiveStateExtractor:
    """交互状态提取器

    用法:
        extractor = InteractiveStateExtractor()

        # 从 HTML 提取交互状态
        state = extractor.extract(html, url="https://example.com")
        print(state.to_state_text())

        # 增量检测
        new_state = extractor.extract(new_html, url="https://example.com")
        delta = state.diff(new_state)
        print(new_state.to_state_text(delta_indices=delta))
    """

    def __init__(
        self,
        include_content_tags: bool = True,
        max_depth: int = 10,
        include_hidden: bool = False,
    ):
        self._include_content_tags = include_content_tags
        self._max_depth = max_depth
        self._include_hidden = include_hidden

    def extract(self, html: str, url: str = "") -> PageState:
        """从 HTML 提取交互状态"""
        tree = SelectolaxParser(html)
        state = PageState(url=url)

        # 提取 title
        title_node = tree.css_first("title")
        if title_node:
            state.title = title_node.text().strip()

        # 从 body 开始遍历（找不到 body 则从根节点开始）
        root = tree.css_first("body") or tree.root

        counter = [0]  # 用列表包装以便闭包内修改
        self._process_node(root, 0, state, counter)

        logger.info(
            "提取了 %d 个交互元素, url=%s, title=%s",
            len(state.elements), url, state.title,
        )
        return state

    def _process_node(self, node: Node, depth: int, state: PageState, counter: list[int]):
        """递归处理 DOM 节点（深度优先遍历）"""
        if depth > self._max_depth:
            return

        child = node.child
        while child:
            # 跳过文本节点
            if child.tag == "-text":
                child = child.next
                continue

            # 可见性检查（非交互元素也检查，因为子树可能有交互元素）
            visible = self._is_visible(child)
            if not visible and not self._include_hidden:
                child = child.next
                continue

            # 如果当前节点可交互，提取它
            if self._is_interactive(child):
                counter[0] += 1
                elem = self._extract_element(child, counter[0], depth)
                elem.visible = visible
                state.elements.append(elem)
                state._hash_map[elem.index] = elem.hash

            # 无论是否可交互，都递归处理子节点
            # （可交互元素内部也可能有交互元素，如 label 内的 input）
            self._process_node(child, depth + 1, state, counter)

            child = child.next

    def _is_interactive(self, node: Node) -> bool:
        """判断节点是否可交互"""
        tag = node.tag.lower()
        return tag in INTERACTIVE_TAGS

    def _is_visible(self, node: Node) -> bool:
        """判断节点是否可见（粗略检查）"""
        attrs = node.attributes

        # aria-hidden="true"
        if attrs.get("aria-hidden", "").lower() == "true":
            return False

        # style 属性中的 display:none / visibility:hidden
        style = attrs.get("style", "")
        if style:
            style_lower = style.lower().replace(" ", "")
            if "display:none" in style_lower or "display: none" in style_lower:
                return False
            if "visibility:hidden" in style_lower or "visibility: hidden" in style_lower:
                return False

        # input type="hidden"
        if node.tag.lower() == "input":
            input_type = attrs.get("type", "").lower()
            if input_type == "hidden":
                return False

        return True

    def _compute_hash(self, node: Node) -> str:
        """计算元素指纹（用于增量检测）

        基于 tag + 关键属性 + 文本内容生成 hash，
        当元素的任何关键特征变化时 hash 会变。
        """
        parts = [node.tag.lower()]
        attrs = node.attributes

        # 按重要性排序的关键属性
        key_attrs = ["id", "class", "type", "name", "value", "href", "placeholder", "disabled"]
        for attr in key_attrs:
            val = attrs.get(attr, "")
            if val:
                parts.append(f"{attr}={val}")

        # 文本内容（直接子文本，不含后代文本）
        direct_text = self._get_direct_text(node)
        if direct_text:
            parts.append(f"text={direct_text.strip()}")

        raw = "|".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _get_direct_text(self, node: Node) -> str:
        """获取节点的直接子文本（不含后代元素的文本）"""
        parts: list[str] = []
        child = node.child
        while child:
            if child.tag == "-text":
                parts.append(child.text())
            child = child.next
        return "".join(parts)

    def _extract_element(self, node: Node, index: int, depth: int) -> InteractiveElement:
        """从 DOM 节点提取 InteractiveElement"""
        attrs = node.attributes
        tag = node.tag.lower()

        elem = InteractiveElement(
            index=index,
            tag=tag,
            id=attrs.get("id", ""),
            classes=attrs.get("class", ""),
            name=attrs.get("name", ""),
            value=attrs.get("value", ""),
            disabled="disabled" in attrs,
            depth=depth,
            hash=self._compute_hash(node),
        )

        # 根据标签类型提取特定属性
        if tag == "input":
            elem.element_type = attrs.get("type", "text")
            elem.placeholder = attrs.get("placeholder", "")
            elem.text = attrs.get("value", "")
        elif tag == "textarea":
            elem.element_type = "textarea"
            elem.placeholder = attrs.get("placeholder", "")
            elem.text = self._get_direct_text(node)
        elif tag == "select":
            pass  # tag 本身已说明类型，不需要 element_type
        elif tag == "option":
            elem.value = attrs.get("value", "")
            elem.text = node.text().strip()
        elif tag == "a":
            elem.href = attrs.get("href", "")
            elem.children_text = self._collect_children_text(node)
        elif tag in ("button", "summary"):
            elem.element_type = attrs.get("type", "button")
            elem.children_text = self._collect_children_text(node)
        elif tag == "label":
            elem.children_text = self._collect_children_text(node)
        elif tag == "details":
            elem.children_text = self._collect_children_text(node)

        return elem

    def _collect_children_text(self, node: Node) -> str:
        """收集元素所有子文本（递归，包括后代文本节点）"""
        parts: list[str] = []
        child = node.child
        while child:
            if child.tag == "-text":
                parts.append(child.text())
            else:
                parts.append(child.text())
            child = child.next
        return "".join(parts).strip()
