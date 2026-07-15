"""
Designer Agent
==============
双重职责：
  1. plan(requirement)  → PlanResult   — 将需求拆解为子任务列表（原 Planner 职责）
  2. design(subtask)    → DesignDoc    — 为每个子任务输出详细设计文档（新增）

开发流程中的定位：
  需求 → [Designer.plan] → 子任务列表
  对每个子任务 → [Designer.design] → 设计文档 → [Coder] → [Reviewer]
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
from models.schemas import DesignDoc, PlanResult, SubTask
from utils.logger import logger

# ── 计划阶段系统提示 ───────────────────────────────────────────────────────────

_PLAN_SYSTEM_PROMPT = """\
You are a senior software architect. Analyze the given requirement and produce a clear implementation plan.

Instructions:
1. Identify the programming language (default Python if not mentioned)
2. Break the requirement into 1-6 concrete, independently implementable subtasks.
   - If the requirement is simple (e.g. a single function), produce exactly ONE subtask for it.
   - NEVER create meaningless meta subtasks such as "create a file", "create a module",
     "set up project structure", or "open/save the file". File creation is handled
     automatically by the system — do NOT implement or test any file I/O for this purpose.
   - Only split into multiple subtasks when there are genuinely independent pieces of logic.
3. Define specific, runnable test cases:
   - All subtask code will be merged into ONE single file and tests run in that same file/scope.
     Therefore test cases must call functions/classes DIRECTLY by name — NEVER use
     "import" or "from ... import ..." statements in test cases.
   - For functions that RETURN a value: use assertion format "func(args) == expected"
   - For functions that mutate IN-PLACE and return None (e.g. reverse a list in place):
     DO NOT write "func(args) == expected". Instead write a two-statement test case
     separated by "; " that first calls the function on a named variable, then asserts
     on that variable, e.g.: "s = ['h','e','l','l','o']; reverse_string(s); assert s == ['o','l','l','e','h']"
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
    "<test assertion or description, no import statements>"
  ]
}
"""

# ── 设计阶段系统提示 ───────────────────────────────────────────────────────────

_DESIGN_SYSTEM_PROMPT = """\
You are a senior software architect providing a detailed implementation design for a specific coding subtask.

Your design document will be handed directly to a Coder Agent. Be specific and precise enough that the coder can implement without ambiguity.

The design must cover:
1. **Architecture** – overall approach, patterns, and data structures to use
2. **Components** – every function/class/method to implement, with expected signatures
3. **Implementation Steps** – ordered step-by-step implementation guide
4. **Considerations** – edge cases, error handling, performance, type safety

