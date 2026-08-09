"""说话人审校分流测试（ticket #10）：human_review auto|required 配置与 script 阶段分流。

覆盖：
1. `_needs_human_review` 纯判定逻辑（auto/required × 0/1/2 说话人）
2. 多人（>=2）script 阶段写 awaiting_human checkpoint 并停止，不放行自动审核
3. 单人（含未分离/0 说话人）自动通过留档
4. required 模式强制单人（1 说话人）也走人审
5. batch_runner 的 process / run_heavy / status 对 awaiting_review 状态的区分
"""

import sys
import inspect
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


def _make_config(human_review="auto", diarize="auto"):
    return {
        "pipeline": {
            "tts_engine": "indextts",
            "min_char_budget": 15,
            "diarize": diarize,
            "whisper_model": "large-v3",
            "segmentation": "sentence",
            "human_review": human_review,
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
                "start": i * 4.5,
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


def _make_automator(tmp_path, human_review="auto", diarize="auto", speakers=None):
    from tools.base_tool import ToolResult

    class _FakeTranscriber:
        def execute(self, inputs):
            return ToolResult(success=True, data=_fake_transcript(speakers=speakers))

    monkeypatch = None  # 调用方注入
    return _FakeTranscriber


def _run_script_stage(tmp_path, monkeypatch, human_review="auto", diarize="auto", speakers=None):
    """用 mock 转录/LLM 走真实 _run_script_stage，返回 (script_data, project_dir, automator)。"""
    from tools.base_tool import ToolResult

    class _FakeTranscriber:
        def execute(self, inputs):
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
        config=_make_config(human_review, diarize),
        db=None,
        glossary=Glossary(keep_english=[], translations={}),
        auto_reviewer=AutoReviewer({"max_fix_loops": 1, "checks": {}}, tmp_path / "projects"),
        quiet=True,
    )
    automator.llm = _FakeLLM()
    automator._cps = 5.0

    script_data = automator._run_script_stage()
    return script_data, project_dir, automator


class TestNeedsHumanReview:
    def test_auto_single_speaker_not_reviewed(self):
        automator = PipelineAutomator.__new__(PipelineAutomator)
        automator.human_review = "auto"
        assert automator._needs_human_review(1) is False

    def test_auto_zero_speaker_not_reviewed(self):
        # 未分离/无说话人视为单人，不审
        automator = PipelineAutomator.__new__(PipelineAutomator)
        automator.human_review = "auto"
        assert automator._needs_human_review(0) is False

    def test_auto_multi_speaker_reviewed(self):
        automator = PipelineAutomator.__new__(PipelineAutomator)
        automator.human_review = "auto"
        assert automator._needs_human_review(2) is True

    def test_required_always_reviewed(self):
        automator = PipelineAutomator.__new__(PipelineAutomator)
        automator.human_review = "required"
        for n in (0, 1, 2):
            assert automator._needs_human_review(n) is True


class TestScriptStageHumanReview:
    def test_multi_speaker_writes_awaiting_human_and_stops(self, tmp_path, monkeypatch):
        script_data, project_dir, automator = _run_script_stage(
            tmp_path, monkeypatch, human_review="auto", speakers=["SPEAKER_00", "SPEAKER_01"]
        )
        # 多人 → script 阶段返回 None（停止），不放行
        assert script_data is None
        assert automator._awaiting_human_review is True
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "awaiting_human"
        assert cp["human_approval_required"] is True
        assert cp["human_approved"] is False
        # script.json 已完整落盘（供人审引用 / #8 审校）
        assert (project_dir / "script.json").exists()
        assert (project_dir / "transcript.json").exists()

    def test_single_speaker_auto_approves(self, tmp_path, monkeypatch):
        script_data, project_dir, automator = _run_script_stage(
            tmp_path, monkeypatch, human_review="auto", speakers=["SPEAKER_00", "SPEAKER_00"]
        )
        assert script_data is not None
        assert automator._awaiting_human_review is False
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "completed"
        assert cp["human_approved"] is True

    def test_required_forces_review_on_single_speaker(self, tmp_path, monkeypatch):
        script_data, project_dir, automator = _run_script_stage(
            tmp_path, monkeypatch, human_review="required", speakers=["SPEAKER_00", "SPEAKER_00"]
        )
        assert script_data is None
        assert automator._awaiting_human_review is True
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "awaiting_human"

    def test_auto_zero_speaker_auto_approves(self, tmp_path, monkeypatch):
        # 未分离（speaker 缺失）→ 视为单人自动通过
        script_data, project_dir, automator = _run_script_stage(
            tmp_path, monkeypatch, human_review="auto", speakers=[None, None]
        )
        assert script_data is not None
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "script")
        assert cp["status"] == "completed"


class TestBatchRunnerAwaitingReview:
    def test_process_has_awaiting_review_branch(self):
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner.process)
        assert "awaiting_review" in src, "process 失败分支必须区分等待人审"
        assert "等待人工审校说话人归属" in src

    def test_run_heavy_has_awaiting_review_branch(self):
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner.run_heavy)
        assert "awaiting_review" in src, "run-heavy 失败分支必须区分等待人审"

    def test_status_labels_include_awaiting_review(self):
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner.status)
        assert "'awaiting_review': '[审]'" in src
