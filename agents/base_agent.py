"""
BaseAgent：所有 Agent 的抽象基类
提供公共的日志记录、消息历史管理接口
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger


class BaseAgent(ABC):
    """所有 Agent 的基类。"""

    def __init__(self, name: str, description: str) -> None:
        self.name: str = name
        self.description: str = description
        self._history: List[Dict[str, str]] = []
        logger.debug(f"Agent [{self.name}] 已初始化")

    # ── 子类必须实现 ────────────────────────────────────────────────────────────

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """执行 Agent 的主要任务。"""

    # ── 公共工具方法 ────────────────────────────────────────────────────────────

    def log(self, action: str, detail: str = "") -> None:
        """打印带 Agent 名称前缀的日志。"""
        msg = f"[{self.name}] {action}"
        if detail:
            msg += f": {detail}"
        logger.info(msg)

    def push_message(self, role: str, content: str) -> None:
        """向对话历史追加一条消息。"""
        self._history.append({"role": role, "content": content})

    def clear_history(self) -> None:
        """清空对话历史。"""
        self._history.clear()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
