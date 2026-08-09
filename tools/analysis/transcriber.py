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


def _subseg(words: list[dict], speaker) -> dict:
    """从 word 列表构造一个 speaker 子段（含文本/时间/words）。"""
    text = " ".join(w.get("word", "") for w in words if w.get("word")).strip()
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)
    return {
        "id": None,  # 切分子段无独立 id，由上游分配
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "text": text,
        "speaker": speaker,
        "words": words,
        "split": True,
    }


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


# ============================================================
# 分段清理链（ticket 01，对标 tachidubb segment_post.py）
# 作用于 diarization 之后的 segments（带 speaker 标签），在原句合并前。
# 三个 pass：合并续句 -> 吸收微段 -> 拆超长段。纯函数，可单测。
# ============================================================

# 句末标点：完整句子的边界（合并续句时视为"已说完"）
_SENTENCE_END_RE = __import__("re").compile(r'[.!?]["\']?\s*$')
# 强断句点：用于拆分超长段（. ! ? 后跟空白/结尾）
_STRONG_BREAK_RE = __import__("re").compile(r'[.!?]["\']?\s+')


def postprocess_segments(
    segments: list[dict],
    merge_gap: float = 0.5,
    max_merge_duration: float = 15.0,
    max_merge_chars: int = 240,
    split_threshold: float = 15.0,
    micro_duration: float = 1.0,
    micro_chars: int = 40,
) -> list[dict]:
    """分段清理链：合并续句 -> 吸收微段 -> 拆超长段。

    在 speaker 分配之后、原句合并之前调用，返回清理后的 segments（新列表）。
    """
    if not segments:
        return segments
    out = _merge_continuation_segments(
        segments, merge_gap, max_merge_duration, max_merge_chars
    )
    out = _absorb_micro_segments(out, micro_duration, micro_chars)
    out = _split_very_long_segments(out, split_threshold)
    return out


def _merge_continuation_segments(
    segments: list[dict],
    merge_gap: float,
    max_dur: float,
    max_chars: int,
) -> list[dict]:
    """合并续句：相邻段同说话人、间隙 <= merge_gap、前段未以句末标点结尾
    （或间隙 < 0.2s 视为短语中切断）且合并后不超时长/字符上限 -> 并入。

    WhisperX 常按呼吸（VAD）切句，把 "who's the most spaz? Nicky" 切成两段；
    本 pass 把未完句的续接合并回去，避免 TTS 拿十几个字符克隆音色。
    """
    if len(segments) < 2:
        return [dict(s) for s in segments]

    out = [dict(segments[0])]
    joined = 0
    for curr in segments[1:]:
        prev = out[-1]
        prev_spk = prev.get("speaker")
        curr_spk = curr.get("speaker")
        same_speaker = (prev_spk == curr_spk) or not prev_spk or not curr_spk

        gap = float(curr["start"]) - float(prev["end"])
        prev_text = (prev.get("text") or "").rstrip()
        prev_unfinished = not _SENTENCE_END_RE.search(prev_text)

        combined_dur = float(curr["end"]) - float(prev["start"])
        combined_chars = len(prev_text) + 1 + len((curr.get("text") or "").strip())

        should_merge = (
            same_speaker
            and gap <= merge_gap
            and (prev_unfinished or gap < 0.2)
            and combined_dur <= max_dur
            and combined_chars <= max_chars
        )
        if should_merge:
            prev["end"] = round(float(curr["end"]), 3)
            prev["text"] = (prev_text + " " + (curr.get("text") or "").strip()).strip()
            if "words" in prev and "words" in curr:
                prev["words"] = prev["words"] + curr["words"]
            joined += 1
        else:
            out.append(dict(curr))

    logging.getLogger(__name__).debug(
        f"[post] Pass 1: joined {joined} continuation segments"
    )
    return out


