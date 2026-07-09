"""
Orchestrator
============
多 Agent 协作的核心调度器，实现以下流程：

  需求输入
     ↓
  [Designer.plan]  拆解为子任务列表
     ↓
  对每个子任务：
     [Designer.design]  生成设计文档
        ↓
     ┌──[Coder]   根据设计生成/修复代码   (工具: generate_code / apply_fix)
     │     ↓
     └──[Reviewer] 审查是否符合设计文档   (工具: review_code)
           ↓ 通过 → 进入下一子任务
           ↓ 不通过 → 重试，最多 MAX_TASK_ATTEMPTS 次
           ↓ 达上限 → 记录问题，强制进入下一子任务
     ↓
  [Assembler]  合并所有子任务代码
     ↓
  [run_tests]  验证最终代码
     ↓
  output/task_<id>.<ext>
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agents.base_agent import BaseAgent
from agents.coder import CoderAgent
from agents.designer import DesignerAgent
from agents.reviewer import ReviewerAgent
from config import MAX_ITERATIONS, MAX_TASK_ATTEMPTS, MIN_QUALITY_SCORE
from models.schemas import (
    AgentState, CodeResult, DesignDoc, SubTask, TaskResult, TaskStatus,
)
from tools.run_tests import run_tests
from utils.logger import logger

console = Console()

# 语言 → 文件扩展名映射
_EXT_MAP = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "java": ".java", "go": ".go", "rust": ".rs", "c++": ".cpp",
    "c": ".c", "ruby": ".rb", "php": ".php", "swift": ".swift",
    "kotlin": ".kt", "shell": ".sh",
}


# ── Orchestrator ───────────────────────────────────────────────────────────────


class Orchestrator(BaseAgent):
    """Pipeline 调度器：Designer → Coder ↔ Reviewer（per-task 循环）→ Tests。"""

    def __init__(self) -> None:
        super().__init__(
            name="Orchestrator",
            description=(
                "协调 Designer / Coder / Reviewer，"
                "逐子任务迭代（最多 MAX_TASK_ATTEMPTS 次）直至全部完成"
            ),
        )
        self.designer = DesignerAgent()
        self.coder = CoderAgent()
        self.reviewer = ReviewerAgent()

    # ── 主入口 ──────────────────────────────────────────────────────────────────

    def run(
        self,
        requirement: str,
        task_id: Optional[str] = None,
    ) -> AgentState:
        """
        执行完整代码生成 Pipeline。

        Args:
            requirement: 自然语言需求
            task_id:     可选任务 ID（不传则自动生成）

        Returns:
            AgentState：包含所有子任务结果、最终代码、测试状态
        """
        if not task_id:
            task_id = uuid.uuid4().hex[:8]

        state = AgentState(
            task_id=task_id,
            requirement=requirement,
            status=TaskStatus.IN_PROGRESS,
        )

        self._print_header(task_id, requirement)

        try:
            # ── Step 1: Designer 拆解需求 ───────────────────────────────────────
            self._print_step(1, "Designer", "分析需求，拆解子任务列表")
            state.plan = self.designer.plan(requirement, task_id)
            state.history.append({"step": "planning", "result": state.plan.to_dict()})
            self._print_plan(state.plan)

            # ── Step 2: 逐子任务执行 ─────────────────────────────────────────────
            all_task_results: List[TaskResult] = []

            for task_idx, subtask in enumerate(state.plan.subtasks):
                self._print_task_banner(task_idx + 1, len(state.plan.subtasks), subtask)

                # ── 2a. Designer 生成设计文档 ────────────────────────────────────
                self._print_step(
                    2, "Designer",
                    f"为子任务 [{subtask.title}] 生成设计文档"
                )
                design_doc: DesignDoc = self.designer.design(subtask, state.plan)
                self._print_design_doc(design_doc)

                task_result = TaskResult(subtask=subtask, design_doc=design_doc)
                current_code: Optional[CodeResult] = None

                # ── 2b~2e. Coder ↔ Reviewer 循环（最多 MAX_TASK_ATTEMPTS 次）────
                for attempt in range(MAX_TASK_ATTEMPTS):
                    # ── Coder ──────────────────────────────────────────────────
                    self._print_step(
                        3, "Coder",
                        f"[{subtask.title}]  第 {attempt + 1}/{MAX_TASK_ATTEMPTS} 次尝试"
                        + ("  — 初始生成" if attempt == 0 else "  — 根据审查意见修复"),
                    )
                    state.status = TaskStatus.IN_PROGRESS
                    current_code = self.coder.run(
                        design_doc=design_doc,
                        subtask=subtask,
                        language=state.plan.language,
                        task_id=task_id,
                        review_feedback=task_result.review_result if attempt > 0 else None,
                        previous_code=current_code if attempt > 0 else None,
                        iteration=attempt,
                    )
                    task_result.code_result = current_code
                    self._print_code_preview(current_code, attempt)

                    # ── Reviewer ───────────────────────────────────────────────
                    self._print_step(
                        4, "Reviewer",
                        f"[{subtask.title}]  第 {attempt + 1}/{MAX_TASK_ATTEMPTS} 次审查"
                    )
                    state.status = TaskStatus.REVIEWING
                    review = self.reviewer.run(
                        code_result=current_code,
                        design_doc=design_doc,
                        subtask=subtask,
                        iteration=attempt,
                    )
                    task_result.review_result = review
                    task_result.attempts = attempt + 1
                    self._print_review(review, attempt)

                    state.history.append({
                        "step": f"task_{task_idx}_attempt_{attempt}",
                        "subtask": subtask.title,
                        "score": review.score,
                        "passed": review.passed,
                    })

                    # ── 判断是否通过 ────────────────────────────────────────────
                    if review.passed:
                        # 2d. 通过 → 进入下一子任务
                        task_result.passed = True
                        console.print(
                            f"\n  [bold green]✅ [{subtask.title}] 通过！"
                            f"得分 {review.score:.1f}/10 ≥ 阈值 {MIN_QUALITY_SCORE}[/bold green]"
                        )
                        break
                    else:
                        remaining = MAX_TASK_ATTEMPTS - attempt - 1
                        if remaining > 0:
                            # 2e. 未通过且还有机会 → 继续
                            console.print(
                                f"\n  [yellow]⚠  得分 {review.score:.1f}/10 未达阈值，"
                                f"Coder 将根据审查意见修改（还剩 {remaining} 次）[/yellow]"
                            )
                        else:
                            # 2f. 达上限仍未通过 → 记录问题，强制进入下一任务
                            note = (
                                f"经过 {MAX_TASK_ATTEMPTS} 次尝试仍未通过"
                                f"（最终得分：{review.score:.1f}/10）"
                            )
                            task_result.failure_notes.append(note)
                            console.print(
                                f"\n  [red]⚠  [{subtask.title}] 已达最大尝试次数 "
                                f"{MAX_TASK_ATTEMPTS}，以当前最优代码继续[/red]"
                            )

                all_task_results.append(task_result)
                state.task_results = all_task_results
                state.code_result = current_code       # 最后处理的代码（向后兼容）
                state.review_result = task_result.review_result

            # ── Step 3: 汇总所有子任务代码 ───────────────────────────────────────
            self._print_step(5, "Assembler", "合并所有子任务代码为最终文件")
            state.final_code = self._assemble_final_code(
                all_task_results, state.plan.language
            )
            state.final_language = state.plan.language

            # ── Step 4: 运行测试 ─────────────────────────────────────────────────
            self._print_step(6, "Tester", "运行测试，验证最终代码")
            state.status = TaskStatus.TESTING
            final_code_result = CodeResult(
                task_id=task_id,
                code=state.final_code,
                language=state.final_language,
                explanation="Assembled final code",
            )
            test_result = run_tests(
                code_result=final_code_result,
                plan=state.plan,
            )
            state.test_result = test_result
            state.history.append({"step": "testing", "result": test_result.to_dict()})
            self._print_test_result(test_result)

            # ── 完成 ───────────────────────────────────────────────────────────
            state.status = TaskStatus.COMPLETED
            self._save_output(state)
            self._print_summary(state)

        except Exception as exc:
            state.status = TaskStatus.FAILED
            logger.error(f"Pipeline 运行失败：{exc}")
            console.print(f"\n[bold red]❌ Pipeline 失败：{exc}[/bold red]")
            raise

        return state

    # ── 私有：显示辅助 ─────────────────────────────────────────────────────────

    def _print_header(self, task_id: str, requirement: str) -> None:
        short_req = requirement if len(requirement) <= 120 else requirement[:120] + "…"
        console.print(
            Panel.fit(
                f"[bold cyan]Design-Code Multi-Agent System[/bold cyan]\n\n"
                f"[yellow]Task ID      :[/yellow] {task_id}\n"
                f"[yellow]Requirement  :[/yellow] {short_req}\n"
                f"[dim]Max Task Attempts: {MAX_TASK_ATTEMPTS}  |  "
                f"Min Quality Score: {MIN_QUALITY_SCORE}/10[/dim]",
                title="🚀  Pipeline 启动",
                border_style="cyan",
            )
        )

    def _print_step(self, num: int, name: str, desc: str) -> None:
        console.print(f"\n[bold blue]{'━' * 60}[/bold blue]")
        console.print(f"[bold blue]  Step {num}: {name}[/bold blue]  [dim]{desc}[/dim]")
        console.print(f"[bold blue]{'━' * 60}[/bold blue]")

    def _print_task_banner(
        self, idx: int, total: int, subtask: SubTask
    ) -> None:
        console.print(f"\n[bold magenta]{'▓' * 60}[/bold magenta]")
        console.print(
            f"[bold magenta]  📌 子任务 {idx} / {total}:  {subtask.title}[/bold magenta]"
        )
        console.print(f"[dim]  {subtask.description[:160]}[/dim]")
        console.print(f"[bold magenta]{'▓' * 60}[/bold magenta]")

    def _print_plan(self, plan) -> None:
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

    def _print_design_doc(self, doc: DesignDoc) -> None:
        console.print(
            f"\n  [bold cyan]📐 设计文档：{doc.subtask_title}[/bold cyan]"
        )
        arch_preview = doc.architecture[:200] + ("…" if len(doc.architecture) > 200 else "")
        console.print(f"  [yellow]架构思路：[/yellow]{arch_preview}")
        if doc.components:
            console.print(f"  [green]核心组件（{len(doc.components)} 个）：[/green]")
            for c in doc.components[:5]:
                console.print(f"    • {c}")
        if doc.implementation_steps:
            console.print(f"  [blue]实现步骤（{len(doc.implementation_steps)} 步）：[/blue]")
            for i, s in enumerate(doc.implementation_steps[:4], 1):
                console.print(f"    {i}. {s[:100]}")

    def _print_code_preview(self, code: CodeResult, attempt: int) -> None:
        lines = code.code.splitlines()
        preview = "\n".join(lines[:28]) + ("\n  …（已截断）" if len(lines) > 28 else "")
        syntax = Syntax(preview, code.language.lower(), theme="monokai", line_numbers=True)
        console.print(
            Panel(
                syntax,
                title=f"💻 代码预览（第 {attempt + 1} 次，共 {len(lines)} 行）",
                border_style="blue",
            )
        )

    def _print_review(self, review, attempt: int) -> None:
        score_color = (
            "green" if review.score >= MIN_QUALITY_SCORE
            else "yellow" if review.score >= 5
            else "red"
        )
        console.print(f"\n  [bold]审查报告（第 {attempt + 1} 次）[/bold]")
        console.print(
            f"  得分：[{score_color} bold]{review.score:.1f} / 10"
            f"[/{score_color} bold]  "
            + ("[green]✓ 通过[/green]" if review.passed else "[red]✗ 未通过[/red]")
        )
        console.print(f"  总结：[dim]{review.summary[:300]}[/dim]")

        if review.issues:
            console.print(f"\n  [yellow]问题列表（{len(review.issues)} 条）：[/yellow]")
            for iss in review.issues:
                sev_color = (
                    "red" if iss.severity == "critical"
                    else "yellow" if iss.severity == "major"
                    else "dim"
                )
                hint = f"  [dim]({iss.line_hint})[/dim]" if iss.line_hint else ""
                console.print(
                    f"    [{sev_color}][{iss.severity.upper():8}][/{sev_color}] "
                    f"[cyan]{iss.category}[/cyan]  {iss.description}{hint}"
                )

        if review.suggestions:
            console.print(f"\n  [blue]改进建议：[/blue]")
            for sug in review.suggestions[:4]:
                console.print(f"    → {sug}")

    def _print_test_result(self, test) -> None:
        if test.passed:
            console.print(
                f"\n  [bold green]✅ 测试通过（耗时 {test.execution_time:.3f}s）[/bold green]"
            )
        else:
            console.print(f"\n  [bold red]❌ 测试未通过[/bold red]")
            for err in test.errors[:3]:
                console.print(f"  [red]  {err[:200]}[/red]")
        if test.output.strip():
            console.print(f"  [dim]输出：{test.output[:300]}[/dim]")

    def _print_summary(self, state: AgentState) -> None:
        # ── 子任务结果表格 ─────────────────────────────────────────────────────
        table = Table(
            title="📊 各子任务执行结果",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("子任务", style="yellow", width=25)
        table.add_column("尝试次数", style="cyan", justify="center", width=8)
        table.add_column("最终得分", style="green", justify="center", width=10)
        table.add_column("状态", justify="center", width=10)
        table.add_column("备注", style="dim")

        for tr in state.task_results:
            score = tr.review_result.score if tr.review_result else 0.0
            status_str = "✅ 通过" if tr.passed else "⚠ 未通过"
            note = tr.failure_notes[0][:40] if tr.failure_notes else ""
            table.add_row(
                tr.subtask.title, str(tr.attempts), f"{score:.1f}/10", status_str, note
            )
        console.print(table)

        # ── Pipeline 完成面板 ──────────────────────────────────────────────────
        test_status = (
            "✅ 通过" if (state.test_result and state.test_result.passed) else "⚠ 失败/跳过"
        )
        passed_count = sum(1 for tr in state.task_results if tr.passed)
        total_count = len(state.task_results)

        console.print(
            Panel(
                f"[bold green]✅ 代码生成完成[/bold green]\n\n"
                f"  任务 ID      : {state.task_id}\n"
                f"  语言         : {state.final_language}\n"
                f"  子任务总数    : {total_count}\n"
                f"  通过子任务    : {passed_count} / {total_count}\n"
                f"  测试状态     : {test_status}\n",
                title="🎉  Pipeline 完成",
                border_style="green",
            )
        )

        syntax = Syntax(
            state.final_code or "",
            (state.final_language or "text").lower(),
            theme="monokai",
            line_numbers=True,
        )
        console.print(
            Panel(
                syntax,
                title=f"📄 最终代码（{state.final_language}）",
                border_style="green",
            )
        )

    # ── 私有：代码汇总 ─────────────────────────────────────────────────────────

    def _assemble_final_code(
        self,
        task_results: List[TaskResult],
        language: str,
    ) -> str:
        """将各子任务的代码拼接成最终文件。"""
        successful = [
            tr for tr in task_results
            if tr.code_result and tr.code_result.code.strip()
        ]

        if not successful:
            return "# No code generated"
        if len(successful) == 1:
            return successful[0].code_result.code

        comment = (
            "#" if language.lower() in ("python", "ruby", "shell", "bash", "r")
            else "//"
        )
        parts = []
        for tr in successful:
            status = "✓ passed" if tr.passed else f"⚠ {tr.attempts} attempts"
            header = (
                f"\n{comment} {'═' * 60}\n"
                f"{comment} Subtask: {tr.subtask.title}  [{status}]\n"
                f"{comment} {'═' * 60}\n"
            )
            parts.append(header + tr.code_result.code)

        return "\n\n".join(parts)

    # ── 私有：保存输出 ─────────────────────────────────────────────────────────

    def _save_output(self, state: AgentState) -> None:
        if not state.final_code:
            return

        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)

        lang = (state.final_language or "python").lower()
        ext = _EXT_MAP.get(lang, ".txt")
        out_path = output_dir / f"task_{state.task_id}{ext}"

        passed = sum(1 for tr in state.task_results if tr.passed)
        total = len(state.task_results)
        header = _build_header(
            state.requirement, state.task_id, passed, total, lang
        )

        out_path.write_text(header + state.final_code, encoding="utf-8")
        console.print(f"\n  [green]💾 代码已保存至：{out_path}[/green]")


def _build_header(
    requirement: str, task_id: str, passed: int, total: int, lang: str
) -> str:
    """为输出文件生成注释头。"""
    cc = "#" if lang in ("python", "ruby", "shell", "bash") else "//"
    lines = [
        f"{cc} Task ID     : {task_id}",
        f"{cc} Tasks       : {passed}/{total} passed",
        f"{cc} Requirement : {requirement}",
        f"{cc} Generated by: Design-Code Multi-Agent System",
        "",
    ]
    return "\n".join(lines)

