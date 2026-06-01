"""日志工具"""

import logging
import os

def get_logger(name: str) -> logging.Logger:
    """获取模块日志器，支持 OMNICRAWL_LOG_LEVEL 环境变量"""
    logger = logging.getLogger(f"omnicrawl.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
        level = os.environ.get("OMNICRAWL_LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
    return logger
