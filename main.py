#!/usr/bin/env python3
"""
Multi-Agent Code Generation System
====================================
入口文件。

用法：
    # 交互模式（命令行提示输入）
    python main.py

    # 直接传入需求
    python main.py "用 Python 实现二分查找，要求有完善的错误处理和测试"
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.prompt import Prompt

from agents.orchestrator import Orchestrator
from utils.logger import logger

console = Console()

# ── 内置示例需求（无输入时使用）──────────────────────────────────────────────
_DEFAULT_REQUIREMENT = (
    "Create a Python module implementing a thread-safe LRU Cache with the following features: "
    "1) get(key) and put(key, value) methods with O(1) complexity; "
    "2) configurable max capacity; "
    "3) optional TTL (time-to-live) per entry; "
    "4) proper error handling; "
    "5) comprehensive docstrings and type hints."
)


# ── 主函数 ─────────────────────────────────────────────────────────────────────


def main() -> int:
    _print_banner()

    # 获取需求
    if len(sys.argv) > 1:
        requirement = " ".join(sys.argv[1:]).strip()
    else:
        console.print("[dim]输入您的编程需求（直接回车使用内置示例）：[/dim]\n")
        requirement = Prompt.ask("  需求", default="").strip()
        if not requirement:
            requirement = _DEFAULT_REQUIREMENT
            console.print(f"\n[dim]使用内置示例需求：{requirement[:80]}…[/dim]\n")

    # 执行 Pipeline
    orchestrator = Orchestrator()
    try:
        state = orchestrator.run(requirement)
        return 0 if state.status.value == "completed" else 1
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        return 130
    except Exception as exc:
        logger.error(f"未捕获异常：{exc}")
        return 1


def _print_banner() -> None:
    banner = """
╔══════════════════════════════════════════════════════╗
║      Multi-Agent Code Generation System              ║
║                                                      ║
║  Planner → Coder → Reviewer → [iterate] → Tests     ║
╚══════════════════════════════════════════════════════╝
"""
    console.print(f"[bold cyan]{banner}[/bold cyan]")


if __name__ == "__main__":
    sys.exit(main())
