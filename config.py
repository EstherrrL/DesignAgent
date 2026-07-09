"""
全局配置文件
从 .env 加载所有环境变量
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（支持从项目任意目录运行）
load_dotenv(Path(__file__).parent / ".env")

# ── LLM 配置 ──────────────────────────────────────────────────
ARK_API_KEY: str = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL: str = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_EP: str = os.getenv("ARK_MODEL_EP", "")

# ── Pipeline 配置 ─────────────────────────────────────────────
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "5"))
MIN_QUALITY_SCORE: float = float(os.getenv("MIN_QUALITY_SCORE", "7.0"))
MAX_TASK_ATTEMPTS: int = int(os.getenv("MAX_TASK_ATTEMPTS", "3"))   # 每个子任务的最大重试次数
CODE_EXECUTION_TIMEOUT: int = int(os.getenv("CODE_EXECUTION_TIMEOUT", "15"))

# ── 日志级别 ──────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
