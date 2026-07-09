"""
工具：run_tests
===============
代码验证工具。
- Python 代码：在沙盒子进程中执行，捕获 stdout/stderr
- JavaScript/TypeScript：使用 node --check 进行语法校验
- 其他语言：静态基础分析（括号平衡、空代码、TODO 检查）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import CodeResult, PlanResult, TestResult
from config import CODE_EXECUTION_TIMEOUT
from utils.logger import logger


# ── 入口 ───────────────────────────────────────────────────────────────────────


def run_tests(
    code_result: CodeResult,
    plan: PlanResult,
    iteration: int = 0,
) -> TestResult:
    """
    对生成的代码运行测试/验证。

    Args:
        code_result: 待测试的代码
        plan:        任务计划（包含测试用例）
        iteration:   当前迭代轮次

    Returns:
        TestResult：包含通过/失败状态及详细输出
    """
    lang = code_result.language.lower()
    logger.info(f"[run_tests] 迭代 {iteration}：对 {code_result.language} 代码运行测试…")

    if "python" in lang:
        return _run_python(code_result, plan)
    if "javascript" in lang or "typescript" in lang:
        return _run_js_check(code_result, plan)
    return _run_static(code_result, plan)


# ── Python 执行 ────────────────────────────────────────────────────────────────


def _run_python(code_result: CodeResult, plan: PlanResult) -> TestResult:
    """在临时子进程中执行 Python 代码并捕获结果。"""
    start = time.monotonic()

    # 构造完整测试文件内容
    test_code = _build_python_test_file(code_result.code, plan.test_cases)

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(test_code)
            tmp_path = f.name

        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=CODE_EXECUTION_TIMEOUT,
        )

        elapsed = time.monotonic() - start
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return TestResult(
                task_id=code_result.task_id,
                passed=False,
                output=stdout,
                errors=[stderr] if stderr else ["进程以非零退出码结束"],
                execution_time=elapsed,
            )

        # 检查测试标记
        failed = [line for line in stdout.splitlines() if line.startswith("✗")]
        if failed:
            return TestResult(
                task_id=code_result.task_id,
                passed=False,
                output=stdout,
                errors=failed,
                execution_time=elapsed,
            )

        return TestResult(
            task_id=code_result.task_id,
            passed=True,
            output=stdout,
            errors=[],
            execution_time=elapsed,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            task_id=code_result.task_id,
            passed=False,
            output="",
            errors=[f"代码执行超时（>{CODE_EXECUTION_TIMEOUT}s）"],
            execution_time=CODE_EXECUTION_TIMEOUT,
        )
    except Exception as exc:
        return TestResult(
            task_id=code_result.task_id,
            passed=False,
            output="",
            errors=[f"测试执行异常：{exc}"],
            execution_time=time.monotonic() - start,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _build_python_test_file(source_code: str, test_cases: List[str]) -> str:
    """将源码与自动生成的测试断言合并为一个可执行文件。"""
    lines = [source_code, ""]

    if not test_cases:
        return "\n".join(lines)

    lines += [
        "# ── 自动生成的测试用例 ──────────────────────────────────",
        "if __name__ == '__main__':",
        "    _passed = 0",
        "    _failed = 0",
    ]

    for tc in test_cases:
        # 支持 "expr == expected" 格式的断言
        if "==" in tc:
            expr, expected = tc.split("==", 1)
            expr, expected = expr.strip(), expected.strip()
            lines += [
                f"    try:",
                f"        _result = {expr}",
                f"        _expected = {expected}",
                f"        assert _result == _expected, f\"期望 {{_expected}}，实际 {{_result}}\"",
                f"        print(f'✓ {tc}')",
                f"        _passed += 1",
                f"    except Exception as _e:",
                f"        print(f'✗ {tc}  →  {{_e}}')",
                f"        _failed += 1",
            ]
        else:
            # 普通表达式，执行不报错即通过
            lines += [
                f"    try:",
                f"        {tc}",
                f"        print(f'✓ {tc}')",
                f"        _passed += 1",
                f"    except Exception as _e:",
                f"        print(f'✗ {tc}  →  {{_e}}')",
                f"        _failed += 1",
            ]

    lines += [
        "    print(f'\\n测试结果：{_passed} 通过 / {_failed} 失败')",
    ]

    return "\n".join(lines)


# ── JavaScript / TypeScript 语法检查 ──────────────────────────────────────────


def _run_js_check(code_result: CodeResult, plan: PlanResult) -> TestResult:
    """使用 node --check 检查 JS/TS 语法。"""
    start = time.monotonic()
    suffix = ".ts" if "typescript" in code_result.language.lower() else ".js"
    tmp_path = ""

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as f:
            f.write(code_result.code)
            tmp_path = f.name

        proc = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )

        passed = proc.returncode == 0
        errors = [proc.stderr.strip()] if proc.stderr.strip() and not passed else []
        return TestResult(
            task_id=code_result.task_id,
            passed=passed,
            output=proc.stdout.strip(),
            errors=errors,
            execution_time=time.monotonic() - start,
        )

    except FileNotFoundError:
        logger.warning("[run_tests] Node.js 未安装，回退到静态分析")
        return _run_static(code_result, plan)
    except subprocess.TimeoutExpired:
        return TestResult(
            task_id=code_result.task_id,
            passed=False,
            output="",
            errors=["语法检查超时"],
            execution_time=10.0,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── 通用静态分析 ───────────────────────────────────────────────────────────────


def _run_static(code_result: CodeResult, plan: PlanResult) -> TestResult:
    """对任意语言执行基础静态规则检查。"""
    start = time.monotonic()
    code = code_result.code
    errors: List[str] = []

    if not code.strip():
        errors.append("代码内容为空")

    # 括号平衡检查
    for open_ch, close_ch in [("{", "}"), ("(", ")"), ("[", "]")]:
        diff = code.count(open_ch) - code.count(close_ch)
        if abs(diff) > 2:
            errors.append(
                f"可能存在括号不匹配：'{open_ch}' 出现 {code.count(open_ch)} 次，"
                f"'{close_ch}' 出现 {code.count(close_ch)} 次"
            )

    # 未完成代码标记
    todo_count = len(re.findall(r"\b(?:TODO|FIXME|HACK|XXX)\b", code, re.IGNORECASE))
    if todo_count > 0:
        errors.append(f"代码包含 {todo_count} 处 TODO/FIXME 标记，可能未完成")

    # 最低代码量检查
    if len(code.splitlines()) < 3:
        errors.append("代码过短，可能不完整")

    passed = len(errors) == 0
    return TestResult(
        task_id=code_result.task_id,
        passed=passed,
        output="静态分析通过" if passed else "静态分析发现问题",
        errors=errors,
        execution_time=time.monotonic() - start,
    )
