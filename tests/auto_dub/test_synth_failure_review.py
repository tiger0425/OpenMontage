"""合成失败重试与人审闸门测试（ticket #11）：单人重试 / 多人直接人审。

覆盖：
1. `parse_synthesis_review_md` 纯解析（`# 重试 <id>` / 忽略其它行）
2. `_wav_is_silent` 静音伪文件判定（缺失/超小/低 rms）
3. `_generate_synthesis_review_md` 生成内容（失败清单 + 修正指令）
4. `apply_synthesis_review` 集成：清空重试 wav + assets checkpoint 放行
5. `_build_block_audio` 重试计数：单人重试上限内成功 / 耗尽静音兜底 / 记录 _synth_failures
6. 多人合成失败 → assets awaiting_human checkpoint + _awaiting_human_review
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
from batch.pipeline_automator import (
    PipelineAutomator,
    parse_synthesis_review_md,
)
from pydub import AudioSegment


def _min_automator(project_dir: Path) -> PipelineAutomator:
    """构造最小 automator（只注入合成审校相关属性）。"""
    a = PipelineAutomator.__new__(PipelineAutomator)
    a.project_id = "auto-dub-x"
    a.project_dir = Path(project_dir)
    a.assets_dir = Path(project_dir) / "assets"
    a.assets_dir.mkdir(parents=True, exist_ok=True)
    a.audio_dir = a.assets_dir / "audio"
    a.audio_dir.mkdir(parents=True, exist_ok=True)
    a.video = {"title": "T"}
    a._awaiting_human_review = False
    a._last_error = None
    a._synth_failures = []
    a.synth_retry_max = 2
    return a


def _write_synth_fixture(project_dir: Path) -> None:
    """写 synthesis_review.md + awaiting_human assets checkpoint。"""
    (project_dir / "synthesis_review.md").write_text(
        "# 合成失败审校文档\n### [u1] 子块 c0 (目标 3.0s)\n- 文本: World\n- 原因: silent\n",
        encoding="utf-8",
    )
    checkpoint.write_checkpoint(
        pipeline_dir=project_dir.parent,
        project_id="auto-dub-x",
        stage="assets",
        status="awaiting_human",
        artifacts={"asset_manifest": {"version": "1.0", "assets": []}},
        pipeline_type="localization-dub",
        human_approval_required=True,
        human_approved=False,
        error="多人合成失败 1 个子块，等待人工审校",
    )


class TestParseSynthesisReviewMd:
    def test_empty_returns_empty(self):
        assert parse_synthesis_review_md("") == {"retry_ids": []}
        assert parse_synthesis_review_md("# 合成失败审校文档\n\n（无修正）") == {"retry_ids": []}

    def test_retry_instruction(self):
        md = "# 重试 u3"
        assert parse_synthesis_review_md(md)["retry_ids"] == ["u3"]

    def test_multiple_retry_instructions(self):
        md = "\n".join(["# 重试 u1", "# 重试 u3"])
        assert parse_synthesis_review_md(md)["retry_ids"] == ["u1", "u3"]

    def test_non_instruction_not_misparsed(self):
        md = "# 重试测试文字不匹配"  # 无空格+id 格式 → 不解析
        assert parse_synthesis_review_md(md)["retry_ids"] == []


class TestWavIsSilent:
    def test_missing_file_is_silent(self, tmp_path):
        assert PipelineAutomator._wav_is_silent(tmp_path / "nope.wav") is True

    def test_tiny_file_is_silent(self, tmp_path):
        f = tmp_path / "tiny.wav"
        f.write_bytes(b"\x00" * 500)
        assert PipelineAutomator._wav_is_silent(f) is True

    def test_silent_wav_is_silent(self, tmp_path):
        f = tmp_path / "silent.wav"
        AudioSegment.silent(duration=500, frame_rate=48000).export(str(f), format="wav")
        assert PipelineAutomator._wav_is_silent(f) is True

    def test_audible_wav_is_not_silent(self, tmp_path):
        f = tmp_path / "tone.wav"
        # 1kHz 响亮正弦 → rms 远高于 100
        import numpy as np
        sr = 48000
        t = np.linspace(0, 0.3, int(sr * 0.3), endpoint=False)
        data = (np.sin(2 * np.pi * 1000 * t) * 12000).astype(np.int16)
        seg = AudioSegment(data.tobytes(), frame_rate=sr, sample_width=2, channels=1)
        seg.export(str(f), format="wav")
        assert PipelineAutomator._wav_is_silent(f) is False


class TestGenerateSynthesisReviewMd:
    def test_md_lists_failures_and_instructions(self):
        automator = _min_automator(Path("."))
        failures = [
            {"id": "u1", "chunk_index": 0, "text": "World", "reason": "silent",
             "target_duration_seconds": 3.0},
            {"id": "u5", "chunk_index": 1, "text": "Again", "reason": "tts_failed",
             "target_duration_seconds": 5.0},
        ]
        md = automator._generate_synthesis_review_md(failures)
        assert "## 失败清单" in md
        assert "### [u1] 子块 c0 (目标 3.0s)" in md
        assert "- 文本: World" in md
        assert "- 原因: silent" in md
        assert "- 原因: tts_failed" in md
        assert "approve-review --video-id" in md
        assert "# 重试 u3" in md


class TestApplySynthesisReview:
    def test_retry_clears_wav_and_sets_in_progress(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        _write_synth_fixture(project_dir)
        automator = _min_automator(project_dir)
        # 已有失败句 u1 的 wav（将被清空）
        stale = automator.audio_dir / "seg_u1_c0.wav"
        AudioSegment.silent(duration=500, frame_rate=48000).export(str(stale), format="wav")
        # 人审决定：重试 u1
        (project_dir / "synthesis_review.md").write_text("# 重试 u1\n", encoding="utf-8")

        summary = automator.apply_synthesis_review()

        assert summary["success"] is True
        assert summary["retry_ids"] == ["u1"]
        assert summary["cleared_blocks"] == ["u1"]
        assert not stale.exists()  # wav 已清空
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "assets")
        assert cp["status"] == "in_progress"  # 有重试 → 待重跑
        assert automator._awaiting_human_review is False

    def test_no_retry_releases_completed(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        _write_synth_fixture(project_dir)
        automator = _min_automator(project_dir)
        # 人审接受现状（静音兜底），无重试指令
        (project_dir / "synthesis_review.md").write_text(
            "# 合成失败审校文档\n（无修正）\n", encoding="utf-8"
        )
        summary = automator.apply_synthesis_review()
        assert summary["success"] is True
        assert summary["retry_ids"] == []
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "assets")
        assert cp["status"] == "completed"
        assert cp["human_approved"] is True

    def test_missing_md_returns_error(self, tmp_path):
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = _min_automator(project_dir)
        summary = automator.apply_synthesis_review()
        assert summary["success"] is False
        assert "synthesis_review.md" in summary["error"]


class TestBuildBlockAudioRetry:
    def _make_retry_automator(self, project_dir: Path, synth_failures_count: int = 1):
        automator = _min_automator(project_dir)
        automator.synth_retry_max = 2
        automator._synth_failures = []
        automator.tempo_budget = 0.05
        automator.inherently_long_seconds = 1.0
        automator.block_max_pause_seconds = 0.8
        automator.chunk_max_chars = 40
        automator.audio_dir = automator.assets_dir / "audio"
        automator.quiet = True
        automator.queue_gap_seconds = 0.1
        return automator

    def test_single_speaker_retries_then_succeeds(self, tmp_path, monkeypatch):
        """单人：前 2 次失败、第 3 次成功 → 重试计数 2 次后成功，不记失败。"""
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = self._make_retry_automator(project_dir)

        call_count = {"n": 0}

        def fake_synth(self_, text, output_path, voice_ref=None, seed=42, target_duration=None):
            call_count["n"] += 1
            import numpy as np
            sr = 48000
            if call_count["n"] < 3:
                # 前两次产出静音 → 判定失败
                AudioSegment.silent(duration=200, frame_rate=48000).export(str(output_path), format="wav")
            else:
                # 第三次产出有声音频 → 成功
                t = np.linspace(0, 0.4, int(sr * 0.4), endpoint=False)
                data = (np.sin(2 * np.pi * 880 * t) * 12000).astype(np.int16)
                seg = AudioSegment(data.tobytes(), frame_rate=sr, sample_width=2, channels=1)
                seg.export(str(output_path), format="wav")
            return True

        monkeypatch.setattr(PipelineAutomator, "_synthesize_indextts", fake_synth)
        monkeypatch.setattr(PipelineAutomator, "_atempo_wav",
                            lambda self_, p, f: p)

        out, dur, status, chunks, gaps = automator._build_block_audio(
            "u0", "你好世界", None, "indextts", None, block_dur=3.0,
        )
        assert call_count["n"] == 3  # 2 次失败 + 1 次成功
        assert automator._synth_failures == []  # 最终成功不记失败
        assert status in ("aligned", "overflow", "inherently_long")

    def test_single_speaker_retries_exhausted_records_failure(self, tmp_path, monkeypatch):
        """单人：重试耗尽仍失败 → 记录失败 + 静音兜底（流程继续）。"""
        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        automator = self._make_retry_automator(project_dir)

        call_count = {"n": 0}

        def fake_synth(self_, text, output_path, voice_ref=None, seed=42, target_duration=None):
            call_count["n"] += 1
            AudioSegment.silent(duration=200, frame_rate=48000).export(str(output_path), format="wav")
            return True  # TTS 返回 ok，但产出静音 → 判定失败

        monkeypatch.setattr(PipelineAutomator, "_synthesize_indextts", fake_synth)
        monkeypatch.setattr(PipelineAutomator, "_atempo_wav", lambda self_, p, f: p)

        out, dur, status, chunks, gaps = automator._build_block_audio(
            "u0", "你好世界", None, "indextts", None, block_dur=3.0,
        )
        assert call_count["n"] == 3  # 1 次 + 2 次重试 = 3 次调用
        assert len(automator._synth_failures) == 1
        assert automator._synth_failures[0]["id"] == "u0"
        assert automator._synth_failures[0]["reason"] == "silent"


class TestBatchRunnerAwaitingReviewCoversAssets:
    def test_is_awaiting_review_checks_script_and_assets(self):
        import inspect
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner._is_awaiting_review)
        assert '"script"' in src
        assert '"assets"' in src

    def test_approve_review_applies_synthesis_doc(self):
        import inspect
        from batch import batch_runner
        src = inspect.getsource(batch_runner.BatchRunner.approve_review)
        assert "synthesis_review.md" in src
        assert "apply_synthesis_review()" in src


class TestDoAssetsStageMultiSynthFailure:
    def _make_automator(self, tmp_path, monkeypatch):
        """构造最小 automator，stub 声纹/合成/混音依赖，验证多人合成失败转人审分支。"""
        from batch.auto_reviewer import AutoReviewer
        from batch.glossary import Glossary
        from tools.base_tool import ToolResult

        project_dir = tmp_path / "projects" / "auto-dub-x"
        project_dir.mkdir(parents=True)
        config = {
            "pipeline": {
                "tts_engine": "indextts", "min_char_budget": 15, "diarize": "auto",
                "whisper_model": "large-v3", "segmentation": "sentence", "human_review": "auto",
                "synth_retry_max": 2, "multi_synth_failure_review": True,
                "alignment": {"merge_gap_seconds": 0.5, "max_utterance_seconds": 15.0,
                              "chunk_max_chars": 40, "tempo_budget": 0.05, "tolerance": 0.15,
                              "inherently_long_seconds": 1.0, "queue_gap_seconds": 0.1},
            },
            "interview": {},
        }
        automator = PipelineAutomator(
            project_id="auto-dub-x", project_dir=project_dir,
            video={"title": "T", "duration_seconds": 6.0, "video_id": "x"},
            config=config, db=None, glossary=Glossary(keep_english=[], translations={}),
            auto_reviewer=AutoReviewer({"max_fix_loops": 1, "checks": {}}, tmp_path / "projects"),
            quiet=True,
        )
        # 模拟多人：2 个 speaker voice refs
        ref1 = project_dir / "assets" / "ref_A.wav"
        ref2 = project_dir / "assets" / "ref_B.wav"
        AudioSegment.silent(duration=2000, frame_rate=48000).export(str(ref1), format="wav")
        AudioSegment.silent(duration=2000, frame_rate=48000).export(str(ref2), format="wav")
        # 预写 transcript.json，使 _do_assets_stage 走多人声纹提取分支
        (project_dir / "transcript.json").write_text(json.dumps({
            "speaker_turns": [
                {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
                {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_01"},
            ],
            "utterances": [],
            "duration_seconds": 6.0,
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(automator, "_extract_speaker_voice_refs",
                            lambda turns: {"SPEAKER_00": ref1, "SPEAKER_01": ref2})
        monkeypatch.setattr(automator, "_classify_speaker_genders",
                            lambda refs: {k: "female" for k in refs})
        # 模拟合成失败：任何 block 都填充失败记录并返回静音兜底
        def fake_build(block_id, text, voice_ref, tts_engine, tts, block_dur, force_resynthesize=False):
            automator._synth_failures.append({
                "id": block_id, "chunk_index": 0, "text": text, "reason": "silent",
                "target_duration_seconds": round(block_dur, 3),
            })
            out = automator.audio_dir / f"seg_{block_id}.wav"
            AudioSegment.silent(duration=500, frame_rate=48000).export(str(out), format="wav")
            return out, 0.5, "aligned", [], []
        monkeypatch.setattr(automator, "_build_block_audio", fake_build)
        # stub 下游（不应被调用到，因多人失败提前返回）
        monkeypatch.setattr(automator, "compute_alignment_metrics",
                            lambda reports, tolerance: {
                                "pass_rate": 0.0, "clutter_rate": 0.0,
                                "inherently_long_count": 0, "max_deviation_seconds": 0.0})
        monkeypatch.setattr(automator, "is_inherently_long", lambda d, t: False)
        automator._get_cps = lambda: 5.0
        automator._heartbeat = lambda *a, **k: None
        return automator, project_dir

    def test_multi_speaker_synth_failure_halts_with_awaiting_assets(self, tmp_path, monkeypatch):
        automator, project_dir = self._make_automator(tmp_path, monkeypatch)
        script_data = {
            "version": "1.0", "title": "T", "total_duration_seconds": 6.0,
            "narration_language": "zh",
            "paragraph_structure": {"mode": "six-act", "compressed_to": 3, "rationale": "r"},
            "sections": [
                {"id": "u0", "text": "Hello", "paragraph_label": "quick_intro",
                 "start_seconds": 0.0, "end_seconds": 3.0,
                 "delivery_cues": {"provider_text": "你好"}, "speaker": "SPEAKER_00"},
                {"id": "u1", "text": "World", "paragraph_label": "quick_intro",
                 "start_seconds": 3.0, "end_seconds": 6.0,
                 "delivery_cues": {"provider_text": "世界"}, "speaker": "SPEAKER_01"},
            ],
        }
        result = automator._do_assets_stage(script_data, {"version": "1.0", "scenes": []})
        assert result is None
        assert automator._awaiting_human_review is True
        assert len(automator._synth_failures) == 2
        # synthesis_review.md 已生成
        synth_md = (project_dir / "synthesis_review.md").read_text(encoding="utf-8")
        assert "## 失败清单" in synth_md
        # assets checkpoint 挂起
        cp = checkpoint.read_checkpoint(project_dir.parent, "auto-dub-x", "assets")
        assert cp["status"] == "awaiting_human"
        assert cp["human_approved"] is False
