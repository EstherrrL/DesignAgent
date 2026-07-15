import sys
import uuid
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import anyio

from graph.pipeline import build_pipeline
from graph.state import PipelineState

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 编译一次，重复使用（LangGraph CompiledGraph 是无状态可复用的）
_pipeline = build_pipeline()

# 语言 → 文件扩展名，用于前端展示文件名
_EXT_MAP = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "java": ".java", "go": ".go", "rust": ".rs", "c++": ".cpp",
    "c": ".c", "ruby": ".rb", "php": ".php", "swift": ".swift",
    "kotlin": ".kt", "shell": ".sh",
}


class RunRequest(BaseModel):
    input: str


def _run_pipeline_sync(requirement: str) -> Dict[str, Any]:
    """同步阻塞地跑一次完整 Pipeline（Designer→Coder→Reviewer→...）。"""
    task_id = uuid.uuid4().hex[:8]
    initial_state: PipelineState = {
        "task_id": task_id,
        "requirement": requirement,
        "current_subtask_idx": 0,
        "current_attempt": 0,
        "task_results": [],
        "history": [],
    }
    final_state: PipelineState = _pipeline.invoke(initial_state)

    lang = (final_state.get("final_language") or "python").lower()
    ext = _EXT_MAP.get(lang, ".txt")
    filename = f"task_{task_id}{ext}"

    task_results = final_state.get("task_results", [])
    design_doc_parts = []
    for tr in task_results:
        dd = getattr(tr, "design_doc", None)
        if dd is not None and getattr(dd, "full_text", None):
            design_doc_parts.append(dd.full_text)
    design_doc = "\n\n---\n\n".join(design_doc_parts) or f"需求：{requirement}"

    passed = sum(1 for tr in task_results if getattr(tr, "passed", False))
    total = len(task_results)

    test_result = final_state.get("test_result")
    test_summary = None
    if test_result is not None:
        test_summary = {
            "passed": getattr(test_result, "passed", None),
            "output": (getattr(test_result, "output", "") or "")[:1000],
            "errors": getattr(test_result, "errors", []),
        }


    return {
        "design_doc": design_doc,
        "files": {filename: final_state.get("final_code") or ""},
        "review": {
            "score": round(passed / total, 2) if total else None,
            "comments": f"{passed}/{total} 子任务通过审查",
        },
        "test_result": test_summary,
    }


@app.post('/api/run')
async def run(req: RunRequest) -> Dict[str, Any]:
    prompt = req.input.strip()
    if not prompt:
        return {"ok": False, "error": "输入不能为空"}

    last_error = None
    # 应用层重试：遇到网络类瞬时错误（如 Connection error）时，整体 pipeline 重跑一次
    for attempt in range(2):
        try:
            result = await anyio.to_thread.run_sync(_run_pipeline_sync, prompt)
            return {"ok": True, "result": result}
        except Exception as e:
            last_error = str(e)
            is_transient = any(
                kw in last_error for kw in ("Connection", "connect", "timeout", "Timeout")
            )
            if attempt == 0 and is_transient:
                continue  # 重试一次
            break
    return {"ok": False, "error": last_error}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run('demo:app', host='0.0.0.0', port=port, reload=True)
