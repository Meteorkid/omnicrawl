"""TLS 指纹管理器测试"""

import pytest
from omnicrawl.fingerprint.tls import TLSFingerprint, BROWSER_PROFILES


class TestTLSFingerprint:
    def test_default_fingerprint(self):
        fp = TLSFingerprint()
        assert fp.get() == "chrome"

    def test_set_fingerprint(self):
        fp = TLSFingerprint()
        fp.set("safari180")
        assert fp.get() == "safari180"

    def test_rotate(self):
        fp = TLSFingerprint()
        fp.rotate(["chrome136", "safari180", "firefox135"])
        assert fp.get() == "chrome136"
        assert fp.next() == "safari180"
        assert fp.next() == "firefox135"
        assert fp.next() == "chrome136"  # 循环

    def test_random_returns_valid(self):
        fp = TLSFingerprint()
        result = fp.random()
        # 随机结果应该在已知指纹列表中
        all_fps = []
        for versions in BROWSER_PROFILES.values():
            all_fps.extend(versions)
        assert result in all_fps

    def test_list_available(self):
        profiles = TLSFingerprint.list_available()
        assert "chrome" in profiles
        assert "safari" in profiles
        assert "firefox" in profiles
        assert len(profiles["chrome"]) > 5

    def test_rotate_empty_list(self):
        fp = TLSFingerprint()
        fp.rotate([])
        # 空列表时 next 应该返回当前值
        assert fp.next() == "chrome"
