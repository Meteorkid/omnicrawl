"""插件系统 — 可扩展的 Spider 钩子机制。"""

from omnicrawl.plugins.base import Plugin, PluginManager
from omnicrawl.plugins.builtin import (
    LoggingPlugin,
    StatsPlugin,
    FilterPlugin,
    TransformPlugin,
)

__all__ = [
    "Plugin",
    "PluginManager",
    "LoggingPlugin",
    "StatsPlugin",
    "FilterPlugin",
    "TransformPlugin",
]
