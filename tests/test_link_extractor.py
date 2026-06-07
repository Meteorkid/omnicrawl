"""LinkExtractor 链接提取测试"""

from __future__ import annotations

import pytest

from omnicrawl.spider.link_extractor import LinkExtractor


class TestLinkExtractor:
    def test_extract_basic(self):
        html = '<a href="/page1">Link1</a><a href="/page2">Link2</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 2
        assert "https://example.com/page1" in links
        assert "https://example.com/page2" in links

    def test_extract_relative_urls(self):
        html = '<a href="../path/page">Link</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com/dir/current")
        assert any("path/page" in l for l in links)

    def test_extract_same_domain_filter(self):
        html = '''
        <a href="/local">Local</a>
        <a href="https://other.com/external">External</a>
        '''
        extractor = LinkExtractor(same_domain=True)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1
        assert "https://example.com/local" in links

    def test_extract_allow_patterns(self):
        html = '''
        <a href="/article/123">Article</a>
        <a href="/about">About</a>
        <a href="/article/456">Article2</a>
        '''
        extractor = LinkExtractor(allow_patterns=[r"/article/\d+"], same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 2

    def test_extract_deny_patterns(self):
        html = '''
        <a href="/page1">Page</a>
        <a href="/login">Login</a>
        <a href="/logout">Logout</a>
        '''
        extractor = LinkExtractor(deny_patterns=[r"/login", r"/logout"], same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1
        assert "https://example.com/page1" in links

    def test_extract_skip_fragments(self):
        html = '<a href="/page#section">Link</a>'
        extractor = LinkExtractor(strip_fragment=True, same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert links == ["https://example.com/page"]

    def test_extract_strip_query(self):
        html = '<a href="/page?ref=home">Link</a>'
        extractor = LinkExtractor(strip_query=True, same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert links == ["https://example.com/page"]

    def test_extract_skip_javascript(self):
        html = '<a href="javascript:void(0)">JS</a><a href="/real">Real</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1

    def test_extract_skip_mailto(self):
        html = '<a href="mailto:test@example.com">Email</a><a href="/page">Page</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1

    def test_extract_skip_static_resources(self):
        html = '''
        <a href="/image.png">PNG</a>
        <a href="/style.css">CSS</a>
        <a href="/page">Page</a>
        '''
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1

    def test_extract_dedup(self):
        html = '<a href="/page">A</a><a href="/page">B</a><a href="/page">C</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html, base_url="https://example.com")
        assert len(links) == 1

    def test_extract_max_links(self):
        links_html = "".join(f'<a href="/page{i}">Link{i}</a>' for i in range(100))
        extractor = LinkExtractor(same_domain=False, max_links=5)
        links = extractor.extract(links_html, base_url="https://example.com")
        assert len(links) == 5

    def test_extract_empty_html(self):
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract("", base_url="https://example.com")
        assert links == []

    def test_extract_no_base_url(self):
        html = '<a href="https://example.com/page">Link</a>'
        extractor = LinkExtractor(same_domain=False)
        links = extractor.extract(html)
        assert len(links) == 1
