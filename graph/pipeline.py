"""
graph/pipeline.py
=================
用 LangGraph StateGraph 构建 Design-Code Pipeline。

图结构：
  START
    │
    ▼
  planner ──────────────────────────────────────────────────┐
    │                                                        │
    ▼                                                        │
  designer ◄────────────────────────── route_after_advance  │
    │                                       ▲               │
    ▼                                       │               │
  coder ◄──── route_after_reviewer          │               │
    │              ▲                        │               │
    ▼              │                        │               │
  reviewer ────────┘──── advance_subtask ───┘               │
                                │                           │
                          (no more subtasks)                │
                                │                           │
                                ▼                           │
                           assembler                        │
                                │                           │
                                ▼                           │
                            tester                          │
                                │                           │
                                ▼                           │
                              END ◄─────────────────────────┘

辅助函数：
  build_pipeline()  → 编译好的 CompiledGraph，可直接 .invoke()
  get_mermaid()     → 返回 Mermaid 图代码字符串（用于可视化）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    advance_subtask_node,
    assembler_node,
    coder_node,
    designer_node,
    planner_node,
    reviewer_node,
    route_after_advance,
    route_after_reviewer,
    tester_node,
)
from graph.state import PipelineState


def build_pipeline():
    """
    构建并编译 LangGraph Pipeline。

    Returns:
        CompiledGraph：可调用 .invoke(initial_state) 执行完整 Pipeline
    """
    graph = StateGraph(PipelineState)

    # ── 注册节点 ────────────────────────────────────────────────────────────────
    graph.add_node("planner",         planner_node)
    graph.add_node("designer",        designer_node)
    graph.add_node("coder",           coder_node)
    graph.add_node("reviewer",        reviewer_node)
    graph.add_node("advance_subtask", advance_subtask_node)
    graph.add_node("assembler",       assembler_node)
    graph.add_node("tester",          tester_node)

    # ── 固定边 ──────────────────────────────────────────────────────────────────
    graph.add_edge(START,            "planner")
    graph.add_edge("planner",        "designer")
    graph.add_edge("designer",       "coder")
    graph.add_edge("coder",          "reviewer")
    graph.add_edge("assembler",      "tester")
    graph.add_edge("tester",         END)

    # ── 条件边：Reviewer → 重试 or 推进 ────────────────────────────────────────
    graph.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "coder":           "coder",           # 未通过 & 有重试机会
            "advance_subtask": "advance_subtask",  # 通过 or 达到上限
        },
    )

    # ── 条件边：推进 → 下一子任务 or 汇总 ──────────────────────────────────────
    graph.add_conditional_edges(
        "advance_subtask",
        route_after_advance,
        {
            "designer":  "designer",   # 还有子任务未处理
            "assembler": "assembler",  # 全部子任务完成
        },
    )

    return graph.compile()


def get_mermaid() -> str:
    """返回 Pipeline 的 Mermaid 流程图代码（可粘贴到 Mermaid Live 预览）。"""
    pipeline = build_pipeline()
    try:
        return pipeline.get_graph().draw_mermaid()
    except Exception:
        # 部分环境可能不支持，返回手写版本
        return """
flowchart TD
    START([START]) --> planner
    planner --> designer
    designer --> coder
    coder --> reviewer
    reviewer -->|通过 or 达上限| advance_subtask
    reviewer -->|未通过 & 有机会| coder
    advance_subtask -->|还有子任务| designer
    advance_subtask -->|全部完成| assembler
    assembler --> tester
    tester --> END([END])
"""
