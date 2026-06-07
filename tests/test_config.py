"""配置模块测试"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from omnicrawl.config import (
    apply_config_to_client,
    find_config,
    get_default,
    get_preset,
    load_config,
    merge_cli_config,
)


class TestLoadConfig:
    def test_no_config(self, tmp_path):
        with patch("omnicrawl.config.CONFIG_SEARCH_PATHS", [tmp_path / "nope.toml"]):
            config = load_config()
        assert config == {}

    def test_load_toml(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text("""
[default]
mode = "stealth"
timeout = 15

[presets]
fast = { mode = "http", timeout = 5 }
""")
        config = load_config(config_file)
        assert config["default"]["mode"] == "stealth"
        assert config["presets"]["fast"]["mode"] == "http"

    def test_auto_find(self, tmp_path):
        config_file = tmp_path / "omnicrawl.toml"
        config_file.write_text('[default]\nmode = "auto"\n')
        with patch("omnicrawl.config.CONFIG_SEARCH_PATHS", [config_file]):
            config = load_config()
        assert config["default"]["mode"] == "auto"


class TestGetDefault:
    def test_with_default(self):
        config = {"default": {"mode": "http", "timeout": 10}}
        assert get_default(config) == {"mode": "http", "timeout": 10}

    def test_without_default(self):
        assert get_default({}) == {}


class TestGetPreset:
    def test_existing_preset(self):
        config = {"presets": {"fast": {"mode": "http"}}}
        assert get_preset(config, "fast") == {"mode": "http"}

    def test_missing_preset(self):
        config = {"presets": {"fast": {"mode": "http"}}}
        assert get_preset(config, "slow") == {}

    def test_no_presets(self):
        assert get_preset({}, "fast") == {}


class TestMergeCliConfig:
    def test_cli_overrides_all(self):
        config = {"default": {"mode": "http", "timeout": 10}}
        result = merge_cli_config({"mode": "browser", "timeout": 20}, config)
        assert result["mode"] == "browser"
        assert result["timeout"] == 20

    def test_preset_overrides_default(self):
        config = {
            "default": {"mode": "http"},
            "presets": {"stealth": {"mode": "stealth"}},
        }
        result = merge_cli_config({}, config, preset="stealth")
        assert result["mode"] == "stealth"

    def test_default_fills_gaps(self):
        config = {"default": {"mode": "http", "timeout": 10}}
        result = merge_cli_config({}, config)
        assert result["mode"] == "http"
        assert result["timeout"] == 10

    def test_env_variables(self):
        with patch.dict(os.environ, {"OMNICRAWL_MODE": "camoufox"}):
            result = merge_cli_config({}, {})
        assert result["mode"] == "camoufox"

    def test_env_proxy_pool(self):
        with patch.dict(os.environ, {"OMNICRAWL_PROXY_POOL": "http://a:8080,http://b:8080"}):
            result = merge_cli_config({}, {})
        assert result["proxy_pool"] == ["http://a:8080", "http://b:8080"]

    def test_waf_from_config(self):
        config = {"default": {"waf": {"strategy": "aliyun_waf"}}}
        result = merge_cli_config({}, config)
        assert result["waf"] == "aliyun_waf"

    def test_proxy_pool_from_config(self):
        config = {"default": {"proxy": {"pool": ["http://p1:8080"]}}}
        result = merge_cli_config({}, config)
        assert result["proxy_pool"] == ["http://p1:8080"]


class TestApplyConfigToClient:
    def test_filters_client_keys(self):
        config = {
            "mode": "http",
            "fingerprint": "chrome",
            "timeout": 30,  # CLI 专用，应被过滤
            "format": "json",  # CLI 专用，应被过滤
            "output": "/tmp/out",  # CLI 专用，应被过滤
        }
        result = apply_config_to_client(config)
        assert "mode" in result
        assert "fingerprint" in result
        assert "timeout" not in result
        assert "format" not in result
        assert "output" not in result
