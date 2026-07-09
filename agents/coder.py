"""
Coder Agent
===========
职责：
  - attempt 0：调用 generate_code 工具，根据设计文档生成初始代码
  - attempt 1+：调用 apply_fix 工具，根据审查反馈针对性修复代码
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from models.schemas import CodeResult, DesignDoc, FixResult, ReviewResult, SubTask
from tools.apply_fix import apply_fix
from tools.generate_code import generate_code


class CoderAgent(BaseAgent):
    """
    Coder Agent：代码生成与迭代修复。

    工具调用路径：
      attempt == 0  →  generate_code（根据设计文档全新生成）
      attempt  > 0  →  apply_fix（根据审查反馈针对性修复）
    """

    def __init__(self) -> None:
        super().__init__(
            name="Coder",
            description="根据 Designer 设计文档生成代码，并根据 Reviewer 反馈迭代修复",
        )

    # ── 公开接口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        design_doc: DesignDoc,
        subtask: SubTask,
        language: str,
        task_id: str,
        review_feedback: Optional[ReviewResult] = None,
        previous_code: Optional[CodeResult] = None,
        iteration: int = 0,
    ) -> CodeResult:
        """
        根据设计文档生成或修复代码。

        Args:
            design_doc:      Designer Agent 输出的设计文档
            subtask:         当前子任务
            language:        目标编程语言
            task_id:         任务 ID
            review_feedback: 上一轮审查反馈（attempt > 0 时提供）
            previous_code:   上一版本代码（attempt > 0 时提供）
            iteration:       当前尝试轮次（0 = 首次生成）

        Returns:
            CodeResult：新版本代码
        """
        if iteration == 0:
            # ── 首次生成 ───────────────────────────────────────────────────────
            self.log("生成初始代码", f"[{subtask.title}] 语言：{language}")
            result = generate_code(
                design_doc=design_doc,
                subtask=subtask,
                language=language,
                task_id=task_id,
                iteration=0,
            )
            self.log("初始代码完成", f"共 {len(result.code.splitlines())} 行")
            return result

        else:
            # ── 根据审查反馈修复 ────────────────────────────────────────────────
            assert review_feedback is not None, "attempt > 0 时必须提供 review_feedback"
            assert previous_code is not None, "attempt > 0 时必须提供 previous_code"

            self.log(
                f"修复代码（第 {iteration + 1} 次尝试）",
                f"[{subtask.title}] 得分 {review_feedback.score}/10，"
                f"问题 {len(review_feedback.issues)} 个",
            )

            fix: FixResult = apply_fix(
                code_result=previous_code,
                review_result=review_feedback,
                design_doc=design_doc,
                subtask=subtask,
                iteration=iteration,
            )

            self.log("修复完成", f"变更 {len(fix.changes_made)} 处")

            return CodeResult(
                task_id=task_id,
                code=fix.fixed_code,
                language=previous_code.language,
                explanation=previous_code.explanation,
                iteration=iteration,
            )
