"""后端集中日志配置。

这个模块使用 Python 标准库 logging 配置应用日志。start.py 会把 uvicorn 进程的标准输出也写入
storage/logs/slides-reader.log；这里负责让后端业务 logger、uvicorn logger 使用同一个轮转文件。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from os import getenv
from pathlib import Path

from config import STORAGE_DIR


LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def resolve_log_dir() -> Path:
    """返回后端日志目录。

    start.py 会设置 SLIDES_READER_LOG_DIR；如果用户直接 uvicorn main:app，则退回到 storage/logs。
    """

    return Path(getenv("SLIDES_READER_LOG_DIR", str(STORAGE_DIR / "logs"))).resolve()


def configure_backend_logging() -> Path:
    """配置后端业务日志和 uvicorn 日志，返回主日志文件路径。"""

    log_dir = resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "slides-reader.log"

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 避免 uvicorn reload 或测试反复 import 时重复挂同一个文件 handler。
    existing_file_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", None) == str(log_path)
    ]
    if not existing_file_handlers:
        root_logger.addHandler(file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate = True

    logging.getLogger(__name__).info("Backend logging configured: %s", log_path)
    return log_path

