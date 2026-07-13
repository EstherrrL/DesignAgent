"""
graph/nodes.py
==============
LangGraph 节点函数。每个函数接收 PipelineState，
返回需要更新的字段字典（只需返回变化的字段）。

节点列表：
  planner        → Designer.plan()  拆解子任务
  designer       → Designer.design()  生成设计文档
  coder          → CoderAgent.run()   生成/修复代码
  reviewer       → ReviewerAgent.run() 审查代码
  advance_subtask → 记录本轮 TaskResult，游标 +1
  assembler      → 合并所有子任务代码
  tester         → run_tests() 验证最终代码

路由函数（条件边）：
  route_after_reviewer  → "coder" | "advance_subtask"
  route_after_advance   → "designer" | "assembler"
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

from agents.designer import DesignerAgent
from agents.coder import CoderAgent
from agents.reviewer import ReviewerAgent
from config import MAX_TASK_ATTEMPTS, MIN_QUALITY_SCORE
from graph.state import PipelineState
from models.schemas import CodeResult, TaskResult
from tools.run_tests import run_tests
from utils.logger import logger

console = Console()

# ── 单例 Agent（复用 LLMClient 连接）──────────────────────────────────────────
_designer = DesignerAgent()
_coder = CoderAgent()
_reviewer = ReviewerAgent()


# ── 显示辅助 ───────────────────────────────────────────────────────────────────

def _step(num: int, name: str, desc: str) -> None:
    console.print(f"\n[bold blue]{'━' * 60}[/bold blue]")
    console.print(f"[bold blue]  Step {num}: {name}[/bold blue]  [dim]{desc}[/dim]")
    console.print(f"[bold blue]{'━' * 60}[/bold blue]")


def _task_banner(idx: int, total: int, title: str, desc: str) -> None:
    console.print(f"\n[bold magenta]{'▓' * 60}[/bold magenta]")
    console.print(f"[bold magenta]  📌 子任务 {idx} / {total}:  {title}[/bold magenta]")
    console.print(f"[dim]  {desc[:160]}[/dim]")
    console.print(f"[bold magenta]{'▓' * 60}[/bold magenta]")


# ── 节点函数 ───────────────────────────────────────────────────────────────────


def planner_node(state: PipelineState) -> Dict[str, Any]:
    """Step 1 — Designer.plan()：拆解需求，输出子任务列表。"""
    task_id = state.get("task_id") or uuid.uuid4().hex[:8]
    requirement = state["requirement"]

    _step(1, "Designer", "分析需求，拆解子任务列表")

    plan = _designer.plan(requirement, task_id)

    from rich.table import Table
    table = Table(title="📋 实现计划", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", width=6)
    table.add_column("子任务", style="yellow", width=22)
    table.add_column("描述", style="white")
    for st in plan.subtasks:
        table.add_row(st.id, st.title, st.description)
    console.print(table)
    if plan.test_cases:
        console.print(f"\n  [green]整体测试用例（{len(plan.test_cases)} 条）：[/green]")
        for tc in plan.test_cases:
            console.print(f"    • {tc}")

    return {
        "task_id": task_id,
        "plan": plan,
        "current_subtask_idx": 0,
        "current_attempt": 0,
        "task_results": [],
        "history": [{"step": "planning", "result": plan.to_dict()}],
    }


def designer_node(state: PipelineState) -> Dict[str, Any]:
    """Step 2 — Designer.design()：为当前子任务生成设计文档。"""
    plan = state["plan"]
    idx = state["current_subtask_idx"]
    subtask = plan.subtasks[idx]

    _task_banner(idx + 1, len(plan.subtasks), subtask.title, subtask.description)
    _step(2, "Designer", f"为子任务 [{subtask.title}] 生成设计文档")

    design_doc = _designer.design(subtask, plan)

    # 打印设计文档摘要
    arch_preview = design_doc.architecture[:200] + ("…" if len(design_doc.architecture) > 200 else "")
    console.print(f"\n  [bold cyan]📐 设计文档：{design_doc.subtask_title}[/bold cyan]")
    console.print(f"  [yellow]架构思路：[/yellow]{arch_preview}")
    if design_doc.components:
        console.print(f"  [green]核心组件（{len(design_doc.components)} 个）：[/green]")
        for c in design_doc.components[:4]:
            console.print(f"    • {c}")
    if design_doc.implementation_steps:
        console.print(f"  [blue]实现步骤（{len(design_doc.implementation_steps)} 步）[/blue]")

    return {
        "current_design_doc": design_doc,
        "current_attempt": 0,      # 每个新子任务重置计数
        "current_code": None,
        "current_review": None,
    }


def coder_node(state: PipelineState) -> Dict[str, Any]:
    """Step 3 — CoderAgent：按设计文档生成代码，或根据审查意见修复。"""
    plan = state["plan"]
    idx = state["current_subtask_idx"]
    subtask = plan.subtasks[idx]
    attempt = state.get("current_attempt", 0)
    design_doc = state["current_design_doc"]
    previous_code = state.get("current_code")
    previous_review = state.get("current_review")

    _step(
        3, "Coder",
        f"[{subtask.title}]  第 {attempt + 1}/{MAX_TASK_ATTEMPTS} 次"
        + ("  — 初始生成" if attempt == 0 else "  — 根据审查意见修复"),
    )

    code = _coder.run(
        design_doc=design_doc,
        subtask=subtask,
        language=plan.language,
        task_id=state["task_id"],
        review_feedback=previous_review if attempt > 0 else None,
        previous_code=previous_code if attempt > 0 else None,
        iteration=attempt,
    )

    # 代码预览
    lines = code.code.splitlines()
    preview = "\n".join(lines[:28]) + ("\n  …（已截断）" if len(lines) > 28 else "")
    syntax = Syntax(preview, code.language.lower(), theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"💻 代码预览（第 {attempt + 1} 次，共 {len(lines)} 行）", border_style="blue"))

    return {"current_code": code}


def reviewer_node(state: PipelineState) -> Dict[str, Any]:
    """Step 4 — ReviewerAgent：以设计文档为基准审查代码，输出评分报告。"""
    plan = state["plan"]
    idx = state["current_subtask_idx"]
    subtask = plan.subtasks[idx]
    attempt = state.get("current_attempt", 0)

    _step(4, "Reviewer", f"[{subtask.title}]  第 {attempt + 1}/{MAX_TASK_ATTEMPTS} 次审查")

    review = _reviewer.run(
        code_result=state["current_code"],
        design_doc=state["current_design_doc"],
        subtask=subtask,
        iteration=attempt,
    )

    # 打印审查报告
    score_color = "green" if review.score >= MIN_QUALITY_SCORE else "yellow" if review.score >= 5 else "red"
    console.print(f"\n  [bold]审查报告（第 {attempt + 1} 次）[/bold]")
    console.print(
        f"  得分：[{score_color} bold]{review.score:.1f} / 10[/{score_color} bold]  "
        + ("[green]✓ 通过[/green]" if review.passed else "[red]✗ 未通过[/red]")
    )
    console.print(f"  总结：[dim]{review.summary[:300]}[/dim]")
    if review.issues:
        console.print(f"\n  [yellow]问题列表（{len(review.issues)} 条）：[/yellow]")
        for iss in review.issues[:5]:
            sev_color = "red" if iss.severity == "critical" else "yellow" if iss.severity == "major" else "dim"
            console.print(
                f"    [{sev_color}][{iss.severity.upper():8}][/{sev_color}] "
                f"[cyan]{iss.category}[/cyan]  {iss.description}"
            )
    if review.suggestions:
        console.print(f"\n  [blue]改进建议：[/blue]")
        for sug in review.suggestions[:3]:
            console.print(f"    → {sug}")

    # 更新历史
    history = list(state.get("history", []))
    history.append({
        "step": f"task_{idx}_attempt_{attempt}",
        "subtask": subtask.title,
        "score": review.score,
        "passed": review.passed,
    })

    return {
        "current_review": review,
        "current_attempt": attempt + 1,   # 递增，供路由函数判断
        "history": history,
    }


def advance_subtask_node(state: PipelineState) -> Dict[str, Any]:
    """将当前子任务结果存入 task_results，游标 +1，重置中间状态。"""
    plan = state["plan"]
    idx = state["current_subtask_idx"]
    subtask = plan.subtasks[idx]
    attempt = state.get("current_attempt", 0)  # 已在 reviewer_node 递增
    review = state.get("current_review")

    passed = bool(review and review.passed)
    failure_notes = (
        [f"经过 {MAX_TASK_ATTEMPTS} 次尝试仍未通过（最终得分：{review.score:.1f}/10）"]
        if review and not review.passed else []
    )

    task_result = TaskResult(
        subtask=subtask,
        design_doc=state.get("current_design_doc"),
        code_result=state.get("current_code"),
        review_result=review,
        attempts=attempt,
        passed=passed,
        failure_notes=failure_notes,
    )

    task_results = list(state.get("task_results", []))
    task_results.append(task_result)

    if passed:
        console.print(
            f"\n  [bold green]✅ [{subtask.title}] 通过！"
            f"得分 {review.score:.1f}/10 ≥ 阈值 {MIN_QUALITY_SCORE}[/bold green]"
        )
    else:
        console.print(
            f"\n  [red]⚠  [{subtask.title}] 已达最大尝试次数 {MAX_TASK_ATTEMPTS}，"
            f"以当前最优代码继续[/red]"
        )

    return {
        "task_results": task_results,
        "current_subtask_idx": idx + 1,
        "current_attempt": 0,
        "current_code": None,
        "current_review": None,
        "current_design_doc": None,
    }


def assembler_node(state: PipelineState) -> Dict[str, Any]:
    """合并所有子任务代码为最终输出文件。"""
    _step(5, "Assembler", "合并所有子任务代码为最终文件")

    task_results = state.get("task_results", [])
    language = state["plan"].language
    final_code = _assemble_code(task_results, language)

    return {"final_code": final_code, "final_language": language}


def tester_node(state: PipelineState) -> Dict[str, Any]:
    """对最终汇总代码运行测试验证。"""
    _step(6, "Tester", "运行测试，验证最终代码")

    final_code_result = CodeResult(
        task_id=state["task_id"],
        code=state["final_code"],
        language=state["final_language"],
        explanation="Assembled final code",
    )
    test_result = run_tests(code_result=final_code_result, plan=state["plan"])

    if test_result.passed:
        console.print(
            f"\n  [bold green]✅ 测试通过（耗时 {test_result.execution_time:.3f}s）[/bold green]"
        )
    else:
        console.print(f"\n  [bold red]❌ 测试未通过[/bold red]")
        for err in test_result.errors[:3]:
            console.print(f"  [red]  {err[:200]}[/red]")
    if test_result.output.strip():
        console.print(f"  [dim]输出：{test_result.output[:300]}[/dim]")

    return {"test_result": test_result}


# ── 路由函数（条件边）──────────────────────────────────────────────────────────


def route_after_reviewer(
    state: PipelineState,
) -> Literal["coder", "advance_subtask"]:
    """
    Reviewer 节点后的路由：
      通过               → advance_subtask（进入下一子任务）
      未通过 & 还有机会  → coder（继续重试）
      未通过 & 已达上限  → advance_subtask（强制推进）
    """
    review = state["current_review"]
    attempt = state["current_attempt"]     # 已在 reviewer_node 递增

    if review.passed:
        return "advance_subtask"
    elif attempt < MAX_TASK_ATTEMPTS:
        console.print(
            f"\n  [yellow]⚠  得分 {review.score:.1f}/10 未达阈值，"
            f"Coder 将根据审查意见修改（还剩 {MAX_TASK_ATTEMPTS - attempt} 次）[/yellow]"
        )
        return "coder"
    else:
        return "advance_subtask"


def route_after_advance(
    state: PipelineState,
) -> Literal["designer", "assembler"]:
    """
    advance_subtask 节点后的路由：
      还有子任务 → designer（处理下一子任务）
      全部完成   → assembler（汇总代码）
    """
    plan = state["plan"]
    idx = state["current_subtask_idx"]

    if idx < len(plan.subtasks):
        return "designer"
    else:
        return "assembler"


# ── 内部工具 ───────────────────────────────────────────────────────────────────


def _assemble_code(task_results: list, language: str) -> str:
    """将各子任务代码按顺序合并为完整文件。"""
    successful = [
        tr for tr in task_results
        if tr.code_result and tr.code_result.code.strip()
    ]
    if not successful:
        return "# No code generated"
    if len(successful) == 1:
        return successful[0].code_result.code

    cc = "#" if language.lower() in ("python", "ruby", "shell", "bash", "r") else "//"
    parts = []
    for tr in successful:
        status = "✓ passed" if tr.passed else f"⚠ {tr.attempts} attempts"
        header = (
            f"\n{cc} {'═' * 60}\n"
            f"{cc} Subtask: {tr.subtask.title}  [{status}]\n"
            f"{cc} {'═' * 60}\n"
        )
        parts.append(header + tr.code_result.code)
    return "\n\n".join(parts)
