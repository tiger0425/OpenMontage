"""二创解说文案生成器：根据原视频转录内容生成中文夸张军事解说文案。

复用 auto-dub 的 LLMClient（DeepSeek/Gemini 自动路由）。
二创模式 = 非逐句翻译，抓亮点重新讲述，语气模仿原视频。
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

# 复用 auto-dub 内核：把 apps/auto-dub 加入 Python 路径
OMO_ROOT = Path(__file__).resolve().parent.parent.parent  # apps/markhasara -> OpenMontage/
AUTODUB_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(AUTODUB_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTODUB_ROOT))

from batch.llm_client import LLMClient  # noqa: E402

logger = logging.getLogger(__name__)


class CommentaryGenerator:
    """根据转录生成二创解说文案。"""

    def __init__(self, config: dict, llm: Optional[LLMClient] = None):
        self.config = config
        self.commentary_cfg = config.get("commentary", {})
        self.llm = llm or LLMClient()
        if not self.llm.is_available():
            logger.warning("LLMClient 不可用：未配置 DEEPSEEK_V4_API_KEY 或 GOOGLE_API_KEY")

    def _build_system_prompt(self) -> str:
        style = self.commentary_cfg.get("style", "military_excited")
        style_hint = {
            "military_excited": "夸张、激昂的军事解说风格，热血、有冲击力，用词大气",
        }.get(style, style)
        return (
            f"你是短视频军事解说文案写手。你的文案风格是：{style_hint}。\n"
            "你只输出解说词正文，不输出任何解释、前言或后记。"
        )

    def _build_prompt(self, title: str, transcript_text: str, duration_seconds: Optional[float] = None) -> str:
        cfg = self.commentary_cfg
        base = cfg.get("prompt_extra", "")
        tone_note = "语气必须模仿原视频解说的节奏和情绪。" if cfg.get("imitate_source_tone") else ""

        # 按视频时长动态算字数预算（中文解说约 3 字/秒，clamp 到 min-max）
        min_chars = int(cfg.get("min_chars", 20))
        max_chars = int(cfg.get("max_chars", 80))
        if duration_seconds and duration_seconds > 0:
            est = int(duration_seconds * 3)
            min_chars = max(min_chars, est - 20)
            max_chars = max(max_chars, est + 20)
        duration_note = f"解说长度必须与视频时长匹配（视频约 {duration_seconds:.0f}s），覆盖全程、节奏紧凑。" \
            if duration_seconds and cfg.get("strict_duration_match") else ""

        # 转录内容：可能为空（原视频无解说，纯画面+引擎声）。为空时只用标题 + 画面线索
        if transcript_text.strip():
            content_part = f"视频转录内容：\n{transcript_text}\n\n"
        else:
            content_part = "（本视频无解说/转录为空，是纯画面+环境音。请根据标题推断画面内容，突出军事/战机/行动的震撼感）\n\n"

        return (
            f"请为下面这条短视频写一段中文解说词。\n"
            f"视频标题：{title}\n"
            f"{content_part}"
            f"要求：\n{base}\n"
            f"{tone_note}\n{duration_note}\n"
            f"总字数控制在 {min_chars}-{max_chars} 字。\n"
            f"直接输出解说词正文。"
        )

    def generate(self, title: str, transcript_text: str, duration_seconds: Optional[float] = None) -> str:
        """生成二创解说文案。失败返回空串，由调用方决定重试/跳过。

        duration_seconds: 视频时长，用于按秒动态算字数预算（约 3 字/秒）。
        """
        if not self.llm.is_available():
            raise RuntimeError("LLM 客户端不可用，请配置 DEEPSEEK_V4_API_KEY 或 GOOGLE_API_KEY")
        sys_prompt = self._build_system_prompt()
        prompt = self._build_prompt(title, transcript_text, duration_seconds)
        try:
            raw = self.llm.generate(prompt, system_instruction=sys_prompt)
            return self._clean(raw)
        except Exception as e:
            logger.error("二创文案生成失败: %s", e)
            return ""

    def _clean(self, raw: str) -> str:
        """清理 LLM 输出：去掉引号、JSON 包裹、多余空白。"""
        raw = raw.strip()
        # 去 JSON 包裹
        m = re.search(r'"([^"]{10,})"', raw)
        if m and raw.strip().startswith(('{', '[')):
            raw = m.group(1)
        # 去首尾引号
        raw = raw.strip('"\'\n ')
        # 去常见前缀
        for prefix in ("解说词：", "解说：", "以下是我创作的解说词：", "好的，"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        return raw.strip()


def load_transcript_text(transcript_path: Path) -> str:
    """从转录 JSON 提取纯文本（拼接所有 utterance/segment 的 text）。"""
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    texts = []
    for utt in data.get("utterances", []):
        if utt.get("text"):
            texts.append(utt["text"])
    if not texts:
        for seg in data.get("segments", []):
            if seg.get("text"):
                texts.append(seg["text"])
    return "\n".join(texts)
