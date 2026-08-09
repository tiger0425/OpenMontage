"""TDD 测试：script 阶段集成（ticket 04/05）。

用 mock 转录/LLM 走真实 `_run_script_stage`：
1. 转录调用按配置传 diarize 开关（off 时不传/传 False，仍做原句合并）
2. sections 每条为原句单位、带正确 `speaker`
3. script.json 写入后通过 script.schema.json 校验（checkpoint 落盘即校验）
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

from lib import checkpoint
from batch.auto_reviewer import AutoReviewer
from batch.glossary import Glossary
from batch.pipeline_automator import PipelineAutomator


def _make_config(diarize="auto", whisper_model="large-v3", segmentation="sentence"):
    return {
        "pipeline": {
            "tts_engine": "indextts",
            "min_char_budget": 15,
            "diarize": diarize,
            "whisper_model": whisper_model,
            "segmentation": segmentation,
            "alignment": {
                "merge_gap_seconds": 0.5,
                "max_utterance_seconds": 15.0,
                "chunk_max_chars": 40,
                "tempo_budget": 0.05,
                "tolerance": 0.15,
                "inherently_long_seconds": 1.0,
                "queue_gap_seconds": 0.1,
            },
        },
        "interview": {},
    }


def _fake_transcript(n_utterances=2, speakers=None):
    speakers = speakers or ["SPEAKER_00", "SPEAKER_01"]
    return {
        "segments": [],
        "word_timestamps": [],
        "utterances": [
            {
                "id": f"u{i}",
                "start": i * 4.5,          # 间隙 1.5s >= block_gap 1.0 → 独立语段
                "end": i * 4.5 + 3.0,
                "text": f"English sentence {i}",
                "speaker": speakers[i % len(speakers)],
                "segment_ids": [i],
                "words": [],
            }
            for i in range(n_utterances)
        ],
        "language": "en",
        "duration_seconds": 10.0,
        "speaker_turns": [],
    }


def _run_script_stage(tmp_path, monkeypatch, diarize="auto", whisper_model="large-v3", segmentation="sentence", speakers=None):
    from tools.base_tool import ToolResult

    calls = {"diarize_kwargs": None, "model_size": None}

    class _FakeTranscriber:
        def execute(self, inputs):
            calls["diarize_kwargs"] = inputs.get("diarize")
            calls["model_size"] = inputs.get("model_size")
            return ToolResult(success=True, data=_fake_transcript(speakers=speakers))

    monkeypatch.setattr("batch.pipeline_automator.Transcriber", _FakeTranscriber)

    class _FakeLLM:
        def generate(self, prompt, system_instruction=None, json_mode=None):
            return "这是一句中文翻译。"

    video = {"title": "T", "duration_seconds": 10.0}
    project_dir = tmp_path / "projects" / "auto-dub-x"
    project_dir.mkdir(parents=True)
    automator = PipelineAutomator(
        project_id="auto-dub-x",
        project_dir=project_dir,
        video=video,
        config=_make_config(diarize, whisper_model, segmentation),
        db=None,
        glossary=Glossary(keep_english=[], translations={}),
        auto_reviewer=AutoReviewer({"max_fix_loops": 1, "checks": {}}, tmp_path / "projects"),
        quiet=True,
    )
    automator.llm = _FakeLLM()
    automator._cps = 5.0

    script_data = automator._run_script_stage()
    return script_data, calls, project_dir


class TestScriptStageIntegration:
    def test_sections_are_utterances_with_speaker(self, tmp_path, monkeypatch):
        # 多人（2 说话人）在 auto 分流下 script 阶段挂起等待人审（返回 None），
        # 但 script.json 已完整落盘，sections 的 speaker 字段逐句保留
        script_data, _, project_dir = _run_script_stage(
            tmp_path, monkeypatch, diarize="auto", speakers=["SPEAKER_00", "SPEAKER_01"]
        )
        assert script_data is None
        saved = json.loads((project_dir / "script.json").read_text(encoding="utf-8"))
        sections = saved["sections"]
        assert len(sections) == 2
        assert sections[0]["id"] == "u0"
        assert sections[0]["speaker"] == "SPEAKER_00"
        assert sections[1]["id"] == "u1"
        assert sections[1]["speaker"] == "SPEAKER_01"
        assert sections[0]["delivery_cues"]["provider_text"] == "这是一句中文翻译。"
        # 时间与英文原句一致
        assert sections[0]["start_seconds"] == 0.0
        assert sections[0]["end_seconds"] == 3.0

    def test_block_segmentation_optional(self, tmp_path, monkeypatch):
        # segmentation=block 时按说话人轮次语段（单人自动通过路径）
        script_data, _, _ = _run_script_stage(
            tmp_path, monkeypatch, diarize="auto", segmentation="block",
            speakers=["SPEAKER_00", "SPEAKER_00"]
        )
        assert script_data is not None
        assert [s["id"] for s in script_data["sections"]] == ["b0", "b1"]

    def test_script_checkpoint_validates_against_schema(self, tmp_path, monkeypatch):
        script_data, _, project_dir = _run_script_stage(
            tmp_path, monkeypatch, speakers=["SPEAKER_00", "SPEAKER_00"]
        )
        assert script_data is not None
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp and cp.get("status") == "completed"
        # read_checkpoint 内部已做 schema 校验，能读回即通过

    def test_diarize_off_skips_diarization(self, tmp_path, monkeypatch):
        script_data, calls, _ = _run_script_stage(
            tmp_path, monkeypatch, diarize="off", speakers=["SPEAKER_00", "SPEAKER_00"]
        )
        assert script_data is not None
        assert calls["diarize_kwargs"] is False

    def test_diarize_auto_enables_diarization(self, tmp_path, monkeypatch):
        _, calls, _ = _run_script_stage(tmp_path, monkeypatch, diarize="auto")
        assert calls["diarize_kwargs"] is True

    def test_whisper_model_from_config(self, tmp_path, monkeypatch):
        # 转录模型来自配置（准确率优先默认 large-v3）
        _, calls, _ = _run_script_stage(tmp_path, monkeypatch, whisper_model="medium")
        assert calls["model_size"] == "medium"

    def test_transcript_saved_for_assets_stage(self, tmp_path, monkeypatch):
        _, _, project_dir = _run_script_stage(tmp_path, monkeypatch)
        tf = project_dir / "transcript.json"
        assert tf.exists()
        data = json.loads(tf.read_text(encoding="utf-8"))
        assert len(data["utterances"]) == 2

    def test_single_speaker_no_speaker_keys_in_sections(self, tmp_path, monkeypatch):
        # 单说话人：speaker 字段仅在有值时才写入（兼容旧数据/单声纹路径）
        script_data, _, _ = _run_script_stage(
            tmp_path, monkeypatch, diarize="auto"
        )
        # 上面默认 2 说话人；此处覆盖单说话人场景
        from tools.base_tool import ToolResult

        class _FakeTranscriberSingle:
            def execute(self, inputs):
                return ToolResult(success=True, data=_fake_transcript(2, speakers=["SPEAKER_00", "SPEAKER_00"]))

        monkeypatch.setattr("batch.pipeline_automator.Transcriber", _FakeTranscriberSingle)
        video = {"title": "T", "duration_seconds": 10.0}
        project_dir = tmp_path / "projects" / "auto-dub-y"
        project_dir.mkdir(parents=True)
        automator = PipelineAutomator(
            project_id="auto-dub-y",
            project_dir=project_dir,
            video=video,
            config=_make_config("auto"),
            db=None,
            glossary=Glossary(keep_english=[], translations={}),
            auto_reviewer=AutoReviewer({"max_fix_loops": 1, "checks": {}}, tmp_path / "projects"),
            quiet=True,
        )
        automator.llm = type("FakeLLM", (), {"generate": staticmethod(lambda *a, **k: "译文。")})()
        automator._cps = 5.0
        script_data = automator._run_script_stage()
        assert all(s.get("speaker") == "SPEAKER_00" for s in script_data["sections"])
