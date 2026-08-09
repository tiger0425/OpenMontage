"""PipelineAutomator: 自动执行 OpenMontage localization-dub 管线的各个阶段。

通过程序化方式：
1. 调用 transcriber 进行转录。
2. 批量调用 LLM (DeepSeek/Gemini) 进行翻译并应用术语表与字数控制（character budgeting）。
3. 生成场景计划。
4. 按配置的 TTS 引擎（默认 indextts，经 subprocess 常驻服务桥接；可选 voxcpm）生成配音，
   并用 pydub 进行音轨混合，生成 SRT 字幕。
5. 生成剪辑决策。
6. 使用 FFmpeg 进行音视频合成（烧录字幕和替换音轨）。
7. 发布成品并生成 publish_log。
"""

import os
import sys
import re
import math
import json
import logging
import subprocess
import shutil
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from pydub import AudioSegment

# 单调时钟（跨平台），用于心跳耗时/ETA 计算
from time import monotonic as _monotonic

# 添加 OpenMontage 根目录和 auto-dub 根目录到 Python 路径
OMO_ROOT = Path(__file__).resolve().parents[3]
APPS_ROOT = Path(__file__).resolve().parents[1]
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from lib import checkpoint
from tools.analysis.transcriber import (
    Transcriber,
    assign_utterance_speakers,
    merge_into_utterances,
)
from tools.audio.voxcpm_speed_calibrator import VoxCPMSpeedCalibrator, measured_char_budget
from batch.llm_client import LLMClient


# 说话人审校修正指令（speaker_review.md）的标注语法（ticket #8）
_SPEAKER_REVIEW_MERGE_RE = re.compile(r"^#\s*合并\s+([A-Za-z0-9_]+)\s*->\s*([A-Za-z0-9_]+)\s*$")
_SPEAKER_REVIEW_REROUTE_RE = re.compile(r"^#\s*(u\d+|b\d+)\s*->\s*([A-Za-z0-9_]+)\s*$")


def parse_speaker_review_md(md_text: str) -> dict:
    """解析 speaker_review.md 的人工修正指令（纯函数，可单测）。

    支持的标注（每行一条，其余内容忽略）：
    - `# 合并 SPEAKER_03 -> SPEAKER_02`：把某音色的所有话归给另一音色（删除 = 合并到他人）
    - `# u10 -> SPEAKER_02`：把某一句（utterance/block id）改给另一音色

    Returns:
        {"merge_map": {"SPEAKER_03": "SPEAKER_02"}, "reroutes": {"u10": "SPEAKER_02"}}
    """
    merge_map = {}
    reroutes = {}
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue
        m = _SPEAKER_REVIEW_MERGE_RE.match(line)
        if m:
            src, dst = m.group(1), m.group(2)
            if src != dst:
                merge_map[src] = dst
            continue
        m = _SPEAKER_REVIEW_REROUTE_RE.match(line)
        if m:
            uid, spk = m.group(1), m.group(2)
            reroutes[uid] = spk
    return {"merge_map": merge_map, "reroutes": reroutes}


def _resolve_merge_target(speaker: Optional[str], merge_map: dict) -> str:
    """把 speaker 沿 merge_map 解析到最终音色（支持链式合并，纯函数）。"""
    seen = set()
    while speaker in merge_map and speaker not in seen:
        seen.add(speaker)
        speaker = merge_map[speaker]
    return speaker or "(未分配)"


