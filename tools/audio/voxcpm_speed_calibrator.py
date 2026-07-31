"""VoxCPM 语速校准模块。

通过让 VoxCPM 合成一段固定参考文本，测量实际音频时长，计算字符每秒（cps），
为中文翻译字数预算提供实测依据。结果会缓存到本地 JSON，避免每次运行都重新测速。
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydub import AudioSegment


def _default_reference_text() -> str:
    """默认参考文本：覆盖常见中文口语长度，用于测速。"""
    return (
        "今天我们要介绍如何在本地免费运行大语言模型。"
        "首先，你需要安装 Ollama 和 LM Studio 等工具。"
        "然后，下载一个开源模型并加载即可开始对话。"
    )


class VoxCPMSpeedCalibrator:
    """VoxCPM 实测语速校准器。

    Args:
        cache_path: cps 缓存文件路径。若存在有效缓存且未强制重测，直接返回。
        fallback_cps: 当 VoxCPM 不可用或校准失败时使用的默认语速（字符/秒）。
        reference_text: 用于测速的参考文本。默认使用一段中性中文科普文本。
        voice_description: 生成参考音频时使用的音色描述。
        seed: 生成参考音频时使用的随机种子，保证音色可复现。
        cfg_value: VoxCPM 的 classifier-free guidance 参数。
    """

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        fallback_cps: float = 4.5,
        reference_text: Optional[str] = None,
        voice_description: str = "温暖成熟的普通话男声，发音清晰平稳，科普讲解员风格",
        seed: int = 42,
        cfg_value: float = 3.0,
    ):
        self.cache_path = cache_path
        self.fallback_cps = fallback_cps
        self.reference_text = reference_text or _default_reference_text()
        self.voice_description = voice_description
        self.seed = seed
        self.cfg_value = cfg_value
        self._cps: Optional[float] = None

    def get_cps(self, force: bool = False) -> float:
        """返回实测或缓存的 cps（字符/秒）。"""
        if self._cps is not None and not force:
            return self._cps

        # 1. 尝试读取缓存
        if not force and self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                cached = float(data.get("cps", 0.0))
                if cached > 0.0:
                    self._cps = cached
                    logging.info(f"[VoxCPM Speed Calibrator] 使用缓存 cps={cached:.2f} ({self.cache_path})")
                    return self._cps
            except Exception as exc:
                logging.warning(f"[VoxCPM Speed Calibrator] 读取缓存失败: {exc}")

        # 2. 执行实测
        try:
            measured = self._measure_cps()
            if measured > 0.0:
                self._cps = measured
                self._save_cache(measured)
                return self._cps
        except Exception as exc:
            logging.warning(f"[VoxCPM Speed Calibrator] 实测失败: {exc}，回退到 fallback_cps={self.fallback_cps}")

        self._cps = self.fallback_cps
        return self._cps

    def _measure_cps(self) -> float:
        """使用 VoxCPM 合成参考文本并计算 cps。"""
        # 延迟导入，避免在 VoxCPM 未安装时导入失败
        from tools.audio.voxcpm_tts import VoxCPMTTS
        from tools.base_tool import ToolStatus

        tts = VoxCPMTTS()
        if tts.get_status() != ToolStatus.AVAILABLE:
            raise RuntimeError("VoxCPM TTS 不可用（缺少 CUDA 或 voxcpm 包）")

        with tempfile.TemporaryDirectory(prefix="voxcpm_speed_calibrate_") as tmpdir:
            out_path = Path(tmpdir) / "calibration.wav"
            print(f"[VoxCPM Speed Calibrator] 正在合成参考文本以测量语速...")
            res = tts.execute({
                "text": self.reference_text,
                "output_path": str(out_path),
                "voice_description": self.voice_description,
                "seed": self.seed,
                "cfg_value": self.cfg_value,
            })
            if not res.success:
                raise RuntimeError(f"VoxCPM 合成失败: {res.error}")

            audio = AudioSegment.from_wav(str(out_path))
            duration = audio.duration_seconds
            if duration <= 0.0:
                raise RuntimeError("校准音频时长为 0")

            cps = len(self.reference_text) / duration
            print(f"[VoxCPM Speed Calibrator] 参考文本长度={len(self.reference_text)} 字符，音频时长={duration:.2f}s，cps={cps:.2f}")
            return cps

    def _save_cache(self, cps: float) -> None:
        """将 cps 写入缓存文件。"""
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "cps": round(cps, 2),
                "reference_text_length": len(self.reference_text),
                "reference_text_hash": _hash_text(self.reference_text),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logging.warning(f"[VoxCPM Speed Calibrator] 写入缓存失败: {exc}")


def _hash_text(text: str) -> str:
    """简单哈希，用于缓存匹配参考文本。"""
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def measured_char_budget(duration_seconds: float, cps: float, safety_factor: float = 0.95) -> int:
    """根据实测语速计算某段时长的中文字符预算。

    Formula: max(2, int(duration * cps * safety_factor))
    """
    if duration_seconds <= 0:
        return 2
    return max(2, int(duration_seconds * cps * safety_factor))
