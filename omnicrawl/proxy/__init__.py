"""代理管理模块"""

from omnicrawl.proxy.rotator import ProxyRotator
from omnicrawl.proxy.validator import ProxyValidator, ProxyStatus

__all__ = ["ProxyRotator", "ProxyValidator", "ProxyStatus"]
