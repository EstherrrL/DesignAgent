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


def _is_invalid_test_case(tc: str) -> bool:
    """
    检测测试用例是否为"非法"内容——即模型误把完整的类/函数定义
    当作测试用例输出，而不是单行断言/表达式。
    这类内容如果被当作单行语句拼接进测试文件，会破坏 Python 语法
    （例如 "class Foo: def __init__..." 被压成一行），
    因此需要提前过滤掉，避免整个测试脚本因语法错误而崩溃。
    """
    stripped = tc.strip()
    if not stripped:
        return True
    # 真正的换行符：说明是多行代码块，而不是单行测试用例
    if "\n" in tc:
        return True
    # 明显是类/函数定义而非断言表达式
    if re.search(r"(^|;)\s*(class|def)\s+\w+", stripped):
        return True
    return False


def _strip_useless_imports(tc: str) -> str:
    """
    移除测试用例中形如 "from xxx import yyy; " 的导入语句。
    所有代码会被合并到同一个文件中执行，模型生成的自我 import
    语句（引用一个并不存在的模块文件）必然导致 ModuleNotFoundError，
    因此直接过滤掉，只保留真正的测试逻辑语句。
    """
    if ";" not in tc and not tc.strip().startswith(("import ", "from ")):
        return tc
    stmts = [s.strip() for s in tc.split(";") if s.strip()]
    kept = [s for s in stmts if not s.startswith(("import ", "from "))]
    return "; ".join(kept) if kept else tc


def _build_python_test_file(source_code: str, test_cases: List[str]) -> str:
    """将源码与自动生成的测试断言合并为一个可执行文件。"""
    lines = [source_code, ""]

    if not test_cases:
        return "\n".join(lines)

    test_cases = [_strip_useless_imports(tc) for tc in test_cases]

    lines += [
        "# ── 自动生成的测试用例 ──────────────────────────────────",
        "if __name__ == '__main__':",
        "    _passed = 0",
        "    _failed = 0",
    ]

    for tc in test_cases:
        # 过滤掉非法测试用例（模型误把完整类/函数定义当作测试用例输出），
        # 避免把它们压成一行导致整个测试文件语法错误崩溃。
        if _is_invalid_test_case(tc):
            logger.warning(f"[run_tests] 跳过非法测试用例（疑似代码块而非断言）：{tc[:80]!r}")
            lines += [
                f"    print('⚠ 跳过非法测试用例（疑似代码块而非断言）：' + {tc[:80]!r})",
            ]
            continue

        # 用 repr() 生成安全的字符串字面量，避免 tc 内部引号与 f-string 引号冲突
        tc_literal = repr(tc)


        if ";" in tc or " assert " in tc or tc.strip().startswith("assert"):
            # 多语句测试用例（如 in-place 修改场景）：
            # "s = [...]; reverse_string(s); assert s == [...]"
            # 按 "; " 拆分为多条独立语句依次执行
            stmts = [s.strip() for s in tc.split(";") if s.strip()]
            lines += [f"    try:"]
            lines += [f"        {stmt}" for stmt in stmts]
            lines += [
                f"        print('✓ ' + {tc_literal})",
                f"        _passed += 1",
                f"    except Exception as _e:",
                f"        print('✗ ' + {tc_literal} + '  →  ' + str(_e))",
                f"        _failed += 1",
            ]
        elif "==" in tc:
            # 支持 "expr == expected" 格式的断言（适用于有返回值的函数）
            expr, expected = tc.split("==", 1)
            expr, expected = expr.strip(), expected.strip()
            lines += [
                f"    try:",
                f"        _result = {expr}",
                f"        _expected = {expected}",
                f"        assert _result == _expected, f\"期望 {{_expected}}，实际 {{_result}}\"",
                f"        print('✓ ' + {tc_literal})",
                f"        _passed += 1",
                f"    except Exception as _e:",
                f"        print('✗ ' + {tc_literal} + '  →  ' + str(_e))",
                f"        _failed += 1",
            ]
        else:
            # 普通表达式，执行不报错即通过
            lines += [
                f"    try:",
                f"        {tc}",
                f"        print('✓ ' + {tc_literal})",
                f"        _passed += 1",
                f"    except Exception as _e:",
                f"        print('✗ ' + {tc_literal} + '  →  ' + str(_e))",
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
