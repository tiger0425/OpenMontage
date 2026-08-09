"""TDD 测试：assets 阶段逐句对齐 + 多音色编排（ticket 06/07）。

用 mock 合成边界走真实 `_do_assets_stage`：
1. 多 speaker 时启用 speaker_refs 并按 speaker 选声纹
2. 变速不可达句触发缩短重翻后重新合成
3. 逐句对齐验收指标写入 segment_timings.json / alignment_report.json
4. 单说话人回退单声纹路径（multi_speaker=False）
"""

import sys
import json
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import lib.checkpoint as checkpoint
from batch.pipeline_automator import PipelineAutomator


def _make_automator(tmp_path):
    project_dir = tmp_path / "proj"
    (project_dir / "assets" / "audio").mkdir(parents=True)
    inst = object.__new__(PipelineAutomator)
    inst.project_id = "auto-dub-x"
    inst.project_dir = project_dir
    inst.assets_dir = project_dir / "assets"
    inst.audio_dir = project_dir / "assets" / "audio"
    inst.renders_dir = project_dir / "renders"
    inst.renders_dir.mkdir(parents=True, exist_ok=True)
    inst.tts_engine = "indextts"
    inst.is_interview = False
    inst.quiet = True
    inst.min_char_budget = 15
    inst._last_warnings = []
    inst._last_drift = None
    inst._last_error = None
    inst.alignment_tolerance = 0.15
    inst.inherently_long_seconds = 1.0
    inst.queue_gap_seconds = 0.1
    inst.tempo_budget = 0.05
    inst.merge_gap_seconds = 0.5
    inst.max_utterance_seconds = 15.0
    inst.chunk_max_chars = 40
    inst.retranslate_enabled = False
    inst._voxcpm_calibrator = None
    inst._cps = 5.0
    return inst


def _sections():
    return [
        {
            "id": "u0",
            "text": "English one",
            "paragraph_label": "quick_intro",
            "start_seconds": 0.0,
            "end_seconds": 5.0,
            "speaker": "A",
            "delivery_cues": {"provider_text": "第一句中文翻译。"},
        },
        {
            "id": "u1",
            "text": "English two",
            "paragraph_label": "main_story",
            "start_seconds": 5.5,
            "end_seconds": 10.5,
            "speaker": "B",
            "delivery_cues": {"provider_text": "第二句中文翻译。"},
        },
    ]


def _full_script(sections=None):
    """构造通过 script.schema.json 校验的完整 script_data。"""
    return {
        "version": "1.0",
        "title": "Test",
        "total_duration_seconds": 10.5,
        "narration_language": "zh",
        "paragraph_structure": {
            "mode": "six-act",
            "compressed_to": 3,
            "rationale": "test",
        },
        "sections": sections or _sections(),
        "metadata": {},
    }


def _write_transcript(inst, speakers=("A", "B")):
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": speakers[0]},
        {"start": 5.5, "end": 10.5, "speaker": speakers[-1]},
    ]
    (inst.project_dir / "transcript.json").write_text(
        json.dumps({"speaker_turns": turns}), encoding="utf-8"
    )


