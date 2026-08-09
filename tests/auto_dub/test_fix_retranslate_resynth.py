"""TDD 测试：修复缩短重翻子块复用 bug + IndexTTS2 测速带声纹。

背景（tt-test 双人验证暴露）：
A. `_build_utterance_audio` 重翻第二次调用复用旧子块 → 字幕是短译文、音频仍是长译文。
   修复：force_resynthesize=True 时先清该句子块（含变速副本）再重合成。
B. `_calibrate_indextts_cps` 测速请求不带 voice_ref → 服务端报错 → 回退 cps=4.0。
   修复：测速前若无声纹，先用源视频现提一个。
"""

import sys
import json
import threading
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from pydub import AudioSegment
from batch.pipeline_automator import PipelineAutomator


class _FakeIndexTTSProc:
    """模拟 IndexTTS2 常驻服务进程：记录请求、固定返回 ok。"""

    def __init__(self):
        class _Stdio:
            def __init__(self):
                self.written = []

            def write(self, s):
                self.written.append(s)

            def flush(self):
                pass

            def readline(self):
                return '{"ok": true}\n'

        self.stdin = _Stdio()
        self.stdout = _Stdio()


def _make_automator(tmp_path):
    inst = object.__new__(PipelineAutomator)
    inst.audio_dir = Path(tmp_path) / "audio"
    inst.audio_dir.mkdir(parents=True, exist_ok=True)
    inst.chunk_max_chars = 40
    inst.queue_gap_seconds = 0.1
    inst.tempo_budget = 0.05
    inst.inherently_long_seconds = 1.0
    inst.block_max_pause_seconds = 0.8
    inst.tts_engine = "indextts"
    return inst


def _silent(path, ms=2000):
    AudioSegment.silent(duration=ms).export(str(path), format="wav")


class TestForceResynthesize:
    def test_force_resynthesize_replaces_old_chunks(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        # 预置旧子块与旧变速副本
        _silent(inst.audio_dir / "seg_b0_c0.wav", 2000)
        tempo_stale = inst.audio_dir / "seg_b0_c0_t981.wav"
        _silent(tempo_stale, 2000)

        synthesized = []

        def fake_synth(text, output_path, voice_ref=None, seed=42, target_duration=None):
            synthesized.append(text)
            _silent(output_path, 1500)
            return True

        monkeypatch.setattr(inst, "_synthesize_indextts", fake_synth)
        # 避免 atempo/拼接落盘：直接返回原路径
        monkeypatch.setattr(inst, "_atempo_wav", lambda path, factor: path)
        monkeypatch.setattr(inst, "_concat_with_gaps", lambda chunk_wavs, gaps, output_file: output_file)

        inst._build_block_audio(
            "b0", "新的重翻译文。", None, "indextts", None, 5.0, force_resynthesize=True
        )
        # 强制重合成：用新译文合成，而不是复用旧子块
        assert synthesized == ["新的重翻译文。"]
        # 旧变速副本被清掉
        assert not tempo_stale.exists()

    def test_no_force_reuses_existing_chunk(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        _silent(inst.audio_dir / "seg_b0_c0.wav", 2000)
        synthesized = []

        def fake_synth(text, output_path, voice_ref=None, seed=42, target_duration=None):
            synthesized.append(text)
            _silent(output_path, 1500)
            return True

        monkeypatch.setattr(inst, "_synthesize_indextts", fake_synth)
        monkeypatch.setattr(inst, "_atempo_wav", lambda path, factor: path)
        monkeypatch.setattr(inst, "_concat_with_gaps", lambda chunk_wavs, gaps, output_file: output_file)

        inst._build_block_audio(
            "b0", "新文本", None, "indextts", None, 5.0, force_resynthesize=False
        )
        # 复用旧子块：不重合成
        assert synthesized == []


class TestCalmEmotion:
    def _make(self, tmp_path, emotion):
        inst = _make_automator(tmp_path)
        inst.tts_emotion = emotion
        inst._indextts_lock = threading.Lock()
        return inst

    def _send(self, inst, monkeypatch):
        fake = _FakeIndexTTSProc()
        monkeypatch.setattr(inst, "_get_indextts_server", lambda: fake)
        inst._synthesize_indextts("你好世界", inst.audio_dir / "x.wav")
        return json.loads(fake.stdin.written[0])

    def test_calm_emotion_forces_fixed_vector(self, tmp_path, monkeypatch):
        inst = self._make(tmp_path, "calm")
        req = self._send(inst, monkeypatch)
        assert req["use_emo_text"] is False
        assert req["emo_vector"] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    def test_auto_emotion_omits_emo_fields(self, tmp_path, monkeypatch):
        inst = self._make(tmp_path, "auto")
        req = self._send(inst, monkeypatch)
        assert "emo_vector" not in req
        assert "use_emo_text" not in req


class TestGenderAndPitchAnchor:
    @staticmethod
    def _tone(path, freq_hz, sr=16000, dur_s=2.0):
        import numpy as np
        import soundfile as sf
        t = np.linspace(0, dur_s, int(sr * dur_s), endpoint=False)
        y = (0.5 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
        sf.write(str(path), y, sr)

    def test_classify_male_female(self, tmp_path):
        inst = _make_automator(tmp_path)
        male = tmp_path / "m.wav"
        female = tmp_path / "f.wav"
        self._tone(male, 110)
        self._tone(female, 250)
        g = inst._classify_speaker_genders({"A": male, "B": female})
        assert g == {"A": "male", "B": "female"}


class TestCalibrateWithVoiceRef:
    def test_calibrate_extracts_voice_ref_when_missing(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        inst.project_dir = tmp_path
        inst.assets_dir = tmp_path / "assets"
        inst.assets_dir.mkdir(exist_ok=True)
        inst.source_video = tmp_path / "source.mp4"

        extracted = []

        def fake_extract(ref_path):
            extracted.append(str(ref_path))
            _silent(ref_path, 2000)
            return True

        monkeypatch.setattr(inst, "_extract_voice_ref", fake_extract)
        monkeypatch.setattr(inst, "_synthesize_indextts",
                            lambda text, output_path, voice_ref=None, seed=42, target_duration=None: _silent(output_path, 5000) or True)

        cps = inst._calibrate_indextts_cps()
        assert len(extracted) == 1  # 声纹缺失时先提取
        assert cps > 4.0  # 真实测得，而非回退 4.0

    def test_calibrate_reuses_existing_voice_ref(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        inst.project_dir = tmp_path
        inst.assets_dir = tmp_path / "assets"
        inst.assets_dir.mkdir(exist_ok=True)
        inst.source_video = tmp_path / "source.mp4"
        _silent(inst.assets_dir / "voice_ref.wav", 2000)

        extracted = []

        def fake_extract(ref_path):
            extracted.append(str(ref_path))
            return True

        monkeypatch.setattr(inst, "_extract_voice_ref", fake_extract)
        monkeypatch.setattr(inst, "_synthesize_indextts",
                            lambda text, output_path, voice_ref=None, seed=42, target_duration=None: _silent(output_path, 5000) or True)

        inst._calibrate_indextts_cps()
        assert extracted == []  # 已存在声纹，不重复提取
