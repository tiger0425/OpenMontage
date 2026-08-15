"""IndexTTS 常驻服务桥接（统一客户端）。

所有工作流统一通过 apps/indextts-bridge/client.py 的 IndexTTSSession 调用，
本模块保留 IndexTTS2Bridge 接口兼容 markhasara 现有调用，内部委托统一客户端。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import importlib.util
import os

logger = logging.getLogger(__name__)

# 统一客户端（apps/indextts-bridge/client.py）
_OMO_ROOT = Path(__file__).resolve().parents[2]
_CLIENT_PATH = _OMO_ROOT / "apps" / "indextts-bridge" / "client.py"
_spec = importlib.util.spec_from_file_location("indextts_bridge_client", _CLIENT_PATH)
_client_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_client_mod)
IndexTTSSession = _client_mod.IndexTTSSession


class IndexTTS2Bridge:
    """IndexTTS 常驻服务桥（兼容接口，委托统一客户端）。一次初始化，多次合成。"""

    def __init__(self, project_dir: Path, voice_ref: Optional[Path] = None,
                 emotion: str = "calm", model_version: str = "2.5",
                 lang: str = "ZH", use_qwen_emo: bool = False):
        self.project_dir = project_dir
        self.voice_ref = voice_ref
        self.model_version = model_version
        self.lang = lang
        self.use_qwen_emo = use_qwen_emo
        self.emotion = emotion
        self._session: Optional[IndexTTSSession] = None

    # ------------------------------------------------------------------
    # 服务生命周期
    # ------------------------------------------------------------------

    def start(self):
        if self._session is None:
            self._session = IndexTTSSession(
                voice_ref=self.voice_ref,
                model_version=self.model_version,
                lang=self.lang,
                use_qwen_emo=self.use_qwen_emo,
                emotion=self.emotion,
                project_dir=self.project_dir,
            )
        self._session.start()

    def stop(self):
        if self._session is not None:
            self._session.stop()
            self._session = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # ------------------------------------------------------------------
    # 合成
    # ------------------------------------------------------------------

    def synthesize(self, text: str, output_path: Path, seed: int = 42,
                   target_duration: Optional[float] = None) -> bool:
        """合成单段音频（委托统一客户端，自动处理 UTF-8 / 情感纯净 / lang / duration_factor）。"""
        if self._session is None:
            self.start()
        return self._session.synthesize(
            text, str(output_path), seed=seed, target_duration=target_duration)
