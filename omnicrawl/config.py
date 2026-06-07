"""OmniCrawl 配置文件支持

支持 TOML 格式的配置文件，按以下优先级加载（高→低）：
1. 命令行参数
2. 环境变量 OMNICRAWL_*
3. 项目目录 ./omnicrawl.toml
4. 用户目录 ~/.omnicrawl.toml

配置文件示例:
    [default]
    mode = "auto"
    format = "markdown"
    fingerprint = "chrome"
    timeout = 30
    max_retries = 2

    [default.waf]
    strategy = "aliyun_waf"

    [default.proxy]
    pool = ["http://proxy1:8080", "http://proxy2:8080"]

    [presets]
    fast = { mode = "http", timeout = 10 }
    stealth = { mode = "stealth", fingerprint = "firefox", max_retries = 3 }
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional


# 配置文件搜索路径
CONFIG_SEARCH_PATHS = [
    Path.cwd() / "omnicrawl.toml",
    Path.home() / ".omnicrawl.toml",
]


def find_config() -> Optional[Path]:
    """查找配置文件（项目目录优先）"""
    for p in CONFIG_SEARCH_PATHS:
        if p.exists():
            return p
    return None


def load_config(path: Optional[Path] = None) -> dict[str, Any]:
    """加载配置文件

    Args:
        path: 配置文件路径，None 则自动查找

    Returns:
        配置字典，空字典表示无配置
    """
    if path is None:
        path = find_config()
    if path is None or not path.exists():
        return {}

    try:
        import tomllib
    except ImportError:
        # Python < 3.11
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def get_default(config: dict[str, Any]) -> dict[str, Any]:
    """从配置中提取 [default] 段"""
    return config.get("default", {})


def get_preset(config: dict[str, Any], name: str) -> dict[str, Any]:
    """从配置中提取指定预设

    Args:
        config: 完整配置
        name: 预设名称

    Returns:
        预设配置字典，空字典表示无此预设
    """
    presets = config.get("presets", {})
    return presets.get(name, {})


def merge_cli_config(
    cli_args: dict[str, Any],
    config: dict[str, Any],
    preset: Optional[str] = None,
) -> dict[str, Any]:
    """合并 CLI 参数和配置文件

    优先级：CLI 参数 > 预设 > [default] > 环境变量

    Args:
        cli_args: CLI 传入的参数（已过滤 None 值）
        config: 配置文件内容
        preset: 预设名称

    Returns:
        合并后的配置字典
    """
    result: dict[str, Any] = {}

    # 1. 从环境变量开始
    env_map = {
        "OMNICRAWL_MODE": "mode",
        "OMNICRAWL_FORMAT": "format",
        "OMNICRAWL_FINGERPRINT": "fingerprint",
        "OMNICRAWL_TIMEOUT": "timeout",
        "OMNICRAWL_WAF": "waf",
        "OMNICRAWL_PROXY_POOL": "proxy_pool",
        "OMNICRAWL_MAX_RETRIES": "max_retries",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if config_key == "proxy_pool":
                result[config_key] = [p.strip() for p in val.split(",")]
            elif config_key in ("timeout",):
                result[config_key] = float(val)
            elif config_key in ("max_retries",):
                result[config_key] = int(val)
            else:
                result[config_key] = val

    # 2. 从 [default] 段
    defaults = get_default(config)
    for k, v in defaults.items():
        if k == "waf" and isinstance(v, dict):
            result["waf"] = v.get("strategy", v)
        elif k == "proxy" and isinstance(v, dict):
            result["proxy_pool"] = v.get("pool", [])
        else:
            result.setdefault(k, v)

    # 3. 从预设
    if preset:
        preset_config = get_preset(config, preset)
        for k, v in preset_config.items():
            result[k] = v

    # 4. CLI 参数覆盖
    for k, v in cli_args.items():
        if v is not None:
            result[k] = v

    return result


def apply_config_to_client(config: dict[str, Any]) -> dict[str, Any]:
    """将配置转换为 OmniClient 构造参数

    过滤掉 CLI 专用参数（format, output 等），只保留 client 参数。

    Args:
        config: 合并后的配置

    Returns:
        OmniClient kwargs
    """
    client_keys = {
        "mode", "fingerprint", "proxy_pool", "waf",
        "min_delay", "max_retries", "max_concurrent",
        "auto_fallback", "session_manager", "captcha_api_key",
    }
    return {k: v for k, v in config.items() if k in client_keys}


def get_storage_config(config: dict[str, Any]) -> dict[str, Any]:
    """从配置中提取 [storage] 段

    Args:
        config: 完整配置

    Returns:
        存储配置字典，默认 {"backend": "memory"}
    """
    return config.get("storage", {"backend": "memory"})


def create_store_from_config(config: dict[str, Any]):
    """根据配置创建 StateStore 实例

    Args:
        config: 完整配置或 storage 子配置

    Returns:
        StateStore 实例
    """
    from omnicrawl.storage import create_store

    storage = config.get("storage", config) if "backend" not in config else config
    backend = storage.get("backend", "memory")

    kwargs = {}
    if backend == "redis":
        if "redis_url" in storage:
            kwargs["url"] = storage["redis_url"]
        if "key_prefix" in storage:
            kwargs["prefix"] = storage["key_prefix"]

    return create_store(backend, **kwargs)
