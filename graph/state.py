"""
PipelineState — LangGraph 全局状态定义
所有节点共享此 TypedDict，每个节点只返回需要更新的字段。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from models.schemas import (
    CodeResult,
    DesignDoc,
    PlanResult,
    ReviewResult,
    TaskResult,
    TestResult,
)


class PipelineState(TypedDict, total=False):
    # ── 基础信息 ────────────────────────────────────────────
    task_id: str
    requirement: str

    # ── Planner 输出 ────────────────────────────────────────
    plan: Optional[PlanResult]

    # ── 子任务游标 ──────────────────────────────────────────
    current_subtask_idx: int      # 当前处理的子任务下标
    current_attempt: int          # 当前子任务已用的重试次数

    # ── 节点间传递的中间产物 ────────────────────────────────
    current_design_doc: Optional[DesignDoc]
    current_code: Optional[CodeResult]
    current_review: Optional[ReviewResult]

    # ── 累积结果 ────────────────────────────────────────────
    task_results: List[TaskResult]

    # ── 最终输出 ────────────────────────────────────────────
    final_code: Optional[str]
    final_language: Optional[str]
    test_result: Optional[TestResult]

    # ── 历史记录 ────────────────────────────────────────────
    history: List[Dict[str, Any]]
