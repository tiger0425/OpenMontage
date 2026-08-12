"""人声分离 + 混音（保留环境音，替换人声）。

二创解说音频处理：
- 有解说视频：demucs 分离原视频音频 → 保留 no_vocals（环境音/伴奏/引擎声）
  + 叠加二创中文人声 → 干净替换人声，保留其他声音
- 无解说视频：保留原声（本来就是环境音）
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEMUCS_EXE = r"C:/Users/tiger/scoop/apps/python/current/Scripts/demucs.exe"


def separate_vocals(audio_in: Path, out_dir: Path, model: str = "htdemucs") -> Optional[tuple[Path, Path]]:
    """用 demucs 分离人声与伴奏。

    Args:
        audio_in: 输入音频路径
        out_dir: 分离结果目录
        model: demucs 模型（htdemucs 四轨 / htdemucs_ft 微调版）

    Returns:
        (vocals_path, no_vocals_path) 或 None（失败）
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        DEMUCS_EXE, "-n", model, "--two-stems", "vocals",
        "-o", str(out_dir),
        str(audio_in),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        logger.error("demucs 分离失败: %s", res.stderr[-500:])
        return None

    # demucs 输出目录：<out_dir>/<model>/<input_stem>/vocals.wav + no_vocals.wav
    stem = audio_in.stem
    result_dir = out_dir / model / stem
    vocals = result_dir / "vocals.wav"
    no_vocals = result_dir / "no_vocals.wav"
    if not vocals.exists() or not no_vocals.exists():
        logger.error("demucs 输出缺失: %s", result_dir)
        return None
    return vocals, no_vocals


def mix_commentary_with_ambience(commentary_audio: Path, ambience_audio: Path,
                                 output_path: Path, total_duration: Optional[float] = None) -> bool:
    """把二创人声叠加到环境音上（保留环境音氛围，音量均衡）。

    二创人声为主声，环境音压低作背景。混音结果取最长时长（环境音通常更长），
    这样视频不会被音频截短；若环境音也短于视频，可用总时长补静音。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 二创人声正常音量，环境音降 30% 作背景，取最长时长
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(commentary_audio),
        "-i", str(ambience_audio),
        "-filter_complex",
        "[0:a]volume=1.0[voice];[1:a]volume=0.3[amb];"
        "[voice][amb]amix=inputs=2:duration=longest:dropout_transition=2[mix]",
        "-map", "[mix]",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        logger.error("混音失败: %s", res.stderr[-500:])
        return False
    return True
