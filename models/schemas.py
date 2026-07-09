"""
数据模型（Schema）
定义 Pipeline 中所有 Agent 之间传递的数据结构
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── 枚举 ───────────────────────────────────────────────────────


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── 计划结果 ───────────────────────────────────────────────────


@dataclass
class SubTask:
    """单个子任务"""
    id: str
    title: str
    description: str
    dependencies: List[str] = field(default_factory=list)


@dataclass
class PlanResult:
    """Planner Agent 的输出：任务拆解计划"""
    task_id: str
    original_requirement: str
    language: str
    subtasks: List[SubTask]
    context: str
    test_cases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.original_requirement,
            "language": self.language,
            "subtasks": [
                {"id": s.id, "title": s.title, "description": s.description}
                for s in self.subtasks
            ],
            "test_cases": self.test_cases,
            "context": self.context,
        }


# ── 设计文档 ───────────────────────────────────────────────────


@dataclass
class DesignDoc:
    """Designer Agent 针对单个子任务输出的设计文档"""
    task_id: str
    subtask_id: str
    subtask_title: str
    architecture: str                   # 整体设计思路
    components: List[str]               # 核心组件 / 函数
    implementation_steps: List[str]     # 逐步实现计划
    considerations: List[str]           # 边界情况 / 质量注意点
    full_text: str                      # 完整设计文档原文

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "subtask_title": self.subtask_title,
            "architecture": self.architecture,
            "components": self.components,
            "implementation_steps": self.implementation_steps,
            "considerations": self.considerations,
        }


# ── 代码结果 ───────────────────────────────────────────────────


@dataclass
class CodeResult:
    """Coder Agent 的输出：生成的代码"""
    task_id: str
    code: str
    language: str
    explanation: str
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "language": self.language,
            "explanation": self.explanation,
            "iteration": self.iteration,
            "lines": len(self.code.splitlines()),
        }


# ── 审查结果 ───────────────────────────────────────────────────


@dataclass
class Issue:
    """单个代码问题"""
    severity: str        # critical | major | minor
    category: str        # correctness | performance | style | security | testing
    description: str
    line_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "line_hint": self.line_hint,
        }


@dataclass
class ReviewResult:
    """Reviewer Agent 的输出：代码审查报告"""
    task_id: str
    score: float          # 0 ~ 10
    passed: bool
    issues: List[Issue]
    suggestions: List[str]
    summary: str
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "score": self.score,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "suggestions": self.suggestions,
            "summary": self.summary,
            "iteration": self.iteration,
        }


# ── 子任务完整执行结果 ──────────────────────────────────────────


@dataclass
class TaskResult:
    """单个子任务的完整执行结果（设计 + 编码 + 审查）"""
    subtask: SubTask
    design_doc: Optional["DesignDoc"] = None
    code_result: Optional["CodeResult"] = None
    review_result: Optional["ReviewResult"] = None
    attempts: int = 0          # 实际执行的 Coder-Reviewer 轮次
    passed: bool = False
    failure_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask.id,
            "subtask_title": self.subtask.title,
            "attempts": self.attempts,
            "passed": self.passed,
            "score": self.review_result.score if self.review_result else 0.0,
            "failure_notes": self.failure_notes,
        }


# ── 修复结果 ───────────────────────────────────────────────────


@dataclass
class FixResult:
    """apply_fix 工具的输出：修复后的代码"""
    task_id: str
    original_code: str
    fixed_code: str
    changes_made: List[str]
    iteration: int = 0


# ── 测试结果 ───────────────────────────────────────────────────


@dataclass
class TestResult:
    """run_tests 工具的输出：测试执行报告"""
    task_id: str
    passed: bool
    output: str
    errors: List[str]
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "output": self.output[:500],
            "errors": self.errors,
            "execution_time": round(self.execution_time, 3),
        }


# ── 全局 Pipeline 状态 ─────────────────────────────────────────


@dataclass
class AgentState:
    """
    Orchestrator 维护的全局状态，贯穿整个 Pipeline。
    """
    task_id: str
    requirement: str
    plan: Optional[PlanResult] = None
    task_results: List[TaskResult] = field(default_factory=list)  # 每个子任务的执行结果
    code_result: Optional[CodeResult] = None    # 最后处理的代码（向后兼容）
    review_result: Optional[ReviewResult] = None
    fix_result: Optional[FixResult] = None
    test_result: Optional[TestResult] = None
    iteration: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    final_code: Optional[str] = None
    final_language: Optional[str] = None