def _absorb_micro_segments(
    segments: list[dict],
    threshold_sec: float,
    threshold_chars: int,
) -> list[dict]:
    """吸收微段：< threshold_sec 且 < threshold_chars 的段并入前段（同说话人、
    间隙 < 1.5s），否则并入后段。这些通常是 pyannote 假说话人翻转产生的
    <1s 孤儿片段，TTS 无法稳定克隆。
    """
    if len(segments) < 2:
        return [dict(s) for s in segments]

    out: list[dict] = []
    absorbed = 0
    i = 0
    while i < len(segments):
        seg = dict(segments[i])
        dur = float(seg["end"]) - float(seg["start"])
        text = (seg.get("text") or "").strip()
        is_micro = dur < threshold_sec and len(text) < threshold_chars

        if is_micro and out:
            prev = out[-1]
            prev_gap = float(seg["start"]) - float(prev["end"])
            prev_same_spk = (
                prev.get("speaker") == seg.get("speaker")
                or not prev.get("speaker")
                or not seg.get("speaker")
            )
            if prev_same_spk and prev_gap < 1.5:
                prev["end"] = round(float(seg["end"]), 3)
                prev["text"] = (
                    (prev.get("text") or "").rstrip() + " " + text
                ).strip()
                if "words" in prev and "words" in seg:
                    prev["words"] = prev["words"] + seg["words"]
                absorbed += 1
                i += 1
                continue

        if is_micro and i + 1 < len(segments):
            nxt = segments[i + 1]
            next_gap = float(nxt["start"]) - float(seg["end"])
            next_same_spk = (
                nxt.get("speaker") == seg.get("speaker")
                or not nxt.get("speaker")
                or not seg.get("speaker")
            )
            if next_same_spk and next_gap < 1.5:
                merged = dict(nxt)
                merged["start"] = round(float(seg["start"]), 3)
                merged["text"] = (text + " " + (nxt.get("text") or "").strip()).strip()
                if "words" in seg and "words" in nxt:
                    merged["words"] = seg["words"] + nxt["words"]
                segments[i] = merged
                segments[i + 1] = merged
                i += 1
                absorbed += 1
                continue

        out.append(seg)
        i += 1

    logging.getLogger(__name__).debug(
        f"[post] Pass 2: absorbed {absorbed} micro-segments "
        f"(<{threshold_sec}s and <{threshold_chars} chars)"
    )
    return out


