"""CLI 测试 — 全 mock，不依赖网络"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from omnicrawl.cli import app, _parse_headers, _parse_mode, _url_to_filename
from omnicrawl.fetchers.base import FetchMode, FetchResult

runner = CliRunner()


def make_result(
    url="http://example.com",
    status=200,
    html="<h1>Test</h1>",
    markdown="# Test",
    text="Test",
    blocked=False,
    mode=FetchMode.HTTP,
):
    r = FetchResult(
        url=url,
        status_code=status,
        html=html,
        headers={"content-type": "text/html"},
        cookies={},
        mode_used=mode,
        elapsed=0.5,
        blocked=blocked,
    )
    r.markdown = markdown
    r.text = text
    return r


# ── version ──────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "omnicrawl" in result.output
        assert "0.2.0" in result.output


# ── fetch ────────────────────────────────────────────────────────────────


class TestFetch:
    def test_fetch_markdown_format(self):
        mock_result = make_result(markdown="# Hello World")
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(app, ["fetch", "http://example.com"])

        assert result.exit_code == 0
        assert "Hello World" in result.output

    def test_fetch_json_format(self):
        mock_result = make_result()
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(app, ["fetch", "http://example.com", "-f", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status_code"] == 200
        assert data["mode_used"] == "http"

    def test_fetch_text_format(self):
        mock_result = make_result(text="Plain text content")
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(app, ["fetch", "http://example.com", "-f", "text"])

        assert result.exit_code == 0
        assert "Plain text content" in result.output

    def test_fetch_html_format(self):
        mock_result = make_result(html="<h1>Raw HTML</h1>")
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(app, ["fetch", "http://example.com", "-f", "html"])

        assert result.exit_code == 0
        assert "<h1>Raw HTML</h1>" in result.output

    def test_fetch_with_mode(self):
        mock_result = make_result(mode=FetchMode.BROWSER)
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(app, ["fetch", "http://example.com", "-m", "browser"])

        assert result.exit_code == 0

    def test_fetch_with_output_file(self, tmp_path):
        mock_result = make_result(markdown="# Saved")
        output_file = tmp_path / "output.md"
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result
            result = runner.invoke(
                app, ["fetch", "http://example.com", "-o", str(output_file)]
            )

        assert result.exit_code == 0
        assert "已保存到" in result.output
        assert output_file.read_text() == "# Saved"

    def test_fetch_missing_url(self):
        result = runner.invoke(app, ["fetch"])
        assert result.exit_code != 0

    def test_fetch_invalid_mode(self):
        result = runner.invoke(app, ["fetch", "http://example.com", "-m", "invalid"])
        assert result.exit_code != 0


# ── batch ────────────────────────────────────────────────────────────────


class TestBatch:
    def test_batch_success(self):
        mock_results = ([make_result(url="http://a.com"), make_result(url="http://b.com")], [])
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results
            result = runner.invoke(app, ["batch", "http://a.com", "http://b.com"])

        assert result.exit_code == 0
        assert "成功: 2" in result.output
        assert "失败: 0" in result.output

    def test_batch_with_errors(self):
        mock_results = (
            [make_result(url="http://ok.com")],
            [("http://fail.com", Exception("timeout"))],
        )
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results
            result = runner.invoke(app, ["batch", "http://ok.com", "http://fail.com"])

        assert result.exit_code == 0
        assert "成功: 1" in result.output
        assert "失败: 1" in result.output
        assert "timeout" in result.output

    def test_batch_output_dir(self, tmp_path):
        mock_results = (
            [make_result(url="http://a.com", markdown="# A"), make_result(url="http://b.com", markdown="# B")],
            [],
        )
        out_dir = tmp_path / "results"
        with patch("omnicrawl.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results
            result = runner.invoke(
                app, ["batch", "http://a.com", "http://b.com", "-d", str(out_dir)]
            )

        assert result.exit_code == 0
        assert out_dir.exists()
        files = list(out_dir.glob("*.md"))
        assert len(files) == 2

    def test_batch_no_urls(self):
        result = runner.invoke(app, ["batch"])
        assert result.exit_code != 0


# ── convert ──────────────────────────────────────────────────────────────


class TestConvert:
    def test_convert_markdown(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Title</h1><p>Content</p>")
        result = runner.invoke(app, ["convert", str(html_file)])
        assert result.exit_code == 0
        assert "Title" in result.output

    def test_convert_json_format(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Title</h1><p>Content</p>")
        result = runner.invoke(app, ["convert", str(html_file), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "markdown" in data
        assert "compression_ratio" in data

    def test_convert_compact(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text(
            "<h1>Title</h1>"
            '<nav><a href="/">Home</a></nav>'
            "<p>Content</p>"
            "<script>alert('x')</script>"
        )
        result = runner.invoke(app, ["convert", str(html_file), "--compact"])
        assert result.exit_code == 0
        assert "alert" not in result.output
        assert "Title" in result.output

    def test_convert_with_output(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Save Me</h1>")
        output_file = tmp_path / "out.md"
        result = runner.invoke(
            app, ["convert", str(html_file), "-o", str(output_file)]
        )
        assert result.exit_code == 0
        assert "Save Me" in output_file.read_text()

    def test_convert_nonexistent_file(self):
        result = runner.invoke(app, ["convert", "/nonexistent.html"])
        assert result.exit_code != 0

    def test_convert_max_tokens(self, tmp_path):
        # 创建一个有多个段落的 HTML
        paragraphs = "".join(f"<p>Paragraph {i} with some content.</p>" for i in range(50))
        html_file = tmp_path / "long.html"
        html_file.write_text(f"<html><body>{paragraphs}</body></html>")
        result = runner.invoke(
            app, ["convert", str(html_file), "-f", "json", "--max-tokens", "20"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["truncated"] is True

    def test_convert_strip_links(self, tmp_path):
        html_file = tmp_path / "links.html"
        html_file.write_text('<p>Text <a href="http://x.com">link</a> more</p>')
        result = runner.invoke(app, ["convert", str(html_file), "--strip-links"])
        assert result.exit_code == 0
        assert "http://x.com" not in result.output

    def test_convert_strip_images(self, tmp_path):
        html_file = tmp_path / "img.html"
        html_file.write_text('<p>Before</p><img src="pic.jpg"><p>After</p>')
        result = runner.invoke(app, ["convert", str(html_file), "--strip-images"])
        assert result.exit_code == 0
        assert "pic.jpg" not in result.output


# ── helper 函数 ──────────────────────────────────────────────────────────


class TestHelpers:
    def test_parse_headers_valid(self):
        headers = _parse_headers(["Content-Type:application/json", "Authorization: Bearer token"])
        assert headers == {"Content-Type": "application/json", "Authorization": "Bearer token"}

    def test_parse_headers_empty(self):
        assert _parse_headers([]) == {}

    def test_parse_headers_invalid(self):
        with pytest.raises(Exception):
            _parse_headers(["NoColonHere"])

    def test_parse_mode_valid(self):
        assert _parse_mode("http") == FetchMode.HTTP
        assert _parse_mode("browser") == FetchMode.BROWSER
        assert _parse_mode("camoufox") == FetchMode.CAMOUFOX
        assert _parse_mode("stealth") == FetchMode.STEALTH
        assert _parse_mode("auto") == FetchMode.AUTO

    def test_parse_mode_invalid(self):
        with pytest.raises(Exception):
            _parse_mode("nonexistent")

    def test_url_to_filename(self):
        assert _url_to_filename("http://example.com/path", 0) == "000_example.com_path.md"
        assert _url_to_filename("https://a.com", 99) == "099_a.com.md"

    def test_url_to_filename_long(self):
        long_url = "http://example.com/" + "a" * 200
        filename = _url_to_filename(long_url, 0)
        assert len(filename) <= 110  # prefix + truncated name + extension


# ── config ───────────────────────────────────────────────────────────────


class TestConfig:
    def test_config_show_no_file(self):
        with patch("omnicrawl.config.find_config", return_value=None):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "未找到配置文件" in result.output

    def test_config_show_with_file(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text('[default]\nmode = "http"\n[presets]\nfast = { mode = "http" }\n')
        with patch("omnicrawl.config.find_config", return_value=config_file):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "http" in result.output
        assert "fast" in result.output

    def test_config_show_preset(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text('[presets]\nfast = { mode = "http", timeout = 5 }\n')
        with patch("omnicrawl.config.find_config", return_value=config_file):
            result = runner.invoke(app, ["config", "show", "--preset", "fast"])
        assert result.exit_code == 0
        assert "fast" in result.output

    def test_config_show_missing_preset(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text('[presets]\nfast = { mode = "http" }\n')
        with patch("omnicrawl.config.find_config", return_value=config_file):
            result = runner.invoke(app, ["config", "show", "--preset", "nonexistent"])
        assert result.exit_code == 0
        assert "不存在" in result.output

    def test_config_path_with_file(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text("")
        with patch("omnicrawl.config.find_config", return_value=config_file):
            result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert str(config_file) in result.output

    def test_config_path_no_file(self):
        with patch("omnicrawl.config.find_config", return_value=None):
            result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "未找到" in result.output
