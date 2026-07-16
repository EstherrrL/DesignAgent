import types
import json
import sys
from pathlib import Path

# Ensure project root is importable when running pytest from any CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.pipeline import build_pipeline
from graph.state import PipelineState


def _make_fake_chat():
    """Return a fake chat method that inspects system_prompt to decide which canned response to return."""

    def fake_chat(self, messages, system_prompt=None, temperature=0.0, max_tokens=1024):
        sp = (system_prompt or "").lower()

        # Planner / plan prompt
        if "analyze the given requirement" in sp or "create a detailed implementation plan" in sp:
            return json.dumps({
                "language": "Python",
                "context": "",
                "subtasks": [
                    {
                        "id": "st_1",
                        "title": "实现 add 函数",
                        "description": "实现函数 add(a, b) 返回 a + b",
                        "dependencies": [],
                    }
                ],
                "test_cases": ["add(1,2) == 3", "add(-1,5) == 4"],
            })

        # Designer / design prompt
        if "provide a detailed implementation design" in sp or "detailed design document" in sp:
            return json.dumps({
                "architecture": "Single function approach",
                "components": ["def add(a, b) -> number: return a + b"],
                "implementation_steps": ["Implement add", "Add docstring"],
                "considerations": ["Handle numeric inputs"],
                "full_text": "Implement a simple add function that returns a+b",
            })

        # generate_code / coder prompt
        if "you are a senior software engineer" in sp or "implement the design document" in sp:
            return json.dumps({
                "code": "def add(a, b):\n    \"\"\"Return the sum of a and b.\"\"\"\n    return a + b\n",
                "language": "python",
                "explanation": "simple add implementation",
            })

        # review_code / reviewer prompt
        if "you are a rigorous senior code reviewer" in sp or "code review" in sp:
            return json.dumps({
                "score": 9.0,
                "passed": True,
                "summary": "Good implementation",
                "issues": [],
                "suggestions": [],
            })

        # fallback
        return "{}"

    return fake_chat


def test_pipeline_end_to_end(monkeypatch):
    # Patch LLMClient.__init__ to avoid constructing real OpenAI client and attach fake chat
    import llm.client as lc

    def fake_init(self):
        # minimal initialization
        self.client = None
        self.model = "test"
        self._initialized = True
        # bind chat
        self.chat = types.MethodType(_make_fake_chat(), self)

    monkeypatch.setattr(lc.LLMClient, "__init__", fake_init)

    # Build pipeline and invoke with a simple requirement
    pipeline = build_pipeline()
    initial_state: PipelineState = {
        "task_id": "test01",
        "requirement": "实现一个 add(a, b) 函数，返回两数之和",
        "current_subtask_idx": 0,
        "current_attempt": 0,
        "task_results": [],
        "history": [],
    }

    final_state = pipeline.invoke(initial_state)

    # Asserts: final_code contains 'def add' and tests passed
    final_code = final_state.get("final_code", "")
    assert "def add" in final_code

    test_result = final_state.get("test_result")
    # If tester ran, ensure it passed; if not, at least confirm code exists
    if test_result:
        assert test_result.passed is True
    else:
        assert final_code.strip() != ""