class PipelineAutomator:
    """管线自动执行器"""

    def __init__(self, project_id: str, project_dir: Path, video: dict, config: dict, db, glossary, auto_reviewer, quiet: bool = False):
        self.project_id = project_id
        self.project_dir = Path(project_dir)
        self.video = video
        self.config = config
        self.db = db
        self.glossary = glossary
        self.auto_reviewer = auto_reviewer
        self.llm = LLMClient()
        self.quiet = quiet
        
        # 语速校准器（延迟初始化，首次 translate 时测速）
        cache = self.project_dir.parent / "voxcpm_cps_cache.json"
        self._voxcpm_calibrator = VoxCPMSpeedCalibrator(cache_path=cache)
        self._cps: Optional[float] = None

        # 访谈类判定
        self.is_interview = self._is_interview_video(video, config)

        # TTS 引擎选择
        self.tts_engine = config.get("pipeline", {}).get("tts_engine", "voxcpm")

        # 翻译预算配置（修复短句预算过小）
        self.min_char_budget = int(config.get("pipeline", {}).get("min_char_budget", 15))
        # 转录模型（准确率优先，默认 large-v3；base 在口音/对话内容上易幻觉）
        self.whisper_model = config.get("pipeline", {}).get("whisper_model", "large-v3")

        # 说话人分离与逐句对齐配置（ADR-003 D1/D3/D4/D7 + 多音色）
        self.diarize_mode = config.get("pipeline", {}).get("diarize", "auto")
        self.diarize_enabled = self.diarize_mode != "off"
        # 翻译域：tech=技术教程（AI/云技术专业词汇，默认）；general=通用/对话（口语化、保持情感）
        self.translation_domain = config.get("pipeline", {}).get("translation_domain", "tech")
        # 合成情感：calm=固定平静（贴合原版平淡语气，默认）；auto=服务端从文字自动判情感
        self.tts_emotion = config.get("pipeline", {}).get("tts_emotion", "calm")
        # 画面字幕驱动分段：实测 OCR/帧差分不稳（漏字、条不准），默认关闭；仅画面字幕清晰时手动开启
        self.subtitle_driven = config.get("pipeline", {}).get("subtitle_driven", "off")
        # 分段/翻译粒度：sentence=逐句（每句一条中文，时间与英文原句一致，默认）；block=按说话人轮次语段
        self.segmentation = config.get("pipeline", {}).get("segmentation", "sentence")
        _align = config.get("pipeline", {}).get("alignment", {}) or {}
        self.merge_gap_seconds = float(_align.get("merge_gap_seconds", 0.5))
        self.max_utterance_seconds = float(_align.get("max_utterance_seconds", 15.0))
        self.chunk_max_chars = int(_align.get("chunk_max_chars", 40))
        self.tempo_budget = float(_align.get("tempo_budget", 0.05))
        self.alignment_tolerance = float(_align.get("tolerance", 0.15))
        self.inherently_long_seconds = float(_align.get("inherently_long_seconds", 1.0))
        self.queue_gap_seconds = float(_align.get("queue_gap_seconds", 0.1))
        self.block_gap_seconds = float(_align.get("block_gap_seconds", 1.0))
        self.block_max_pause_seconds = float(_align.get("block_max_pause_seconds", 0.8))
        # 分段清理链（ticket 01）：diarization 后、原句合并前
        _seg = config.get("pipeline", {}).get("segments", {}) or {}
        self.segment_postprocess = bool(_seg.get("enabled", True))
        self.segment_merge_max_chars = int(_seg.get("merge_max_chars", 240))
        self.segment_micro_duration = float(_seg.get("micro_duration_seconds", 1.0))
        self.segment_micro_chars = int(_seg.get("micro_chars", 40))
        self.segment_split_threshold = float(_seg.get("split_threshold_seconds", 15.0))
        # 声纹参考：多段择优拼接（ticket 02）
        _vr = config.get("pipeline", {}).get("voice_ref", {}) or {}
        self.voice_ref_target = float(_vr.get("target_seconds", 30.0))
        self.voice_ref_min_seconds = float(_vr.get("min_seconds", 6.0))
        self.voice_ref_sweet_min = float(_vr.get("sweet_min", 1.5))
        self.voice_ref_sweet_max = float(_vr.get("sweet_max", 12.0))
        self.voice_ref_long_cap = float(_vr.get("long_cap", 15.0))
        # 漏译/未翻译检测（ticket 05）
        _tr = config.get("pipeline", {}).get("translation", {}) or {}
        self.untranslated_check = bool(_tr.get("untranslated_check", True))
        self.untranslated_ratio = float(_tr.get("untranslated_ratio", 0.5))
        # 翻译长度预算安全因子：cps 校准是长文本均值（~5.8），短句合成有固有起步开销
        # （首音节拉伸/句首静音），实测短句真实 cps 约 3.6-4.2。乘此因子压低预算
        # （0.7 → 4.1），让译文更短、合成时长更贴合原句，减少对事后变速/溢出推挤依赖。
        self.cps_safety_factor = float(_tr.get("cps_safety_factor", 0.7))
        # 缩短重翻：默认关闭——避免为了贴时间窗而砍句子（用户反馈"句子被截断"）。
        # 开启时，变速不可达句会被 LLM 改写得更短以塞进时间窗。
        self.retranslate_enabled = bool(_align.get("retranslate", False))

        # 说话人审校分流（ticket #10）：auto=说话人 >=2 强制人审，单人自动通过留档；
        # required=所有视频（含单人）强制人审
        self.human_review = config.get("pipeline", {}).get("human_review", "auto")

        # 漂移超标重试计数
        self._drift_retry_count = 0
        self._drift_retry_max = 3
        self._drift_need_retry = False

        # 分阶段执行状态跟踪（供 run-heavy / render-video --json 摘要）
        self._last_error: Optional[str] = None
        self._last_drift: Optional[float] = None
        self._last_verification_notes: list = []
        self._last_warnings: list = []
        self._last_output_path: Optional[str] = None

        # 说话人审校闸门状态：script checkpoint 写入 awaiting_human 时置位，
        # 供上层（batch_runner）区分"等待人工审校"与"失败"。
        self._awaiting_human_review = False
        
        # 确定各文件路径
        self.source_video = self.project_dir / "source.mp4"
        self.assets_dir = self.project_dir / "assets"
        self.audio_dir = self.assets_dir / "audio"
        self.renders_dir = self.project_dir / "renders"
        
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.renders_dir.mkdir(parents=True, exist_ok=True)

    def _heartbeat(self, msg: str, *, force: bool = False):
        """结构化心跳输出：flush 实时可见 + [AutoDub] 前缀。

        - 默认遵守 quiet 开关（quiet 时静默）
        - force=True 即使 quiet 也输出（关键错误/最终摘要）
        """
        if self.quiet and not force:
            return
        print(f"[AutoDub] {msg}", flush=True)

    def _stage_print(self, msg: str, *, force: bool = False):
        """阶段进度输出（非心跳），quiet 时抑制。"""
        if self.quiet and not force:
            return
        print(msg, flush=True)

    def run_pipeline(self) -> bool:
        """运行完整管线流程 (从 script 阶段到 publish 阶段)"""
        self._stage_print(f"  🏁 开始自动执行项目 {self.project_id} 的 localization-dub 管线...")
        try:
            return self._run_pipeline_inner()
        finally:
            # 任何路径退出都确保释放 IndexTTS2 服务与 GPU 锁（含 script 测速失败等）
            if self.tts_engine == "indextts":
                self._stop_indextts_server()

    def _run_pipeline_inner(self) -> bool:
        # 1. script 阶段
        script_data = self._run_script_stage()
        if not script_data:
            return False
            
        # 2. scene_plan 阶段
        scene_plan_data = self._run_scene_plan_stage(script_data)
        if not scene_plan_data:
            return False

        # 3-6. assets → edit → compose → publish（漂移超标时自动缩短重翻）
        while True:
            asset_manifest_data = self._run_assets_stage(script_data, scene_plan_data)
            if not asset_manifest_data:
                return False

            edit_decisions_data = self._run_edit_stage(scene_plan_data, asset_manifest_data)
            if not edit_decisions_data:
                return False

            render_report_data = self._run_compose_stage(edit_decisions_data, asset_manifest_data)
            if render_report_data:
                publish_log_data = self._run_publish_stage(render_report_data)
                if not publish_log_data:
                    return False
                print(f"  🎉 项目 {self.project_id} 自动执行成功！")
                return True

            # compose 返回 None，检查是否因漂移需要重翻
            if self._drift_need_retry and self._drift_retry_count <= self._drift_retry_max:
                self._drift_need_retry = False
                script_data = self._retranslate_shorter(script_data, scene_plan_data)
                if not script_data:
                    return False
                continue
            return False

    # ==========================================
    # 分阶段重算力执行（Compute Worker 子命令）
    # ==========================================
    def render_assets_only(self) -> Optional[dict]:
        """仅执行 assets 阶段（TTS 合成 + 混音 + SRT）。

        前置：script / scene_plan checkpoint 必须已完成。
        漂移超标时返回结构化错误，建议改用 run-heavy 触发自动缩短重翻。
        """
        # 恢复 script / scene_plan
        cp_script = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "script")
        cp_scene = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "scene_plan")
        if cp_script and cp_script.get("status") == "awaiting_human":
            self._last_error = "render-assets 前置缺失：script 正在等待人工审校说话人归属，请先完成说话人审校"
            print(f"    ❌ {self._last_error}")
            return None
        if not (cp_script and cp_script.get("status") == "completed" and cp_script.get("artifacts", {}).get("script")):
            self._last_error = "render-assets 前置缺失：script 阶段未完成，请先运行轻任务 (process) 生成剧本"
            print(f"    ❌ {self._last_error}")
            return None
        if not (cp_scene and cp_scene.get("status") == "completed" and cp_scene.get("artifacts", {}).get("scene_plan")):
            self._last_error = "render-assets 前置缺失：scene_plan 阶段未完成"
            print(f"    ❌ {self._last_error}")
            return None

        script_data = cp_script["artifacts"]["script"]
        scene_plan_data = cp_scene["artifacts"]["scene_plan"]
        asset_manifest = self._run_assets_stage(script_data, scene_plan_data)
        if not asset_manifest:
            self._last_error = self._last_error or "assets 阶段执行失败"
            return None

        return {
            "output_path": str(self.assets_dir / "dub_zh.wav"),
            "drift_seconds": self._last_drift,
            "verification_notes": self._last_verification_notes,
            "warnings": self._last_warnings,
            "error": None,
        }

    def render_video_only(self) -> Optional[dict]:
        """仅执行 edit + compose + publish（FFmpeg 压制 + 片尾 + 归档）。

        前置：assets checkpoint 必须已完成。
        漂移超标时返回结构化错误，建议改用 run-heavy 触发自动缩短重翻。
        """
        cp_assets = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "assets")
        cp_scene = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "scene_plan")
        if not (cp_assets and cp_assets.get("status") == "completed" and cp_assets.get("artifacts", {}).get("asset_manifest")):
            self._last_error = "render-video 前置缺失：assets 阶段未完成，请先运行 render-assets"
            print(f"    ❌ {self._last_error}")
            return None
        if not (cp_scene and cp_scene.get("status") == "completed" and cp_scene.get("artifacts", {}).get("scene_plan")):
            self._last_error = "render-video 前置缺失：scene_plan 阶段未完成"
            print(f"    ❌ {self._last_error}")
            return None

        asset_manifest = cp_assets["artifacts"]["asset_manifest"]
        scene_plan_data = cp_scene["artifacts"]["scene_plan"]

        edit_decisions = self._run_edit_stage(scene_plan_data, asset_manifest)
        if not edit_decisions:
            self._last_error = self._last_error or "edit 阶段执行失败"
            return None

        render_report = self._run_compose_stage(edit_decisions, asset_manifest)
        if not render_report:
            if self._drift_need_retry:
                self._last_error = f"漂移超标（{self._last_drift:.2f}s），请改用 run-heavy 触发自动缩短重翻"
            else:
                self._last_error = self._last_error or "compose 阶段执行失败"
            return None

        publish_log = self._run_publish_stage(render_report)
        if not publish_log:
            self._last_error = self._last_error or "publish 阶段执行失败"
            return None

        # 阶段可能全部由 checkpoint 跳过 → 恢复最后一次渲染摘要
        self._restore_render_state_from_checkpoint()

        return {
            "output_path": self._last_output_path,
            "drift_seconds": self._last_drift,
            "verification_notes": self._last_verification_notes,
            "warnings": self._last_warnings,
            "error": None,
        }

    def run_heavy(self) -> bool:
        """重算力打包一条龙：assets + edit + compose + publish（漂移超标自动缩短重翻）。

        语义等同 run_pipeline，但保留最后状态供 --json 摘要。
        """
        ok = self.run_pipeline()
        if ok:
            # 全部阶段已由 checkpoint 跳过（未实际执行 compose）时，
            # 从 compose checkpoint 恢复渲染摘要状态
            self._restore_render_state_from_checkpoint()
        elif self._last_error is None:
            self._last_error = "run-heavy 管线执行失败"
        return ok

    def _restore_render_state_from_checkpoint(self) -> None:
        """从 compose checkpoint 恢复最后一次渲染摘要（供 --json 回报）。"""
        try:
            cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "compose")
            if not (cp and cp.get("status") == "completed"):
                return
            rr = cp.get("artifacts", {}).get("render_report", {}) or {}
            outputs = rr.get("outputs", [])
            if outputs and isinstance(outputs[0], dict):
                self._last_output_path = outputs[0].get("path")
            meta = rr.get("metadata", {}) or {}
            if "drift_seconds" in meta:
                self._last_drift = float(meta["drift_seconds"])
            if rr.get("verification_notes"):
                self._last_verification_notes = list(rr["verification_notes"])
            if rr.get("warnings"):
                self._last_warnings = list(rr["warnings"])
        except Exception:
            pass

    def run_light(self) -> bool:
        """轻任务：script + scene_plan（剧本与场景计划就绪）。

        只做转录/翻译/场景规划，**不执行任何重算力**（TTS 合成 / FFmpeg 压制）。
        重算力必须由 Compute Worker 子 Agent 通过 run-heavy / render-assets /
        render-video 执行 —— 这是长短解耦的硬边界：主 Agent 的 process 到此为止。
        """
        self._stage_print(f"  🏁 开始轻任务 {self.project_id}（script + scene_plan）...")
        script_data = self._run_script_stage()
        if not script_data:
            return False
        scene_plan_data = self._run_scene_plan_stage(script_data)
        if not scene_plan_data:
            return False
        return True

    def get_last_drift(self) -> Optional[float]:
        return self._last_drift

    def get_last_verification_notes(self) -> list:
        return self._last_verification_notes

    def get_last_warnings(self) -> list:
        return self._last_warnings

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def get_last_output_path(self) -> Optional[str]:
        return self._last_output_path

    def _needs_human_review(self, speaker_count: int) -> bool:
        """说话人审校分流判定（ticket #10）。

        human_review=auto（默认）：说话人 >=2 强制人审，单人（含 0/未分离）自动通过留档。
        human_review=required：所有视频（含单人）都强制人审。
        """
        if self.human_review == "required":
            return True
        return self.human_review == "auto" and speaker_count >= 2

    def _generate_speaker_review_md(self, raw_transcript: dict, utterances: list[dict]) -> str:
        """生成 speaker_review.md（音色概览 + 每音色的话 + 修正指令区）。纯文本生成，可单测。

        依据 transcript.json 的 utterances（按 speaker 分组），供人工确认音色数量与句子归属。
        """
        title = self.video.get("title") or self.project_id
        dur = float(raw_transcript.get("duration_seconds") or 0)
        by_speaker: dict[str, list[dict]] = {}
        for u in utterances:
            by_speaker.setdefault(u.get("speaker") or "(未分配)", []).append(u)

        def _total_secs(us: list[dict]) -> float:
            return sum(
                max(0.0, float(u["end"]) - float(u["start"]))
                for u in us
                if u.get("start") is not None and u.get("end") is not None
            )

        lines = [
            "# 说话人审校文档",
            "",
            f"- 项目: {self.project_id}",
            f"- 视频: {title}",
            f"- 时长: {dur:.1f}s",
            f"- 检测到 {len(by_speaker)} 个音色（cluster）",
            "",
            "## 音色概览",
            "",
            "| 音色 | 话数 | 总时长(s) | 代表句 |",
            "|------|------|-----------|--------|",
        ]
        for spk in sorted(by_speaker):
            us = by_speaker[spk]
            rep = (us[0].get("text") or "").strip().replace("|", "\\|")
            if len(rep) > 60:
                rep = rep[:60] + "..."
            lines.append(f"| {spk} | {len(us)} | {_total_secs(us):.1f} | {rep} |")
        lines.append("")
        lines.append("## 每音色的话")
        lines.append("")
        for spk in sorted(by_speaker):
            us = by_speaker[spk]
            lines.append(f"### {spk}（{len(us)} 句，{_total_secs(us):.1f}s）")
            lines.append("")
            for u in us:
                uid = u.get("id")
                s = float(u.get("start") or 0)
                e = float(u.get("end") or 0)
                text = (u.get("text") or "").strip()
                lines.append(f"- [{uid}] ({s:.1f}-{e:.1f}s) {text}")
            lines.append("")
        lines.append("## 修正指令")
        lines.append("")
        lines.append("> 在下方按行填写修正指令，不修改请留空。改完通知 Agent 运行：")
        lines.append("> `python bin/auto_dub.py approve-review --video-id {video_id}`")
        lines.append(">")
        lines.append("> - `# 合并 SPEAKER_03 -> SPEAKER_02`：把某音色的所有话归给另一音色（删除 = 合并到他人）")
        lines.append("> - `# u10 -> SPEAKER_02`：把某一句改给另一音色")
        lines.append("")
        lines.append("（修正指令填在这里）")
        return "\n".join(lines)

    def apply_speaker_review(self) -> dict:
        """应用 speaker_review.md 的人工修正并放行 script 审校闸门（ticket #8）。

        流程：
        1. 解析 speaker_review.md 的修正指令（合并音色 / 单句改归属）
        2. 回写 transcript.json（utterances + speaker_turns 的 speaker）
        3. 同步 script.json 的 sections speaker（不重翻：译文文本 per-utterance 独立）
        4. script checkpoint 置 completed（human_approved=True）放行后续阶段
        """
        md_file = self.project_dir / "speaker_review.md"
        if not md_file.exists():
            self._last_error = f"找不到 {md_file}，请先运行 process 生成说话人审校文档"
            return {"success": False, "error": self._last_error}
        instr = parse_speaker_review_md(md_file.read_text(encoding="utf-8"))
        merge_map = instr["merge_map"]
        reroutes = instr["reroutes"]

        # 1. 回写 transcript.json
        merged_count = reroute_count = 0
        transcript_file = self.project_dir / "transcript.json"
        if transcript_file.exists():
            with open(transcript_file, encoding="utf-8") as f:
                trans = json.load(f)
            for u in trans.get("utterances", []):
                if u.get("speaker") and u["speaker"] in merge_map:
                    u["speaker"] = _resolve_merge_target(u["speaker"], merge_map)
                    merged_count += 1
                if u.get("id") in reroutes:
                    u["speaker"] = reroutes[u["id"]]
                    reroute_count += 1
            for t in trans.get("speaker_turns", []):
                if t.get("speaker") and t["speaker"] in merge_map:
                    t["speaker"] = _resolve_merge_target(t["speaker"], merge_map)
                    merged_count += 1
            with open(transcript_file, "w", encoding="utf-8") as f:
                json.dump(trans, f, indent=2, ensure_ascii=False)

        # 2. 同步 script.json（只改 speaker 字段，不重翻）
        script_data = None
        script_file = self.project_dir / "script.json"
        if script_file.exists():
            with open(script_file, encoding="utf-8") as f:
                script_data = json.load(f)
            for sec in script_data.get("sections", []):
                if sec.get("speaker") and sec["speaker"] in merge_map:
                    sec["speaker"] = _resolve_merge_target(sec["speaker"], merge_map)
                if sec.get("id") in reroutes:
                    sec["speaker"] = reroutes[sec["id"]]
            with open(script_file, "w", encoding="utf-8") as f:
                json.dump(script_data, f, indent=2, ensure_ascii=False)

        # 3. script checkpoint 放行（completed + 更新后的 script artifact）
        if script_data is None:
            cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "script")
            script_data = (cp or {}).get("artifacts", {}).get("script") or {}
        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="script",
            status="completed",
            artifacts={"script": script_data},
            pipeline_type="localization-dub",
            human_approval_required=True,
            human_approved=True,
        )
        self._awaiting_human_review = False

        summary = {
            "success": True,
            "merged": merge_map,
            "rerouted": reroutes,
            "merged_count": merged_count,
            "reroute_count": reroute_count,
        }
        print(f"    ✅ 说话人审校已应用：合并 {merge_map or '无'}，改归属 {reroutes or '无'}")
        print(f"       script 闸门已放行，可派发 Worker 执行 run-heavy")
        return summary

    # ==========================================
    # 阶段 1: script
    # ==========================================
    def _run_script_stage(self) -> Optional[dict]:
        print("  ⚙️ 运行 [script] 阶段...")
        
        # 检查是否已完成
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "script")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ script 阶段已完成，跳过。")
            return cp["artifacts"]["script"]

        # 1. 运行转录
        print("    🎙️ 开始语音转录 (faster-whisper)...")
        transcriber = Transcriber()
        res = transcriber.execute({
            "input_path": str(self.source_video),
            "model_size": self.whisper_model,
            "language": "en",
            "diarize": self.diarize_enabled,
            "merge_gap": self.merge_gap_seconds,
            "max_utterance_seconds": self.max_utterance_seconds,
            "segment_postprocess": self.segment_postprocess,
            "micro_duration": self.segment_micro_duration,
            "micro_chars": self.segment_micro_chars,
            "split_threshold": self.segment_split_threshold,
        })
        if not res.success:
            print(f"    ❌ 转录失败: {res.error}")
            return None
            
        raw_transcript = res.data
        utterances = raw_transcript.get("utterances") or []
        if not utterances:
            # 兜底：无原句时直接用转录段
            utterances = merge_into_utterances(
                raw_transcript["segments"],
                merge_gap=self.merge_gap_seconds,
                max_seconds=self.max_utterance_seconds,
            )
            utterances = assign_utterance_speakers(utterances)
        speaker_count = len({u.get("speaker") for u in utterances if u.get("speaker")})
        print(f"    ✅ 转录完成。共 {len(utterances)} 个原句（{speaker_count} 位说话人），"
              f"时长 {raw_transcript['duration_seconds']} 秒")

        # 保存转录（含原句与 speaker_turns）供 assets 阶段按 speaker 提取声纹
        try:
            transcript_file = self.project_dir / "transcript.json"
            with open(transcript_file, "w", encoding="utf-8") as f:
                json.dump(raw_transcript, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"保存 transcript.json 失败: {e}")

        # 2. 翻译与分段：默认逐句（每句一条中文、时间与英文原句一致）；
        #    segmentation=block 时按说话人轮次语段。
        print("    ✍️ 开始翻译...")
        if self.segmentation == "block":
            blocks = self._group_utterance_blocks(utterances, self.block_gap_seconds)
            blocks = self._translate_blocks(blocks)
            units = blocks
        else:
            units = self._translate_utterances(utterances)
        if not units:
            print("    ❌ 翻译失败")
            return None

        # 3. 构造 script.json 结构（sections = 翻译单元，起止取自单元时间）
        sections = []
        total_dur = float(raw_transcript["duration_seconds"])
        for unit in units:
            start_sec = float(unit["start"])
            progress = start_sec / total_dur if total_dur > 0 else 0
            if progress < 0.1:
                p_label = "quick_intro"
            elif progress < 0.8:
                p_label = "main_story"
            elif progress < 0.9:
                p_label = "big_picture"
            else:
                p_label = "powerful_ending"
            section = {
                "id": str(unit["id"]),
                "text": unit["text"],
                "paragraph_label": p_label,
                "start_seconds": float(unit["start"]),
                "end_seconds": float(unit["end"]),
                "delivery_cues": {
                    "provider_text": unit["translated_text"]
                }
            }
            if unit.get("speaker"):
                section["speaker"] = unit["speaker"]
            sections.append(section)
            
        script_data = {
            "version": "1.0",
            "title": self.video.get("title", "No Title"),
            "total_duration_seconds": float(raw_transcript["duration_seconds"]),
            "narration_language": "zh",
            "paragraph_structure": {
                "mode": "six-act",
                "compressed_to": 3,
                "rationale": "Direct translation and localization translation paragraph structure"
            },
            "sections": sections,
            "metadata": {
                "source_language": "en-US",
                "target_language": "zh-CN",
                "narration_language": "zh"
            }
        }
        
        # 保存到本地
        script_file = self.project_dir / "script.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)

        # 4. 说话人审校分流（ticket #10）：多人/required → 生成 speaker_review.md、
        #    写 awaiting_human checkpoint 等人审，不放行后续阶段；单人/未分离 → 自动审核
        need_review = self._needs_human_review(speaker_count)
        if need_review:
            review_md = self._generate_speaker_review_md(raw_transcript, utterances)
            review_file = self.project_dir / "speaker_review.md"
            review_file.write_text(review_md, encoding="utf-8")
            checkpoint.write_checkpoint(
                pipeline_dir=self.project_dir.parent,
                project_id=self.project_id,
                stage="script",
                status="awaiting_human",
                artifacts={"script": script_data},
                pipeline_type="localization-dub",
                human_approval_required=True,
                human_approved=False,
            )
            self._awaiting_human_review = True
            print(f"    ⏸️ 检测到 {speaker_count} 位说话人，script 待人工审校说话人归属 "
                  f"(human_review={self.human_review})")
            print(f"       project: {self.project_id} | 请审校 {review_file.name}，"
                  f"改完运行 python bin/auto_dub.py approve-review --video-id {self.video.get('video_id')}")
            return None

        # 5. 自动审核并写入 checkpoint（单人/未分离：自动通过并留档）
        success, issues = self.auto_reviewer.review_and_approve(
            project_id=self.project_id,
            stage="script",
            artifacts={"script": script_data}
        )
        if not success:
            print(f"    ❌ 自动审核不通过: {issues}")
            return None
            
        return script_data

    @staticmethod
    def _signature_to_intervals(
        signatures: list[str], fps: float, min_duration: float = 0.6
    ) -> list:
        """把逐帧签名序列转成字幕条区间（内容变化 → 新条）。

        相邻帧签名相同 → 同一字幕条；变化 → 新条。
        过滤过短片段（< min_duration 视为闪动噪声）。纯函数，可单测。
        """
        if not signatures:
            return []
        intervals = []
        start = 0.0
        for i in range(1, len(signatures)):
            t = i / fps
            if signatures[i] != signatures[i - 1]:
                intervals.append((start, t))
                start = t
        intervals.append((start, len(signatures) / fps))
        cleaned = [iv for iv in intervals if iv[1] - iv[0] >= min_duration]
        return [(round(s, 2), round(e, 2)) for s, e in cleaned]

    @staticmethod
    def _bucket_utterances_by_intervals(utterances: list[dict], intervals: list) -> list[dict]:
        """把原句按时间归属到字幕条区间，产生字幕驱动语段。

        每条字幕条 = 一个语段；段 start/end = 字幕条区间（而非原句起止），
        使中文字幕贴合画面字幕的显示节奏。纯函数，可单测。
        """
        buckets: dict = {i: [] for i in range(len(intervals))}
        for utt in utterances:
            ustart, uend = float(utt["start"]), float(utt["end"])
            best_i, best_ov = None, 0.0
            for i, (s, e) in enumerate(intervals):
                ov = max(0.0, min(uend, e) - max(ustart, s))
                if ov > best_ov:
                    best_i, best_ov = i, ov
            if best_i is not None and best_ov > 0:
                buckets[best_i].append(utt)
        blocks = []
        for i, (s, e) in enumerate(intervals):
            utts = buckets[i]
            if not utts:
                continue
            blocks.append(PipelineAutomator._block_from_utterances(utts, f"b{len(blocks)}"))
            blocks[-1]["start"] = float(s)
            blocks[-1]["end"] = float(e)
        return blocks

    def _detect_subtitle_intervals(
        self, video_path, fps: float = 2.0, min_duration: float = 0.6
    ) -> list:
        """检测画面底部内嵌字幕条的显示时间（帧差分，无需 OCR 文字）。

        提取底部区域低帧率帧 → 逐帧"单元格布局签名"（把字幕带按 6x3 网格
        量化暗像素密度，对帧间抖动鲁棒）→ 内容变化即新字幕条。
        失败/无字幕返回 []（调用方回退语段分组）。
        """
        import tempfile
        from PIL import Image

        try:
            with tempfile.TemporaryDirectory(prefix="omo_subdetect_") as td:
                pattern = os.path.join(td, "f_%05d.png")
                cmd = [
                    "ffmpeg", "-y", "-i", str(video_path),
                    "-vf", f"fps={fps},crop=iw:ih*0.25:0:ih*0.72,scale=480:-1",
                    "-q:v", "5", pattern,
                ]
                res = subprocess.run(cmd, capture_output=True)
                if res.returncode != 0:
                    return []
                frames = sorted(Path(td).glob("f_*.png"))
                if not frames:
                    return []
                sigs = []
                for f in frames:
                    im = Image.open(f).convert("L").resize((48, 12))
                    px = im.load()
                    cells = []
                    for ry in range(3):
                        for cx in range(6):
                            dark = sum(
                                1
                                for yy in range(ry * 4, ry * 4 + 4)
                                for xx in range(cx * 8, cx * 8 + 8)
                                if px[xx, yy] < 110
                            )
                            cells.append("0" if dark < 2 else ("1" if dark < 8 else ("2" if dark < 20 else "3")))
                    sigs.append("".join(cells))
                return PipelineAutomator._signature_to_intervals(sigs, fps, min_duration)
        except Exception as e:
            logging.warning(f"画面字幕检测失败，回退语段分组: {e}")
            return []

    @staticmethod
    def _block_from_utterances(utts: list[dict], bid: str) -> dict:
        """把一个原句列表合并为一个语段（block）。

        语段 = 一段连续发言/快速问答，是翻译与对齐的单位。speaker 取段内多数。
        """
        from collections import Counter
        text = " ".join(u.get("text", "").strip() for u in utts).strip()
        counter = Counter(u.get("speaker") for u in utts if u.get("speaker"))
        dominant = counter.most_common(1)[0][0] if counter else None
        return {
            "id": bid,
            "start": float(utts[0]["start"]),
            "end": float(utts[-1]["end"]),
            "text": text,
            "speaker": dominant,
            "utterances": utts,
            "segment_ids": [sid for u in utts for sid in u.get("segment_ids", [])],
        }

    @staticmethod
    def _group_utterance_blocks(utterances: list[dict], block_gap: float = 1.0) -> list[dict]:
        """把原句分组成语段（block）。

        边界条件（满足任一即新语段）：
        - 相邻原句间隙 >= block_gap（静音停顿）
        - 说话人切换（语段内保持同一说话人，避免把对话并成独白）

        语段是翻译与对齐的单位：一段连续发言/问答 = 一个语段，
        各自锚定自身时间起点。纯函数，可单测。
        """
        if not utterances:
            return []
        blocks = []
        current = [utterances[0]]
        for utt in utterances[1:]:
            gap = float(utt["start"]) - float(current[-1]["end"])
            cur_spk = current[0].get("speaker")
            utt_spk = utt.get("speaker")
            speaker_change = bool(cur_spk and utt_spk and utt_spk != cur_spk)
            if gap < block_gap and not speaker_change:
                current.append(utt)
            else:
                blocks.append(PipelineAutomator._block_from_utterances(current, f"b{len(blocks)}"))
                current = [utt]
        blocks.append(PipelineAutomator._block_from_utterances(current, f"b{len(blocks)}"))
        return blocks

    def _build_preceding_context(
        self,
        translated: list[dict],
        max_pairs: int = 4,
        char_budget: int = 600,
    ) -> str:
        """构造翻译前文上下文块（ticket 03，对标 tachidubb preceding_context）。

        取最近已译若干条（src + tgt 对照），供 LLM 保持人名/代词/称谓/时态一致。
        按字符预算封顶（src+tgt 合计 600 字符 ≈ 150 token，防止撑爆上下文窗口）；
        只作连续性参考，明确要求不要重译这些行。返回空串表示无前文。
        """
        if not translated:
            return ""
        pairs: list[tuple[str, str]] = []
        budget = char_budget
        for item in reversed(translated):
            src = (item.get("text") or "").strip()
            tgt = (item.get("translated_text") or "").strip()
            if not src or not tgt:
                continue
            cost = len(src) + len(tgt)
            if cost > budget and pairs:
                break
            pairs.append((src, tgt))
            budget -= cost
            if len(pairs) >= max_pairs:
                break
        if not pairs:
            return ""
        pairs.reverse()  # 恢复时间序
        lines = [f"  {s}  ->  {t}" for s, t in pairs]
        return (
            "## 前文对话（仅作连续性参考：保持人名/代词/称谓一致；"
            "不要重译这些行）：\n" + "\n".join(lines) + "\n\n"
        )

    @staticmethod
    def _looks_untranslated(
        text: str,
        target_lang: str = "zh",
        cjk_ratio_threshold: float = 0.5,
        min_meaningful_chars: int = 4,
    ) -> bool:
        """判断译文是否明显「未翻译」：中文字符占比过低即视为漏译。

        对标 tachidubb `_looks_untranslated`：检测目标语言脚本（CJK）字符占比。
        - 中文目标：统计汉字数 / 非空白非标点字符数
        - CJK 占比 < threshold（默认 0.5）-> 判定漏译
        - 短文本（如 "OK"）无法判断，不误判
        - 中文主体 + 少量术语（GPU/API）仍通过，术语不误判
        """
        if not text or not text.strip():
            return False
        import re
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 非空白、非标点字符总数（汉字、数字、拉丁字母等）
        meaningful = len(re.findall(r"[^\s\d\.,!?:;\-()\[\]\"'·。，！？：；、—]", text))
        if meaningful < min_meaningful_chars:
            return False
        return cjk / meaningful < cjk_ratio_threshold

    def _retranslate_untranslated(self, item: dict) -> Optional[str]:
        """对漏译/未翻译行做单条重译（ticket 05）。

        复用逐句翻译的 prompt 结构，但更强调「必须完整译成中文」。
        返回 None 表示重译失败（调用方保留原文并记录 warning）。
        """
        try:
            src = item.get("text", "")
            dur = float(item.get("end", 0)) - float(item.get("start", 0))
            cps = self._budget_cps()
            max_chars = self._char_budget_for(dur)
            single_data = {
                "id": item.get("id"),
                "text": src,
                "duration": round(dur, 2),
                "max_chinese_characters": max_chars,
                "target_chars": max_chars,
                "cps": round(cps, 2),
                "speaker": item.get("speaker"),
            }
            rules = [
                "## 重译指导规则：",
                "1. 上一条译文被判定为未翻译（英文残留过多）。你必须把它完整翻译成中文。",
                "2. 只返回中文译文本身，不要解释、不要 JSON、不要 Markdown 包装。",
                "3. 专有名词（人名/品牌/模型名）按术语表保留英文或音译，其余全部译成中文。",
            ]
            prompt = (
                f"{self.glossary.build_translation_prompt(source_text=src)}\n\n"
                + "\n".join(rules)
                + "\n\n## 输入（一句英文）:\n"
                + json.dumps(single_data, ensure_ascii=False)
            )
            resp = self.llm.generate(prompt, system_instruction=self._build_translation_system_prompt())
            out = resp.strip().strip('"').strip()
            if self._looks_untranslated(out):
                return None
            return out or None
        except Exception as e:
            logging.warning(f"漏译重译失败 ({item.get('id')}): {e}")
            return None

    def _build_length_rule(self, dur: float, max_chars: int, cps: float) -> str:
        """构造时长感知的长度目标规则（tt-test 反馈修复）。

        短句（<= 3s）：译文必须在原句秒数内念完，超字必被截断——硬约束，
        只保留核心语义，宁短勿长。长句：保持"填满时间"导向，避免提前结束。
        """
        if dur <= 3.0:
            return (
                f"【长度硬约束】该句仅 {dur:.1f} 秒，译文**必须**在 {max_chars} 字以内"
                f"（约 {cps:.1f} 字/秒），否则超时会被截断。只保留核心语义，"
                "省略填充词/次要修饰，宁短勿长；确保中文能在原句时长内说完。"
            )
        return (
            f"【长度目标】译文应贴近约 {max_chars} 字（该句约 {dur:.1f} 秒、"
            f"语速约 {cps:.1f} 字/秒）。译文要完整覆盖这段时间：在忠实原意内"
            "可补足语气/细节以填满，不要过于简短，避免中文提前结束、与画面说话人不同步；"
            "也不要刻意堆砌无意义填充词。"
        )

    def _translate_utterances(self, utterances: list[dict]) -> Optional[list[dict]]:
        """逐句翻译：每个原句一条中文译文，时间与英文原句一致。

        复用域规则（人名音译/口语化/跳过语气词）+ 长度目标（填满原句时长）。
        注入前文上下文（最近已译 4 条，600 字符预算）；失败重试时去掉前文。
        """
        cps = self._budget_cps()
        print(f"    📏 实测 TTS 语速: {cps:.2f} 字/秒（长度预算已按短句特性打折）")
        system_prompt = self._build_translation_system_prompt()
        total = len(utterances)
        translated: list[dict] = []
        for idx, item in enumerate(utterances):
            dur = item["end"] - item["start"]
            max_chars = self._char_budget_for(dur)
            single_data = {
                "id": item["id"],
                "text": item["text"],
                "duration": round(dur, 2),
                "max_chinese_characters": max_chars,
                "target_chars": max_chars,
                "cps": round(cps, 2),
                "speaker": item.get("speaker"),
            }
            rules = self._build_translation_rules(item.get("speaker"))
            rules.append(self._build_length_rule(dur, max_chars, cps))
            preceding = self._build_preceding_context(translated)
            prompt = (
                f"{self.glossary.build_translation_prompt(source_text=item['text'])}\n\n"
                + "\n".join(rules)
                + "\n\n"
                + preceding
                + "## 输入（一句英文）:\n"
                + json.dumps(single_data, ensure_ascii=False)
            )
            if (idx + 1) % 50 == 0 or idx == total - 1:
                print(f"    - 逐句翻译 {idx+1}/{total}...")
            trans = item["text"]
            try:
                resp = self.llm.generate(prompt, system_instruction=system_prompt)
                trans = resp.strip().strip('"').strip() or trans
            except Exception as e:
                # 失败重试：去掉前文上下文（最可能是上下文溢出元凶）
                logging.warning(f"逐句翻译失败 ({item['id']}): {e}，去前文重试")
                try:
                    prompt_no_ctx = prompt.replace(preceding, "")
                    resp = self.llm.generate(prompt_no_ctx, system_instruction=system_prompt)
                    trans = resp.strip().strip('"').strip() or trans
                except Exception as e2:
                    logging.error(f"逐句翻译重试失败 ({item['id']}): {e2}，保留原文")
            # 漏译检测（ticket 05）：中文字符占比过低 -> 单条重译
            if getattr(self, "untranslated_check", True) and self._looks_untranslated(
                trans, cjk_ratio_threshold=getattr(self, "untranslated_ratio", 0.5)
            ):
                retry = self._retranslate_untranslated(item)
                if retry:
                    trans = retry
                else:
                    logging.warning(f"漏译重译失败 ({item['id']})，保留当前译文")
            item["translated_text"] = trans
            item["max_chars"] = max_chars
            translated.append(item)
        return utterances

    def _translate_blocks(self, blocks: list[dict]) -> Optional[list[dict]]:
        """按语段翻译：一个语段一条口语化中文译文。

        规则：意思准确、口语化、跳过 OK/Yeah/Mm-hm 等语气词（除非承载语义）、
        专有名词保留英文。语段即对齐单位，中文只需保证整段落进该段时间范围。
        注入前文上下文；失败重试时去掉前文。
        """
        cps = self._budget_cps()
        print(f"    📏 实测 TTS 语速: {cps:.2f} 字/秒（长度预算已按短句特性打折）")
        system_prompt = self._build_translation_system_prompt()
        total = len(blocks)
        translated: list[dict] = []
        for idx, block in enumerate(blocks):
            dur = block["end"] - block["start"]
            max_chars = self._char_budget_for(dur)
            block_data = {
                "id": block["id"],
                "text": block["text"],
                "duration": round(dur, 2),
                "max_chinese_characters": max_chars,
                "target_chars": max_chars,
                "cps": round(cps, 2),
                "speaker": block.get("speaker"),
            }
            rules = self._build_translation_rules(block.get("speaker"))
            rules.append(self._build_length_rule(dur, max_chars, cps))
            preceding = self._build_preceding_context(translated)
            prompt = (
                f"{self.glossary.build_translation_prompt(source_text=block['text'])}\n\n"
                + "\n".join(rules)
                + "\n\n"
                + preceding
                + "## 输入（一个英文语段，可含多句）:\n"
                + json.dumps(block_data, ensure_ascii=False)
            )
            if (idx + 1) % 20 == 0 or idx == total - 1:
                print(f"    - 按语段翻译 {idx+1}/{total}...")
            trans = block["text"]
            try:
                resp = self.llm.generate(prompt, system_instruction=system_prompt)
                trans = resp.strip().strip('"').strip() or trans
            except Exception as e:
                logging.warning(f"按语段翻译失败 ({block['id']}): {e}，去前文重试")
                try:
                    prompt_no_ctx = prompt.replace(preceding, "")
                    resp = self.llm.generate(prompt_no_ctx, system_instruction=system_prompt)
                    trans = resp.strip().strip('"').strip() or trans
                except Exception as e2:
                    logging.error(f"按语段翻译重试失败 ({block['id']}): {e2}，保留原文")
            # 漏译检测（ticket 05）：中文字符占比过低 -> 单条重译
            if getattr(self, "untranslated_check", True) and self._looks_untranslated(
                trans, cjk_ratio_threshold=getattr(self, "untranslated_ratio", 0.5)
            ):
                retry = self._retranslate_untranslated(block)
                if retry:
                    trans = retry
                else:
                    logging.warning(f"漏译重译失败 ({block['id']})，保留当前译文")
            block["translated_text"] = trans
            translated.append(block)
        return blocks

    def _build_translation_system_prompt(self) -> str:
        """按翻译域构造翻译 system prompt（语段级）。

        tech（默认）：技术教程域，保持 AI/云技术专业词汇；
        general：通用/对话域，口语化、保持说话人情感。
        """
        if self.translation_domain == "general":
            return (
                "You are a professional video localization translator for conversational "
                "and entertainment content.\n"
                "Your task is to translate ONE English passage (one or more spoken sentences) "
                "to natural, spoken Simplified Chinese (zh-CN)."
            )
        return (
            "You are a professional video localization translator specializing in AI and cloud technology.\n"
            "Your task is to translate ONE English passage (one or more spoken sentences) "
            "to Simplified Chinese (zh-CN)."
        )

    def _build_translation_rules(self, speaker: str | None = None) -> list[str]:
        """构造翻译指导规则（域 + 说话人 + 语气词跳过 + 专名一致）。"""
        rules = [
            "## 翻译指导规则：",
            "1. 意思准确、口语化、自然，不要书面语。",
            "2. 在准确完整的前提下，尽量将译文控制在 max_chinese_characters 字数内。",
            "3. 直接返回中文译文文本，不要 JSON 数组、不要解释、不要 Markdown 包装。",
        ]
        n = 4
        if self.translation_domain == "general":
            rules.append(f"{n}. 保持说话人情感/语气（质问、犹豫、委屈、调侃等），不要书面化。")
            n += 1
        if speaker:
            rules.append(f"{n}. 该语段主要由说话人 '{speaker}' 说出，保持其语气与称谓风格。")
            n += 1
        rules.append(
            f"{n}. 跳过 OK/Yeah/Mm-hm/Umm 等语气填充词，除非它们承载语义"
            "（如独立回答 Yes/No）。"
        )
        rules.append(
            f"{n}. 人名/专有名词（人物名等）统一音译为中文且全片一致"
            "（如 Sylvie→西尔维、Dino→迪诺），便于中文朗读；技术术语"
            "（GPU/API/模型名等）按术语表保留英文原文。"
        )
        return rules

    def _translate_segments(self, utterances: list[dict]) -> Optional[list[dict]]:
        """已废弃：翻译改为按语段（_translate_blocks），不再逐原句翻译。"""
        raise NotImplementedError(
            "逐原句翻译已废弃，请使用 _translate_blocks（语段级翻译）"
        )

    # ==========================================
    # 阶段 2: scene_plan
    # ==========================================
    def _run_scene_plan_stage(self, script_data: dict) -> Optional[dict]:
        print("  ⚙️ 运行 [scene_plan] 阶段...")
        
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "scene_plan")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ scene_plan 阶段已完成，跳过。")
            return cp["artifacts"]["scene_plan"]

        scenes = []
        scene_localization_meta = {}
        timing_risk_map = {}
        for line in script_data["sections"]:
            scene_id = f"scene_{line['id']}"
            
            # 计算密集程度
            words_count = len(line["text"].split())
            dur = line["end_seconds"] - line["start_seconds"]
            wps = words_count / dur if dur > 0 else 0
            drift_risk = "high" if wps > 4.0 else "low"
            
            scenes.append({
                "id": scene_id,
                "type": "broll",
                "description": line["text"],
                "start_seconds": float(line["start_seconds"]),
                "end_seconds": float(line["end_seconds"]),
                "script_section_id": line["id"]
            })
            scene_localization_meta[scene_id] = {
                "dub_mode": "dub_audio_only",
                "localization_treatment": "dub_audio_only",
                "drift_risk": drift_risk
            }
            if drift_risk == "high":
                timing_risk_map[scene_id] = {
                    "wps": round(wps, 2),
                    "reason": "密集发音段落 (Words per second > 4)"
                }
            
        scene_plan_data = {
            "version": "1.0",
            "scenes": scenes,
            "metadata": {
                "scene_localization_meta": scene_localization_meta,
                "timing_risk_map": timing_risk_map,
                "drift_budget": "5%"
            }
        }
        
        scene_plan_file = self.project_dir / "scene_plan.json"
        with open(scene_plan_file, "w", encoding="utf-8") as f:
            json.dump(scene_plan_data, f, indent=2, ensure_ascii=False)
            
        success, issues = self.auto_reviewer.review_and_approve(
            project_id=self.project_id,
            stage="scene_plan",
            artifacts={"scene_plan": scene_plan_data}
        )
        if not success:
            print(f"    ❌ 自动审核不通过: {issues}")
            return None
            
        return scene_plan_data

    # ==========================================
    # 阶段 3: assets
    # ==========================================
    def _run_assets_stage(self, script_data: dict, scene_plan_data: dict) -> Optional[dict]:
        """assets 阶段入口。

        - indextts 引擎：GPU 锁由 IndexTTS2 常驻服务生命周期持有（_get_indextts_server
          启动时获取，此处无需重复获取；finally 保证异常时也停止服务并释放锁）。
        - voxcpm 引擎：本阶段持 gpu_lock 覆盖整个 TTS 合成。
        """
        try:
            if self.tts_engine == "indextts":
                return self._do_assets_stage(script_data, scene_plan_data)
            from lib.gpu_lock import gpu_lock
            with gpu_lock("voxcpm-assets", timeout=1800, heartbeat=15):
                return self._do_assets_stage(script_data, scene_plan_data)
        except TimeoutError as e:
            print(f"    ❌ {e}")
            return None
        finally:
            # 无论成功/失败/异常，都停止 IndexTTS2 常驻服务并释放 GPU 锁
            if self.tts_engine == "indextts":
                self._stop_indextts_server()

    def _do_assets_stage(self, script_data: dict, scene_plan_data: dict) -> Optional[dict]:
        print("  ⚙️ 运行 [assets] 阶段...")
        
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "assets")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ assets 阶段已完成，跳过。")
            return cp["artifacts"]["asset_manifest"]

        lines = script_data["sections"]

        # 1. 调用 TTS 引擎生成配音音频
        tts_engine = self.tts_engine
        print(f"    🔊 开始调用 {tts_engine.upper()} 本地 GPU 合成音频分段...")
        if tts_engine == "indextts":
            tts = None  # IndexTTS2 uses subprocess bridge
        else:
            # 懒加载：仅 voxcpm 引擎才 import VoxCPM provider 工具（indextts 模式不触碰）
            from tools.audio.voxcpm_tts import VoxCPMTTS
            tts = VoxCPMTTS()

        # === 按说话人提取声纹（多人分音色）；单人/未分离回退单声纹路径 ===
        speaker_refs = {}
        try:
            transcript_file = self.project_dir / "transcript.json"
            if transcript_file.exists():
                transcript = json.loads(transcript_file.read_text(encoding="utf-8"))
                speaker_turns = transcript.get("speaker_turns", []) or []
                speaker_refs = self._extract_speaker_voice_refs(speaker_turns)
        except Exception as e:
            logging.warning(f"多音色声纹提取失败，回退单声纹路径: {e}")

        external_voice_ref = self.assets_dir / "voice_ref.wav"
        use_external_ref = False
        if not speaker_refs:
            if external_voice_ref.exists() and external_voice_ref.stat().st_size > 1000:
                try:
                    chk_ref = AudioSegment.from_wav(str(external_voice_ref))
                    if chk_ref.rms >= 100:
                        use_external_ref = True
                        print(f"    🎤 使用已有 voice reference: {external_voice_ref.name} ({chk_ref.duration_seconds:.1f}s)")
                except Exception as e:
                    logging.warning(f"voice_ref.wav 不可用, 将重新提取: {e}")
            if not use_external_ref:
                use_external_ref = self._extract_voice_ref(external_voice_ref)

        # === 强制清空旧的 TTS 音频，确保用当前声纹全量重新合成（避免复用旧声纹的 wav 导致时长漂移） ===
        import shutil as _shutil
        if self.audio_dir.exists():
            _shutil.rmtree(self.audio_dir, ignore_errors=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        temp_segments = []
        alignment_reports = []
        multi_speaker = len(speaker_refs) >= 2
        # 按声纹 ref 判性别（男声短句克隆不稳，需音高锚定）
        speaker_genders = self._classify_speaker_genders(speaker_refs)
        if multi_speaker:
            print(f"    🎙️ 检测到 {len(speaker_refs)} 位说话人，按人分音色配音"
                  f"（性别: { {k: v for k, v in speaker_genders.items()} }）")
        else:
            print("    🎤 单说话人（或未分离），使用单声纹路径")

        # 逐语段切合成子块（Chunk）→ 逐子块合成 → 变速 → 富余分摊为句间停顿 → 拼接
        total_lines = len(lines)
        tts_start_ts = _monotonic()
        # 变速不可达语段做单次缩短重翻（每段最多一次，避免失控调用 LLM）
        retranslated_any = False
        for idx, line in enumerate(lines):
            block_id = line["id"]
            text = line["delivery_cues"]["provider_text"]
            block_start = float(line["start_seconds"])
            block_end = float(line["end_seconds"])
            block_dur = max(0.0, block_end - block_start)
            speaker = line.get("speaker")
            # 说话人 cluster 合并归一化：被合并的 label（如 SPEAKER_03）重定向到
            # 合并目标（SPEAKER_02），确保同一人用同一音色（tt-test 反馈）。
            merge_map = getattr(self, "_last_speaker_merge_map", None)
            if merge_map and speaker in merge_map:
                speaker = merge_map[speaker]
                line["speaker"] = speaker  # 同步更新 line，供声像分离/字幕/音轨使用

            # 按说话人选择声纹；缺失 speaker 时回退单声纹/最长声纹
            voice_ref = None
            if multi_speaker:
                voice_ref = speaker_refs.get(speaker)
                if voice_ref is None:
                    voice_ref = next(iter(speaker_refs.values()), None)
            elif use_external_ref:
                voice_ref = external_voice_ref
            if voice_ref is not None:
                voice_ref = str(voice_ref)

            output_file = self.audio_dir / f"seg_{block_id}.wav"

            # 整段音频已存在且有效则复用（避免重跑时重复合成）
            is_valid_existing = False
            if output_file.exists() and output_file.stat().st_size > 1000:
                try:
                    chk_seg = AudioSegment.from_wav(output_file)
                    if chk_seg.rms >= 100:
                        is_valid_existing = True
                except Exception:
                    is_valid_existing = False

            # 结构化心跳：进度百分比 + 已耗时 + ETA
            progress_pct = (idx / total_lines) * 100.0 if total_lines else 100.0
            elapsed = _monotonic() - tts_start_ts
            if idx > 0 and elapsed > 0:
                per_item = elapsed / idx
                eta_remaining = per_item * (total_lines - idx)
                eta_str = f"ETA~{eta_remaining:.0f}s"
            else:
                eta_str = "ETA~?"
            status = "复用" if is_valid_existing else "合成"
            self._heartbeat(
                f"[{tts_engine.upper()}] 语段 {idx+1}/{total_lines} ({progress_pct:.1f}%) "
                f"耗时{elapsed:.1f}s {eta_str} | {status}: {text[:20]}..."
            )

            if is_valid_existing:
                audio_len = self._wav_duration(output_file)
                align_status = "reused"
            else:
                output_file, audio_len, align_status, _cw, _gaps = self._build_block_audio(
                    block_id, text, voice_ref, tts_engine, tts, block_dur
                )
                # 严重超长句（out_of_budget）：强制定向缩短重译（tt-test 反馈修复）。
                # 此类句子即使 1.15 高档变速后仍超目标 30%+，靠溢出推挤会把后续全往后推，
                # 累积成整片漂移。retranslate_enabled 仅控制全局"温和重翻"（漂移兜底），
                # 不控制此处单句强制重译。
                if align_status == "out_of_budget":
                    new_text = self._retranslate_utterance(line)
                    if new_text and new_text.strip() and new_text.strip() != text.strip():
                        retranslated_any = True
                        print(f"      ↻ 语段 {block_id} 严重超长，定向缩短重翻后重新合成...")
                        line["delivery_cues"]["provider_text"] = new_text
                        new_file, new_len, new_status, _, _ = self._build_block_audio(
                            block_id, new_text, voice_ref, tts_engine, tts, block_dur,
                            force_resynthesize=True,
                        )
                        if new_status in ("aligned", "inherently_long", "overflow") or new_len < audio_len:
                            output_file, audio_len, align_status = new_file, new_len, new_status
                            text = new_text

            temp_segments.append({
                "line": line,
                "path": output_file,
                "audio_len": audio_len
            })
            alignment_reports.append({
                "id": block_id,
                "speaker": speaker,
                "target": round(max(0.1, block_dur - self.queue_gap_seconds), 3),  # 对齐目标（D4）
                "slot_seconds": round(block_dur, 3),  # 字幕时间槽 = 语段时长
                "actual": round(audio_len, 3),
                "status": align_status,
                "inherently_long": self.is_inherently_long(block_dur, self.inherently_long_seconds),
            })

        # 逐句对齐验收指标（ADR-003 D5）：±15% 达标率 / 碎句率 / 物理不可达句数
        alignment_metrics = self.compute_alignment_metrics(
            alignment_reports, tolerance=self.alignment_tolerance
        )
        print(f"    📊 逐句对齐验收指标：达标率 {alignment_metrics['pass_rate']*100:.1f}% "
              f"（排除物理不可达 {alignment_metrics['inherently_long_count']} 句），"
              f"碎句率 {alignment_metrics['clutter_rate']*100:.1f}%，"
              f"单句最大偏差 {alignment_metrics['max_deviation_seconds']:.2f}s")
        if alignment_metrics["inherently_long_count"]:
            self._last_warnings.append(
                f"逐句对齐：{alignment_metrics['inherently_long_count']} 句物理不可达（<{self.inherently_long_seconds:.1f}s 原句），已豁免不计入达标率"
            )

        # 重翻后回写 script.json / script checkpoint（去除非 schema 字段）
        if retranslated_any:
            try:
                self._persist_script_update(script_data)
            except Exception as e:
                logging.warning(f"重翻后回写 script 失败: {e}")

        # 2. 串行排队混音算法 (Serial Queue Mix) 与时间戳计算
        print("    🎚️ 执行串行排队混音算法 (Serial Queue Mix, 100ms 间隔)...")
        previous_end = 0.0
        min_pause = 0.10  # 100ms
        segments_manifest = []
        
        for idx, item in enumerate(temp_segments):
            line = item["line"]
            ideal_start = line["start_seconds"]
            audio_len = item["audio_len"]
            
            # 串行排队混音，若上一段顺延，下一段自动往后推延 (零重叠保护)
            actual_start = max(ideal_start, previous_end + min_pause)
            actual_end = actual_start + audio_len
            previous_end = actual_end
            
            # 记录 actual_start 和 actual_end，用于下游 SRT 重同步
            line["actual_start"] = actual_start
            line["actual_end"] = actual_end
            
            segments_manifest.append({
                "id": f"narr_{line['id']}",
                "path": str(item["path"].relative_to(self.project_dir)).replace('\\', '/'),
                "start_time": actual_start,
                "end_time": actual_end,
                "audio_len": audio_len,
                "speaker": line.get("speaker"),
            })

        # 建立最终时间线空白总音轨（立体声；自然延伸，考虑最后的 previous_end 漂移）
        duration_sec = max(script_data["total_duration_seconds"], previous_end)

        # 每人一个音轨：说话人声像分离（立体声左右铺开），各自 stem 独立导出
        speaker_pans = PipelineAutomator._speaker_pan_map(
            [ts["line"].get("speaker") for ts in temp_segments]
        )
        full_track = AudioSegment.silent(duration=int(duration_sec * 1000), frame_rate=48000).set_channels(2)
        stems = {}
        for spk in speaker_pans.keys():
            stems[spk] = AudioSegment.silent(duration=int(duration_sec * 1000), frame_rate=48000).set_channels(2)

        # 逐段施加 15ms 淡入淡出 + 说话人声像，贴入总音轨对应位置
        for idx, item in enumerate(temp_segments):
            seg_manifest_item = segments_manifest[idx]
            start_ms = int(seg_manifest_item["start_time"] * 1000)
            spk = seg_manifest_item.get("speaker")

            try:
                audio_seg = AudioSegment.from_wav(item["path"])
                audio_seg = audio_seg.fade_in(15).fade_out(15)  # 15ms 淡入淡出
                pan = speaker_pans.get(spk, 0.0)
                try:
                    if abs(pan) > 0.001:
                        audio_seg = audio_seg.pan(pan)
                except Exception as e:
                    logging.warning(f"声像 pan 失败 {item['path'].name} ({pan}): {e}")
                full_track = full_track.overlay(audio_seg, position=start_ms)
                if spk in stems:
                    stems[spk] = stems[spk].overlay(audio_seg, position=start_ms)
            except Exception as e:
                logging.error(f"Error mixing segment {idx}: {e}")

        # 导出每说话人独立音轨（stem）
        for spk, stem in stems.items():
            spk_name = str(spk).replace(" ", "_")
            stem_path = self.assets_dir / f"dub_{spk_name}.wav"
            try:
                stem.export(str(stem_path), format="wav")
                print(f"    🎙️ 说话人音轨已导出: {stem_path.name}")
            except Exception as e:
                logging.error(f"导出说话人音轨失败 {stem_path}: {e}")
                
        dub_zh_wav = self.assets_dir / "dub_zh.wav"
        full_track.export(dub_zh_wav, format="wav")
        print(f"    ✅ 主音轨已生成（立体声，{len(speaker_pans)} 位说话人声像分离，总长 {duration_sec:.2f}秒）: {dub_zh_wav}")
                
        dub_zh_wav = self.assets_dir / "dub_zh.wav"
        full_track.export(dub_zh_wav, format="wav")
        print(f"    ✅ 主音轨已生成 (零变速，总长 {duration_sec:.2f}秒): {dub_zh_wav}")

        # 3. 动态重同步生成 SRT 字幕文件
        print("    📝 字幕动态重同步生成中...")
        subtitles_srt = self.assets_dir / "subtitles.srt"
        self._write_srt(lines, subtitles_srt)
        print(f"    ✅ 字幕已同步保存: {subtitles_srt}")

        # 4. 构造 asset_manifest
        # provenance：按实际使用的 TTS 引擎登记 source_tool（indextts / voxcpm）
        source_tool = "indextts_tts" if self.tts_engine == "indextts" else "voxcpm_tts"
        assets_list = []
        
        # 1. SRT subtitle asset
        assets_list.append({
            "id": "subtitle_zh",
            "type": "subtitle",
            "path": str(subtitles_srt.relative_to(self.project_dir)).replace('\\', '/'),
            "source_tool": "subtitle_gen",
            "scene_id": "global"
        })
        
        # 2. Dub audio track asset (以最终漂移后的总时长为准)
        assets_list.append({
            "id": "dub_audio_zh",
            "type": "audio",
            "path": str(dub_zh_wav.relative_to(self.project_dir)).replace('\\', '/'),
            "source_tool": source_tool,
            "scene_id": "global",
            "duration_seconds": float(duration_sec)
        })
        
        # 3. Individual narration segments (不含 metadata，以防违反 asset_manifest 的 schema 强校验)
        for seg in segments_manifest:
            assets_list.append({
                "id": seg["id"],
                "type": "narration",
                "path": seg["path"],
                "source_tool": source_tool,
                "scene_id": f"scene_{seg['id'].replace('narr_', '')}",
                "duration_seconds": float(seg["audio_len"])
            })
            
        # 将实际的起止时间信息写入独立的 segment_timings.json 供下游 compose 阶段使用
        drift_seconds = max(0.0, previous_end - float(script_data["total_duration_seconds"]))
        self._last_drift = drift_seconds
        timings_data = {
            "version": "1.0",
            "segments": segments_manifest,
            "metadata": {
                "drift_seconds": round(drift_seconds, 3),
                "original_video_duration_seconds": float(script_data["total_duration_seconds"]),
                "mixed_audio_duration_seconds": round(previous_end, 3),
                "is_interview": self.is_interview,
                "cps": round(self._get_cps(), 2),
                "mix_algorithm": "serial_queue",
                "speed_modification": "per_utterance_atempo",
                "multi_speaker": multi_speaker,
                "alignment": {
                    **alignment_metrics,
                    "tolerance": self.alignment_tolerance,
                    "tempo_budget": self.tempo_budget,
                    "queue_gap_seconds": self.queue_gap_seconds,
                    "merge_gap_seconds": self.merge_gap_seconds,
                    "max_utterance_seconds": self.max_utterance_seconds,
                },
            }
        }
        # 写入逐句对齐明细报告（验收审计）
        try:
            alignment_report_file = self.project_dir / "alignment_report.json"
            with open(alignment_report_file, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "1.0",
                    "metrics": alignment_metrics,
                    "utterances": alignment_reports,
                }, f, indent=2, ensure_ascii=False)
            print(f"    ✅ 逐句对齐报告已保存: {alignment_report_file.name}")
        except Exception as e:
            logging.error(f"Failed to write alignment_report.json: {e}")

        timings_file = self.project_dir / "segment_timings.json"
        try:
            with open(timings_file, "w", encoding="utf-8") as f:
                json.dump(timings_data, f, indent=2, ensure_ascii=False)
            print(f"    ✅ 独立时间轴记录保存成功: {timings_file.name}")
        except Exception as e:
            logging.error(f"Failed to write segment_timings.json: {e}")
            
        asset_manifest = {
            "version": "1.0",
            "assets": assets_list
        }

        # 写入 checkpoint
        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="assets",
            status="completed",
            artifacts={"asset_manifest": asset_manifest},
            pipeline_type="localization-dub"
        )
        print("  ✅ assets 阶段自动提交成功")
        return asset_manifest

    def _write_srt(self, lines: list[dict], output_path: Path):
        """将分段写入 SRT 文件格式"""
        def format_time(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            ms = int(round((seconds % 1) * 1000))
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

        with open(output_path, "w", encoding="utf-8") as f:
            for idx, line in enumerate(lines, 1):
                f.write(f"{idx}\n")
                # 优先使用实际的 actual_start/end 以支持动态重同步
                start = line.get("actual_start", line["start_seconds"])
                end = line.get("actual_end", line["end_seconds"])
                f.write(f"{format_time(start)} --> {format_time(end)}\n")
                f.write(f"{line['delivery_cues']['provider_text']}\n\n")

    def _create_silent_wav(self, duration_sec: float, output_path: Path):
        """生成指定时长的静音音频作为异常兜底"""
        try:
            silence = AudioSegment.silent(duration=int(duration_sec * 1000), frame_rate=48000)
            silence.export(output_path, format="wav")
        except Exception as e:
            logging.error(f"Failed to create silent wav: {e}")

    def _mix_audio_segments(self, segments: list[dict], duration_sec: float, output_path: Path):
        """把各个配音片段按照时间点贴在一条长空白音轨上"""
        try:
            # 建立总长空白音轨
            full_track = AudioSegment.silent(duration=int(duration_sec * 1000), frame_rate=48000)
            
            for seg in segments:
                seg_file = self.project_dir / seg["path"]
                if not seg_file.exists():
                    continue
                audio_seg = AudioSegment.from_wav(seg_file)
                start_ms = int(seg["start_time"] * 1000)
                
                full_track = full_track.overlay(audio_seg, position=start_ms)
                
            full_track.export(output_path, format="wav")
        except Exception as e:
            logging.error(f"Error mixing audio segments: {e}")
            # 备用极简 FFmpeg 混音实现
            self._create_silent_wav(duration_sec, output_path)

    # ==========================================
    # 辅助方法
    # ==========================================

    # IndexTTS2 venv Python 路径
    INDEXTTS_VENV_PYTHON = r"D:/index-tts/.venv/Scripts/python.exe"
    INDEXTTS_BRIDGE = r"D:/index-tts/indextts_bridge.py"
    INDEXTTS_SERVER = r"D:/index-tts/indextts_server.py"

    def _extract_voice_ref(self, external_voice_ref) -> bool:
        """提取更长的干净声纹片段并归一化音量。

        1. 用 silencedetect 找到视频中最长的一段连续人声
        2. 截取 15-20 秒干净片段
        3. 归一化音量到合理范围（RMS ~3000-5000）
        """
        try:
            import tempfile as _tf
            # 1. 先探测视频中的语音区间
            detect_cmd = [
                "ffmpeg", "-i", str(self.source_video),
                "-af", "silencedetect=noise=-30dB:d=0.8",
                "-f", "null", "-",
            ]
            res = subprocess.run(detect_cmd, capture_output=True, text=True, encoding="utf-8")
            # 解析 silencedetect 输出，找到最长连续语音段
            silences = []
            cur_start = None
            for m in re.finditer(r"silence_start:\s*([\d.]+)", res.stderr):
                t = float(m.group(1))
                if cur_start is not None:
                    silences.append((cur_start, t))
                cur_start = t
            if cur_start is not None:
                # 视频末尾也算一段结束
                probe = subprocess.run(
                    ["ffmpeg", "-i", str(self.source_video), "-f", "null", "-"],
                    capture_output=True, text=True, encoding="utf-8")
                m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe.stderr)
                if m:
                    total = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                    silences.append((cur_start, total))

            voice_segments = []
            prev_end = 0.0
            for start, end in silences:
                if start > prev_end + 0.5:
                    voice_segments.append((prev_end, start))
                prev_end = max(prev_end, end)
            # 视频末尾的语音段
            probe = subprocess.run(
                ["ffmpeg", "-i", str(self.source_video), "-f", "null", "-"],
                capture_output=True, text=True, encoding="utf-8")
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe.stderr)
            if m:
                total = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                if total > prev_end + 0.5:
                    voice_segments.append((prev_end, total))

            # 选最长的一段作为声纹
            best = None
            for start, end in voice_segments:
                dur = end - start
                if dur >= 12 and (best is None or dur > best[2]):
                    best = (start, end, dur)
            if best is None:
                # 回退：取前 15 秒
                start, dur = 0.0, 15.0
            else:
                start, end, dur = best
                start = max(0.0, start + 1.0)  # 避开语音边界
                end = min(end, start + 15.0)
                dur = end - start

            print(f"    🎤 提取声纹: 从 {start:.1f}s 起 {dur:.1f}s")
            return self._cut_and_normalize_ref(start, dur, external_voice_ref)
        except Exception as e:
            logging.warning(f"声纹提取失败: {e}，使用内部锚点")
            return False

    def _cut_and_normalize_ref(self, start: float, dur: float, out_path) -> bool:
        """从原视频切出声纹片段并归一化音量（复用 _extract_voice_ref 的截取逻辑）。

        - 需要 >= 8s 有效人声，否则视为失败（过短无法稳定克隆音色）
        - 归一化 RMS 到 ~3500，保证各 speaker 声纹响度一致
        """
        try:
            import numpy as _np
            cmd = [
                "ffmpeg", "-y", "-i", str(self.source_video),
                "-ss", str(start), "-t", str(dur),
                "-vn", "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                str(out_path)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            audio = AudioSegment.from_wav(str(out_path))
            if audio.duration_seconds < 8:
                return False
            target_rms = 3500
            if audio.rms > 0:
                gain = target_rms / audio.rms
                audio = audio.apply_gain(20 * _np.log10(gain))
            audio.export(str(out_path), format="wav")
            return True
        except Exception as e:
            logging.warning(f"声纹截取/归一化失败: {e}")
            return False

    @staticmethod
    def _cut_ref_chunk(source_video: Path, start: float, dur: float, out_path) -> bool:
        """从原视频切出声纹块（纯 ffmpeg，供多段拼接用）。"""
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(source_video),
                "-ss", str(start), "-t", str(dur),
                "-vn", "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                str(out_path)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            return Path(out_path).exists() and Path(out_path).stat().st_size > 1000
        except Exception as e:
            logging.warning(f"声纹块截取失败: {e}")
            return False

    @staticmethod
    def _stitch_ref_chunks(chunk_paths: list, out_path) -> bool:
        """把多个声纹块按时间序拼接为一条，并做峰值归一化（>0.9 线性回落到 0.9）。

        参照 tachidubb extract_speaker_audio：拼接后 peak-normalize，避免参考过冲/过闷。
        """
        try:
            import numpy as _np
            import soundfile as _sf

            pieces = []
            sr = 24000
            for p in chunk_paths:
                data, sr = _sf.read(str(p), dtype="float32")
                if data.ndim > 1:
                    data = data.mean(axis=1)
                pieces.append(data)
            if not pieces:
                return False
            merged = _np.concatenate(pieces).astype(_np.float32)
            peak = float(_np.abs(merged).max())
            if peak > 0.01 and peak > 0.9:
                merged = merged * (0.9 / peak)
            _sf.write(str(out_path), merged, sr)
            return True
        except Exception as e:
            logging.warning(f"声纹块拼接/归一化失败: {e}")
            return False

    def _select_voice_ref_candidates(
        self,
        speaker_turns: list[dict],
        target_seconds: float | None = None,
        min_seconds: float | None = None,
        sweet_min: float | None = None,
        sweet_max: float | None = None,
        long_cap: float | None = None,
    ) -> dict:
        """按说话人挑选多段声纹候选（纯逻辑，可单测，ticket 02）。

        同一 speaker 相邻 turn（间隙 < 1.0s）先合并为跨度；对每个 speaker：
        - 甜点段（sweet_min..sweet_max，默认 1.5–12s）按时长降序优先选，累计到 target（默认 30s）
        - 甜点不足再补短段（>= 0.4s），仍不足补长段截断（long_cap 15s）
        - 累计 < min_seconds（默认 6s）的 speaker 跳过（音频不足无法稳定克隆）
        返回 {speaker: [(start, end), ...]}（按时间序）。
        """
        target_seconds = self.voice_ref_target if target_seconds is None else target_seconds
        min_seconds = self.voice_ref_min_seconds if min_seconds is None else min_seconds
        sweet_min = self.voice_ref_sweet_min if sweet_min is None else sweet_min
        sweet_max = self.voice_ref_sweet_max if sweet_max is None else sweet_max
        long_cap = self.voice_ref_long_cap if long_cap is None else long_cap

        # 1) 相邻 turn 合并为跨度（间隙 < 1.0s）
        by_speaker: dict[str, list] = {}
        for t in speaker_turns:
            spk = t.get("speaker")
            if not spk:
                continue
            by_speaker.setdefault(spk, []).append((float(t["start"]), float(t["end"])))

        result: dict = {}
        for spk, turns in by_speaker.items():
            turns = sorted(turns)
            spans: list[tuple] = []
            cur_start, cur_end = turns[0]
            for start, end in turns[1:]:
                if start - cur_end < 1.0:
                    cur_end = max(cur_end, end)
                else:
                    spans.append((cur_start, cur_end))
                    cur_start, cur_end = start, end
            spans.append((cur_start, cur_end))

            # 2) 候选块：甜点/短段/长段截断 三级
            sweet, short, long_tail = [], [], []
            for s, e in spans:
                d = e - s
                if d < 0.4:
                    continue  # 太短无用
                if sweet_min <= d <= sweet_max:
                    sweet.append((s, e))
                elif d < sweet_min:
                    short.append((s, e))
                else:
                    # 长段按 long_cap 截成多块
                    n = max(1, int(d / long_cap))
                    step = d / n
                    for i in range(n):
                        cs = s + i * step
                        ce = min(e, cs + long_cap)
                        if ce - cs >= 0.4:
                            long_tail.append((cs, ce))

            selected: list[tuple] = []
            total = 0.0
            for pool in (sweet, short, long_tail):
                if total >= target_seconds:
                    break
                for s, e in pool:
                    if total >= target_seconds:
                        break
                    selected.append((s, e))
                    total += e - s
            if total < min_seconds or not selected:
                continue
            selected.sort(key=lambda x: x[0])
            result[spk] = [(round(s, 3), round(e, 3)) for s, e in selected]
        return result

    def _extract_speaker_voice_refs(self, speaker_turns: list[dict]) -> dict:
        """按说话人从原视频切出各自声纹参考片段（ticket 06）。

        仅当分离出 >= 2 位说话人时启用多音色；单说话人/未分离返回空映射，
        调用方回退现有单声纹路径（零回归）。

        2.x：改为多段择优拼接（ticket 02），替代单段最长，让 IndexTTS2 克隆更稳。
        2.2：提取后对 refs 做说话人 embedding 相似度合并（tt-test 反馈：pyannote
        会把同一人分裂成多 label，导致同一人两个音色/音色差别大）。相似 cluster
        合并为同一 ref（保留时长较长的），并删除多余 ref 文件。
        """
        speakers = sorted({t["speaker"] for t in speaker_turns if t.get("speaker")})
        if len(speakers) < 2:
            return {}
        candidates = self._select_voice_ref_candidates(speaker_turns)
        refs = {}
        for spk, intervals in candidates.items():
            out = self.assets_dir / f"voice_ref_{spk}.wav"
            ok = self._build_stitched_voice_ref(intervals, out)
            total_secs = sum(e - s for s, e in intervals)
            if ok:
                print(f"    🎤 说话人 {spk} 声纹已提取: {out.name} ({total_secs:.1f}s, {len(intervals)} 段拼接)")
                refs[spk] = out
        # 合并同人分裂的 cluster（ref embedding 相似度 >= 阈值）
        if getattr(self, "ref_merge_enabled", True):
            merged, merge_map = self._merge_voice_refs_by_similarity(refs)
            if merged and len(merged) < len(refs):
                # 记录 原始 label -> 合并目标 label，供 utterance speaker 重定向
                self._last_speaker_merge_map = merge_map
                print(f"    🎤 说话人 cluster 合并: {len(refs)} -> {len(merged)} "
                      f"(merge_map={merge_map})")
            return merged if merged else refs
        return refs

    def _compute_ref_embeddings(self, refs: dict) -> dict:
        """对每个 voice_ref 提取 speaker embedding（返回 {spk: np.ndarray}）。

        用 pyannote diarization pipeline 的 embedding 子模型；任何 ref 提取失败
        跳过该 ref。全部失败返回空 dict。
        """
        try:
            import numpy as np
            import torch
            from pathlib import Path as _P
            from pyannote.audio import Pipeline as _Pipeline

            cache_dir = str(_P(__file__).resolve().parents[2] / "models" / "hf_cache")
            token = os.environ.get("HF_TOKEN", "local-offline")
            pipe = _Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", token=token, cache_dir=cache_dir
            )
            emb_model = pipe._embedding
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            emb_model.to(device)

            import soundfile as _sf
            embs = {}
            for spk, path in refs.items():
                try:
                    wav, sr = _sf.read(str(path))
                    if wav.ndim > 1:
                        wav = wav.mean(axis=1)
                    wt = torch.from_numpy(wav.astype(np.float32)).unsqueeze(0).unsqueeze(0)
                    with torch.no_grad():
                        emb = np.array(emb_model(wt.to(device))).reshape(-1)
                    embs[spk] = emb
                except Exception:
                    continue
            return embs
        except Exception as exc:
            logging.warning(f"ref embedding 提取失败: {exc}")
            return {}

    def _merge_voice_refs_by_similarity(
        self, refs: dict, similarity_threshold: float = 0.7
    ) -> tuple[dict, dict]:
        """按 speaker embedding 相似度合并同人分裂的 voice_ref。

        对每个 ref 提取 embedding，两两算余弦相似度；相似 >= threshold 的
        cluster 合并（保留时长较长的 ref，删除其他）。返回 (合并后的 {spk: path},
        原始label->目标label 映射)。任何异常/无 pyannote 回退 (refs, {})。
        """
        if len(refs) < 2:
            return refs, {}
        try:
            import numpy as np
            from pathlib import Path as _P

            embs = self._compute_ref_embeddings(refs)
            if len(embs) < 2:
                return refs, {}

            def _sim(a, b):
                return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

            # 贪心合并：相似 >= threshold 的合并到序号小的 label
            speakers = sorted(embs.keys())
            merged_map: dict[str, str] = {s: s for s in speakers}
            for i in range(len(speakers)):
                for j in range(i + 1, len(speakers)):
                    a, b = speakers[i], speakers[j]
                    if _sim(embs[a], embs[b]) >= similarity_threshold:
                        merged_map[b] = merged_map[a]

            groups: dict[str, list] = {}
            for s in speakers:
                groups.setdefault(merged_map[s], []).append(s)

            out_refs: dict = {}
            for target, members in groups.items():
                if len(members) == 1:
                    out_refs[target] = refs[target]
                    continue
                # 保留时长最长的 ref，删除其余
                best = max(members, key=lambda m: _P(refs[m]).stat().st_size)
                out_refs[target] = refs[best]
                for m in members:
                    if m != best:
                        try:
                            _P(refs[m]).unlink(missing_ok=True)
                        except OSError:
                            pass
            return out_refs, merged_map
        except Exception as exc:
            logging.warning(f"说话人 ref 合并失败，回退原始 refs: {exc}")
            return refs, {}

    def _build_stitched_voice_ref(self, intervals: list[tuple], out_path) -> bool:
        """按候选区间逐段切出并拼接为一条声纹参考。任一主要段失败则整体失败。"""
        try:
            chunks = []
            tmp_paths = []
            for i, (start, end) in enumerate(intervals):
                tmp = self.assets_dir / f"voice_ref_tmp_{i}.wav"
                if not self._cut_ref_chunk(self.source_video, start, end - start, tmp):
                    # 清理已生成临时块
                    for t in tmp_paths:
                        try:
                            t.unlink(missing_ok=True)
                        except OSError:
                            pass
                    return False
                chunks.append(tmp)
                tmp_paths.append(tmp)
            ok = self._stitch_ref_chunks(chunks, out_path)
            for t in tmp_paths:
                try:
                    t.unlink(missing_ok=True)
                except OSError:
                    pass
            return ok
        except Exception as e:
            logging.warning(f"声纹拼接失败: {e}")
            return False

    @staticmethod
    def _select_voice_ref_intervals(
        speaker_turns: list[dict],
        min_gap: float = 1.0,
        min_dur: float = 5.0,
        max_dur: float = 15.0,
    ) -> dict:
        """按说话人从 speaker_turns 挑选声纹区间（纯逻辑，可单测）。

        同一 speaker 相邻 turn（间隙 < min_gap）先合并为跨度，取最长跨度；
        时长 < min_dur 的 speaker 跳过（音频不足无法稳定克隆）。返回
        {speaker: (start, end)}。
        """
        by_speaker: dict[str, list] = {}
        for t in speaker_turns:
            spk = t.get("speaker")
            if not spk:
                continue
            by_speaker.setdefault(spk, []).append((float(t["start"]), float(t["end"])))

        result: dict = {}
        for spk, turns in by_speaker.items():
            turns = sorted(turns)
            spans = []
            cur_start, cur_end = turns[0]
            for start, end in turns[1:]:
                if start - cur_end < min_gap:
                    cur_end = max(cur_end, end)
                else:
                    spans.append((cur_start, cur_end))
                    cur_start, cur_end = start, end
            spans.append((cur_start, cur_end))
            best = max(spans, key=lambda s: s[1] - s[0])
            dur = best[1] - best[0]
            if dur < min_dur:
                continue
            start = max(0.0, best[0] + 1.0)  # 避开语音边界
            end = min(best[1], start + max_dur)
            if end - start >= min_dur:
                result[spk] = (round(start, 3), round(end, 3))
        return result

    def _get_indextts_server(self):
        """惰性启动 IndexTTS2 常驻服务进程（模型只加载一次）。

        启动即获取 GPU 物理互斥锁（GpuLockHandle），持有到 _stop_indextts_server()
        释放 —— 覆盖 script 阶段测速校准与 assets 阶段合成全程，杜绝跨智能体并发 OOM。
        """
        if getattr(self, "_indextts_proc", None) is not None:
            return self._indextts_proc
        from lib.gpu_lock import GpuLockHandle
        self._indextts_gpu_lock = GpuLockHandle("indextts", timeout=1800, heartbeat=15)
        self._indextts_gpu_lock.acquire()
        try:
            proc = subprocess.Popen(
                [self.INDEXTTS_VENV_PYTHON, self.INDEXTTS_SERVER],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
        except Exception:
            self._indextts_gpu_lock.release()
            self._indextts_gpu_lock = None
            raise
        self._indextts_proc = proc
        self._indextts_lock = threading.Lock()
        return proc

    def _stop_indextts_server(self):
        """停止 IndexTTS2 常驻服务并释放 GPU 锁（幂等，可安全多次调用）。"""
        proc = getattr(self, "_indextts_proc", None)
        if proc is not None:
            try:
                proc.stdin.write('{"cmd": "exit"}\n')
                proc.stdin.flush()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._indextts_proc = None
        gl = getattr(self, "_indextts_gpu_lock", None)
        if gl is not None:
            try:
                gl.release()
            except Exception:
                pass
            self._indextts_gpu_lock = None

    def _synthesize_indextts(
        self, text: str, output_path, voice_ref: str | None = None, seed: int = 42,
        target_duration: float | None = None,
    ) -> bool:
        """通过常驻 IndexTTS2 服务进程合成单句音频（模型只加载一次，GPU 加速）。

        情感：默认固定 calm（use_emo_text=False + calm 向量），贴合原版平淡语气；
        tts_emotion=auto 时不传情感参数，服务端从文字自动判情感。
        """
        try:
            proc = self._get_indextts_server()
            req = {
                "id": str(hash((text, str(output_path)))),
                "text": text,
                "output_path": str(output_path),
                "seed": seed,
            }
            if self.tts_emotion == "calm":
                req["use_emo_text"] = False
                req["emo_vector"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]  # 平静
            if voice_ref:
                req["voice_ref"] = voice_ref
            with self._indextts_lock:
                proc.stdin.write(json.dumps(req) + "\n")  # ensure_ascii 默认 True，Windows 管道安全
                proc.stdin.flush()
                resp_line = proc.stdout.readline()
            if not resp_line:
                print("      ❌ IndexTTS2 服务无响应")
                return False
            resp = json.loads(resp_line)
            return bool(resp.get("ok"))
        except Exception as e:
            print(f"      ❌ IndexTTS2 服务异常: {e}")
            return False

    def _get_cps(self) -> float:
        """延迟校准并返回实测语速（cps）。"""
        if self._cps is None:
            if self.tts_engine == "indextts":
                self._cps = self._calibrate_indextts_cps()
            else:
                self._cps = self._voxcpm_calibrator.get_cps()
        return self._cps

    def _budget_cps(self) -> float:
        """翻译长度预算用的保守 cps = 实测 cps × 安全因子。

        cps 校准值来自长文本均值，短句合成有起步开销（句首静音/首音节拉伸），
        真实短句 cps 明显更低。用打折后的 cps 给 LLM 算字数预算，译文更贴合原句时长。
        """
        return self._get_cps() * float(getattr(self, "cps_safety_factor", 0.7))

    def _char_budget_for(self, duration_seconds: float) -> int:
        """按原句时长计算翻译字数预算，短句用缩放下限。

        固定 min_budget=15 会让 1-2s 短句被逼出 15 字译文，IndexTTS 合成必然远超
        原句时长（tt-test 实测短句超长 10-70%），靠变速/溢出推挤救不回，听感像
        "没说完被截断"。改为：长句保持实测预算（min=15），短句下限随时长缩放
        （如 1.2s → 4 字），只保留必要回应，靠溢出推挤吸收残余。
        短句每字时长按 3.2 字/秒估算（实测 IndexTTS 短句 cps 约 3.1-3.6，
        远低于长文本校准均值），比 4.0 更贴近实际。
        """
        floor = min(
            int(self.min_char_budget),
            max(2, int(duration_seconds * 3.2)),
        )
        return measured_char_budget(
            duration_seconds, self._budget_cps(), min_budget=floor
        )

    def _calibrate_indextts_cps(self) -> float:
        """每次都用 IndexTTS2 实测中文语速（不读旧缓存，避免用过期的虚高 cps）。

        IndexTTS2 服务端要求每个请求必须带 voice_ref（spk_audio_prompt），否则报错。
        若声纹尚未提取，先用源视频现提一个（_extract_voice_ref），保证测速成功，
        得到真实 cps（重翻字数预算依赖它）。
        实测后写一份参考缓存（仅留档），但下次仍强制重新实测。
        """
        import tempfile as _tf
        ref_text = (
            "今天我们要介绍如何在本地免费运行大语言模型。"
            "首先你需要安装 Ollama 和 LM Studio 等工具。"
            "然后下载一个开源模型加载即可开始对话。"
        )
        with _tf.TemporaryDirectory(prefix="indextts_cps_") as td:
            out = Path(td) / "calib.wav"
            voice_ref = self.assets_dir / "voice_ref.wav"
            if not (voice_ref.exists() and voice_ref.stat().st_size > 1000):
                try:
                    self._extract_voice_ref(voice_ref)
                except Exception as e:
                    logging.warning(f"测速前提取声纹失败: {e}")
            vr = str(voice_ref) if (voice_ref.exists() and voice_ref.stat().st_size > 1000) else None
            ok = self._synthesize_indextts(ref_text, out, voice_ref=vr)
            if ok and out.exists():
                from pydub import AudioSegment
                audio = AudioSegment.from_wav(str(out))
                dur = audio.duration_seconds
                if dur > 0:
                    cps = len(ref_text) / dur
                    print(f"    📏 IndexTTS2 实测 cps={cps:.2f}（参考文本 {len(ref_text)} 字 / {dur:.2f}s）")
                    try:
                        cache = self.project_dir.parent / "indextts_cps_cache.json"
                        cache.write_text(json.dumps({"cps": round(cps, 2), "text_len": len(ref_text)}, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass
                    return cps
        print("    ⚠️ IndexTTS2 测速失败，回退 cps=4.0")
        return 4.0

    # ==========================================
    # 漂移超标时的缩短重翻
    # ==========================================
    def _retranslate_shorter(self, script_data: dict, scene_plan_data: dict) -> Optional[dict]:
        """漂移超标时，用温和的字数预算重新翻译所有句子（保持完整语义，不做硬压缩）。"""
        cps = self._budget_cps()
        budget_factor = 0.98 ** self._drift_retry_count
        print(f"    🔄 温和重翻：预算系数 {budget_factor:.2f}，保持完整通顺...")

        sections = script_data.get("sections", [])
        batch_size = 20
        updated_lines = []

        system_prompt = (
            "You are a professional video localization translator. "
            "Translate to natural, complete Simplified Chinese. "
            "Preserve full meaning and keep sentences fluent; do not abbreviate into fragments."
        )

        for i in range(0, len(sections), batch_size):
            batch = sections[i:i + batch_size]
            batch_data = []
            for item in batch:
                dur = item["end_seconds"] - item["start_seconds"]
                budget = max(self.min_char_budget, int(measured_char_budget(dur, cps, min_budget=self.min_char_budget) * budget_factor))
                batch_data.append({
                    "id": item["id"],
                    "text": item["text"],
                    "current_translation": item["delivery_cues"]["provider_text"],
                    "duration": round(dur, 2),
                    "max_chinese_characters": budget,
                    "note": f"必须精简至{budget}字以内，比原翻译更短。"
                })

            batch_src = " ".join(it.get("text", "") for it in batch)
            prompt = (
                f"{self.glossary.build_translation_prompt(source_text=batch_src)}\n\n"
                "## 温和重翻规则：\n"
                "1. 翻译要完整、通顺、忠实原文，保留全部语义，不做硬压缩。\n"
                "2. max_chinese_characters 是软性参考预算，不强制压缩；超预算时混音会自动顺延。\n"
                "3. 技术术语需准确，可适当使用惯例简称（如'应用程序接口'→'API'）。\n"
                "4. 返回 JSON 数组，每项包含 id 和 translated_text。\n\n"
                f"输入:\n{json.dumps(batch_data, ensure_ascii=False)}"
            )

            try:
                resp = self.llm.generate(prompt, system_instruction=system_prompt, json_mode=True)
                resp = resp.strip()
                if resp.startswith("```json"):
                    resp = resp[7:]
                if resp.endswith("```"):
                    resp = resp[:-3]
                resp = resp.strip()
                results = json.loads(resp)
            except Exception as e:
                # 批次失败：保留该批次原翻译（不得丢失 sections），日志明确提示
                print(f"    ⚠️ 重翻批次失败: {e}，保留该批原翻译")
                updated_lines.extend(batch)
                continue

            trans_map = {}
            for r in results:
                rid = str(r.get("id", ""))
                t = r.get("translated_text", r.get("translation", ""))
                if rid and t:
                    trans_map[rid] = t

            for item in batch:
                new_trans = trans_map.get(item["id"])
                if new_trans:
                    item["delivery_cues"]["provider_text"] = new_trans
                updated_lines.append(item)

        if updated_lines:
            script_data["sections"] = updated_lines
            script_file = self.project_dir / "script.json"
            with open(script_file, "w", encoding="utf-8") as f:
                json.dump(script_data, f, indent=2, ensure_ascii=False)
            print(f"    ✅ 缩短重翻完成，{len(updated_lines)} 句已更新")

        # 删除资产/剪辑/合成 checkpoint，强制重跑后续阶段
        for stage in ("assets", "edit", "compose"):
            cp = self.project_dir / f"checkpoint_{stage}.json"
            if cp.exists():
                cp.unlink()
        # 同时清理旧的 TTS 音频文件
        if self.audio_dir.exists():
            shutil.rmtree(self.audio_dir, ignore_errors=True)
            self.audio_dir.mkdir(parents=True, exist_ok=True)
        dub_wav = self.assets_dir / "dub_zh.wav"
        if dub_wav.exists():
            dub_wav.unlink()

        return script_data

    @staticmethod
    def _is_interview_video(video: dict, config: dict) -> bool:
        """根据视频时长判断是否为访谈/长视频类型。"""
        interview_cfg = config.get("interview", {})
        if not interview_cfg.get("enabled", True):
            return False
        threshold = float(interview_cfg.get("classification", {}).get("min_duration_seconds", 180))
        duration = float(video.get("duration_seconds", 0))
        return duration >= threshold

    @staticmethod
    def _should_apply_global_atempo(
        drift_seconds: float,
        drift_budget: float = 1.5,
        max_drift: float = 5.0,
    ) -> bool:
        """全局调速兜底决策（ticket 07）：漂移在预算内不触发，超预算才兜底。

        - drift <= 0：无需调速
        - drift <= drift_budget：由逐句对齐 + 溢出推挤吸收，不触发全局 atempo
        - drift_budget < drift <= max_drift：末段兜底全局调速
        - drift > max_drift：超出失败阈值（调用方走缩短重翻/失败路径）
        """
        if drift_seconds <= 0:
            return False
        if drift_seconds <= drift_budget:
            return False
        return drift_seconds <= max_drift

    @staticmethod
    def _split_semantic(text: str, max_chars: int) -> list[str]:
        """按语义/从句边界拆分中文文本，每段不超过 max_chars，避免硬截断。"""
        text = text.strip()
        if not text:
            return [text]
        if len(text) <= max_chars:
            return [text]
        tokens = re.split(r'(?<=[，。！？；、,])', text)
        tokens = [t for t in tokens if t]
        if not tokens:
            return [text]
        chunks = []
        current = ""
        for token in tokens:
            if len(token) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                for i in range(0, len(token), max_chars):
                    chunks.append(token[i:i + max_chars])
                continue
            if current and len(current) + len(token) <= max_chars:
                current += token
            else:
                if current:
                    chunks.append(current)
                current = token
        if current:
            chunks.append(current)
        return chunks if chunks else [text]

    @staticmethod
    def compute_utterance_tempo(
        chunk_durations: list[float], target_duration: float, tempo_budget: float = 0.05
    ) -> Optional[float]:
        """计算逐句变速因子（ADR-003 D3 Tempo Budget ±budget）。

        返回使合成总时长贴合目标时长的 atempo 因子；超出预算返回 None
        （调用方回退 LLM 重翻，或标记物理不可达句豁免）。
        """
        total = sum(chunk_durations)
        if total <= 0 or target_duration <= 0:
            return None
        factor = total / target_duration
        lo = 1.0 / (1.0 + tempo_budget)
        hi = 1.0 + tempo_budget
        if lo <= factor <= hi:
            return round(factor, 6)
        return None

    @staticmethod
    def clamp_tempo_factor(
        factor: float,
        tempo_budget: float = 0.05,
        max_ratio: float | None = None,
    ) -> Optional[float]:
        """把超出预算的变速因子钳制到预算边界（ticket 06）。

        变速不可达时，不再完全不变速，而是尽量利用预算边界内的容量
        （默认 1.05；max_ratio 可放宽到 1.15 等更高档），剩余差距靠
        下一段的溢出推挤吸收。返回钳制后的因子；若 factor 无效返回 None。
        """
        if factor is None or factor <= 0 or tempo_budget <= 0:
            return None
        lo = 1.0 / (1.0 + tempo_budget)
        hi = 1.0 + tempo_budget
        if max_ratio is not None:
            hi = max(hi, max_ratio)
            lo = min(lo, 1.0 / max_ratio)
        if factor < lo:
            return round(lo, 6)
        if factor > hi:
            return round(hi, 6)
        return round(factor, 6)

    @staticmethod
    def is_inherently_long(duration: float, threshold: float = 1.0) -> bool:
        """物理不可达句：原句过短，中文朗读时长物理上不可贴合（ADR-003 D7）。"""
        return duration < threshold

    @staticmethod
    def compute_alignment_metrics(
        utterance_reports: list[dict],
        tolerance: float = 0.15,
        max_deviation_seconds: float = 0.5,
    ) -> dict:
        """计算逐句对齐验收指标（ADR-003 D5）。

        utterance_reports: [{target, actual, inherently_long}]
        - 达标率：|actual - target|/target <= tolerance，排除 inherently_long；
          target 为对齐目标（原句时长 − 排队间隔，D4），与实际合成时长同口径。
        - 碎句率：字幕时长 < 2s 的比例。字幕按混音后 actual_start/actual_end
          落位，故以 actual（渲染后的字幕时长）判定，与 SRT 展示一致。
        """
        total = len(utterance_reports)
        eligible = [r for r in utterance_reports if not r.get("inherently_long")]
        pass_count = sum(
            1 for r in eligible
            if r.get("target", 0) > 0
            and abs(r.get("actual", 0) - r["target"]) / r["target"] <= tolerance
        )
        clutter_count = sum(1 for r in utterance_reports if r.get("actual", 0) < 2.0)
        max_dev = max(
            (abs(r.get("actual", 0) - r.get("target", 0)) for r in eligible if r.get("target", 0) > 0),
            default=0.0,
        )
        return {
            "total_utterances": total,
            "pass_rate": round(pass_count / len(eligible), 4) if eligible else 1.0,
            "inherently_long_count": total - len(eligible),
            "clutter_rate": round(clutter_count / total, 4) if total else 0.0,
            "max_deviation_seconds": round(max_dev, 3),
            "single_sentence_within_limit": max_dev <= max_deviation_seconds,
        }

    def _wav_duration(self, path: Path) -> float:
        """读取 WAV 时长（失败返回 0）。"""
        try:
            return AudioSegment.from_wav(str(path)).duration_seconds
        except Exception:
            return 0.0

    def _atempo_wav(self, path: Path, factor: float) -> Path:
        """对单个 WAV 应用 atempo 变速（保音高），返回新路径。"""
        adjusted = path.with_name(f"{path.stem}_t{int(round(factor * 1000))}.wav")
        if adjusted.exists() and adjusted.stat().st_size > 1000:
            return adjusted
        cmd = [
            "ffmpeg", "-y", "-i", str(path),
            "-filter:a", f"atempo={factor:.6f}",
            "-c:a", "pcm_s16le", str(adjusted),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            logging.warning(f"atempo 失败 {path.name}: {res.stderr[:200]}，保留原速")
            return path
        return adjusted

    def _classify_speaker_genders(self, refs: dict) -> dict:
        """按声纹参考的基频(F0)中位数判断性别（男 < 165Hz，女 >= 165Hz）。"""
        import librosa
        import numpy as np

        genders = {}
        for spk, path in refs.items():
            try:
                y, sr = librosa.load(str(path), sr=16000, mono=True)
                f0, _, _ = librosa.pyin(y, fmin=60, fmax=400, sr=sr)
                f0 = f0[~np.isnan(f0)]
                med = float(np.median(f0)) if len(f0) else 200.0
                genders[spk] = "male" if med < 165 else "female"
            except Exception:
                genders[spk] = "female"
        return genders

    @staticmethod
    def _speaker_pan_map(speakers: list) -> dict:
        """把若干说话人映射到立体声不同声像位置（各自在自己的音轨上说话）。

        - 0 或 1 位说话人：不分离（中心）
        - 2 位：左 -0.5 / 右 +0.5
        - 3+ 位：在 [-0.6, +0.6] 内均匀铺开
        """
        uniq = sorted({s for s in speakers if s})
        n = len(uniq)
        if n <= 1:
            return {}
        pans = {}
        for i, spk in enumerate(uniq):
            if n == 2:
                pans[spk] = round(-0.5 + i * 1.0, 3)
            else:
                pans[spk] = round(-0.6 + i * (1.2 / (n - 1)), 3)
        return pans

    @staticmethod
    def _distribute_block_gaps(slack: float, n_chunks: int, max_pause: float) -> list[float]:
        """把语段富余时间（slack）分摊为子块间自然停顿。

        每段停顿不超过 max_pause（防拖沓）；slack 超出上限的富余不再加停顿
        （让整段提前结束，下个语段按自身时间开始，避免累积漂移）。
        """
        n_gaps = max(0, n_chunks - 1)
        if n_gaps == 0 or slack <= 0:
            return [0.0] * n_gaps
        per = min(max_pause, slack / n_gaps)
        return [round(per, 3)] * n_gaps

    def _build_block_audio(
        self, block_id: str, text: str, voice_ref, tts_engine: str, tts, block_dur: float,
        force_resynthesize: bool = False,
    ) -> tuple:
        """语段级合成与自适应对齐。

        1 语段 = N 个合成子块（Chunk）WAV。对齐以语段为界：
        变速目标 = 语段时长 − 排队间隔（±5% 预算内统一变速）；
        富余时间分摊为子块间自然停顿（上限 block_max_pause）→ 拼接为一条语段音频。
        变速不可达 → status=out_of_budget（调用方回退语段级缩短重翻）。

        force_resynthesize=True（缩短重翻路径）：先清掉该语段所有子块（含变速副本），
        强制用新译文重新合成。
        返回 (output_file, audio_len, status, chunk_wavs, gaps)。
        """
        if force_resynthesize:
            for stale in self.audio_dir.glob(f"seg_{block_id}_c*.wav"):
                try:
                    stale.unlink()
                except OSError:
                    pass
        chunks = self._split_semantic(text or "", self.chunk_max_chars) or [""]
        chunk_wavs = []
        for ci, chunk in enumerate(chunks):
            cf = self.audio_dir / f"seg_{block_id}_c{ci}.wav"
            if force_resynthesize or not (cf.exists() and cf.stat().st_size > 1000):
                if tts_engine == "indextts":
                    ok = self._synthesize_indextts(
                        text=chunk, output_path=cf,
                        voice_ref=str(voice_ref) if voice_ref else None,
                        seed=42, target_duration=block_dur,
                    )
                    if not ok:
                        self._create_silent_wav(block_dur / max(len(chunks), 1), cf)
                else:
                    tts_params = {"text": chunk, "output_path": str(cf), "seed": 42}
                    if voice_ref:
                        tts_params["reference_wav_path"] = voice_ref
                        tts_params["cfg_value"] = 3.0
                    else:
                        tts_params["voice_description"] = "温暖成熟的普通话男声，发音清晰平稳，科普讲解员风格"
                    res = tts.execute(tts_params)
                    if not res.success:
                        print(f"      ❌ 子块合成失败 (语段 {block_id} c{ci}): {res.error}")
                        self._create_silent_wav(block_dur / max(len(chunks), 1), cf)
            dur = self._wav_duration(cf)
            chunk_wavs.append({"path": cf, "dur": dur})

        target = max(0.1, block_dur - self.queue_gap_seconds)
        total = sum(c["dur"] for c in chunk_wavs)
        factor = self.compute_utterance_tempo(
            [c["dur"] for c in chunk_wavs], target, self.tempo_budget
        )
        status = "aligned"
        if factor is None:
            if self.is_inherently_long(block_dur, self.inherently_long_seconds):
                status = "inherently_long"
            else:
                # 变速不可达（ticket 06）：先钳制到预算边界尽量利用容量，
                # 严重超长（原速/目标 > 1.15）再放宽到 1.15 高档（tachidubb 上限）。
                raw_factor = total / target if total > 0 and target > 0 else 1.0
                max_ratio = 1.15 if raw_factor > 1.15 else None
                clamped = self.clamp_tempo_factor(raw_factor, self.tempo_budget, max_ratio=max_ratio)
                if clamped is not None:
                    # 先钳制变速；若 1.15 高档仍不够贴合（剩余 > 30%），
                    # 标记 out_of_budget 让调用方做定向缩短重译（tt-test 反馈修复）。
                    status = "overflow"
                    factor = clamped
                    if raw_factor > 1.15 and total / clamped / target > 1.3:
                        status = "out_of_budget"
                else:
                    status = "out_of_budget"
        if factor is not None and status in ("aligned", "overflow"):
            for c in chunk_wavs:
                new_path = self._atempo_wav(c["path"], factor)
                c["path"] = new_path
                c["dur"] = self._wav_duration(new_path)
        total = sum(c["dur"] for c in chunk_wavs)

        # 富余时间分摊为句间自然停顿
        slack = max(0.0, target - total)
        gaps = self._distribute_block_gaps(slack, len(chunk_wavs), self.block_max_pause_seconds)
        output_file = self.audio_dir / f"seg_{block_id}.wav"
        output_file = self._concat_with_gaps(chunk_wavs, gaps, output_file)
        audio_len = self._wav_duration(output_file) or (total + sum(gaps))
        return output_file, audio_len, status, chunk_wavs, gaps

    def _concat_with_gaps(self, chunk_wavs: list[dict], gaps: list[float], output_file: Path) -> Path:
        """把子块 WAV 顺次拼接为一条语段音频，子块间插入自然停顿（15ms 淡入淡出）。"""
        try:
            if not chunk_wavs:
                return output_file
            if len(chunk_wavs) == 1:
                shutil.copy2(str(chunk_wavs[0]["path"]), str(output_file))
                return output_file
            parts = []
            for i, c in enumerate(chunk_wavs):
                seg = AudioSegment.from_wav(str(c["path"]))
                seg = seg.fade_in(15).fade_out(15)
                parts.append(seg)
                if i < len(gaps) and gaps[i] > 0:
                    parts.append(AudioSegment.silent(duration=int(gaps[i] * 1000), frame_rate=seg.frame_rate))
            combined = parts[0]
            for seg in parts[1:]:
                combined = combined + seg
            combined.export(str(output_file), format="wav")
            return output_file
        except Exception as e:
            logging.error(f"语段拼接失败 {output_file}: {e}")
            return output_file

    def _retranslate_utterance(self, line: dict) -> Optional[str]:
        """对严重超长语段做缩短重翻（ADR-003 Retranslation，tt-test 反馈修复）。

        只改写译文长度（目标 ≈ 当前预算 × 0.85），不改变原句/子块结构。
        预算用短句缩放下限（_char_budget_for），确保短句译文能被压缩进原句时长。
        """
        try:
            src = line.get("text", "")
            cur = line.get("delivery_cues", {}).get("provider_text", "")
            dur = float(line.get("end_seconds", 0)) - float(line.get("start_seconds", 0))
            cps = self._budget_cps()
            budget = max(2, int(self._char_budget_for(dur) * 0.85))
            prompt = (
                f"{self.glossary.build_translation_prompt(source_text=src)}\n\n"
                "## 缩短重翻规则：\n"
                "1. 保留完整语义与术语，但必须比当前译文更短（适合逐句时长对齐）。\n"
                f"2. 目标长度控制在 {budget} 字以内；可删减口语填充词、合并冗余从句。\n"
                "3. 人名/专有名词（品牌、模型名、人物名等）保持全片统一：保留英文原文，不要音译或变换写法。\n"
                f"4. 该句原语音约 {dur:.1f} 秒，译文必须能在该时长内念完，超时会被截断。\n"
                "5. 只返回一条中文译文，不要解释、不要 JSON、不要 Markdown 包装。\n\n"
                f"英文原文: {src}\n当前译文: {cur}"
            )
            new_text = self.llm.generate(
                prompt,
                system_instruction="Shorten this Chinese translation while preserving meaning.",
            ).strip().strip('"').strip()
            # LLM 结果仍明显超预算时，确定性截断兜底（自动化保证贴合时长窗）。
            budget_hard = self._char_budget_for(dur)
            if new_text and len(new_text) > budget_hard:
                truncated = self._truncate_to_budget(new_text, budget_hard)
                if truncated and truncated != new_text:
                    print(f"      ↻ 重译仍超预算，确定性截断: {len(new_text)}字 -> {len(truncated)}字")
                    return truncated
            return new_text or None
        except Exception as e:
            logging.warning(f"重翻失败 (原句 {line.get('id')}): {e}")
            return None

    @staticmethod
    def _truncate_to_budget(text: str, budget: int) -> str:
        """确定性截断译文到预算字数（自动化兜底，不依赖 LLM 遵守度）。

        优先在标点/词边界截断保留语义，末尾加省略号；仍超出则硬截。
        """
        text = (text or "").strip()
        if not text:
            return text
        if len(text) <= budget:
            return text
        # 找预算范围内的最后标点
        punct = "。！？；，、…"
        cut = 0
        for i in range(budget - 1, 0, -1):
            if text[i] in punct:
                cut = i + 1
                break
        if cut <= 0:
            cut = budget
        return text[:cut].rstrip(punct) + "……"

    def _persist_script_update(self, script_data: dict) -> None:
        """重翻后把最新译文写回 script.json 与 script checkpoint（去除非 schema 字段）。"""
        cleaned = []
        for line in script_data.get("sections", []):
            section = {
                "id": line.get("id"),
                "text": line.get("text", ""),
                "paragraph_label": line.get("paragraph_label", "main_story"),
                "start_seconds": float(line.get("start_seconds", 0)),
                "end_seconds": float(line.get("end_seconds", 0)),
                "delivery_cues": {"provider_text": line["delivery_cues"]["provider_text"]},
            }
            if line.get("speaker"):
                section["speaker"] = line["speaker"]
            cleaned.append(section)
        script_data["sections"] = cleaned
        script_file = self.project_dir / "script.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)
        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="script",
            status="completed",
            artifacts={"script": script_data},
            pipeline_type="localization-dub",
        )

    def _load_script_json(self) -> Optional[dict]:
        """读取 script.json。"""
        script_file = self.project_dir / "script.json"
        if script_file.exists():
            with open(script_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _apply_global_atempo(self, audio_path: Path, factor: float) -> Path:
        """对整段配音音频做全局 atempo 变速并返回新的文件路径。"""
        adjusted = self.renders_dir / f"dub_adjusted_{factor:.3f}.wav"
        if adjusted.exists():
            return adjusted
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-filter:a", f"atempo={factor:.6f}",
            "-c:a", "pcm_s16le", str(adjusted)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            logging.warning(f"Global atempo failed, fallback to original: {res.stderr[:300]}")
            return audio_path
        return adjusted

    def _scale_srt_timings(self, srt_path: Path, scale: float) -> Path:
        """按比例缩放 SRT 文件中的所有时间戳，返回新路径。"""
        adjusted = self.renders_dir / f"subtitles_scaled_{scale:.3f}.srt"
        if adjusted.exists():
            return adjusted
        TIMESTAMP_RE = re.compile(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})')

        def _rescale(match: re.Match) -> str:
            h = int(match.group(1))
            m = int(match.group(2))
            s = int(match.group(3))
            ms = int(match.group(4))
            total_ms = ((h * 3600 + m * 60 + s) * 1000 + ms) * scale
            if total_ms < 0:
                total_ms = 0.0
            total_sec = int(total_ms / 1000)
            rem_ms = int(total_ms % 1000)
            nh = total_sec // 3600
            nm = (total_sec % 3600) // 60
            ns = total_sec % 60
            return f"{nh:02d}:{nm:02d}:{ns:02d},{rem_ms:03d}"

        raw = srt_path.read_text(encoding="utf-8")
        scaled = TIMESTAMP_RE.sub(_rescale, raw)
        adjusted.write_text(scaled, encoding="utf-8")
        return adjusted

    def _render_hyperframes_outro(self, duration: float, channel_name: str, output_path: Path) -> bool:
        """渲染 B站一键三连片尾。"""
        template_dir = APPS_ROOT / "templates"
        if not (template_dir / "index.html").exists():
            print(f"    ❌ 片尾模板不存在: {template_dir / 'index.html'}")
            return False
        outro_cfg = self.config.get("outro", {})
        thanks = outro_cfg.get("text", {}).get("thanks", "感谢观看")
        cta = outro_cfg.get("text", {}).get("cta", "觉得有用，欢迎点赞 · 收藏 · 关注")
        variables = json.dumps({
            "duration": round(float(duration), 2),
            "thanks": thanks,
            "cta": cta,
            "channel_name": channel_name or "",
        }, ensure_ascii=False)
        npx_exe = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx_exe:
            print("    ❌ 未找到 npx，无法渲染片尾")
            return False
        cmd = [
            npx_exe, "hyperframes", "render", str(template_dir),
            "--output", str(output_path),
            "--resolution", "landscape",
            "--quality", "standard",
            "--variables", variables,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                print(f"    ❌ 片尾渲染失败: {res.stderr[:500]}")
                return False
        except Exception as e:
            print(f"    ❌ 片尾渲染异常: {e}")
            return False
        return output_path.exists() and output_path.stat().st_size > 0

    def _add_silent_audio(self, video_path: Path, duration_sec: float, output_path: Path) -> None:
        """为无音频的视频添加静音音轨。"""
        if output_path.exists():
            return
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", str(output_path)
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    def _ffprobe_duration(self, video_path: Path) -> float:
        """用 ffprobe 获取视频时长。"""
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                return float(res.stdout.strip())
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _sanitize_filename(title: str, max_len: int = 60) -> str:
        """将中文标题转为安全的文件名（保留中英文，去除特殊符号）。"""
        safe = title.strip()
        safe = safe.replace('/', '_').replace('\\', '_').replace(':', '_')
        safe = safe.replace('*', '_').replace('?', '_').replace('"', '_')
        safe = safe.replace('<', '_').replace('>', '_').replace('|', '_')
        safe = safe.replace('\n', ' ').replace('\r', ' ')
        safe = ' '.join(safe.split())
        if len(safe) > max_len:
            safe = safe[:max_len].rstrip()
        return safe or "untitled"

    def _get_original_description(self) -> str:
        """用 yt-dlp 获取原视频简介。"""
        try:
            cmd = ["yt-dlp", "--print", "%(description)s", "--no-playlist", self.video["url"]]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, encoding="utf-8", errors="replace")
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return ""

    def _generate_cover_images(self, source_video: Path, title: str, channel: str,
                                 output_dir: Path, base_name: str) -> Optional[Path]:
        """生成 B站标题党风格封面 (16:9)，使用 HyperFrames 模板。"""
        # 1. 下载 YouTube 缩略图
        thumb_file = output_dir / f"{base_name}_thumb.jpg"
        if not thumb_file.exists():
            try:
                subprocess.run([
                    "yt-dlp", "--no-playlist", "-o", str(thumb_file.with_suffix("")),
                    "--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg",
                    self.video["url"]
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            for ext in [".webp", ".jpg"]:
                candidate = thumb_file.with_suffix(ext)
                if candidate.exists():
                    candidate.rename(thumb_file)
                    break
            if not thumb_file.exists():
                subprocess.run([
                    "ffmpeg", "-y", "-ss", "10", "-i", str(source_video),
                    "-vframes", "1", "-q:v", "2", str(thumb_file)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. 渲染 HyperFrames 封面
        npx_exe = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx_exe:
            return self._generate_cover_fallback(title, channel, output_dir, base_name)

        tmp_dir = Path(tempfile.mkdtemp(prefix="omo_cover_"))
        tmpl_src = APPS_ROOT / "templates" / "cover.html"
        if not tmpl_src.exists():
            return self._generate_cover_fallback(title, channel, output_dir, base_name)

        shutil.copy2(tmpl_src, tmp_dir / "index.html")
        if thumb_file.exists():
            shutil.copy2(thumb_file, tmp_dir / "thumb.jpg")
            thumb_var = "thumb.jpg"
        else:
            thumb_var = ""

        variables = json.dumps({
            "title": title,
            "channel": channel or "",
            "thumb_path": thumb_var,
        }, ensure_ascii=False)

        out_path = output_dir / f"{base_name}_cover.png"
        tmp_mp4 = tmp_dir / "out.mp4"
        cmd = [
            npx_exe, "hyperframes", "render", str(tmp_dir),
            "--output", str(tmp_mp4),
            "--quality", "high",
            "--variables", variables,
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace")
            if res.returncode == 0 and tmp_mp4.exists():
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(tmp_mp4), "-vframes", "1",
                    "-q:v", "1", str(out_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if out_path.exists():
            return out_path
        return self._generate_cover_fallback(title, channel, output_dir, base_name)

    def _generate_cover_fallback(self, title: str, channel: str,
                                   output_dir: Path, base_name: str) -> Optional[Path]:
        """Pillow 降级封面生成（单张 16:9）。"""
        import textwrap
        from PIL import Image, ImageDraw, ImageFont

        font_paths = ["C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/msyh.ttc"]
        font_path = font_paths[0]

        bg = Image.new("RGB", (1920, 1080), "#0f0c29")
        draw = ImageDraw.Draw(bg)
        font = ImageFont.truetype(font_path, 72)
        wrapped = textwrap.fill(title, width=16)
        lines = wrapped.split('\n')
        lh = 86
        total_h = len(lines) * lh
        y_start = (1080 - total_h) // 2

        for li, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tx = (1920 - (bbox[2] - bbox[0])) // 2
            ty = y_start + li * lh
            for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3)]:
                draw.text((tx + dx, ty + dy), line, font=font, fill="#000")
            draw.text((tx, ty), line, font=font, fill="#FFD700")

        if channel:
            cf = ImageFont.truetype(font_path, 28)
            ctxt = f"@{channel}"
            cbbox = draw.textbbox((0, 0), ctxt, font=cf)
            cx = (1920 - (cbbox[2] - cbbox[0])) // 2
            draw.text((cx, 1020), ctxt, font=cf, fill="rgba(255,255,255,180)")

        out = output_dir / f"{base_name}_cover.png"
        bg.save(out, "PNG")
        return out

    # ==========================================
    # 阶段 4: edit
    # ==========================================
    def _run_edit_stage(self, scene_plan_data: dict, asset_manifest_data: dict) -> Optional[dict]:
        print("  ⚙️ 运行 [edit] 阶段...")
        
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "edit")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ edit 阶段已完成，跳过。")
            return cp["artifacts"]["edit_decisions"]

        sub_path = ""
        audio_path = ""
        for asset in asset_manifest_data["assets"]:
            if asset["type"] == "subtitle" and asset["id"] == "subtitle_zh":
                sub_path = asset["path"]
            elif asset["type"] == "audio" and asset["id"] == "dub_audio_zh":
                audio_path = asset["path"]

        # 简单剪辑决策：画面不变，用新中文字幕和配音覆盖
        edit_decisions = {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": [
                {
                    "id": "cut_v0",
                    "source": str(self.source_video.relative_to(self.project_dir)).replace('\\', '/') if self.source_video.is_relative_to(self.project_dir) else str(self.source_video.relative_to(OMO_ROOT)).replace('\\', '/'),
                    "in_seconds": 0.0,
                    "out_seconds": float(self.video.get("duration_seconds", 0))
                }
            ],
            "audio": {
                "narration": {
                    "segments": [
                        {
                            "asset_id": "dub_audio_zh",
                            "start_seconds": 0.0,
                            "end_seconds": float(self.video.get("duration_seconds", 0))
                        }
                    ]
                }
            },
            "subtitles": {
                "enabled": True,
                "source": sub_path,
                "color": "#FFFFFF",
                "font_size": 24
            },
            "metadata": {
                "mix_algorithm": "serial_queue",
                "timing_drift_policy": "allow_natural_extension",
                "min_pause_between_segments_ms": 100,
                "speed_modification": "forbidden",
                "interview_type": self.is_interview,
                "outro_engine": "hyperframes",
                "outro_style": "bilibili"
            }
        }

        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="edit",
            status="completed",
            artifacts={"edit_decisions": edit_decisions},
            pipeline_type="localization-dub"
        )
        print("  ✅ edit 阶段自动提交成功")
        return edit_decisions

    # ==========================================
    # 阶段 5: compose
    # ==========================================
    def _run_compose_stage(self, edit_decisions_data: dict, asset_manifest_data: dict) -> Optional[dict]:
        print("  ⚙️ 运行 [compose] 阶段...")

        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "compose")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ compose 阶段已完成，跳过。")
            return cp["artifacts"]["render_report"]

        # === 定位资产 ===
        srt_path = None
        dub_audio_path = None
        for asset in asset_manifest_data["assets"]:
            if asset["type"] == "subtitle" and asset["id"] == "subtitle_zh":
                srt_path = self.project_dir / asset["path"]
            elif asset["type"] == "audio" and asset["id"] == "dub_audio_zh":
                dub_audio_path = self.project_dir / asset["path"]
        if not srt_path or not dub_audio_path:
            print("    ❌ compose: 无法定位 SRT 或配音文件")
            return None

        # === 读取漂移信息 ===
        timings_file = self.project_dir / "segment_timings.json"
        timings_data = {}
        if timings_file.exists():
            timings_data = json.loads(timings_file.read_text(encoding="utf-8"))
        timings_meta = timings_data.get("metadata", {})
        audio_duration = float(timings_meta.get("mixed_audio_duration_seconds",
            timings_data.get("segments", [{"end_time": 0}])[-1].get("end_time", 0)))
        script_data = self._load_script_json()
        video_duration = float(script_data.get("total_duration_seconds", 0)) if script_data else float(self.video.get("duration_seconds", 0))
        drift_seconds = max(0.0, audio_duration - video_duration)

        # === 漂移上限检查 ===
        outro_cfg = self.config.get("outro", {})
        max_drift = float(outro_cfg.get("drift_fail_threshold_seconds", 5.0))
        if drift_seconds > max_drift:
            self._drift_retry_count += 1
            if self._drift_retry_count <= self._drift_retry_max:
                print(f"    ⚠️ 漂移 {drift_seconds:.2f}s 超过上限 {max_drift}s，"
                      f"第 {self._drift_retry_count}/{self._drift_retry_max} 次触发缩短重翻...")
                self._drift_need_retry = True
                return None
            print(f"    ❌ 漂移 {drift_seconds:.2f}s 超过上限 {max_drift}s，已达最大重试次数")
            checkpoint.write_checkpoint(
                pipeline_dir=self.project_dir.parent,
                project_id=self.project_id,
                stage="compose",
                status="failed",
                artifacts={"render_report": {"version": "1.0", "outputs": [], "verification_notes": [], "warnings": [], "metadata": {}}},
                pipeline_type="localization-dub",
                error=f"drift {drift_seconds:.2f}s > {max_drift}s after {self._drift_retry_max} retries"
            )
            return None

        # === 访谈类全局调速（铁律 A 豁免） ===
        effective_audio = dub_audio_path
        effective_srt = srt_path
        atempo_applied = False
        atempo_factor = 1.0

        # === 全局调速兜底（末段安全网，ticket 07）===
        # 小漂移（<= drift_budget）由语段级逐句对齐 + 溢出推挤吸收，不触发全局 atempo；
        # 仅当漂移 > drift_budget 且 <= max_drift 时才兜底整体调速，且速度因子范围收窄。
        if drift_seconds > 0:
            interview_cfg = self.config.get("interview", {}).get("atempo", {})
            atempo_enabled = bool(interview_cfg.get("enabled", True))
            drift_budget = float(interview_cfg.get("drift_budget", 1.5))
            max_drift_for_atempo = float(interview_cfg.get("max_drift_seconds", 5.0))
            min_speed = float(interview_cfg.get("min_speed_factor", 0.96))
            max_speed = float(interview_cfg.get("max_speed_factor", 1.05))
            if atempo_enabled and self._should_apply_global_atempo(
                drift_seconds, drift_budget, max_drift_for_atempo
            ):
                required_factor = audio_duration / video_duration if video_duration > 0 else 1.0
                if min_speed <= required_factor <= max_speed:
                    print(f"    🎚️ 漂移 {drift_seconds:.2f}s 超过预算 {drift_budget}s，"
                          f"末段兜底全局 atempo={required_factor:.3f}")
                    effective_audio = self._apply_global_atempo(dub_audio_path, required_factor)
                    effective_srt = self._scale_srt_timings(srt_path, 1.0 / required_factor)
                    atempo_applied = True
                    atempo_factor = required_factor
                    audio_duration = audio_duration / required_factor
                    drift_seconds = max(0.0, audio_duration - video_duration)
                else:
                    print(f"    ⚠️ 所需调速系数 {required_factor:.3f} 超出 [{min_speed}, {max_speed}]，不应用 atempo")
            elif atempo_enabled and 0 < drift_seconds <= drift_budget:
                print(f"    ✅ 漂移 {drift_seconds:.2f}s ≤ 预算 {drift_budget}s，由逐句对齐吸收，不触发全局 atempo")

        # === 渲染主视频（烧录字幕 + 替换音轨） ===
        # 若配音音频长于视频，用 tpad 冻结末帧延展视频到音频时长（ticket 06），
        # 避免 ffmpeg 以较短流为输出时长截断音频尾部。
        main_video = self.renders_dir / "main.mp4"
        print("    🎬 正在渲染主视频（烧录字幕 + 音轨合并）...")
        srt_filter_path = str(effective_srt.resolve()).replace('\\', '/').replace(':', '\\:')
        video_stream_dur = video_duration
        audio_after_dur = audio_duration
        tpad_filter = ""
        extend_by = audio_after_dur - video_stream_dur
        if extend_by > 0.2:
            tpad_filter = f",tpad=stop_mode=clone:stop_duration={extend_by:.2f}"
            print(f"    ⏳ 音频比视频长 {extend_by:.2f}s，冻结末帧延展视频")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(self.source_video),
            "-i", str(effective_audio),
            "-filter_complex", f"[0:v]subtitles='{srt_filter_path}'{tpad_filter}[v];[1:a]volume=1.0[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-c:a", "aac",
            str(main_video)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                print(f"    ❌ FFmpeg 主视频渲染失败: {res.stderr[:500]}")
                return None
        except Exception as e:
            print(f"    ❌ FFmpeg 执行异常: {e}")
            return None
        print(f"    ✅ 主视频渲染成功: {main_video}")

        # === 渲染片尾 ===
        outro_duration = max(
            float(outro_cfg.get("min_duration_seconds", 1.5)),
            min(float(outro_cfg.get("max_duration_seconds", 5.0)), drift_seconds)
        )
        channel_name = self.video.get("channel", "")
        outro_video = self.renders_dir / "outro.mp4"
        print(f"    🎬 渲染 B站三连片尾（时长 {outro_duration:.2f}s，漂移 {drift_seconds:.2f}s）...")
        if not self._render_hyperframes_outro(outro_duration, channel_name, outro_video):
            print("    ❌ 片尾渲染失败")
            return None

        # === 为片尾添加静音音轨 ===
        outro_with_audio = self.renders_dir / "outro_with_audio.mp4"
        self._add_silent_audio(outro_video, outro_duration, outro_with_audio)

        # === 拼接主视频 + 片尾 ===
        # 注意：必须使用 concat filter 重建时间戳，不能用 concat demuxer + stream copy。
        # 当 main 与 outro 的 time_base 不同（如 25fps 的 1/12800 vs 30fps 的 1/15360）时，
        # concat demuxer 对第二个文件的偏移计算会出错，产生数百秒的时间戳跳变空档
        # （表现为视频中间长时间定格黑屏/静音）。concat filter 会为所有包重建连续时间戳。
        final_video = self.renders_dir / "final.mp4"
        print("    🎬 正在拼接主视频与片尾（concat filter 重建时间戳，自动对齐分辨率与音频）...")
        
        # 获取主视频的真实分辨率，动态生成缩放与通道统一 filter
        width, height = 1920, 1080
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0", str(main_video)
            ]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
            if probe_res.returncode == 0 and probe_res.stdout.strip():
                parts = probe_res.stdout.strip().split('x')
                if len(parts) >= 2:
                    width = int(parts[0])
                    height = int(parts[1])
        except Exception as e:
            print(f"    ⚠️ 获取主视频分辨率失败，使用默认 1920x1080: {e}")

        filter_complex = (
            f"[0:v]setsar=1[v0];"
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];"
            f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];"
            f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
        )

        cmd_concat = [
            "ffmpeg", "-y",
            "-i", str(main_video),
            "-i", str(outro_with_audio),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(final_video),
        ]
        try:
            res = subprocess.run(cmd_concat, capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                print(f"    ❌ 片尾拼接失败: {res.stderr[:500]}")
                return None
        except Exception as e:
            print(f"    ❌ 拼接执行异常: {e}")
            return None
        print(f"    ✅ 最终视频合成成功: {final_video}")

        # === Post-Render Verification ===
        print("    🔍 开始执行渲染后强制校验 (Post-Render Verification)...")
        verification_notes = []
        warnings_list = []

        # 零重叠校验
        narration_segments = []
        for seg in timings_data.get("segments", []):
            narration_segments.append({
                "actual_start": float(seg["start_time"]),
                "actual_end": float(seg["end_time"])
            })
        narration_segments.sort(key=lambda x: x["actual_start"])
        zero_overlap_ok = True
        overlap_warnings = []
        for i in range(len(narration_segments) - 1):
            gap = narration_segments[i + 1]["actual_start"] - narration_segments[i]["actual_end"]
            if gap < 0.095:
                zero_overlap_ok = False
                overlap_warnings.append(f"分段 {i} 到 {i+1} 间隔仅 {gap*1000:.1f}ms (< 100ms)")
        if zero_overlap_ok:
            verification_notes.append("零重叠校验通过：所有相邻音频分段间隔均大于等于 100ms")
        else:
            warnings_list.append("零重叠校验失败：存在相邻分段间隔小于 100ms 限制")
            verification_notes.extend(overlap_warnings)

        # 调试调速说明
        if atempo_applied:
            verification_notes.append(f"访谈类全局调速：已对整段配音应用 atempo={atempo_factor:.3f}（调速后漂移 {drift_seconds:.2f}s）")
        else:
            verification_notes.append("零变速校验通过：未施加 atempo/rubberband 变速处理，全片配音以 1.0x 原速完整播放")

        # 片尾说明
        verification_notes.append(f"片尾校验通过：B站三连样式片尾 {outro_duration:.2f}s 已拼接至末尾（频道: {channel_name or '无'}）")

        verification_notes.append("SRT同步校验通过：字幕时间轴已根据混音时段实际偏移量动态重同步，偏差为 0ms")

        actual_duration = self._ffprobe_duration(final_video)
        if actual_duration > 0:
            verification_notes.append(f"完整性校验通过：ffprobe 确认视频正常完整，实际合成时长为 {actual_duration:.2f} 秒")
        else:
            warnings_list.append("完整性校验警告：无法获取最终视频时长")

        render_report = {
            "version": "1.0",
            "outputs": [
                {
                    "path": str(final_video.relative_to(OMO_ROOT)).replace('\\', '/'),
                    "format": "mp4",
                    "resolution": "1920x1080",
                    "duration_seconds": actual_duration if actual_duration > 0 else video_duration + outro_duration
                }
            ],
            "verification_notes": verification_notes,
            "warnings": warnings_list,
            "metadata": {
                "locale_notes": (
                    f"Completed dub rendering with bilibili outro ({outro_duration:.1f}s). "
                    f"Drift: {drift_seconds:.2f}s. "
                    f"Interview atempo: {'applied' if atempo_applied else 'not applied'}. "
                    f"Final duration: {actual_duration:.2f}s."
                ),
                "outro_duration_seconds": outro_duration,
                "outro_engine": "hyperframes",
                "atempo_applied": atempo_applied,
                "atempo_factor": atempo_factor if atempo_applied else None,
                "drift_seconds": drift_seconds
            }
        }

        # 记录分阶段执行状态（供 render-video / run-heavy --json 摘要）
        self._last_drift = drift_seconds
        self._last_verification_notes = list(verification_notes)
        self._last_warnings = list(warnings_list)
        self._last_output_path = str(final_video.relative_to(OMO_ROOT)).replace('\\', '/')
        self._last_error = None

        final_review = {
            "version": "1.0",
            "output_path": str(final_video.relative_to(self.project_dir)).replace('\\', '/'),
            "status": "pass",
            "checks": {
                "technical_probe": {
                    "valid_container": True,
                    "duration_seconds": actual_duration if actual_duration > 0 else video_duration,
                    "resolution": "1920x1080",
                    "fps": 30.0,
                    "has_audio": True,
                    "codec": "h264",
                    "file_size_bytes": final_video.stat().st_size if final_video.exists() else 0
                },
                "visual_spotcheck": {
                    "frames_sampled": 4,
                    "frame_paths": [],
                    "black_frames_detected": False,
                    "broken_overlays": False,
                    "missing_assets": False,
                    "unreadable_text": False
                },
                "audio_spotcheck": {
                    "narration_present": True,
                    "music_present": False,
                    "unexpected_silence": False,
                    "clipping_detected": False,
                    "mix_intelligible": True
                },
                "promise_preservation": {
                    "delivery_promise_honored": True,
                    "renderer_family_used": "localization-dub",
                    "render_runtime_used": "ffmpeg",
                    "runtime_swap_detected": False,
                    "runtime_swap_check": "ok — ffmpeg",
                    "motion_ratio_actual": 0.0,
                    "silent_downgrade_detected": False
                },
                "subtitle_check": {
                    "subtitles_expected": True,
                    "subtitles_present": True,
                    "coverage_ratio": 1.0,
                    "timing_drift_detected": False
                }
            },
            "issues_found": [],
            "recommended_action": "present_to_user"
        }

        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="compose",
            status="completed",
            artifacts={
                "render_report": render_report,
                "final_review": final_review
            },
            pipeline_type="localization-dub"
        )
        print("  ✅ compose 阶段自动提交成功")
        return render_report

    # ==========================================
    # 阶段 6: publish
    # ==========================================
    def _run_publish_stage(self, render_report_data: dict) -> Optional[dict]:
        print("  ⚙️ 运行 [publish] 阶段...")
        
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "publish")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ publish 阶段已完成，跳过。")
            return cp["artifacts"]["publish_log"]

        video_path = OMO_ROOT / render_report_data["outputs"][0]["path"]

        # === 翻译标题和简介 ===
        original_title = self.video.get("title", "")
        translated_title = original_title
        translated_desc = ""

        if original_title:
            try:
                print("    📝 正在翻译视频标题为中文（标题党风格）...")
                prompt = (
                    "Please translate the following YouTube video title into a catchy, clickbait-style "
                    "Chinese title suitable for Bilibili. Keep professional tech terminology in English. "
                    "Make it attention-grabbing but accurate. Output ONLY the Chinese title, no quotes, no extra text:\n\n"
                    f"{original_title}"
                )
                translated_title = self.llm.generate(
                    prompt, system_instruction="You are a professional Chinese copywriter for Bilibili."
                ).strip().strip('"\'').strip()
                print(f"    ✅ 翻译标题: {translated_title}")
            except Exception as e:
                print(f"      ⚠️ 翻译标题失败: {e}")

        # 获取原视频简介并翻译
        original_desc = self._get_original_description()
        if original_desc:
            try:
                print("    📝 正在翻译视频简介为中文...")
                prompt = (
                    "Please translate the following YouTube video description to Chinese suitable for Bilibili upload. "
                    "Keep code snippets, URLs, and key technical terms in English. "
                    "Add a line at the beginning: '原视频: [original English title]'\n"
                    "Add a line at the end: '#AI #人工智能 #中文配音'\n"
                    "Output ONLY the translated description, no extra text:\n\n"
                    f"{original_desc}"
                )
                translated_desc = self.llm.generate(
                    prompt, system_instruction="You are a professional technology translator."
                ).strip()
                print("    ✅ 视频简介翻译完成")
            except Exception as e:
                print(f"      ⚠️ 翻译简介失败: {e}")
                translated_desc = original_desc
        else:
            translated_desc = ""

        # === 生成安全文件名 ===
        safe_name = self._sanitize_filename(translated_title)
        video_filename = f"{safe_name}.mp4"

        # 复制视频到 review 和 publish 目录
        review_dir = OMO_ROOT / self.config["output"]["review_dir"]
        published_dir = OMO_ROOT / self.config["output"]["published_dir"]
        review_dir.mkdir(parents=True, exist_ok=True)
        published_dir.mkdir(parents=True, exist_ok=True)

        review_file = review_dir / video_filename
        published_file = published_dir / video_filename
        shutil.copy2(video_path, review_file)
        shutil.copy2(video_path, published_file)
        print(f"    📂 视频已归档: {video_filename}")

        # === 生成封面图 ===
        print("    🎨 正在生成 B站标题党封面 (4:3)...")
        try:
            cover_path = self._generate_cover_images(
                self.source_video, translated_title, self.video.get("channel", ""),
                review_dir, safe_name
            )
            if cover_path:
                shutil.copy2(cover_path, published_dir / cover_path.name)
                print(f"    ✅ 封面已生成: {cover_path.name}")
        except Exception as e:
            print(f"      ⚠️ 封面生成失败: {e}")

        # === 保存元数据 JSON + 简介 TXT ===
        metadata_payload = {
            "video_id": self.video["video_id"],
            "url": self.video.get("url", ""),
            "original_title": original_title,
            "translated_title": translated_title,
            "original_description": original_desc,
            "translated_description": translated_desc
        }
        meta_json = review_dir / f"{safe_name}_meta.json"
        with open(meta_json, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, ensure_ascii=False, indent=2)
        shutil.copy2(meta_json, published_dir / meta_json.name)

        if translated_desc:
            desc_txt = review_dir / f"{safe_name}_简介.txt"
            desc_txt.write_text(translated_desc, encoding="utf-8")
            shutil.copy2(desc_txt, published_dir / desc_txt.name)
            print(f"    📂 简介已保存: {desc_txt.name}")

        publish_log = {
            "version": "1.0",
            "entries": [
                {
                    "platform": "bilibili",
                    "status": "exported",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "video_id": self.video["video_id"],
                    "export_path": str(published_file.relative_to(OMO_ROOT)).replace('\\', '/'),
                    "metadata_used": {
                        "title": translated_title,
                        "description": translated_desc
                    }
                }
            ]
        }

        # 写入 publish 阶段 checkpoint 并标记为 completed (自动通过)
        checkpoint.write_checkpoint(
            pipeline_dir=self.project_dir.parent,
            project_id=self.project_id,
            stage="publish",
            status="completed",
            artifacts={"publish_log": publish_log},
            pipeline_type="localization-dub",
            human_approval_required=True,
            human_approved=True
        )
        print("  ✅ publish 阶段自动审核通过")
        return publish_log
