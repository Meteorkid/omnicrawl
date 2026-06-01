"""解析器测试"""

import pytest
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.parser.html_parser import HTMLParser


class TestMarkdownConverter:
    def test_basic_conversion(self):
        converter = MarkdownConverter()
        md = converter.convert("<h1>Title</h1><p>Hello World</p>")
        assert "Title" in md
        assert "Hello World" in md

    def test_removes_script_tags(self):
        converter = MarkdownConverter()
        md = converter.convert("<p>Text</p><script>alert('xss')</script>")
        assert "alert" not in md
        assert "Text" in md

    def test_removes_style_tags(self):
        converter = MarkdownConverter()
        md = converter.convert("<p>Text</p><style>body{color:red}</style>")
        assert "color:red" not in md
        assert "Text" in md

    def test_removes_nav_footer(self):
        converter = MarkdownConverter()
        md = converter.convert("<nav>Menu</nav><main>Content</main><footer>Bottom</footer>")
        assert "Menu" not in md
        assert "Bottom" not in md
        assert "Content" in md

    def test_strip_images(self):
        converter = MarkdownConverter(strip_images=True)
        md = converter.convert('<p>Text</p><img src="photo.jpg"/>')
        assert "photo.jpg" not in md

    def test_strip_links(self):
        converter = MarkdownConverter(strip_links=True)
        md = converter.convert('<p><a href="/link">Click</a></p>')
        assert "/link" not in md

    def test_strip_images_and_links_together(self):
        converter = MarkdownConverter(strip_images=True, strip_links=True)
        md = converter.convert('<p><a href="/link">Click</a></p><img src="photo.jpg"/>')
        assert "/link" not in md
        assert "photo.jpg" not in md

    def test_token_count(self):
        count = MarkdownConverter.token_count("Hello World")
        assert count > 0
        assert count < 10

    def test_empty_html(self):
        converter = MarkdownConverter()
        md = converter.convert("")
        assert md == ""


class TestHTMLParser:
    def test_css_first_text(self):
        parser = HTMLParser("<h1>Title</h1><p>Paragraph</p>")
        assert parser.css_first("h1::text") == "Title"

    def test_css_first_attr(self):
        parser = HTMLParser('<a href="/link">Click</a>')
        assert parser.css_first("a::attr(href)") == "/link"

    def test_css_first_default(self):
        parser = HTMLParser("<p>Text</p>")
        assert parser.css_first("h1::text", default="N/A") == "N/A"

    def test_css_all_text(self):
        parser = HTMLParser("<p>A</p><p>B</p><p>C</p>")
        results = parser.css_all("p::text")
        assert results == ["A", "B", "C"]

    def test_css_all_attr(self):
        parser = HTMLParser('<a href="/a">A</a><a href="/b">B</a>')
        results = parser.css_all("a::attr(href)")
        assert results == ["/a", "/b"]

    def test_title(self):
        parser = HTMLParser("<html><head><title>Page Title</title></head><body></body></html>")
        assert parser.title() == "Page Title"

    def test_links(self):
        parser = HTMLParser('<a href="/a">A</a><a href="/b">B</a>')
        assert parser.links() == ["/a", "/b"]

    def test_text(self):
        parser = HTMLParser("<p>Hello</p><p>World</p>")
        assert "Hello" in parser.text()
        assert "World" in parser.text()

    def test_meta(self):
        parser = HTMLParser('<meta name="description" content="A test page">')
        assert parser.meta("description") == "A test page"

    def test_meta_property(self):
        parser = HTMLParser('<meta property="og:title" content="OG Title">')
        assert parser.meta("og:title") == "OG Title"
