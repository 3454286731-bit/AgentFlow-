"""
日志配置。

为什么单独放一个模块：日志格式要在应用启动时统一设定一次，
各模块只负责拿 logger 打日志，不关心格式与输出目标。
后续要接日志采集系统时，改这一个文件就够了。
"""

from __future__ import annotations

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-26s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """初始化根日志器。重复调用只会重置配置，不会叠加重复的处理器。"""
    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level_name)

    # 第三方库默认太吵，压到 WARNING
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
