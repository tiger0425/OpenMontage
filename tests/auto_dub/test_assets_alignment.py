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
    inst.mix_mode = "replace"
    inst.subtitle_mode = "bottom"
    inst.game_audio_volume = 1.0
    inst._game_audio_separated = False
    inst.tts_model_version = "2.5"
    inst.tts_engine = "indextts"
    inst.force_resynth = False
    inst.subtitle_split_sentences = False
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


class TestDensityRiskDiscount:
    """ADR-006 D1/D2/D3：漂移风险前向驱动（英→中膨胀率 + 保守折扣）。"""

    def _inst(self):
        inst = object.__new__(PipelineAutomator)
        inst.zh_chars_per_en_word = 1.046
        inst.risk_discount_floor = 0.9
        inst.risk_trigger_threshold = 1.3
        return inst

    def test_no_discount_when_not_dense(self):
        inst = self._inst()
        # 2 英文词 → 预估 2.092 字；预算 10 → overrun 0.21 < 1.3 → 不触发
        r = inst._density_risk_discount("hello world", 5.0, 10)
        assert r["en_words"] == 2
        assert r["estimated_zh_chars"] == round(2 * 1.046, 2)
        assert r["overrun"] < 1.3
        assert r["discount"] == 1.0
        assert r["final_budget"] == 10
        assert r["triggered"] is False

    def test_discount_clamps_to_floor(self):
        inst = self._inst()
        # 20 英文词 → 预估 20.92 字；预算 5 → overrun 4.18 → 触发，1/4.18=0.239 → clamp 到 floor 0.9
        r = inst._density_risk_discount(" ".join(["word"] * 20), 5.0, 5)
        assert r["overrun"] > 1.3
        assert r["triggered"] is True
        assert r["discount"] == 0.9
        assert r["final_budget"] == int(5 * 0.9)  # 4

    def test_discount_between_floor_and_one(self):
        inst = self._inst()
        # 8 英文词 → 预估 8.368；预算 4 → overrun 2.092 → 1/2.092=0.478 < floor 0.9 → 仍 clamp 0.9
        r = inst._density_risk_discount("a b c d e f g h", 4.0, 4)
        assert r["overrun"] > 1.3
        assert r["discount"] == 0.9  # floor 兜底

        # overrun 刚好略超阈值但 1/overrun > floor 时用 1/overrun：
        # 需要 overrun > 1.3 且 1/overrun > 0.9 → overrun < 1.111，矛盾（阈值>1.3）。
        # 故 floor=0.9 下，trigger 时永远是 floor。用更低的 floor 验证非 floor 分支：
        inst.risk_discount_floor = 0.5
        r2 = inst._density_risk_discount("a b c d e f", 4.0, 4)  # 6词→6.276, overrun 1.569, 1/1.569=0.637 > 0.5
        assert r2["triggered"] is True
        assert abs(r2["discount"] - 0.637) < 0.01

    def test_zero_budget_triggers_discount(self):
        inst = self._inst()
        r = inst._density_risk_discount("hello world", 5.0, 0)
        assert r["overrun"] is None  # inf 记为 None
        assert r["triggered"] is True
        assert r["final_budget"] == 0  # 0 * discount = 0

    def test_alignment_report_carries_risk_dimension(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        inst.zh_chars_per_en_word = 1.046
        inst.risk_discount_floor = 0.9
        inst.risk_trigger_threshold = 1.3
        _write_transcript(inst)
        monkeypatch.setattr(inst, "_extract_speaker_voice_refs", lambda turns: {})
        monkeypatch.setattr(inst, "_extract_voice_ref", lambda p: True)
        monkeypatch.setattr(checkpoint, "read_checkpoint", lambda *a, **k: None)

        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            out = inst.audio_dir / f"seg_{block_id}.wav"
            target = max(0.1, block_dur - inst.queue_gap_seconds)
            inst._create_silent_wav(target, out)
            return out, target, "aligned", [], []

        monkeypatch.setattr(inst, "_build_block_audio", fake_build)
        inst._do_assets_stage(_full_script(), {})

        report = json.loads((inst.project_dir / "alignment_report.json").read_text(encoding="utf-8"))
        u0 = report["utterances"][0]
        # _sections 里 u0 = 2 英文词、5.0s；预算按 cps 5.0*0.7=3.5 → measured_char_budget(5,3.5)
        for key in ("en_words", "density_risk", "risk_discount", "pre_budget_chars", "post_budget_chars"):
            assert key in u0, f"alignment_report 缺 {key}"
        assert u0["en_words"] == 2  # "English one"
        assert u0["risk_discount"] == 1.0  # 2 词 5s 不密集，不触发折扣


class TestExtractQaContext:
    """ADR-006 D5：publish 阶段 QA 上下文提取（审阅上下文随包走）。"""

    def test_empty_input(self):
        assert PipelineAutomator._extract_qa_context(None) == {}
        assert PipelineAutomator._extract_qa_context({}) == {}

    def test_extracts_warnings_notes_and_meta(self):
        rr = {
            "version": "1.0",
            "outputs": [{"path": "x.mp4", "format": "mp4", "resolution": "1920x1080", "duration_seconds": 100}],
            "warnings": ["零重叠校验失败：存在相邻分段间隔小于 100ms 限制"],
            "verification_notes": ["零变速校验通过", "SRT同步校验通过"],
            "metadata": {
                "drift_seconds": 2.3,
                "atempo_applied": True,
                "atempo_factor": 1.03,
                "outro_duration_seconds": 2.3,
            },
        }
        qa = PipelineAutomator._extract_qa_context(rr)
        assert qa["qa_warnings"] == ["零重叠校验失败：存在相邻分段间隔小于 100ms 限制"]
        assert qa["qa_notes"] == ["零变速校验通过", "SRT同步校验通过"]
        assert qa["drift_seconds"] == 2.3
        assert qa["atempo_applied"] is True
        assert qa["atempo_factor"] == 1.03
        assert qa["outro_duration_seconds"] == 2.3
        assert qa["has_synthesis_fallback"] is False

    def test_detects_synthesis_fallback(self):
        rr = {
            "warnings": ["多人合成失败 2 个子块，静音兜底"],
            "verification_notes": [],
            "metadata": {},
        }
        qa = PipelineAutomator._extract_qa_context(rr)
        assert qa["has_synthesis_fallback"] is True

    def test_missing_meta_fields_default_none(self):
        rr = {"warnings": [], "verification_notes": [], "metadata": {}}
        qa = PipelineAutomator._extract_qa_context(rr)
        assert qa["drift_seconds"] is None
        assert qa["atempo_applied"] is None
        assert qa["has_synthesis_fallback"] is False


class TestBuildConfigDecisionEntries:
    """ADR-006 D8：项目级配置决策条目（轻量 decision_log 审计）。"""

    def _config(self, **overrides):
        cfg = {
            "pipeline": {
                "tts_engine": "indextts",
                "mix_mode": "replace",
                "subtitle_mode": "bottom",
            },
            "cover": {"engine": "hyperframes"},
        }
        if overrides:
            cfg["pipeline"].update({k: v for k, v in overrides.items() if k in ("tts_engine", "mix_mode", "subtitle_mode")})
            if "cover_engine" in overrides:
                cfg["cover"]["engine"] = overrides["cover_engine"]
        return cfg

    def test_produces_four_entries(self):
        from batch.batch_runner import build_config_decision_entries
        entries = build_config_decision_entries(self._config())
        assert len(entries) == 4
        ids = {e["decision_id"] for e in entries}
        assert ids == {"d-cfg-tts-engine", "d-cfg-mix-mode", "d-cfg-subtitle-mode", "d-cfg-cover-engine"}

    def test_every_entry_has_two_plus_options_and_valid_selected(self):
        from batch.batch_runner import build_config_decision_entries
        entries = build_config_decision_entries(self._config())
        for e in entries:
            assert len(e["options_considered"]) >= 2, e["decision_id"]
            option_ids = {o["option_id"] for o in e["options_considered"]}
            assert e["selected"] in option_ids, e["decision_id"]
            assert e["reason"], e["decision_id"]

    def test_selected_reflects_config(self):
        from batch.batch_runner import build_config_decision_entries
        cfg = self._config(tts_engine="voxcpm", mix_mode="game_audio", subtitle_mode="none", cover_engine="ai_image")
        entries = build_config_decision_entries(cfg)
        by_id = {e["decision_id"]: e for e in entries}
        assert by_id["d-cfg-tts-engine"]["selected"] == "voxcpm"
        assert by_id["d-cfg-mix-mode"]["selected"] == "game_audio"
        assert by_id["d-cfg-subtitle-mode"]["selected"] == "none"
        assert by_id["d-cfg-cover-engine"]["selected"] == "ai_image"

    def test_invalid_engine_falls_back_to_default(self):
        from batch.batch_runner import build_config_decision_entries
        entries = build_config_decision_entries(self._config(tts_engine="unknown_engine"))
        by_id = {e["decision_id"]: e for e in entries}
        assert by_id["d-cfg-tts-engine"]["selected"] == "indextts"

    def test_entries_validate_against_schema(self):
        import jsonschema
        from batch.batch_runner import build_config_decision_entries
        schema = json.loads(
            (Path(__file__).parent.parent.parent / "schemas" / "artifacts" / "decision_log.schema.json")
            .read_text(encoding="utf-8")
        )
        entries = build_config_decision_entries(self._config())
        decision_log = {"version": "1.0", "project_id": "x", "decisions": entries}
        jsonschema.validate(decision_log, schema)  # 不应抛异常

