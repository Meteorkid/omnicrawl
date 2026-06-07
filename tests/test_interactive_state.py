"""InteractiveStateExtractor 单元测试"""

import pytest
from omnicrawl.parser.interactive_state import (
    InteractiveStateExtractor, InteractiveElement, PageState,
)


# ===========================================================================
# InteractiveElement
# ===========================================================================

class TestInteractiveElement:
    def test_to_state_line_basic(self):
        elem = InteractiveElement(index=1, tag="button", text="Click")
        line = elem.to_state_line()
        assert "[1]<button" in line
        assert "Click" in line

    def test_to_state_line_with_attrs(self):
        elem = InteractiveElement(
            index=3, tag="input", element_type="text",
            placeholder="Search", id="q", name="query",
        )
        line = elem.to_state_line()
        assert "type=text" in line
        assert 'placeholder="Search"' in line
        assert "id=q" in line
        assert "name=query" in line

    def test_to_state_line_delta(self):
        elem = InteractiveElement(index=5, tag="a", href="/go", depth=1)
        line = elem.to_state_line(delta=True)
        assert line.startswith("  *[5]")  # depth=1 缩进 + delta 前缀

    def test_to_state_line_with_children_text(self):
        elem = InteractiveElement(index=2, tag="a", children_text="Link Text")
        line = elem.to_state_line()
        assert "Link Text" in line

    def test_to_state_line_with_depth(self):
        elem = InteractiveElement(index=1, tag="button", depth=2)
        line = elem.to_state_line()
        assert line.startswith("    [")  # 2 级缩进 = 4 空格


# ===========================================================================
# PageState
# ===========================================================================

class TestPageState:
    def test_to_state_text_basic(self):
        state = PageState(
            url="http://test.com",
            title="Test",
            elements=[
                InteractiveElement(index=1, tag="button", text="OK"),
                InteractiveElement(index=2, tag="a", href="/go", children_text="Link"),
            ],
        )
        text = state.to_state_text()
        assert "url=http://test.com" in text
        assert "title=Test" in text
        assert "[1]<button" in text
        assert "[2]<a" in text

    def test_to_state_text_with_delta(self):
        state = PageState(
            elements=[
                InteractiveElement(index=1, tag="button", text="OK"),
                InteractiveElement(index=2, tag="button", text="Cancel"),
            ],
        )
        text = state.to_state_text(delta_indices={2})
        assert "[1]<button" in text
        assert "*[2]<button" in text

    def test_to_state_text_empty(self):
        state = PageState()
        text = state.to_state_text()
        assert text.strip() == ""

    def test_diff_new_elements(self):
        old = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="abc"),
        ])
        new = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="abc"),
            InteractiveElement(index=2, tag="a", hash="def"),
        ])
        changed = old.diff(new)
        assert 2 in changed
        assert 1 not in changed

    def test_diff_changed_hash(self):
        old = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="abc"),
        ])
        new = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="xyz"),
        ])
        changed = old.diff(new)
        assert 1 in changed

    def test_diff_no_changes(self):
        old = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="abc"),
        ])
        new = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash="abc"),
        ])
        changed = old.diff(new)
        assert len(changed) == 0

    def test_diff_no_hash_treated_as_changed(self):
        old = PageState(elements=[])
        new = PageState(elements=[
            InteractiveElement(index=1, tag="button", hash=""),
        ])
        changed = old.diff(new)
        assert 1 in changed


# ===========================================================================
# InteractiveStateExtractor
# ===========================================================================

