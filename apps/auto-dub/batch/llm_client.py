"""LLM 客户端：统一封装 DeepSeek 和 Gemini 的 API 调用，支持自动选择可用提供商。"""

import os
import json
import logging
from typing import Optional, Any

# 尝试导入新版 google.genai
try:
    from google import genai
    _GENAI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai
        _GENAI_AVAILABLE = True
    except ImportError:
        genai = None
        _GENAI_AVAILABLE = False

# 导入 openai 库 (用于 DeepSeek 调用)
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


class LLMClient:
    """LLM 统一客户端"""

    def __init__(self):
        self.provider = None
        self._client = None
        
        # 1. 优先使用 DeepSeek (由于 DEEPSEEK_V4_API_KEY 已配置)
        deepseek_key = os.environ.get("DEEPSEEK_V4_API_KEY")
        if _OPENAI_AVAILABLE and deepseek_key:
            self.provider = "deepseek"
            self._client = OpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1"
            )
            logging.info("LLMClient: 使用 DeepSeek API 作为主力模型。")
            return

        # 2. 其次使用 Gemini
        gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if _GENAI_AVAILABLE and gemini_key:
            self.provider = "gemini"
            try:
                self._client = genai.Client(api_key=gemini_key)
            except (AttributeError, TypeError):
                genai.configure(api_key=gemini_key)
                self._client = genai
            logging.info("LLMClient: 使用 Gemini API 作为主力模型。")
            return

        logging.warning("LLMClient: 未检测到任何可用的 LLM API 密钥（DeepSeek / Gemini）。")

    def is_available(self) -> bool:
        """检查客户端是否可用"""
        return self.provider is not None

    def generate(self, prompt: str, system_instruction: Optional[str] = None, json_mode: bool = False) -> str:
        """生成文本内容
        
        Args:
            prompt: 提示词
            system_instruction: 系统设定/指导词
            json_mode: 是否强制以 JSON 格式返回 (仅在模型支持时有效)
        """
        if not self.is_available():
            raise RuntimeError("LLM 客户端不可用，请配置 API 密钥（DEEPSEEK_V4_API_KEY 或 GOOGLE_API_KEY）。")

        if self.provider == "deepseek":
            return self._generate_deepseek(prompt, system_instruction, json_mode)
        elif self.provider == "gemini":
            return self._generate_gemini(prompt, system_instruction, json_mode)
        
        raise RuntimeError("未知的 LLM 提供商")

    def _generate_deepseek(self, prompt: str, system_instruction: Optional[str], json_mode: bool) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        # DeepSeek 支持 response_format={"type": "json_object"}
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            **kwargs
        )
        return response.choices[0].message.content

    def _generate_gemini(self, prompt: str, system_instruction: Optional[str], json_mode: bool) -> str:
        # 新版 SDK
        if hasattr(self._client, 'models'):
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction
            if json_mode:
                config["response_mime_type"] = "application/json"
            
            response = self._client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=config
            )
            return response.text
        else:
            # 旧版 SDK
            model_name = "gemini-2.0-flash"
            model = self._client.GenerativeModel(
                model_name,
                system_instruction=system_instruction
            )
            kwargs = {}
            if json_mode:
                kwargs["generation_config"] = {"response_mime_type": "application/json"}
                
            response = model.generate_content(prompt, **kwargs)
            return response.text