def _split_very_long_segments(
    segments: list[dict],
    threshold: float,
) -> list[dict]:
    """拆超长段：> threshold 秒且文本 >= 40 字符的段，在 .!? 强断句点
    （离两端 > 20 字符）处就近中位拆分；无边界则不拆（宁长勿裂）。
    避免超长段在装配阶段被迫强变速。
    """
    out: list[dict] = []
    split_count = 0
    for seg in segments:
        dur = float(seg["end"]) - float(seg["start"])
        text = seg.get("text") or ""
        if dur <= threshold or len(text) < 40:
            out.append(dict(seg))
            continue

        boundaries = [
            m.end()
            for m in _STRONG_BREAK_RE.finditer(text)
            if 20 < m.end() < len(text) - 20
        ]
        if not boundaries:
            out.append(dict(seg))
            continue

        middle = len(text) / 2
        best = min(boundaries, key=lambda b: abs(b - middle))
        frac = best / len(text)
        split_time = float(seg["start"]) + dur * frac

        first = dict(seg)
        first["end"] = round(split_time, 3)
        first["text"] = text[:best].strip()

        second = dict(seg)
        second["start"] = round(split_time, 3)
        second["text"] = text[best:].strip()

        if "words" in seg:
            n = len(seg["words"])
            cut = int(n * frac)
            first["words"] = seg["words"][:cut]
            second["words"] = seg["words"][cut:]

        out.extend([first, second])
        split_count += 1

    logging.getLogger(__name__).debug(
        f"[post] Pass 3: split {split_count} long segments "
        f"(>{threshold}s at sentence boundaries)"
    )
    return out


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
            "segment_postprocess": {"type": "boolean", "default": True, "description": "是否启用分段清理链（合并续句/吸收微段/拆超长段）"},
            "micro_duration": {"type": "number", "default": 1.0, "description": "分段清理：微段时长阈值（秒）"},
            "micro_chars": {"type": "number", "default": 40, "description": "分段清理：微段字符阈值"},
            "split_threshold": {"type": "number", "default": 15.0, "description": "分段清理：超长段拆分阈值（秒）"},
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
        segment_postprocess = inputs.get("segment_postprocess", True)
        micro_duration = inputs.get("micro_duration", 1.0)
        micro_chars = inputs.get("micro_chars", 40)
        split_threshold = inputs.get("split_threshold", 15.0)
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

        # 分段清理链（ticket 01）：合并续句/吸收微段/拆超长段，在 speaker 分配后、
        # 原句合并前应用，治理假说话人翻转微段与按呼吸切句。
        if segment_postprocess and segments:
            segments = postprocess_segments(
                segments,
                merge_gap=float(merge_gap),
                max_merge_duration=float(max_utterance_seconds),
                split_threshold=float(split_threshold),
                micro_duration=float(micro_duration),
                micro_chars=int(micro_chars),
            )

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

            # 合并分裂的说话人 cluster（tt-test 反馈：pyannote 把同一人分裂成多 label，
            # 导致音色差别大/错配）。用 speaker embedding 相似度 > 阈值合并。
            # 无 embedding 组件（如测试 fake）时跳过合并，直接使用原始 turns。
            if hasattr(pipeline, "_embedding") and pipeline._embedding is not None:
                speaker_turns = self._merge_speaker_clusters(
                    speaker_turns, waveform, wav_tensor, emb_model=pipeline._embedding
                )

            segments = self._assign_speakers(segments, speaker_turns)
            return segments, speaker_turns
        except Exception as exc:  # noqa: BLE001
            # Diarization is best-effort; degrade to no-speaker transcription.
            logging.getLogger(__name__).warning(
                f"Speaker diarization failed, continuing without speakers: {exc}"
            )
            return segments, []

    @staticmethod
    def _merge_speaker_clusters(
        speaker_turns: list[dict],
        waveform,
        wav_tensor,
        emb_model,
        similarity_threshold: float = 0.7,
        min_samples_seconds: float = 2.0,
    ) -> list[dict]:
        """合并被 pyannote 分裂的同一说话人 cluster（解决音色差别大/错配）。

        方法：对每个 cluster 提取一段代表性音频的 speaker embedding，两两算余弦相似度；
        相似度 >= threshold 的 cluster 合并（重命名为同一 label）。簇内代表性音频取
        该 cluster 所有 turn 中总时长最长的一段（>= min_samples_seconds）。

        返回重命名后的 speaker_turns。任何异常回退原 turns（best-effort）。
        """
        if not speaker_turns:
            return speaker_turns
        try:
            import numpy as np
            import torch

            # 1) 按 cluster 分组，取代表性区间（时长最长）
            by_spk: dict[str, list[tuple]] = {}
            for t in speaker_turns:
                by_spk.setdefault(t["speaker"], []).append((t["start"], t["end"]))
            speakers = sorted(by_spk.keys())
            if len(speakers) < 2:
                return speaker_turns

            # 2) 提取每个 cluster 的 embedding
            sr = 16000
            embs: dict[str, np.ndarray] = {}
            for spk in speakers:
                turns = sorted(by_spk[spk], key=lambda x: x[1] - x[0], reverse=True)
                best = None
                for s, e in turns:
                    if e - s >= min_samples_seconds:
                        best = (s, e)
                        break
                if best is None:
                    best = turns[0]
                s, e = best
                clip = wav_tensor[..., int(s * sr):int(e * sr)]
                if clip.numel() == 0:
                    continue
                with torch.no_grad():
                    emb = np.array(emb_model(clip.unsqueeze(0).to(emb_model.device))).reshape(-1)
                embs[spk] = emb

            if len(embs) < 2:
                return speaker_turns

            # 3) 贪心合并：相似度 >= threshold 的 label 映射到同一目标
            def _sim(a: np.ndarray, b: np.ndarray) -> float:
                return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

            label_map: dict[str, str] = {}
            for spk in speakers:
                label_map[spk] = spk
            for i in range(len(speakers)):
                for j in range(i + 1, len(speakers)):
                    a, b = speakers[i], speakers[j]
                    if a not in embs or b not in embs:
                        continue
                    if _sim(embs[a], embs[b]) >= similarity_threshold:
                        # 合并：统一用序号较小的 label
                        label_map[b] = label_map[a]

            merged = len({label_map[s] for s in speakers})
            if merged == len(speakers):
                return speaker_turns

            logging.getLogger(__name__).info(
                f"[diarization] 合并说话人 cluster: {len(speakers)} -> {merged} "
                f"(label_map={label_map})"
            )
            renamed = []
            for t in speaker_turns:
                nt = dict(t)
                nt["speaker"] = label_map.get(t["speaker"], t["speaker"])
                renamed.append(nt)
            return renamed
        except Exception as exc:
            logging.getLogger(__name__).warning(
                f"说话人 cluster 合并失败，回退原始 turns: {exc}"
            )
            return speaker_turns

    @staticmethod
    def _assign_speakers(
        segments: list[dict], speaker_turns: list[dict]
    ) -> list[dict]:
        """Assign speaker labels to segments, splitting on speaker changes.

        Word-level assignment: each word takes the speaker whose turn covers its
        midpoint (more accurate than segment-level overlap for cross-talk). If
        words within one Whisper segment belong to different speakers (e.g. a
        question by host + short answer by another person), the segment is split
        at the speaker-change boundary into sub-segments, each carrying its own
        speaker. This fixes the "host asks, other answers" case where the whole
        segment was forced to a single voice.
        """
        out_segments: list[dict] = []

        def _speaker_at(t: float) -> str | None:
            best_spk = None
            best_overlap = 0.0
            for turn in speaker_turns:
                if turn["start"] <= t <= turn["end"]:
                    # 选覆盖该时刻的 turn；重叠时选更短的（更精确）
                    d = turn["end"] - turn["start"]
                    if best_overlap == 0.0 or d < best_overlap:
                        best_overlap = d
                        best_spk = turn["speaker"]
            return best_spk

        for seg in segments:
            words = seg.get("words")
            seg_start = seg["start"]
            seg_end = seg["end"]
            # segment 级兜底 speaker（无 words 或全无归属时用）
            seg_len = max(seg_end - seg_start, 1e-6)
            seg_best = None
            seg_best_ratio = 0.0
            for turn in speaker_turns:
                overlap = max(0.0, min(seg_end, turn["end"]) - max(seg_start, turn["start"]))
                ratio = overlap / seg_len
                if ratio > seg_best_ratio:
                    seg_best_ratio = ratio
                    seg_best = turn["speaker"]

            if not words:
                seg["speaker"] = seg_best
                out_segments.append(seg)
                continue

            # 为每个 word 分配 speaker（word 级）
            word_spks: list[str | None] = []
            for w in words:
                mid = (w.get("start", 0) + w.get("end", 0)) / 2.0
                spk = _speaker_at(mid)
                if spk is None:
                    # 无 turn 覆盖该词 -> 继承前一词或 segment 兜底
                    spk = word_spks[-1] if word_spks else seg_best
                word_spks.append(spk)

            # 按 speaker 切换切分 words
            sub_segments: list[dict] = []
            cur_words: list[dict] = []
            cur_spk = None
            for w, spk in zip(words, word_spks):
                if cur_spk is None:
                    cur_spk = spk
                if spk != cur_spk:
                    if cur_words:
                        sub_segments.append(_subseg(cur_words, cur_spk))
                    cur_words = [w]
                    cur_spk = spk
                else:
                    cur_words.append(w)
            if cur_words:
                sub_segments.append(_subseg(cur_words, cur_spk))

            if len(sub_segments) <= 1:
                # 无说话人切换，保留原 segment（speaker = 主要说话人）
                seg["speaker"] = sub_segments[0]["speaker"] if sub_segments else seg_best
                out_segments.append(seg)
            else:
                # 有切换：用切分后的子段替换原 segment
                out_segments.extend(sub_segments)

        return out_segments
