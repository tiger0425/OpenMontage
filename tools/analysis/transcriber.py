"""Transcription tool wrapping faster-whisper / pyannote.

Provides speech-to-text with word-level timestamps and optional speaker
diarization (pyannote 4.x). Falls back gracefully when GPU or diarization
dependencies are not available.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)


# 句末标点：作为原句（Utterance）边界判断依据（ADR-003 D1）
_SENTENCE_ENDINGS = (".", "!", "?", "...", "…")


def _ends_with_sentence_endings(text: str) -> bool:
    """判断文本是否以句末标点结尾（Utterance 合并的句子边界条件）。"""
    text = (text or "").strip()
    return any(text.endswith(e) for e in _SENTENCE_ENDINGS)


def _majority_speaker(segments: list[dict]) -> Optional[str]:
    """取一组转录段中出现最多、且最早出现的说话人；全无则返回 None。"""
    from collections import Counter

    counts = Counter(s.get("speaker") for s in segments if s.get("speaker"))
    if not counts:
        return None
    best, best_count = None, -1
    for seg in segments:
        spk = seg.get("speaker")
        if spk and counts[spk] > best_count:
            best_count, best = counts[spk], spk
    return best


def _utterance_from_segments(segments: list[dict], uid: str) -> dict:
    """把一个转录段列表合并为一个原句（Utterance）。

    Utterance 是字幕与逐句时长对齐的锚点单位（ADR-003 D1/D2）：
    1 原句 = N 个合成子块 = 1 条字幕。
    """
    text = " ".join(s.get("text", "").strip() for s in segments).strip()
    words: list[dict] = []
    for seg in segments:
        words.extend(seg.get("words", []) or [])
    return {
        "id": uid,
        "start": round(float(segments[0]["start"]), 3),
        "end": round(float(segments[-1]["end"]), 3),
        "text": text,
        "speaker": _majority_speaker(segments),
        "segment_ids": [s["id"] for s in segments],
        "words": words,
    }


def merge_into_utterances(
    segments: list[dict],
    merge_gap: float = 0.5,
    max_seconds: float = 15.0,
) -> list[dict]:
    """把 Whisper 碎段按确定性规则合并为原句（Utterance）。

    满足任一条件即开启新原句：
    - 与上一段的时间间隙 >= merge_gap（默认 0.5s，Merge Gap）
    - 上一段以句末标点（. ! ?）结尾（真正的句子边界）
    - 并入后原句时长超过 max_seconds（默认 15s，超长单句不硬并）

    纯函数，不依赖 GPU/模型，可直接单测。
    """
    if not segments:
        return []
    utterances: list[dict] = []
    current = [segments[0]]
    for seg in segments[1:]:
        prev = current[-1]
        gap = float(seg["start"]) - float(prev["end"])
        sentence_boundary = _ends_with_sentence_endings(prev.get("text", ""))
        over_limit = (float(seg["end"]) - float(current[0]["start"])) > max_seconds
        if gap < merge_gap and not sentence_boundary and not over_limit:
            current.append(seg)
        else:
            utterances.append(_utterance_from_segments(current, f"u{len(utterances)}"))
            current = [seg]
    utterances.append(_utterance_from_segments(current, f"u{len(utterances)}"))
    return utterances


def assign_utterance_speakers(utterances: list[dict]) -> list[dict]:
    """填充无 speaker 的原句：继承最近的相邻原句说话人（前向补，再后向补）。"""
    last = None
    for utt in utterances:
        if utt.get("speaker"):
            last = utt["speaker"]
        elif last:
            utt["speaker"] = last
    last = None
    for utt in reversed(utterances):
        if utt.get("speaker"):
            last = utt["speaker"]
        elif last:
            utt["speaker"] = last
    return utterances


class Transcriber(BaseTool):
    name = "transcriber"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "whisperx"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["python:faster_whisper", "python:pyannote.audio"]
    install_instructions = (
        "pip install faster-whisper  # CPU mode\n"
        "pip install faster-whisper[gpu]  # GPU mode (requires CUDA)\n"
        "pip install pyannote.audio whisperx  # For diarization support"
    )
    agent_skills = ["speech-to-text"]

    capabilities = [
        "transcribe",
        "word_timestamps",
        "diarization",
        "language_detection",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {"type": "string", "description": "Path to audio or video file"},
            "model_size": {
                "type": "string",
                "enum": ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                "default": "base",
            },
            "language": {"type": "string", "description": "ISO 639-1 language code, or null for auto-detect"},
            "diarize": {"type": "boolean", "default": False},
            "merge_gap": {"type": "number", "default": 0.5, "description": "原句合并最大时间间隙（秒）"},
            "max_utterance_seconds": {"type": "number", "default": 15.0, "description": "原句时长上限（秒），超限不硬并"},
            "output_dir": {"type": "string", "description": "Directory for output files"},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "segments": {"type": "array"},
            "word_timestamps": {"type": "array"},
            "utterances": {
                "type": "array",
                "description": "原句（Utterance）锚点：字幕与逐句时长对齐的单位",
            },
            "language": {"type": "string"},
            "duration_seconds": {"type": "number"},
            "speaker_turns": {
                "type": "array",
                "description": "Diarization turns: [{start, end, speaker}] (empty when not diarized)",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2,
        ram_mb=2048,
        vram_mb=0,  # CPU by default; GPU optional
        disk_mb=500,
        network_required=False,
    )

    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["MemoryError"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["input_path", "model_size", "language"]
    side_effects = ["writes transcript JSON to output_dir"]
    fallback = None
    user_visible_verification = [
        "Check transcript text against source audio",
        "Verify word timestamps align with speech",
    ]

    def get_status(self) -> ToolStatus:
        try:
            import faster_whisper  # noqa: F401
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def _has_diarization(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import whisperx.audio  # noqa: F401
            return True
        except ImportError:
            return False

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        """Rough estimate: ~0.5x real-time on CPU for 'base' model."""
        return 60.0  # conservative default

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        model_size = inputs.get("model_size", "base")
        language = inputs.get("language")
        diarize = inputs.get("diarize", False)
        merge_gap = inputs.get("merge_gap", 0.5)
        max_utterance_seconds = inputs.get("max_utterance_seconds", 15.0)
        output_dir = Path(inputs.get("output_dir", input_path.parent))

        if not input_path.exists():
            return ToolResult(success=False, error=f"Input file not found: {input_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return ToolResult(
                success=False,
                error="faster-whisper is not installed. Run: pip install faster-whisper",
            )

        start = time.time()

        # Load model (CPU by default, CUDA if available)
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
        except ImportError:
            device = "cpu"
            compute_type = "int8"

        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        # Transcribe
        segments_iter, info = model.transcribe(
            str(input_path),
            language=language,
            word_timestamps=True,
            vad_filter=True,
        )

        segments = []
        word_timestamps = []

        for seg in segments_iter:
            seg_data = {
                "id": seg.id,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            }

            if seg.words:
                words = []
                for w in seg.words:
                    word_entry = {
                        "word": w.word,
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "probability": round(w.probability, 3),
                    }
                    words.append(word_entry)
                    word_timestamps.append(word_entry)
                seg_data["words"] = words

            segments.append(seg_data)

        detected_language = language or info.language
        duration = info.duration

        # Optional diarization pass
        if diarize and self._has_diarization():
            segments, speaker_turns = self._apply_diarization(
                str(input_path), segments
            )
        else:
            speaker_turns = []

        # 原句（Utterance）合并：字幕与逐句时长对齐的锚点单位（ADR-003 D1）
        utterances = merge_into_utterances(
            segments,
            merge_gap=float(merge_gap),
            max_seconds=float(max_utterance_seconds),
        )
        utterances = assign_utterance_speakers(utterances)

        elapsed = time.time() - start

        result_data = {
            "segments": segments,
            "word_timestamps": word_timestamps,
            "utterances": utterances,
            "language": detected_language,
            "duration_seconds": round(duration, 3),
            "model_size": model_size,
            "device": device,
            "speaker_turns": speaker_turns,
        }

        # Write transcript JSON
        output_path = output_dir / f"{input_path.stem}_transcript.json"
        output_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

        return ToolResult(
            success=True,
            data=result_data,
            artifacts=[str(output_path)],
            duration_seconds=round(elapsed, 2),
        )

    def _apply_diarization(
        self,
        audio_path: str,
        segments: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Apply pyannote 4.x diarization to assign speaker labels.

        Returns (segments with speaker, speaker_turns). Best-effort: on any
        failure returns (segments, []) so transcription still succeeds.
        """
        try:
            import os

            import torch
            from pyannote.audio import Pipeline
            from whisperx.audio import load_audio

            # Offline model cache under models/hf_cache (gitignored local copy).
            # Offline loading does not require a valid token (verified to load
            # with a dummy token when the cache is warm); real token used when set.
            cache_dir = str(Path(__file__).resolve().parents[2] / "models" / "hf_cache")
            token = os.environ.get("HF_TOKEN", "local-offline")
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            pipeline = Pipeline.from_pretrained(  # type: ignore[attr-defined]
                "pyannote/speaker-diarization-3.1",
                token=token,
                cache_dir=cache_dir,
            ).to(device)  # type: ignore[union-attr]

            # Decode via ffmpeg CLI (librosa path) to avoid torchcodec.
            waveform = load_audio(audio_path)
            wav_tensor = torch.from_numpy(waveform).unsqueeze(0)
            output = pipeline(  # type: ignore[index]
                {
                    "waveform": wav_tensor,
                    "sample_rate": 16000,
                    "uri": audio_path,
                }
            )

            speaker_turns = [
                {
                    "start": round(turn["start"], 3),
                    "end": round(turn["end"], 3),
                    "speaker": turn["speaker"],
                }
                for turn in output.serialize()["diarization"]  # type: ignore[attr-defined]
            ]

            segments = self._assign_speakers(segments, speaker_turns)
            return segments, speaker_turns
        except Exception as exc:  # noqa: BLE001
            # Diarization is best-effort; degrade to no-speaker transcription.
            logging.getLogger(__name__).warning(
                f"Speaker diarization failed, continuing without speakers: {exc}"
            )
            return segments, []

    @staticmethod
    def _assign_speakers(
        segments: list[dict], speaker_turns: list[dict]
    ) -> list[dict]:
        """Assign a speaker to each segment by temporal overlap ratio.

        A segment takes the speaker whose turn covers the largest fraction of
        the segment's own duration. Segments with no overlap keep speaker=None.
        """
        for seg in segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            seg_len = max(seg_end - seg_start, 1e-6)

            best_speaker = None
            best_ratio = 0.0
            for turn in speaker_turns:
                overlap = max(0.0, min(seg_end, turn["end"]) - max(seg_start, turn["start"]))
                ratio = overlap / seg_len
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_speaker = turn["speaker"]

            seg["speaker"] = best_speaker

        return segments
