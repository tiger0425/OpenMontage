"""翻译校验闸门测试（ticket #9）：translation_review.md 生成、译文解析、回写与放行。

覆盖：
1. `parse_translation_review_md` 纯解析（ZH 行提取 / 块归属 / EN 行忽略 / 无归属忽略）
2. `_generate_translation_review_md` 生成内容（全量逐句中英对照 + 修改说明）
3. `apply_translation_review` 集成：回写 script.json 的 provider_text + script checkpoint 放行
4. script 阶段多人/required 时同时生成 speaker_review.md 与 translation_review.md
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
from batch.pipeline_automator import PipelineAutomator, parse_translation_review_md


def _min_automator(project_dir: Path) -> PipelineAutomator:
    """构造最小 automator（只注入 apply_translation_review 需要的属性）。"""
    a = PipelineAutomator.__new__(PipelineAutomator)
    a.project_id = "auto-dub-x"
    a.project_dir = Path(project_dir)
    a._awaiting_human_review = True
    a._last_error = None
    return a


def _make_script() -> dict:
    return {
        "version": "1.0",
        "title": "T",
        "total_duration_seconds": 9.0,
        "narration_language": "zh",
        "paragraph_structure": {"mode": "six-act", "compressed_to": 3, "rationale": "r"},
        "sections": [
            {"id": "u0", "text": "Hello", "paragraph_label": "quick_intro", "start_seconds": 0.0, "end_seconds": 3.0,
             "delivery_cues": {"provider_text": "你好"}, "speaker": "SPEAKER_00"},
            {"id": "u1", "text": "World", "paragraph_label": "quick_intro", "start_seconds": 3.0, "end_seconds": 6.0,
             "delivery_cues": {"provider_text": "世界"}, "speaker": "SPEAKER_03"},
            {"id": "u2", "text": "Again", "paragraph_label": "quick_intro", "start_seconds": 6.0, "end_seconds": 9.0,
             "delivery_cues": {"provider_text": "再次"}, "speaker": "SPEAKER_02"},
        ],
    }


def _write_fixture(project_dir: Path) -> dict:
    """写 script.json / awaiting_human checkpoint，返回 script。"""
    script = _make_script()
    (project_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    checkpoint.write_checkpoint(
        pipeline_dir=project_dir.parent,
        project_id="auto-dub-x",
        stage="script",
        status="awaiting_human",
        artifacts={"script": script},
        pipeline_type="localization-dub",
        human_approval_required=True,
        human_approved=False,
    )
    return script


class TestParseTranslationReviewMd:
    def test_empty_returns_empty(self):
        assert parse_translation_review_md("") == {"edits": {}}
        assert parse_translation_review_md("# 翻译审校文档\n\n（无修正）") == {"edits": {}}

    def test_extracts_zh_by_block(self):
        md = "\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "- EN: Hello",
            "- ZH: 你好呀",
            "### [u1] (3.0-6.0s) [SPEAKER_03]",
            "- EN: World",
            "- ZH: 世界！",
        ])
        out = parse_translation_review_md(md)
        assert out["edits"] == {"u0": "你好呀", "u1": "世界！"}

    def test_zh_without_dash_prefix(self):
        md = "\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "EN: Hello",
            "ZH: 你好",
        ])
        assert parse_translation_review_md(md)["edits"] == {"u0": "你好"}

    def test_en_lines_ignored(self):
        # 人审误改 EN 行不应被当作译文
        md = "\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "- EN: Hello world",
            "- ZH: 你好",
            "### [u1] (3.0-6.0s) [SPEAKER_03]",
            "- EN: World changed by reviewer",
            "- ZH: 世界",
        ])
        out = parse_translation_review_md(md)
        assert out["edits"] == {"u0": "你好", "u1": "世界"}

    def test_zh_without_block_header_ignored(self):
        md = "- ZH: 无归属译文"
        assert parse_translation_review_md(md)["edits"] == {}

    def test_multiline_collapses_to_first_zh_per_block(self):
        md = "\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "- ZH: 第一版",
            "- ZH: 第二版",
        ])
        # 后出现覆盖先出现（块内最后一行生效）
        assert parse_translation_review_md(md)["edits"] == {"u0": "第二版"}


class TestGenerateTranslationReviewMd:
    def test_md_contains_full_bilingual_pairs(self):
        automator = _min_automator(Path("."))
        automator.video = {"title": "Interview"}
        script = _make_script()
        md = automator._generate_translation_review_md(script)
        assert "## 逐句对照" in md
        assert "### [u0] (0.0-3.0s) [SPEAKER_00]" in md
        assert "- EN: Hello" in md
        assert "- ZH: 你好" in md
        assert "### [u1] (3.0-6.0s) [SPEAKER_03]" in md
        assert "- EN: World" in md
        assert "- ZH: 世界" in md
        # 修改说明提示 approve-review 命令
        assert "approve-review --video-id" in md


class TestApplyTranslationReview:
    def test_apply_rewrites_and_releases_gate(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        _write_fixture(project_dir)
        # 人审修改 u0、u1 两句译文；u2 保持不动
        (project_dir / "translation_review.md").write_text("\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "- EN: Hello",
            "- ZH: 你好呀！",
            "### [u1] (3.0-6.0s) [SPEAKER_03]",
            "- EN: World",
            "- ZH: 世界！！",
            "### [u2] (6.0-9.0s) [SPEAKER_02]",
            "- EN: Again",
            "- ZH: 再次",
        ]), encoding="utf-8")

        automator = _min_automator(project_dir)
        summary = automator.apply_translation_review()

        assert summary["success"] is True
        assert summary["changed_count"] == 2
        assert set(summary["changed_ids"]) == {"u0", "u1"}

        # script.json：仅被修改的句子译文更新，未改的保持原样（不重翻）
        s = json.loads((project_dir / "script.json").read_text(encoding="utf-8"))
        texts = [sec["delivery_cues"]["provider_text"] for sec in s["sections"]]
        assert texts == ["你好呀！", "世界！！", "再次"]

        # checkpoint 放行
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "completed"
        assert cp["human_approved"] is True
        assert automator._awaiting_human_review is False

    def test_no_changes_still_releases(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        _write_fixture(project_dir)
        (project_dir / "translation_review.md").write_text("\n".join([
            "### [u0] (0.0-3.0s) [SPEAKER_00]",
            "- EN: Hello",
            "- ZH: 你好",
            "### [u1] (3.0-6.0s) [SPEAKER_03]",
            "- EN: World",
            "- ZH: 世界",
        ]), encoding="utf-8")
        automator = _min_automator(project_dir)
        summary = automator.apply_translation_review()
        assert summary["success"] is True
        assert summary["changed_count"] == 0
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "completed"

    def test_missing_md_returns_error(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = _min_automator(project_dir)
        summary = automator.apply_translation_review()
        assert summary["success"] is False
        assert "translation_review.md" in summary["error"]


class TestScriptStageGeneratesBothReviewDocs:
    def test_multi_speaker_generates_speaker_and_translation_md(self, tmp_path, monkeypatch):
        """多人时 script 阶段同时生成 speaker_review.md 与 translation_review.md。"""
        from tools.base_tool import ToolResult

        class _FakeTranscriber:
            def execute(self, inputs):
                return ToolResult(success=True, data={
                    "segments": [], "word_timestamps": [], "utterances": [
                        {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "SPEAKER_00",
                         "segment_ids": [], "words": []},
                        {"id": "u1", "start": 3.0, "end": 6.0, "text": "World", "speaker": "SPEAKER_01",
                         "segment_ids": [], "words": []},
                    ],
                    "language": "en", "duration_seconds": 6.0, "speaker_turns": [],
                })

        class _FakeLLM:
            def generate(self, prompt, system_instruction=None, json_mode=None):
                return "这是中文。"

        monkeypatch.setattr("batch.pipeline_automator.Transcriber", _FakeTranscriber)

        from batch.auto_reviewer import AutoReviewer
        from batch.glossary import Glossary

        config = {
            "pipeline": {
                "tts_engine": "indextts", "min_char_budget": 15, "diarize": "auto",
                "whisper_model": "large-v3", "segmentation": "sentence", "human_review": "auto",
                "alignment": {"merge_gap_seconds": 0.5, "max_utterance_seconds": 15.0,
                              "chunk_max_chars": 40, "tempo_budget": 0.05, "tolerance": 0.15,
                              "inherently_long_seconds": 1.0, "queue_gap_seconds": 0.1},
            },
            "interview": {},
        }
        video = {"title": "T", "duration_seconds": 6.0, "video_id": "x"}
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = PipelineAutomator(
            project_id="auto-dub-x", project_dir=project_dir, video=video, config=config,
            db=None, glossary=Glossary(keep_english=[], translations={}),
            auto_reviewer=AutoReviewer({"max_fix_loops": 1, "checks": {}}, tmp_path / "projects"),
            quiet=True,
        )
        automator.llm = _FakeLLM()
        automator._cps = 5.0

        script_data = automator._run_script_stage()
        assert script_data is None  # 等待人审
        assert automator._awaiting_human_review is True
        assert (project_dir / "speaker_review.md").exists()
        assert (project_dir / "translation_review.md").exists()
        # translation_review.md 内容为全量中英对照
        trans_md = (project_dir / "translation_review.md").read_text(encoding="utf-8")
        assert "- ZH: 这是中文。" in trans_md


class TestBatchRunnerApproveReviewCombines:
    def test_approve_review_applies_both_docs(self):
        """approve-review 必须同时应用 speaker 与 translation 审校文档（存在才应用）。"""
        import inspect
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner.approve_review)
        assert "speaker_review.md" in src
        assert "translation_review.md" in src
        assert "apply_speaker_review()" in src
        assert "apply_translation_review()" in src

