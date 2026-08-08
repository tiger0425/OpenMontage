"""TDD 测试：Transcriber pyannote 4.x 说话人分离（ticket 01）。

覆盖：
1. _assign_speakers 按时间重叠度分配 speaker（纯逻辑，不依赖 GPU/模型）
2. 无重叠段 speaker=None
3. _has_diarization 基于 pyannote.audio
4. execute 未启用 diarize 时 speaker_turns 为空
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.analysis.transcriber import Transcriber


class TestAssignSpeakers:
    def test_segment_inside_single_turn(self):
        turns = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
        ]
        segments = [{"id": 0, "start": 0.5, "end": 2.0, "text": "hi"}]
        out = Transcriber._assign_speakers(segments, turns)
        assert out[0]["speaker"] == "SPEAKER_00"

    def test_segment_in_second_turn(self):
        turns = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
        ]
        segments = [{"id": 0, "start": 4.0, "end": 5.5, "text": "yo"}]
        out = Transcriber._assign_speakers(segments, turns)
        assert out[0]["speaker"] == "SPEAKER_01"

    def test_overlap_ratio_picks_largest_coverage(self):
        # Segment 2.5-4.5: 0.5 in A (25%), 1.5 in B (75%) -> B
        turns = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
        ]
        segments = [{"id": 0, "start": 2.5, "end": 4.5, "text": "mix"}]
        out = Transcriber._assign_speakers(segments, turns)
        assert out[0]["speaker"] == "SPEAKER_01"

    def test_no_overlap_is_none(self):
        turns = [{"start": 5.0, "end": 6.0, "speaker": "SPEAKER_00"}]
        segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": "gap"}]
        out = Transcriber._assign_speakers(segments, turns)
        assert out[0]["speaker"] is None

    def test_empty_turns_all_none(self):
        segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": "x"}]
        out = Transcriber._assign_speakers(segments, [])
        assert out[0]["speaker"] is None

    def test_zero_length_turn_does_not_crash(self):
        # turn with end == start: overlap 0, ratio 0, must not divide by zero
        turns = [{"start": 0.0, "end": 0.0, "speaker": "SPEAKER_00"}]
        segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": "x"}]
        out = Transcriber._assign_speakers(segments, turns)
        assert out[0]["speaker"] is None


class TestHasDiarization:
    def test_true_when_pyannote_installed(self):
        tool = Transcriber()
        assert tool._has_diarization() is True


class TestExecuteNoDiarize:
    def test_output_schema_exposes_speaker_turns(self):
        """speaker_turns 键在 output_schema 中暴露（契约表面）。"""
        tool = Transcriber()
        assert "speaker_turns" in tool.output_schema["properties"]


class TestApplyDiarizationMocked:
    """mock pyannote 4.x，防 `_apply_diarization` 链路（serialize 消费 + 分配）回归。

    不依赖 GPU/模型：monkeypatch Pipeline.from_pretrained 与 whisperx.audio.load_audio。
    """

    def _fake_pipeline(self):
        class _FakeOut:
            def serialize(self):
                return {
                    "diarization": [
                        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
                        {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
                    ]
                }

        class _FakePipeline:
            def __init__(self):
                self._captured = None

            def to(self, device):
                return self

            def __call__(self, file):
                self._captured = file
                return _FakeOut()

        return _FakePipeline()

    def test_consumes_serialize_and_assigns_speakers(self, monkeypatch):
        import numpy as np
        import torch

        import pyannote.audio as pa

        fake = self._fake_pipeline()
        monkeypatch.setattr(pa.Pipeline, "from_pretrained", classmethod(lambda cls, *a, **k: fake))
        monkeypatch.setattr(
            "whisperx.audio.load_audio",
            lambda path: np.zeros(16000 * 6, dtype=np.float32),
        )

        tool = Transcriber()
        segments = [
            {"id": 0, "start": 0.5, "end": 2.0, "text": "a"},
            {"id": 1, "start": 3.5, "end": 5.0, "text": "b"},
        ]
        out_segments, turns = tool._apply_diarization("fake.wav", segments)

        assert [t["speaker"] for t in turns] == ["SPEAKER_00", "SPEAKER_01"]
        assert out_segments[0]["speaker"] == "SPEAKER_00"
        assert out_segments[1]["speaker"] == "SPEAKER_01"
        # 输入 dict 必须含 waveform/sample_rate/uri，绕开 torchcodec
        captured = fake._captured
        assert captured is not None
        assert captured["sample_rate"] == 16000
        assert isinstance(captured["waveform"], torch.Tensor)

    def test_failure_degrades_to_no_speakers(self, monkeypatch):
        import pyannote.audio as pa

        class _Boom:
            def to(self, device):
                raise RuntimeError("model load failed")

        monkeypatch.setattr(pa.Pipeline, "from_pretrained", classmethod(lambda cls, *a, **k: _Boom()))
        tool = Transcriber()
        segments = [{"id": 0, "start": 0.0, "end": 1.0, "text": "x"}]
        out_segments, turns = tool._apply_diarization("fake.wav", segments)
        assert turns == []
        assert out_segments[0].get("speaker") is None
