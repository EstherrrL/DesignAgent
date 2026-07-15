"""
工具：generate_code
===================
Coder Agent 的核心工具，调用 LLM 根据 Designer 提供的设计文档生成代码。
支持初始生成（iteration=0）和基于审查反馈的重新生成（iteration>0）两种模式。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.client import LLMClient
from models.schemas import CodeResult, DesignDoc, ReviewResult, SubTask
from utils.logger import logger

# ── 系统提示 ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior software engineer who writes clean, efficient, and production-ready code.

You will receive a design document from a Designer Agent — implement it faithfully.

Guidelines:
1. Follow the design's architecture and component structure exactly
2. Implement ALL specified components — no placeholders or TODOs
3. Add meaningful docstrings and inline comments
4. Handle every edge case listed in the design's considerations
5. Ensure the code is testable and uses correct type hints
6. Match the expected function/class signatures from the design

Respond ONLY with valid JSON (no markdown wrapper):
{
    "code": "<complete source code as a single string>",
    "language": "<programming language name>",
    "explanation": "<brief note on how the design was implemented>"
}
"""


# ── 主函数 ─────────────────────────────────────────────────────────────────────


def generate_code(
    design_doc: DesignDoc,
    subtask: SubTask,
    language: str,
    task_id: str,
    review_feedback: Optional[ReviewResult] = None,
    previous_code: Optional[str] = None,
    iteration: int = 0,
) -> CodeResult:
    """
    根据设计文档生成代码。

    Args:
        design_doc:      Designer Agent 输出的设计文档
        subtask:         当前子任务
        language:        目标编程语言
        task_id:         任务 ID
        review_feedback: 上一轮 Reviewer 的反馈（iteration>0 时使用）
        previous_code:   上一版本代码（iteration>0 时使用）
        iteration:       当前迭代轮次（0=初次生成）

    Returns:
        CodeResult：包含生成的代码及说明
    """
    llm = LLMClient()

    # ── 构造设计文档区块 ───────────────────────────────────────────────────────
    components_block = "\n".join(
        f"  - {c}" for c in design_doc.components
    ) or "  （未指定组件）"
    steps_block = "\n".join(
        f"  {i + 1}. {s}" for i, s in enumerate(design_doc.implementation_steps)
    ) or "  （未指定步骤）"
    considerations_block = "\n".join(
        f"  - {c}" for c in design_doc.considerations
    ) or "  （无特殊注意事项）"

    sections: list[str] = [
        f"## Task: {subtask.title}",
        subtask.description,
        f"\n## Target Language\n{language}",
        "\n## Design Document from Designer Agent",
        f"\n### Architecture Approach\n{design_doc.architecture}",
        f"\n### Components / Functions to Implement\n{components_block}",
        f"\n### Implementation Steps\n{steps_block}",
        f"\n### Edge Cases & Considerations\n{considerations_block}",
    ]

    if design_doc.full_text:
        sections.append(f"\n### Full Design Notes\n{design_doc.full_text}")

    # ── 迭代模式：附上前版代码 + 审查反馈 ────────────────────────────────────
    if iteration > 0 and previous_code and review_feedback:
        sections.append(
            f"\n## Previous Code (attempt {iteration}, score {review_feedback.score}/10)"
        )
        sections.append(f"```{language}\n{previous_code}\n```")
        sections.append(f"\n## Review Feedback\nSummary: {review_feedback.summary}")

        if review_feedback.issues:
            sections.append("\n### Issues to Fix")
            for iss in review_feedback.issues:
                hint = f" — near: {iss.line_hint}" if iss.line_hint else ""
                sections.append(
                    f"- [{iss.severity.upper()}] ({iss.category}) {iss.description}{hint}"
                )

        if review_feedback.suggestions:
            sections.append("\n### Suggestions")
            sections.extend(f"- {s}" for s in review_feedback.suggestions)

        sections.append(
            "\nFix ALL issues. Stay faithful to the design document. Return COMPLETE revised code."
        )
    else:
        sections.append(
            "\nImplement the design document above. Return complete, production-quality code."
        )

    prompt = "\n".join(sections)

    # ── 调用 LLM ───────────────────────────────────────────────────────────────
    logger.info(
        f"[generate_code] 子任务 [{subtask.title}] attempt {iteration}：调用 LLM 生成代码…"
    )
    response = llm.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=4096,
    )

    return _parse_response(response, task_id, language, iteration)


# ── 响应解析 ───────────────────────────────────────────────────────────────────


def _strip_markdown_fence(code: str) -> str:
    """
    去除代码字符串首尾可能残留的 Markdown 代码围栏（```lang ... ```）。
    有时模型在 JSON 的 "code" 字段值里仍会附带围栏，需要额外清理。
    """
    code = code.strip()
    m = re.match(r"^```(?:\w+)?\n(.*?)\n?```$", code, re.DOTALL)
    if m:
        return m.group(1).strip()
    return code


def _parse_response(
    response: str, task_id: str, language: str, iteration: int
) -> CodeResult:
    """将 LLM 原始响应解析为 CodeResult。"""
    try:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            code = _strip_markdown_fence(data.get("code", "").strip())
            if code:
                return CodeResult(
                    task_id=task_id,
                    code=code,
                    language=data.get("language", language),
                    explanation=data.get("explanation", ""),
                    iteration=iteration,
                )
    except (json.JSONDecodeError, AttributeError):
        pass

    # 回退：从 Markdown 代码块提取
    md_match = re.search(r"```(?:\w+)?\n(.*?)```", response, re.DOTALL)
    code = md_match.group(1).strip() if md_match else response.strip()
    code = _strip_markdown_fence(code)

    logger.warning("[generate_code] JSON 解析失败，已回退到 Markdown 提取")
    return CodeResult(
        task_id=task_id,
        code=code,
        language=language,
        explanation="（JSON 解析失败，已提取代码块）",
        iteration=iteration,
    )
