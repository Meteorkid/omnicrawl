"""TLS 指纹管理 — 封装 curl_cffi 的 impersonate 能力"""

from __future__ import annotations

import random
from typing import Optional, Union
from omnicrawl.utils.logger import get_logger

logger = get_logger("fingerprint")

# curl_cffi 支持的浏览器指纹（按类型分组）
BROWSER_PROFILES = {
    "chrome": [
        "chrome99", "chrome100", "chrome101", "chrome104", "chrome107",
        "chrome110", "chrome116", "chrome119", "chrome120", "chrome123",
        "chrome124", "chrome131", "chrome133a", "chrome136", "chrome142",
        "chrome145", "chrome146",
    ],
    "safari": [
        "safari153", "safari155", "safari170", "safari180", "safari184",
        "safari260", "safari2601",
    ],
    "firefox": [
        "firefox133", "firefox135", "firefox144", "firefox147",
    ],
    "edge": ["edge99", "edge101"],
    "safari_ios": [
        "safari172_ios", "safari180_ios", "safari184_ios", "safari260_ios",
    ],
    "chrome_android": ["chrome99_android", "chrome131_android"],
    "tor": ["tor145"],
}


class TLSFingerprint:
    """TLS 指纹管理器

    用法:
        fp = TLSFingerprint()
        fp.set("chrome")          # 使用最新 Chrome
        fp.set("chrome136")       # 使用特定版本
        fp.random()               # 随机选择
        fp.rotate(["chrome", "safari", "firefox"])  # 设置轮换列表
        fingerprint = fp.get()    # 获取当前指纹
    """

    def __init__(self, default: str = "chrome"):
        self._current: Optional[str] = None
        self._rotation_list: list[str] = []
        self._rotation_index: int = 0
        self.set(default)

    def set(self, fingerprint: str) -> "TLSFingerprint":
        """设置固定指纹"""
        self._current = fingerprint
        self._rotation_list = []
        logger.debug(f"TLS 指纹设置为: {fingerprint}")
        return self

    def random(self) -> str:
        """随机选择一个指纹"""
        all_fps = []
        for versions in BROWSER_PROFILES.values():
            all_fps.extend(versions)
        self._current = random.choice(all_fps)
        logger.debug(f"随机 TLS 指纹: {self._current}")
        return self._current

    def rotate(self, fingerprints: list[str]) -> "TLSFingerprint":
        """设置轮换列表"""
        self._rotation_list = list(fingerprints)
        self._rotation_index = 0
        if self._rotation_list:
            self._current = self._rotation_list[0]
        logger.debug(f"TLS 指纹轮换列表: {fingerprints}")
        return self

    def next(self) -> str:
        """轮换到下一个指纹"""
        if not self._rotation_list:
            return self._current or "chrome"
        self._rotation_index = (self._rotation_index + 1) % len(self._rotation_list)
        self._current = self._rotation_list[self._rotation_index]
        logger.debug(f"轮换 TLS 指纹: {self._current}")
        return self._current

    def get(self) -> str:
        """获取当前指纹"""
        return self._current or "chrome"

    @staticmethod
    def list_available() -> dict[str, list[str]]:
        """列出所有可用指纹"""
        return dict(BROWSER_PROFILES)
