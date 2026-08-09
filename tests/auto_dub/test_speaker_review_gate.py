"""说话人审校闸门测试（ticket #8）：speaker_review.md 生成、修正指令解析、回写与放行。

覆盖：
1. `parse_speaker_review_md` 纯解析（合并 / 单句改归属 / 忽略其它行 / 非指令不误匹配）
2. `_resolve_merge_target` 链式合并解析
3. `_generate_speaker_review_md` 生成内容（音色概览 + 每音色的话 + 修正指令语法）
4. `apply_speaker_review` 集成：回写 transcript.json / script.json + script checkpoint 放行
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
from batch.pipeline_automator import PipelineAutomator, parse_speaker_review_md, _resolve_merge_target


def _min_automator(project_dir: Path) -> PipelineAutomator:
    """构造最小 automator（只注入 apply_speaker_review 需要的属性）。"""
    a = PipelineAutomator.__new__(PipelineAutomator)
    a.project_id = "auto-dub-x"
    a.project_dir = Path(project_dir)
    a._awaiting_human_review = True
    a._last_error = None
    return a


def _write_fixture(project_dir: Path) -> dict:
    """写 transcript.json / script.json / awaiting_human checkpoint，返回各数据。"""
    transcript = {
        "utterances": [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "SPEAKER_00", "words": [], "segment_ids": []},
            {"id": "u1", "start": 3.0, "end": 6.0, "text": "World", "speaker": "SPEAKER_03", "words": [], "segment_ids": []},
            {"id": "u2", "start": 6.0, "end": 9.0, "text": "Again", "speaker": "SPEAKER_02", "words": [], "segment_ids": []},
        ],
        "speaker_turns": [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_03"},
        ],
        "duration_seconds": 9.0,
        "language": "en",
    }
    script = {
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
    (project_dir / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
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
    return transcript, script


class TestParseSpeakerReviewMd:
    def test_empty_returns_empty(self):
        assert parse_speaker_review_md("") == {"merge_map": {}, "reroutes": {}}
        assert parse_speaker_review_md("# 说话人审校文档\n\n（无修正）") == {"merge_map": {}, "reroutes": {}}

    def test_merge_instruction(self):
        md = "# 合并 SPEAKER_03 -> SPEAKER_02"
        assert parse_speaker_review_md(md)["merge_map"] == {"SPEAKER_03": "SPEAKER_02"}

    def test_reroute_instruction(self):
        md = "# u10 -> SPEAKER_02"
        out = parse_speaker_review_md(md)
        assert out["reroutes"] == {"u10": "SPEAKER_02"}
        assert out["merge_map"] == {}

    def test_mixed_instructions(self):
        md = "\n".join([
            "# 合并 SPEAKER_03 -> SPEAKER_02",
            "# u2 -> SPEAKER_00",
            "## 注释标题",
            "- [u5] (1.0-2.0s) plain list line, ignored",
        ])
        out = parse_speaker_review_md(md)
        assert out["merge_map"] == {"SPEAKER_03": "SPEAKER_02"}
        assert out["reroutes"] == {"u2": "SPEAKER_00"}

    def test_non_instruction_not_misparsed(self):
        # 无「合并」关键字且不是 u/b 开头的 id → 不解析（避免把 SPEAKER_03 当成单句 uid）
        md = "# SPEAKER_03 -> SPEAKER_02"
        assert parse_speaker_review_md(md) == {"merge_map": {}, "reroutes": {}}

    def test_same_target_merge_ignored(self):
        md = "# 合并 SPEAKER_02 -> SPEAKER_02"
        assert parse_speaker_review_md(md)["merge_map"] == {}

    def test_chain_merge_parsed(self):
        md = "\n".join(["# 合并 A -> B", "# 合并 B -> C"])
        assert parse_speaker_review_md(md)["merge_map"] == {"A": "B", "B": "C"}


class TestResolveMergeTarget:
    def test_no_merge_passthrough(self):
        assert _resolve_merge_target("SPEAKER_00", {}) == "SPEAKER_00"

    def test_direct_merge(self):
        assert _resolve_merge_target("SPEAKER_03", {"SPEAKER_03": "SPEAKER_02"}) == "SPEAKER_02"

    def test_chain_merge(self):
        assert _resolve_merge_target("A", {"A": "B", "B": "C"}) == "C"


class TestGenerateSpeakerReviewMd:
    def test_md_contains_overview_and_per_speaker(self):
        automator = _min_automator(Path("."))
        automator.project_id = "auto-dub-x"
        automator.video = {"title": "Interview"}
        transcript = {"duration_seconds": 9.0}
        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "SPEAKER_00"},
            {"id": "u1", "start": 3.0, "end": 6.0, "text": "World", "speaker": "SPEAKER_03"},
            {"id": "u2", "start": 6.0, "end": 9.0, "text": "Again", "speaker": "SPEAKER_00"},
        ]
        md = automator._generate_speaker_review_md(transcript, utterances)
        assert "## 音色概览" in md
        assert "| SPEAKER_00 | 2 | 6.0 | Hello |" in md
        assert "| SPEAKER_03 | 1 | 3.0 | World |" in md
        assert "### SPEAKER_00（2 句，6.0s）" in md
        assert "- [u1] (3.0-6.0s) World" in md
        # 修正指令语法说明
        assert "# 合并 SPEAKER_03 -> SPEAKER_02" in md
        assert "# u10 -> SPEAKER_02" in md


class TestApplySpeakerReview:
    def test_apply_rewrites_and_releases_gate(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        transcript, script = _write_fixture(project_dir)
        # 修正：合并 SPEAKER_03 -> SPEAKER_02 + 单句 u2 改给 SPEAKER_00
        (project_dir / "speaker_review.md").write_text(
            "# 合并 SPEAKER_03 -> SPEAKER_02\n# u2 -> SPEAKER_00\n", encoding="utf-8"
        )

        automator = _min_automator(project_dir)
        summary = automator.apply_speaker_review()

        assert summary["success"] is True
        assert summary["merged"] == {"SPEAKER_03": "SPEAKER_02"}
        assert summary["rerouted"] == {"u2": "SPEAKER_00"}

        # transcript.json：utterances 合并 + 单句改归属
        t = json.loads((project_dir / "transcript.json").read_text(encoding="utf-8"))
        assert [u["speaker"] for u in t["utterances"]] == ["SPEAKER_00", "SPEAKER_02", "SPEAKER_00"]
        # speaker_turns 也随合并更新
        assert [x["speaker"] for x in t["speaker_turns"]] == ["SPEAKER_00", "SPEAKER_02"]

        # script.json：sections speaker 同步（不重翻，文本不变）
        s = json.loads((project_dir / "script.json").read_text(encoding="utf-8"))
        assert [sec["speaker"] for sec in s["sections"]] == ["SPEAKER_00", "SPEAKER_02", "SPEAKER_00"]
        assert s["sections"][1]["delivery_cues"]["provider_text"] == "世界"  # 译文未变

        # checkpoint 放行
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "completed"
        assert cp["human_approved"] is True
        assert automator._awaiting_human_review is False

    def test_no_corrections_still_releases(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        _write_fixture(project_dir)
        (project_dir / "speaker_review.md").write_text("# 说话人审校文档\n（无修正）\n", encoding="utf-8")
        automator = _min_automator(project_dir)
        summary = automator.apply_speaker_review()
        assert summary["success"] is True
        t = json.loads((project_dir / "transcript.json").read_text(encoding="utf-8"))
        assert [u["speaker"] for u in t["utterances"]] == ["SPEAKER_00", "SPEAKER_03", "SPEAKER_02"]

    def test_missing_md_returns_error(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = _min_automator(project_dir)
        summary = automator.apply_speaker_review()
        assert summary["success"] is False
        assert "speaker_review.md" in summary["error"]
