"""日志工具 - 基于 Rich 的彩色控制台输出"""

import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def _get_log_level() -> int:
    try:
        from config import LOG_LEVEL
        return getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    except ImportError:
        return logging.INFO


logging.basicConfig(
    level=_get_log_level(),
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_path=False,
        )
    ],
)

logger = logging.getLogger("multi_agent")
