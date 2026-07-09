"""
工具：review_code
=================
Reviewer Agent 的核心工具，调用 LLM 审查代码是否符合 Designer 的设计文档，
输出 0-10 分的质量评分及详细反馈。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.client import LLMClient
from models.schemas import CodeResult, DesignDoc, Issue, ReviewResult, SubTask
from config import MIN_QUALITY_SCORE
from utils.logger import logger

# ── 系统提示 ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = f"""\
You are a rigorous senior code reviewer. Your PRIMARY goal is to verify that the code faithfully implements the design document from the Designer Agent, AND meets general quality standards.

Review dimensions:
1. **Design Adherence** – Does the code match the architecture and components in the design?
2. **Completeness**     – Are all components/functions from the design present and implemented?
3. **Correctness**      – Does the code correctly implement all required functionality?
4. **Robustness**       – Are edge cases handled as specified in the design's considerations?
5. **Code Quality**     – Is the code clean, readable, and idiomatic?

Score thresholds:
  9–10  Excellent — fully implements design, production-ready
  7–8   Good — only minor deviations  (passing threshold ≥ {MIN_QUALITY_SCORE})
  5–6   Acceptable — some design components missing or partially implemented
  3–4   Poor — significant design violations or functional bugs
  0–2   Unacceptable — does not implement the design

Respond ONLY with valid JSON:
{{
  "score": <float 0-10>,
  "passed": <true|false>,
  "summary": "<one-paragraph assessment focused on design adherence and correctness>",
  "issues": [
    {{
      "severity": "critical|major|minor",
      "category": "design_adherence|correctness|completeness|robustness|style",
      "description": "<clear description of the issue>",
      "line_hint": "<optional: relevant function/variable name>"
    }}
  ],
  "suggestions": ["<actionable improvement 1>", "..."]
}}
"""


# ── 主函数 ─────────────────────────────────────────────────────────────────────


def review_code(
    code_result: CodeResult,
    design_doc: DesignDoc,
    subtask: SubTask,
    iteration: int = 0,
) -> ReviewResult:
    """
    审查代码是否符合设计文档。

    Args:
        code_result: 待审查的代码
        design_doc:  Designer 输出的设计文档（审查基准）
        subtask:     当前子任务
        iteration:   当前迭代轮次

    Returns:
        ReviewResult：评分 + 问题列表 + 建议
    """
    llm = LLMClient()

    components_block = "\n".join(f"- {c}" for c in design_doc.components) or "（未指定）"
    steps_block = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(design_doc.implementation_steps)
    ) or "（未指定）"
    considerations_block = (
        "\n".join(f"- {c}" for c in design_doc.considerations) or "（无）"
    )

    prompt = (
        f"## Code Review — Task: {subtask.title}  (Attempt {iteration + 1})\n\n"
        f"### Original Task Description\n{subtask.description}\n\n"
        f"### Design Document (the specification the code MUST follow)\n"
        f"**Architecture:** {design_doc.architecture}\n\n"
        f"**Required Components:**\n{components_block}\n\n"
        f"**Implementation Steps:**\n{steps_block}\n\n"
        f"**Considerations:**\n{considerations_block}\n\n"
        f"### Code Under Review ({code_result.language})\n"
        f"```{code_result.language}\n{code_result.code}\n```\n\n"
        "Review this code against the design document. "
        "Focus especially on whether all design components are implemented correctly."
    )

    logger.info(
        f"[review_code] 子任务 [{subtask.title}] attempt {iteration}："
        f"审查代码（{len(code_result.code.splitlines())} 行）…"
    )
    response = llm.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=2048,
    )

    return _parse_response(response, code_result.task_id, iteration)


# ── 响应解析 ───────────────────────────────────────────────────────────────────


def _parse_response(raw: str, task_id: str, iteration: int) -> ReviewResult:
    """将 LLM 原始响应解析为 ReviewResult。"""
    try:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())

            issues = [
                Issue(
                    severity=iss.get("severity", "minor"),
                    category=iss.get("category", "style"),
                    description=iss.get("description", ""),
                    line_hint=iss.get("line_hint"),
                )
                for iss in data.get("issues", [])
            ]

            score = float(data.get("score", 0.0))
            passed_flag = data.get("passed")
            if not isinstance(passed_flag, bool):
                passed_flag = score >= MIN_QUALITY_SCORE

            return ReviewResult(
                task_id=task_id,
                score=score,
                passed=passed_flag,
                issues=issues,
                suggestions=data.get("suggestions", []),
                summary=data.get("summary", ""),
                iteration=iteration,
            )
    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        logger.warning(f"[review_code] 响应解析失败：{exc}")

    return ReviewResult(
        task_id=task_id,
        score=5.0,
        passed=False,
        issues=[Issue(severity="major", category="style", description="审查响应解析失败，请重试")],
        suggestions=["重新提交代码进行审查"],
        summary="LLM 响应无法解析为结构化审查报告",
        iteration=iteration,
    )
