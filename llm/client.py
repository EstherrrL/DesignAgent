"""
LLM 客户端（单例模式）
封装对 ARK（火山引擎）OpenAI 兼容接口的所有调用
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

# 确保项目根目录在 sys.path（无论从哪里运行）
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL_EP
from utils.logger import logger


class LLMClient:
    """
    线程安全的 LLM 客户端单例。
    基于 OpenAI SDK，适配火山引擎 ARK API。
    """

    _instance: Optional[LLMClient] = None

    def __new__(cls) -> LLMClient:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:          # type: ignore[attr-defined]
            return
        self.client = OpenAI(
            api_key=ARK_API_KEY,
            base_url=ARK_BASE_URL,
            max_retries=8,       # 网络偶发抖动时，多次重试提高成功率
            timeout=60.0,        # 单次请求超时时间（秒）
        )
        self.model: str = ARK_MODEL_EP
        self._initialized = True
        logger.debug(f"LLMClient 初始化完成，模型：{self.model}")

    # ------------------------------------------------------------------
    # 核心调用方法
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        发起一次对话请求。

        Args:
            messages:      用户 / 助手消息列表（无需包含 system）
            system_prompt: 可选的系统提示，会自动插入首位
            temperature:   采样温度（0=确定性，1=创造性）
            max_tokens:    最大输出 token 数

        Returns:
            模型返回的文本内容
        """
        all_messages: List[Dict[str, str]] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            logger.debug(f"LLM 请求：{len(all_messages)} 条消息，temperature={temperature}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,   # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content: str = response.choices[0].message.content or ""
            logger.debug(f"LLM 响应：{len(content)} 字符")
            return content
        except Exception as exc:
            logger.error(f"LLM API 调用失败：{exc}")
            raise