class TestExtractor:
    def setup_method(self):
        self.extractor = InteractiveStateExtractor()

    def test_extract_basic(self):
        html = '''
        <html><head><title>Test</title></head>
        <body>
            <button id="btn1">Click</button>
            <a href="/go">Link</a>
            <input type="text" name="q" placeholder="Search">
        </body></html>
        '''
        state = self.extractor.extract(html, url="http://test.com")
        assert state.url == "http://test.com"
        assert state.title == "Test"
        assert len(state.elements) == 3
        assert state.elements[0].tag == "button"
        assert state.elements[1].tag == "a"
        assert state.elements[2].tag == "input"

    def test_extract_indices_start_at_one(self):
        html = '<body><button>A</button><button>B</button></body>'
        state = self.extractor.extract(html)
        assert state.elements[0].index == 1
        assert state.elements[1].index == 2

    def test_extract_input_types(self):
        html = '''
        <body>
            <input type="text" placeholder="Name">
            <input type="email" placeholder="Email">
            <input type="password">
            <input type="hidden" name="token" value="abc">
            <textarea placeholder="Comment">Default text</textarea>
        </body>
        '''
        state = self.extractor.extract(html)
        # hidden input 应被过滤
        assert len(state.elements) == 4
        assert state.elements[0].element_type == "text"
        assert state.elements[1].element_type == "email"
        assert state.elements[2].element_type == "password"
        assert state.elements[3].element_type == "textarea"

    def test_extract_hidden_filtered(self):
        html = '''
        <body>
            <button>Visible</button>
            <div style="display:none"><button>Hidden</button></div>
            <div aria-hidden="true"><button>AriaHidden</button></div>
        </body>
        '''
        state = self.extractor.extract(html)
        assert len(state.elements) == 1
        assert state.elements[0].children_text == "Visible"

    def test_extract_hidden_included_when_flag(self):
        extractor = InteractiveStateExtractor(include_hidden=True)
        html = '''
        <body>
            <button>Visible</button>
            <div style="display:none"><button>Hidden</button></div>
        </body>
        '''
        state = extractor.extract(html)
        assert len(state.elements) == 2

    def test_extract_select_and_options(self):
        html = '''
        <body>
            <select name="color">
                <option value="r">Red</option>
                <option value="g">Green</option>
            </select>
        </body>
        '''
        state = self.extractor.extract(html)
        # select + 2 options = 3
        assert len(state.elements) == 3
        assert state.elements[0].tag == "select"
        assert state.elements[1].tag == "option"
        assert state.elements[1].text == "Red"

    def test_extract_link_with_href(self):
        html = '<body><a href="/about" id="about-link">About Us</a></body>'
        state = self.extractor.extract(html)
        assert state.elements[0].href == "/about"
        assert state.elements[0].children_text == "About Us"

    def test_extract_button_with_type(self):
        html = '<body><button type="submit">Send</button></body>'
        state = self.extractor.extract(html)
        assert state.elements[0].element_type == "submit"
        assert state.elements[0].children_text == "Send"

    def test_extract_label(self):
        html = '<body><label for="email">Email Address</label></body>'
        state = self.extractor.extract(html)
        assert state.elements[0].tag == "label"
        assert state.elements[0].children_text == "Email Address"

    def test_extract_disabled_element(self):
        html = '<body><button disabled>Can\'t click</button></body>'
        state = self.extractor.extract(html)
        assert state.elements[0].disabled is True

    def test_extract_empty_html(self):
        state = self.extractor.extract("")
        assert len(state.elements) == 0

    def test_extract_no_body(self):
        html = '<button>Outside body</button>'
        state = self.extractor.extract(html)
        # 应从根节点开始遍历
        assert len(state.elements) == 1

    def test_extract_max_depth(self):
        extractor = InteractiveStateExtractor(max_depth=2)
        html = '''
        <body>
            <div><div><div><div><button>Deep</button></div></div></div></div>
        </body>
        '''
        state = extractor.extract(html)
        # 超过 max_depth 的 button 不应被提取
        assert len(state.elements) == 0

    def test_compute_hash_consistency(self):
        html = '<body><button id="btn">Click</button></body>'
        state1 = self.extractor.extract(html)
        state2 = self.extractor.extract(html)
        assert state1.elements[0].hash == state2.elements[0].hash

    def test_compute_hash_changes_on_attr(self):
        html1 = '<body><button id="btn1">Click</button></body>'
        html2 = '<body><button id="btn2">Click</button></body>'
        state1 = self.extractor.extract(html1)
        state2 = self.extractor.extract(html2)
        assert state1.elements[0].hash != state2.elements[0].hash

    def test_extract_complex_page(self):
        html = '''
        <html>
        <head><title>Complex</title></head>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/about">About</a>
            </nav>
            <main>
                <h1>Welcome</h1>
                <form>
                    <input type="text" name="username" placeholder="Username">
                    <input type="password" name="password" placeholder="Password">
                    <button type="submit">Login</button>
                </form>
                <select name="lang">
                    <option value="en">English</option>
                    <option value="zh">中文</option>
                </select>
            </main>
        </body>
        </html>
        '''
        state = self.extractor.extract(html)
        # 2 links + 2 inputs + 1 button + 1 select + 2 options = 8
        assert len(state.elements) == 8
        assert state.title == "Complex"

    def test_visibility_hidden_style(self):
        html = '''
        <body>
            <button style="visibility:hidden">Invisible</button>
            <button style="opacity:0">Transparent</button>
            <button>Visible</button>
        </body>
        '''
        state = self.extractor.extract(html)
        assert len(state.elements) == 1
        assert state.elements[0].children_text == "Visible"
