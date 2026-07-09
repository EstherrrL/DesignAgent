"""
Reviewer Agent
==============
职责：审查 Coder 生成的代码是否符合 Designer 的设计文档，
输出结构化评分报告。质量阈值（MIN_QUALITY_SCORE）以上视为通过。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from config import MIN_QUALITY_SCORE
from models.schemas import CodeResult, DesignDoc, ReviewResult, SubTask
from tools.review_code import review_code


class ReviewerAgent(BaseAgent):
    """
    Reviewer Agent：代码质量审查（基于设计文档）。

    工具：review_code
    评分标准：0-10 分，>= MIN_QUALITY_SCORE 视为通过
    """

    def __init__(self) -> None:
        super().__init__(
            name="Reviewer",
            description=f"审查代码是否符合设计文档，通过阈值：{MIN_QUALITY_SCORE}/10",
        )

    # ── 公开接口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        code_result: CodeResult,
        design_doc: DesignDoc,
        subtask: SubTask,
        iteration: int = 0,
    ) -> ReviewResult:
        """
        审查代码是否符合设计文档。

        Args:
            code_result: 待审查的代码
            design_doc:  Designer 的设计文档（审查基准）
            subtask:     当前子任务
            iteration:   当前尝试轮次

        Returns:
            ReviewResult：评分 + 问题列表 + 建议
        """
        self.log(
            f"开始审查（attempt {iteration + 1}）",
            f"[{subtask.title}]  {len(code_result.code.splitlines())} 行 "
            f"{code_result.language} 代码",
        )

        result: ReviewResult = review_code(
            code_result=code_result,
            design_doc=design_doc,
            subtask=subtask,
            iteration=iteration,
        )

        verdict = "✓ 通过" if result.passed else "✗ 需要改进"
        self.log(
            "审查完成",
            f"得分 {result.score:.1f}/10  {verdict}  问题数 {len(result.issues)}",
        )
        return result

