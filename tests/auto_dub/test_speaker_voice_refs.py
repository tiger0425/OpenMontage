"""TDD 测试：按 speaker 提取 voice_ref（ticket 06）。

覆盖：
1. _select_voice_ref_intervals：多 speaker 各得一段区间；同 speaker 邻近 turn 合并；过短 speaker 跳过
2. _extract_speaker_voice_refs：< 2 speaker 返回空映射（回退单声纹路径）；多 speaker 生成对应数量文件
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.pipeline_automator import PipelineAutomator


class TestSelectVoiceRefIntervals:
    def test_three_speakers_get_intervals(self):
        turns = [
            {"start": 0.0, "end": 10.0, "speaker": "A"},
            {"start": 12.0, "end": 22.0, "speaker": "B"},
            {"start": 24.0, "end": 34.0, "speaker": "C"},
        ]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        assert set(intervals) == {"A", "B", "C"}

    def test_merges_close_turns_same_speaker(self):
        turns = [
            {"start": 0.0, "end": 4.0, "speaker": "A"},
            {"start": 4.5, "end": 9.0, "speaker": "A"},  # 间隙 0.5 < min_gap 1.0 -> 合并
        ]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        # 合并后跨度 (0,9)，起点避开语音边界 +1s
        assert intervals["A"] == (1.0, 9.0)

    def test_speaker_too_short_skipped(self):
        turns = [{"start": 0.0, "end": 1.0, "speaker": "A"}]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns, min_dur=5.0)
        assert "A" not in intervals

    def test_single_speaker_returns_its_interval(self):
        # 纯函数：返回该 speaker 的区间；是否启用多音色由调用方判定
        turns = [{"start": 0.0, "end": 20.0, "speaker": "A"}]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        # 起点 +1s 避边界，长度封顶 15s
        assert intervals == {"A": (1.0, 16.0)}

    def test_prefers_longest_span(self):
        turns = [
            {"start": 0.0, "end": 4.0, "speaker": "A"},
            {"start": 30.0, "end": 45.0, "speaker": "A"},  # 更长
        ]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        assert intervals["A"] == (31.0, 45.0)


class TestExtractSpeakerVoiceRefs:
    def _make_automator(self, tmp_path):
        """构造最小 PipelineAutomator 实例（绕过重量级 __init__）。"""
        inst = object.__new__(PipelineAutomator)
        inst.assets_dir = Path(tmp_path) / "assets"
        inst.assets_dir.mkdir(parents=True, exist_ok=True)
        inst.source_video = Path(tmp_path) / "source.mp4"
        return inst

    def test_single_speaker_returns_empty(self, tmp_path, monkeypatch):
        inst = self._make_automator(tmp_path)
        refs = inst._extract_speaker_voice_refs(
            [{"start": 0.0, "end": 30.0, "speaker": "A"}]
        )
        assert refs == {}

    def test_no_turns_returns_empty(self, tmp_path):
        inst = self._make_automator(tmp_path)
        assert inst._extract_speaker_voice_refs([]) == {}

    def test_two_speakers_generates_two_refs(self, tmp_path, monkeypatch):
        inst = self._make_automator(tmp_path)

        # 模拟 ffmpeg 切片成功
        monkeypatch.setattr(
            "batch.pipeline_automator.subprocess.run",
            lambda *a, **k: __import__("subprocess").CompletedProcess(args=[], returncode=0),
        )

        # 模拟 AudioSegment.from_wav 返回一个足够长、可归一化的音频对象
        class _FakeAudio:
            duration_seconds = 12.0
            rms = 1000

            def apply_gain(self, gain):
                return self

            def export(self, out_path, *a, **k):
                Path(out_path).write_bytes(b"\x00" * 4096)  # 落盘，模拟实际导出

        import batch.pipeline_automator as pa
        monkeypatch.setattr(pa.AudioSegment, "from_wav", staticmethod(lambda path: _FakeAudio()))

        turns = [
            {"start": 0.0, "end": 15.0, "speaker": "A"},
            {"start": 20.0, "end": 35.0, "speaker": "B"},
        ]
        refs = inst._extract_speaker_voice_refs(turns)
        assert set(refs) == {"A", "B"}
        for path in refs.values():
            assert Path(path).exists()
