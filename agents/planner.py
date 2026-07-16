"""
Planner Agent
=============
职责：接收自然语言需求，将其拆解为结构化实现计划（PlanResult）。
输出：目标语言、子任务列表、测试用例、上下文约束。
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from llm.client import LLMClient
from models.schemas import PlanResult, SubTask
from utils.logger import logger

# ── 系统提示 ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior software architect. Analyze the given requirement and produce a detailed implementation plan.

Instructions:
1. Identify the programming language (default Python if not mentioned)
2. Break the requirement into 1-6 concrete, implementable subtasks.
   - If the requirement is simple (e.g. a single function), produce exactly ONE subtask.
   - NEVER create meaningless meta subtasks such as "create a file" or "set up project structure".
3. Define specific, runnable test cases. All code will be merged into ONE file and tests
   run in that same scope — NEVER use "import" statements in test cases.
   Prefer assertion format: "func(args) == expected"
   Each test case MUST be a single line containing only expression(s)/assert statement(s)
   separated by "; ". NEVER include a "class " or "def " definition, multi-line code
   blocks, or newline characters inside a test case.
4. Note any important constraints or context

Respond ONLY with valid JSON (no surrounding markdown):
{
  "language": "<language name>",
  "context": "<key constraints, assumptions, or background>",
  "subtasks": [
    {
      "id": "st_1",
      "title": "<short imperative title>",
      "description": "<detailed description of what to implement>",
      "dependencies": []
    }
  ],
  "test_cases": [
    "<test assertion or description>"
  ]
}
"""


# ── Agent ──────────────────────────────────────────────────────────────────────


class PlannerAgent(BaseAgent):
    """
    Planner Agent：需求分析与任务拆解。

    输入：自然语言需求字符串
    输出：PlanResult（语言 + 子任务 + 测试用例 + 上下文）
    """

    def __init__(self) -> None:
        super().__init__(
            name="Planner",
            description="将自然语言需求拆解为结构化实现计划",
        )
        self.llm = LLMClient()

    # ── 公开接口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        requirement: str,
        task_id: Optional[str] = None,
    ) -> PlanResult:
        """
        分析需求并输出实现计划。

        Args:
            requirement: 自然语言需求描述
            task_id:     可选任务 ID（若不传则自动生成）

        Returns:
            PlanResult
        """
        if not task_id:
            task_id = uuid.uuid4().hex[:8]

        short_req = requirement[:80] + ("…" if len(requirement) > 80 else "")
        self.log("分析需求", short_req)

        response = self.llm.chat(
            messages=[
                {
                    "role": "user",
                    "content": f"Please analyze this requirement and create a detailed implementation plan:\n\n{requirement}",
                }
            ],
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.5,
        )

        plan = self._parse(response, requirement, task_id)
        self.log(
            "计划已生成",
            f"语言={plan.language}  子任务={len(plan.subtasks)}  测试用例={len(plan.test_cases)}",
        )
        return plan

    # ── 私有方法 ────────────────────────────────────────────────────────────────

    def _parse(self, raw: str, requirement: str, task_id: str) -> PlanResult:
        """解析 LLM 响应为 PlanResult。"""
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                subtasks = [
                    SubTask(
                        id=st.get("id", f"st_{i + 1}"),
                        title=st.get("title", f"Subtask {i + 1}"),
                        description=st.get("description", ""),
                        dependencies=st.get("dependencies", []),
                    )
                    for i, st in enumerate(data.get("subtasks", []))
                ]
                if not subtasks:
                    subtasks = [self._fallback_subtask(requirement)]

                return PlanResult(
                    task_id=task_id,
                    original_requirement=requirement,
                    language=data.get("language", "Python"),
                    subtasks=subtasks,
                    context=data.get("context", ""),
                    test_cases=data.get("test_cases", []),
                )
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning(f"[Planner] 响应解析失败：{exc}，使用兜底计划")

        # 兜底
        return PlanResult(
            task_id=task_id,
            original_requirement=requirement,
            language="Python",
            subtasks=[self._fallback_subtask(requirement)],
            context="",
            test_cases=[],
        )

    @staticmethod
    def _fallback_subtask(requirement: str) -> SubTask:
        return SubTask(
            id="st_1",
            title="实现需求",
            description=requirement,
        )
