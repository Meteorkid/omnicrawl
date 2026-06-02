"""HTML 解析器 — CSS 选择器 + XPath"""

from __future__ import annotations

import re
from typing import Optional, Union
from selectolax.parser import HTMLParser as SelectolaxParser, Node


class HTMLParser:
    """高性能 HTML 解析器

    用法:
        parser = HTMLParser(html)
        titles = parser.css_all("h1::text")
        links = parser.css_all("a::attr(href)")
        first = parser.css_first(".content p")
    """

    def __init__(self, html: str):
        self._tree = SelectolaxParser(html)

    def css_first(self, selector: str, default: str = "") -> str:
        """CSS 选择器获取第一个匹配元素的文本"""
        text = selector.endswith("::text")
        attr_match = re.search(r"::attr\((\w+)\)", selector)
        clean_selector = re.sub(r"::(text|attr\(\w+\))", "", selector)

        node = self._tree.css_first(clean_selector)
        if not node:
            return default

        if text:
            return node.text(strip=True)
        elif attr_match:
            return node.attributes.get(attr_match.group(1), default)
        return node.html

    def css_all(self, selector: str) -> list[str]:
        """CSS 选择器获取所有匹配元素"""
        text = selector.endswith("::text")
        attr_match = re.search(r"::attr\((\w+)\)", selector)
        clean_selector = re.sub(r"::(text|attr\(\w+\))", "", selector)

        results = []
        for node in self._tree.css(clean_selector):
            if text:
                results.append(node.text(strip=True))
            elif attr_match:
                results.append(node.attributes.get(attr_match.group(1), ""))
            else:
                results.append(node.html)
        return results

    def xpath_first(self, xpath: str) -> Optional[str]:
        """XPath 获取第一个匹配（仅支持基本模式）

        支持: //tag[@attr="value"]
        不支持时抛出 NotImplementedError。
        """
        match = re.match(r"//(\w+)\[@(\w+)=[\"']([^\"']+)[\"']\]", xpath)
        if match:
            tag, attr, value = match.groups()
            return self.css_first(f'{tag}[{attr}="{value}"]::text')
        raise NotImplementedError(
            f"XPath 模式 '{xpath}' 不受支持。仅支持 '//tag[@attr=\"value\"]' 格式。"
            f"请使用 css_first() 或 css_all() 代替。"
        )

    def text(self) -> str:
        """获取纯文本"""
        return self._tree.body.text(strip=True) if self._tree.body else ""

    def title(self) -> str:
        """获取页面标题"""
        return self.css_first("title::text")

    def links(self) -> list[str]:
        """获取所有链接"""
        return self.css_all("a::attr(href)")

    def meta(self, name: str) -> str:
        """获取 meta 标签内容"""
        return (
            self.css_first(f'meta[name="{name}"]::attr(content)')
            or self.css_first(f'meta[property="{name}"]::attr(content)')
        )