Respond ONLY with valid JSON:
{
  "architecture": "<overall design rationale and structural approach>",
  "components": [
    "<ComponentName / function_name(params) -> return_type: one-line role>"
  ],
  "implementation_steps": [
    "<step 1: concrete action>",
    "<step 2: concrete action>"
  ],
  "considerations": [
    "<edge case or quality concern>"
  ],
  "full_text": "<complete design document in natural language, 3-5 paragraphs>"
}
"""


# ── Agent ──────────────────────────────────────────────────────────────────────


class DesignerAgent(BaseAgent):
    """
    Designer Agent：需求拆解 + 逐任务设计文档输出。

    plan()   → PlanResult（子任务列表，原 Planner 功能）
    design() → DesignDoc （单任务详细设计，新功能）
    run()    → 向后兼容 alias → plan()
    """

    def __init__(self) -> None:
        super().__init__(
            name="Designer",
            description="需求拆解 + 为每个子任务生成详细设计文档",
        )
        self.llm = LLMClient()

    # ── 公开接口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        requirement: str,
        task_id: Optional[str] = None,
    ) -> PlanResult:
        """向后兼容 alias → plan()"""
        return self.plan(requirement, task_id)

    def plan(
        self,
        requirement: str,
        task_id: Optional[str] = None,
    ) -> PlanResult:
        """
        分析需求，拆解为子任务列表。

        Args:
            requirement: 自然语言需求描述
            task_id:     可选任务 ID（若不传则自动生成）

        Returns:
            PlanResult：子任务列表 + 语言 + 测试用例
        """
        if not task_id:
            task_id = uuid.uuid4().hex[:8]

        short_req = requirement[:80] + ("…" if len(requirement) > 80 else "")
        self.log("拆解需求", short_req)

        response = self.llm.chat(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Please analyze this requirement and create a detailed implementation plan:\n\n"
                        + requirement
                    ),
                }
            ],
            system_prompt=_PLAN_SYSTEM_PROMPT,
            temperature=0.5,
        )

        plan = self._parse_plan(response, requirement, task_id)
        self.log(
            "计划已生成",
            f"语言={plan.language}  子任务={len(plan.subtasks)}  测试用例={len(plan.test_cases)}",
        )
        return plan

    def design(
        self,
        subtask: SubTask,
        plan: PlanResult,
    ) -> DesignDoc:
        """
        为单个子任务生成详细设计文档。

        Args:
            subtask: 目标子任务
            plan:    整体计划（提供上下文）

        Returns:
            DesignDoc：架构思路 + 组件列表 + 实现步骤 + 注意事项
        """
        self.log("生成设计文档", f"子任务：{subtask.title}")

        # 构造上下文：告知 Designer 本任务在整体计划中的位置
        other_tasks = [
            f"- {st.title}" for st in plan.subtasks if st.id != subtask.id
        ]
        context_block = "\n".join(other_tasks) if other_tasks else "（无其他子任务）"

        prompt = (
            f"## Overall Requirement\n{plan.original_requirement}\n\n"
            f"## Target Language\n{plan.language}\n\n"
            f"## Other Subtasks in This Project (for context)\n{context_block}\n\n"
            f"## Subtask to Design\n"
            f"**ID**: {subtask.id}\n"
            f"**Title**: {subtask.title}\n"
            f"**Description**: {subtask.description}\n\n"
            "Produce a detailed design document for THIS subtask only."
        )

        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_DESIGN_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=2048,
        )

        design_doc = self._parse_design(response, plan.task_id, subtask)
        self.log(
            "设计文档完成",
            f"组件={len(design_doc.components)}  步骤={len(design_doc.implementation_steps)}",
        )
        return design_doc

    # ── 私有：解析方法 ──────────────────────────────────────────────────────────

    def _parse_plan(
        self, raw: str, requirement: str, task_id: str
    ) -> PlanResult:
        """将 LLM 响应解析为 PlanResult。"""
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
            logger.warning(f"[Designer] plan 响应解析失败：{exc}，使用兜底计划")

        return PlanResult(
            task_id=task_id,
            original_requirement=requirement,
            language="Python",
            subtasks=[self._fallback_subtask(requirement)],
            context="",
            test_cases=[],
        )

    def _parse_design(
        self, raw: str, task_id: str, subtask: SubTask
    ) -> DesignDoc:
        """将 LLM 响应解析为 DesignDoc。"""
        try:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return DesignDoc(
                    task_id=task_id,
                    subtask_id=subtask.id,
                    subtask_title=subtask.title,
                    architecture=data.get("architecture", ""),
                    components=data.get("components", []),
                    implementation_steps=data.get("implementation_steps", []),
                    considerations=data.get("considerations", []),
                    full_text=data.get("full_text", ""),
                )
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning(f"[Designer] design 响应解析失败：{exc}，使用兜底设计")

        # 兜底：将原始响应作为 full_text
        return DesignDoc(
            task_id=task_id,
            subtask_id=subtask.id,
            subtask_title=subtask.title,
            architecture=f"Implement: {subtask.description}",
            components=[subtask.title],
            implementation_steps=[subtask.description],
            considerations=["Follow language best practices", "Add error handling"],
            full_text=raw[:2000],
        )

    @staticmethod
    def _fallback_subtask(requirement: str) -> SubTask:
        return SubTask(id="st_1", title="实现需求", description=requirement)
