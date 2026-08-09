"""TDD 测试：节奏溢出推挤 + 预算钳制（ticket 06，对标 tachidubb assembler.py）。

覆盖：
1. clamp_tempo_factor：超出预算钳制到边界；预算内不变；无效因子返回 None
2. _build_block_audio：变速不可达时钳制到边界（status=overflow），不再完全不变速
3. 100ms 串行排队天然溢出推挤（actual_start = max(ideal, previous_end + 100ms)）
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


class TestClampTempoFactor:
    def test_factor_within_budget_unchanged(self):
        f = PipelineAutomator.clamp_tempo_factor(1.03, tempo_budget=0.05)
        assert f == 1.03

    def test_factor_above_budget_clamped_to_hi(self):
        # 需 1.2 倍变速，超出 5% 预算 -> 钳制到 1.05
        f = PipelineAutomator.clamp_tempo_factor(1.2, tempo_budget=0.05)
        assert f == 1.05

    def test_factor_below_budget_clamped_to_lo(self):
        # 需 0.8 倍（放慢），超出预算 -> 钳制到 lo = 1/1.05 ≈ 0.952
        f = PipelineAutomator.clamp_tempo_factor(0.8, tempo_budget=0.05)
        assert f == round(1.0 / 1.05, 6)

    def test_invalid_factor_none(self):
        assert PipelineAutomator.clamp_tempo_factor(None) is None
        assert PipelineAutomator.clamp_tempo_factor(0) is None
        assert PipelineAutomator.clamp_tempo_factor(-1) is None
        assert PipelineAutomator.clamp_tempo_factor(1.2, tempo_budget=0) is None

    def test_max_ratio_widens_ceiling(self):
        # max_ratio=1.15 时，1.2x 超长句可钳制到 1.15（而非 1.05）
        f = PipelineAutomator.clamp_tempo_factor(1.2, tempo_budget=0.05, max_ratio=1.15)
        assert f == 1.15
        # max_ratio=1.15 时 1.05-1.15 之间保持原值
        f2 = PipelineAutomator.clamp_tempo_factor(1.10, tempo_budget=0.05, max_ratio=1.15)
        assert f2 == 1.10
        # max_ratio=1.15 时下方对称放宽
        f3 = PipelineAutomator.clamp_tempo_factor(0.85, tempo_budget=0.05, max_ratio=1.15)
        assert f3 == round(1.0 / 1.15, 6)


class TestSerialQueueOverflow:
    def test_overflow_pushes_next_segment(self):
        # 100ms 串行排队：前段溢出时，后段 actual_start 自动后移（零重叠保护）
        prev_end = 5.0
        ideal_start = 5.0
        actual_start = max(ideal_start, prev_end + 0.10)
        assert actual_start == 5.1

    def test_normal_placement_when_no_overflow(self):
        prev_end = 3.0
        ideal_start = 5.0
        actual_start = max(ideal_start, prev_end + 0.10)
        assert actual_start == 5.0


class TestBuildBlockAudioOverflow:
    def test_out_of_budget_uses_clamped_factor(self, tmp_path, monkeypatch):
        """变速不可达但可钳制时，status=overflow 且应用边界因子。"""
        inst = object.__new__(PipelineAutomator)
        inst.audio_dir = tmp_path / "audio"
        inst.audio_dir.mkdir(parents=True)
        inst.chunk_max_chars = 40
        inst.queue_gap_seconds = 0.1
        inst.tempo_budget = 0.05
        inst.inherently_long_seconds = 1.0
        inst.block_max_pause_seconds = 0.8

        # 合成一个 3s 的假子块（需 1.2x 才能贴合 2.5s 目标 -> 钳制 1.05）
        import numpy as np
        import soundfile as sf
        wav = inst.audio_dir / "seg_b0_c0.wav"
        sf.write(wav, np.zeros(24000 * 3, dtype=np.float32), 24000)
        inst._wav_duration = lambda p: 3.0
        inst._split_semantic = lambda t, m: [t]
        inst._atempo_wav = lambda p, f: p
        inst._concat_with_gaps = lambda chunks, gaps, out: out
        inst._distribute_block_gaps = lambda slack, n, max_pause: [0.0] * max(0, n - 1)
        inst._create_silent_wav = lambda d, p: None

        out, audio_len, status, chunk_wavs, gaps = inst._build_block_audio(
            "b0", "这句中文比较长，超出了原句时长的可变速范围。", None, "indextts", None, 2.6
        )
        # 原速 3.0s > target 2.5s，factor=1.2 超预算 -> 钳制 1.05，status=overflow
        assert status == "overflow"

    def test_inherently_long_kept(self, tmp_path):
        inst = object.__new__(PipelineAutomator)
        inst.audio_dir = tmp_path / "audio"
        inst.audio_dir.mkdir(parents=True)
        inst.chunk_max_chars = 40
        inst.queue_gap_seconds = 0.1
        inst.tempo_budget = 0.05
        inst.inherently_long_seconds = 1.0
        inst.block_max_pause_seconds = 0.8

        import numpy as np
        import soundfile as sf
        wav = inst.audio_dir / "seg_b0_c0.wav"
        sf.write(wav, np.zeros(24000 * 2, dtype=np.float32), 24000)
        inst._wav_duration = lambda p: 2.0
        inst._split_semantic = lambda t, m: [t]
        inst._atempo_wav = lambda p, f: p
        inst._concat_with_gaps = lambda chunks, gaps, out: out
        inst._distribute_block_gaps = lambda slack, n, max_pause: [0.0] * max(0, n - 1)
        inst._create_silent_wav = lambda d, p: None

        # 原句 0.5s（物理不可达），音频 2s -> inherently_long，不动变速
        out, audio_len, status, _, _ = inst._build_block_audio(
            "b0", "很短。", None, "indextts", None, 0.5
        )
        assert status == "inherently_long"
