"""TDD 测试：声纹参考多段择优拼接（ticket 02）。

覆盖：
1. _select_voice_ref_candidates：甜点段优先、短段补足、长段截断、目标时长封顶、不足跳过
2. _build_stitched_voice_ref / _stitch_ref_chunks：多段切出拼接、峰值归一化、失败清理
3. 旧 _select_voice_ref_intervals 兼容（单段最长，供既有路径/回归）
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


def _make_automator(tmp_path):
    """构造最小 PipelineAutomator 实例（绕过重量级 __init__），带默认 voice_ref 参数。"""
    inst = object.__new__(PipelineAutomator)
    inst.assets_dir = Path(tmp_path) / "assets"
    inst.assets_dir.mkdir(parents=True, exist_ok=True)
    inst.source_video = Path(tmp_path) / "source.mp4"
    inst.voice_ref_target = 30.0
    inst.voice_ref_min_seconds = 6.0
    inst.voice_ref_sweet_min = 1.5
    inst.voice_ref_sweet_max = 12.0
    inst.voice_ref_long_cap = 15.0
    inst.ref_merge_enabled = False  # 单测跳过 pyannote 合并（慢）
    return inst


class TestSelectVoiceRefCandidates:
    def test_prefers_sweet_spot_segments(self):
        inst = _make_automator(Path("."))
        turns = [
            {"start": 0.0, "end": 2.0, "speaker": "A"},    # 甜点
            {"start": 3.0, "end": 20.0, "speaker": "A"},   # 超甜点 -> 截断
            {"start": 0.5, "end": 0.9, "speaker": "B"},    # 太短 -> 跳过
        ]
        cands = inst._select_voice_ref_candidates(turns)
        assert "A" in cands
        assert "B" not in cands
        # A 的候选应为 1 个甜点段 + 长段截断块
        total = sum(e - s for s, e in cands["A"])
        assert total >= inst.voice_ref_min_seconds

    def test_accumulates_to_target_seconds(self):
        inst = _make_automator(Path("."))
        # 多个小甜点段，累计接近 target
        turns = [
            {"start": float(i * 13.0), "end": float(i * 13.0 + 10.0), "speaker": "A"}
            for i in range(6)  # 6 * 10s = 60s，应封顶 30s
        ]
        cands = inst._select_voice_ref_candidates(turns)
        total = sum(e - s for s, e in cands["A"])
        assert total <= inst.voice_ref_target + 0.001

    def test_short_speaker_skipped(self):
        inst = _make_automator(Path("."))
        turns = [
            {"start": 0.0, "end": 3.0, "speaker": "A"},   # 只有 3s，< min 6s
        ]
        cands = inst._select_voice_ref_candidates(turns)
        assert "A" not in cands

    def test_sweet_spot_preferred_over_long(self):
        inst = _make_automator(Path("."))
        # 甜点段(8s) + 长段(30s) 都有时，甜点先被选中
        turns = [
            {"start": 0.0, "end": 8.0, "speaker": "A"},
            {"start": 10.0, "end": 40.0, "speaker": "A"},
        ]
        cands = inst._select_voice_ref_candidates(turns)
        # 第一个候选应是甜点段
        assert cands["A"][0] == (0.0, 8.0)

    def test_candidates_sorted_chronological(self):
        inst = _make_automator(Path("."))
        turns = [
            {"start": 20.0, "end": 30.0, "speaker": "A"},
            {"start": 0.0, "end": 10.0, "speaker": "A"},
        ]
        cands = inst._select_voice_ref_candidates(turns)
        starts = [s for s, e in cands["A"]]
        assert starts == sorted(starts)


class TestStitchRef:
    def test_stitch_ref_chunks_writes_file(self, tmp_path):
        inst = _make_automator(tmp_path)
        # 造两个真实 wav 块
        import numpy as np
        import soundfile as sf
        c1 = inst.assets_dir / "c1.wav"
        c2 = inst.assets_dir / "c2.wav"
        sf.write(c1, np.zeros(48000, dtype=np.float32), 24000)   # 2s
        sf.write(c2, np.ones(24000, dtype=np.float32) * 0.5, 24000)  # 1s, peak 0.5
        out = inst.assets_dir / "stitched.wav"
        assert inst._stitch_ref_chunks([c1, c2], out)
        assert out.exists()
        data, sr = sf.read(out)
        assert abs(len(data) / sr - 3.0) < 0.05
        assert abs(float(np.abs(data).max()) - 0.5) < 0.05  # 未超 0.9 不缩放

    def test_stitch_ref_peak_normalizes_above_09(self, tmp_path):
        inst = _make_automator(tmp_path)
        import numpy as np
        import soundfile as sf
        c = inst.assets_dir / "c.wav"
        sf.write(c, np.full(24000, 0.99, dtype=np.float32), 24000)  # peak 0.99 > 0.9
        out = inst.assets_dir / "stitched.wav"
        assert inst._stitch_ref_chunks([c], out)
        data, _ = sf.read(out)
        assert abs(float(np.abs(data).max()) - 0.9) < 0.01

    def test_empty_chunks_fails(self, tmp_path):
        inst = _make_automator(tmp_path)
        assert not inst._stitch_ref_chunks([], inst.assets_dir / "out.wav")


class TestSelectVoiceRefIntervalsCompat:
    """旧单段最长逻辑保留（既有路径/回归）。"""

    def test_three_speakers_get_intervals(self):
        turns = [
            {"start": 0.0, "end": 10.0, "speaker": "A"},
            {"start": 12.0, "end": 22.0, "speaker": "B"},
            {"start": 24.0, "end": 34.0, "speaker": "C"},
        ]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        assert set(intervals) == {"A", "B", "C"}

    def test_prefers_longest_span(self):
        turns = [
            {"start": 0.0, "end": 4.0, "speaker": "A"},
            {"start": 30.0, "end": 45.0, "speaker": "A"},
        ]
        intervals = PipelineAutomator._select_voice_ref_intervals(turns)
        assert intervals["A"] == (31.0, 45.0)


class TestExtractSpeakerVoiceRefsStitch:
    def test_two_speakers_generate_stitched_refs(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)

        # mock ffmpeg 切块成功：落盘一个真实 wav（用 soundfile 写）
        import numpy as np
        import soundfile as sf

        def _fake_run(cmd, **kw):
            # 从 cmd 提取 -ss/-t/输出路径，写一个真实 wav
            args = list(cmd)
            start = float(args[args.index("-ss") + 1])
            dur = float(args[args.index("-t") + 1])
            out = args[-1]
            sf.write(out, np.zeros(int(dur * 24000), dtype=np.float32), 24000)
            return __import__("subprocess").CompletedProcess(args=[], returncode=0)

        monkeypatch.setattr(
            "batch.pipeline_automator.subprocess.run", _fake_run
        )

        turns = [
            {"start": 0.0, "end": 8.0, "speaker": "A"},
            {"start": 10.0, "end": 18.0, "speaker": "B"},
        ]
        refs = inst._extract_speaker_voice_refs(turns)
        assert set(refs) == {"A", "B"}
        for path in refs.values():
            assert Path(path).exists()

    def test_single_speaker_returns_empty(self, tmp_path):
        inst = _make_automator(tmp_path)
        assert inst._extract_speaker_voice_refs(
            [{"start": 0.0, "end": 30.0, "speaker": "A"}]
        ) == {}

    def test_no_turns_returns_empty(self, tmp_path):
        inst = _make_automator(tmp_path)
        assert inst._extract_speaker_voice_refs([]) == {}