class TestAssetsAlignment:
    def test_multi_speaker_uses_speaker_refs_and_metrics(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        _write_transcript(inst)
        ref_a = inst.assets_dir / "voice_ref_A.wav"
        ref_b = inst.assets_dir / "voice_ref_B.wav"
        monkeypatch.setattr(
            inst, "_extract_speaker_voice_refs",
            lambda turns: {"A": ref_a, "B": ref_b},
        )
        monkeypatch.setattr(inst, "_extract_voice_ref", lambda p: True)
        monkeypatch.setattr(checkpoint, "read_checkpoint", lambda *a, **k: None)

        chosen = []

        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            chosen.append(voice_ref)
            out = inst.audio_dir / f"seg_{block_id}.wav"
            # 合成时长贴合目标（目标=原句时长-100ms），状态 aligned
            target = max(0.1, block_dur - inst.queue_gap_seconds)
            inst._create_silent_wav(target, out)
            return out, target, "aligned", [], []

        monkeypatch.setattr(inst, "_build_block_audio", fake_build)

        manifest = inst._do_assets_stage(_full_script(), {})
        assert manifest is not None
        assert {str(v) for v in chosen} == {str(ref_a), str(ref_b)}  # 按 speaker 选声纹

        timings = json.loads((inst.project_dir / "segment_timings.json").read_text(encoding="utf-8"))
        meta = timings["metadata"]
        assert meta["multi_speaker"] is True
        assert meta["speed_modification"] == "per_utterance_atempo"
        assert meta["alignment"]["total_utterances"] == 2
        assert meta["alignment"]["pass_rate"] == 1.0

        report = json.loads((inst.project_dir / "alignment_report.json").read_text(encoding="utf-8"))
        assert len(report["utterances"]) == 2

    def test_single_speaker_falls_back(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        _write_transcript(inst, speakers=("A", "A"))  # 单说话人
        monkeypatch.setattr(inst, "_extract_speaker_voice_refs", lambda turns: {})
        monkeypatch.setattr(inst, "_extract_voice_ref", lambda p: True)
        monkeypatch.setattr(checkpoint, "read_checkpoint", lambda *a, **k: None)

        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            out = inst.audio_dir / f"seg_{block_id}.wav"
            target = max(0.1, block_dur - inst.queue_gap_seconds)
            inst._create_silent_wav(target, out)
            return out, target, "aligned", [], []

        monkeypatch.setattr(inst, "_build_block_audio", fake_build)
        manifest = inst._do_assets_stage(_full_script(), {})
        assert manifest is not None
        timings = json.loads((inst.project_dir / "segment_timings.json").read_text(encoding="utf-8"))
        assert timings["metadata"]["multi_speaker"] is False

    def test_out_of_budget_triggers_retranslate(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        inst.retranslate_enabled = True  # 该测试专门验证缩短重翻路径（默认关闭）
        _write_transcript(inst)
        monkeypatch.setattr(
            inst, "_extract_speaker_voice_refs",
            lambda turns: {"A": inst.assets_dir / "ref_A.wav", "B": inst.assets_dir / "ref_B.wav"},
        )
        monkeypatch.setattr(inst, "_extract_voice_ref", lambda p: True)
        monkeypatch.setattr(checkpoint, "read_checkpoint", lambda *a, **k: None)
        monkeypatch.setattr(inst, "_retranslate_utterance", lambda line: "更短的译文。")

        call_count = {"n": 0}

        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            call_count["n"] += 1
            out = inst.audio_dir / f"seg_{block_id}.wav"
            # 第一次（原译文）超长 → out_of_budget；重翻后贴合 → aligned
            if call_count["n"] == 1:
                inst._create_silent_wav(block_dur * 1.5, out)  # 超过 ±5% 可调范围
                return out, block_dur * 1.5, "out_of_budget", [], []
            inst._create_silent_wav(max(0.1, block_dur - inst.queue_gap_seconds), out)
            return out, block_dur - inst.queue_gap_seconds, "aligned", [], []

        monkeypatch.setattr(inst, "_build_block_audio", fake_build)

        script_data = _full_script()
        manifest = inst._do_assets_stage(script_data, {})
        assert manifest is not None
        # 至少 3 次调用（u0 两次：原译文+重翻后；u1 一次）
        assert call_count["n"] >= 3
        # script 回写：provider_text 更新为短译文
        script_file = inst.project_dir / "script.json"
        assert script_file.exists()
        updated = json.loads(script_file.read_text(encoding="utf-8"))
        assert updated["sections"][0]["delivery_cues"]["provider_text"] == "更短的译文。"

    def test_inherently_long_marked_in_report(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        _write_transcript(inst)
        monkeypatch.setattr(inst, "_extract_speaker_voice_refs", lambda turns: {})
        monkeypatch.setattr(inst, "_extract_voice_ref", lambda p: True)
        monkeypatch.setattr(checkpoint, "read_checkpoint", lambda *a, **k: None)

        sections = _sections()
        # 造一个 0.5s 物理不可达原句
        sections[0]["end_seconds"] = 0.5

        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            out = inst.audio_dir / f"seg_{block_id}.wav"
            inst._create_silent_wav(max(0.1, block_dur), out)
            return out, max(0.1, block_dur), "inherently_long", [], []

        monkeypatch.setattr(inst, "_build_block_audio", fake_build)
        inst._do_assets_stage(_full_script(sections), {})
        report = json.loads((inst.project_dir / "alignment_report.json").read_text(encoding="utf-8"))
        assert report["metrics"]["inherently_long_count"] >= 1
        assert report["utterances"][0]["inherently_long"] is True
