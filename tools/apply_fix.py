"""
工具：apply_fix
================
代码修复工具，根据 Reviewer 的审查报告，结合 Designer 的设计文档，
对代码进行针对性的"外科手术式"局部修复（与 generate_code 的完整重写不同）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.client import LLMClient
from models.schemas import CodeResult, DesignDoc, FixResult, ReviewResult, SubTask
from utils.logger import logger

# ── 系统提示 ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert software engineer performing targeted code fixes.

You will receive:
1. The original design document (the specification the code must follow)
2. The current code with issues
3. A list of specific issues from a code reviewer

Your responsibilities:
1. Fix EVERY issue listed — no issue should remain unaddressed
2. Apply all reviewer suggestions
3. Ensure the fixed code still faithfully follows the design document
4. Preserve the overall structure unless a structural change is explicitly required
5. Return the COMPLETE fixed file — not just the changed hunks
6. Document each meaningful change you made

Respond ONLY with valid JSON:
{
    "fixed_code": "<complete corrected source code>",
    "changes_made": [
        "<concise description of change 1>",
        "<concise description of change 2>"
    ]
}
"""


# ── 主函数 ─────────────────────────────────────────────────────────────────────


def apply_fix(
    code_result: CodeResult,
    review_result: ReviewResult,
    design_doc: DesignDoc,
    subtask: SubTask,
    iteration: int = 0,
) -> FixResult:
    """
    根据审查反馈对代码进行修复。

    Args:
        code_result:   当前存在问题的代码
        review_result: Reviewer 的审查报告
        design_doc:    Designer 的设计文档（确保修复不偏离设计）
        subtask:       当前子任务
        iteration:     当前迭代轮次

    Returns:
        FixResult：包含修复后的代码及变更说明
    """
    llm = LLMClient()

    # ── 整理问题列表 ────────────────────────────────────────────────────────────
    issues_block = "\n".join(
        f"- [{iss.severity.upper()}] ({iss.category}) {iss.description}"
        + (f"\n  → near: `{iss.line_hint}`" if iss.line_hint else "")
        for iss in review_result.issues
    ) or "无严重问题，以通用质量提升为主"

    suggestions_block = (
        "\n".join(f"- {s}" for s in review_result.suggestions) or "无额外建议"
    )

    components_block = "\n".join(f"- {c}" for c in design_doc.components) or "（未指定）"

    prompt = (
        f"## Code Fix Request — {subtask.title} (Attempt {iteration + 1})\n\n"
        f"### Design Document Summary (MUST be respected after fix)\n"
        f"**Architecture:** {design_doc.architecture}\n"
        f"**Required Components:**\n{components_block}\n\n"
        f"### Code to Fix (current score: {review_result.score}/10)\n"
        f"```{code_result.language}\n{code_result.code}\n```\n\n"
        f"### Issues That Must Be Fixed\n{issues_block}\n\n"
        f"### Reviewer Suggestions\n{suggestions_block}\n\n"
        f"### Reviewer Summary\n{review_result.summary}\n\n"
        "Fix ALL issues. The fixed code must still follow the design document. "
        "Return the COMPLETE corrected code."
    )

    logger.info(
        f"[apply_fix] 子任务 [{subtask.title}] attempt {iteration}："
        f"修复 {len(review_result.issues)} 个问题…"
    )
    response = llm.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.5,
        max_tokens=4096,
    )

    return _parse_response(response, code_result, iteration)


# ── 响应解析 ───────────────────────────────────────────────────────────────────


def _parse_response(raw: str, original: CodeResult, iteration: int) -> FixResult:
    """将 LLM 原始响应解析为 FixResult。"""
    try:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            fixed_code = data.get("fixed_code", "").strip()
            if fixed_code:
                return FixResult(
                    task_id=original.task_id,
                    original_code=original.code,
                    fixed_code=fixed_code,
                    changes_made=data.get("changes_made", []),
                    iteration=iteration,
                )
    except (json.JSONDecodeError, AttributeError):
        pass

    # 回退：提取 Markdown 代码块
    md_match = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
    fixed_code = md_match.group(1).strip() if md_match else original.code

    logger.warning("[apply_fix] JSON 解析失败，已回退到 Markdown 提取")
    return FixResult(
        task_id=original.task_id,
        original_code=original.code,
        fixed_code=fixed_code,
        changes_made=["（应用了建议修复，详情解析失败）"],
        iteration=iteration,
    )
