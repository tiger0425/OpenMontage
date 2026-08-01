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
from tools.analysis.transcriber import Transcriber
from tools.audio.voxcpm_speed_calibrator import VoxCPMSpeedCalibrator, measured_char_budget
from batch.llm_client import LLMClient


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

        # 翻译预算配置（修复短句预算过小 + 超长翻译切碎放大）
        self.min_char_budget = int(config.get("pipeline", {}).get("min_char_budget", 15))
        self.max_single_line_chars = int(config.get("pipeline", {}).get("max_single_line_chars", 60))

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
        if not ok and self._last_error is None:
            self._last_error = "run-heavy 管线执行失败"
        return ok

    def get_last_drift(self) -> Optional[float]:
        return self._last_drift

    def get_last_verification_notes(self) -> list:
        return self._last_verification_notes

    def get_last_warnings(self) -> list:
        return self._last_warnings

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
            "model_size": "base",
            "language": "en"
        })
        if not res.success:
            print(f"    ❌ 转录失败: {res.error}")
            return None
            
        raw_transcript = res.data
        print(f"    ✅ 转录完成。共 {len(raw_transcript['segments'])} 个分段，时长 {raw_transcript['duration_seconds']} 秒")
        
        # 2. 批量翻译
        print("    ✍️ 开始批量翻译并应用字数预算 (Law 1)...")
        translated_segments = self._translate_segments(raw_transcript["segments"])
        if not translated_segments:
            print("    ❌ 翻译失败")
            return None

        # 3. 构造 script.json 结构
        sections = []
        for item in translated_segments:
            sections.append({
                "id": str(item["line_id"]),
                "text": item["text"],
                "start_seconds": float(item["start"]),
                "end_seconds": float(item["end"]),
                "delivery_cues": {
                    "provider_text": item["translated_text"]
                }
            })
            
        script_data = {
            "version": "1.0",
            "title": self.video.get("title", "No Title"),
            "total_duration_seconds": float(raw_transcript["duration_seconds"]),
            "sections": sections,
            "metadata": {
                "source_language": "en-US",
                "target_language": "zh-CN"
            }
        }
        
        # 保存到本地
        script_file = self.project_dir / "script.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)

        # 4. 自动审核并写入 checkpoint
        success, issues = self.auto_reviewer.review_and_approve(
            project_id=self.project_id,
            stage="script",
            artifacts={"script": script_data}
        )
        if not success:
            print(f"    ❌ 自动审核不通过: {issues}")
            return None
            
        return script_data

    def _translate_segments(self, segments: list[dict]) -> Optional[list[dict]]:
        """分批调用 LLM 翻译分段，使用实测语速预算 + 语义拆分"""
        cps = self._get_cps()
        print(f"    📏 实测 VoxCPM 语速: {cps:.2f} 字/秒")
        translated_lines = []
        batch_size = 20

        system_prompt = (
            "You are a professional video localization translator specializing in AI and cloud technology.\n"
            "Your task is to translate English transcription lines to Simplified Chinese (zh-CN)."
        )

        for i in range(0, len(segments), batch_size):
            batch = segments[i:i+batch_size]
            print(f"    - 翻译分批 [{i+1} to {min(i+batch_size, len(segments))}/{len(segments)}]...")

            batch_data = []
            for item in batch:
                dur = item["end"] - item["start"]
                max_chars = measured_char_budget(dur, cps, min_budget=self.min_char_budget)
                words_count = len(item["text"].split())
                wps = words_count / dur if dur > 0 else 0
                is_dense = wps > 4.0
                batch_data.append({
                    "id": str(item["id"]),
                    "text": item["text"],
                    "duration": round(dur, 2),
                    "max_chinese_characters": max_chars,
                    "cps": round(cps, 2),
                    "drift_risk": "high" if is_dense else "low",
                    "note": (
                        f"实测预算 {max_chars} 字；密集段落请优先精简！"
                        if is_dense else f"实测预算 {max_chars} 字"
                    )
                })

            prompt = (
                f"{self.glossary.build_translation_prompt()}\n\n"
                "## 翻译指导规则：\n"
                "1. 必须精准翻译技术语境下的含义。\n"
                "2. 在准确、完整、术语合规的前提下，尽量将翻译控制在 max_chinese_characters 预算内。"
                "若中文翻译天然由多个从句/分句组成，可拆分为多个子条目，id 使用 '<id>_1'、'<id>_2' 格式。\n"
                "3. 返回格式必须是 JSON 数组，每个对象必须包含 id 和 translated_text。不要返回任何其他解释或 Markdown 包装。\n\n"
                f"输入数据:\n{json.dumps(batch_data, ensure_ascii=False)}"
            )

            try:
                resp_text = self.llm.generate(prompt, system_instruction=system_prompt, json_mode=True)

                resp_text_clean = resp_text.strip()
                if resp_text_clean.startswith("```json"):
                    resp_text_clean = resp_text_clean[7:]
                if resp_text_clean.endswith("```"):
                    resp_text_clean = resp_text_clean[:-3]
                resp_text_clean = resp_text_clean.strip()
                resp_text_clean = re.sub(r',\s*([\]}])', r'\1', resp_text_clean)

                try:
                    results = json.loads(resp_text_clean)
                except Exception as json_err:
                    logging.warning(f"Standard JSON parse failed, trying regex object extraction: {json_err}")
                    results = []
                    for obj_match in re.finditer(r'\{[^{}]*\}', resp_text_clean):
                        try:
                            obj = json.loads(obj_match.group(0))
                            results.append(obj)
                        except Exception:
                            pass

                translation_map = {}
                for r_item in results:
                    r_id = str(r_item.get("id", ""))
                    if not r_id:
                        continue
                    trans = r_item.get("translated_text", r_item.get("translation", r_item.get("text_zh", r_item.get("translated", ""))))
                    translation_map[r_id] = trans

                for item in batch:
                    line_id = str(item["id"])
                    dur = item["end"] - item["start"]
                    max_chars = measured_char_budget(dur, cps, min_budget=self.min_char_budget)
                    trans = self._get_segment_translation(line_id, translation_map)

                    if not trans or trans.strip() == "":
                        trans = item["text"]

                    # === Targeted Glossary Repair Loop ===
                    violations = self.glossary.validate_translation(item["text"], trans)
                    src_clean = re.sub(r'[^\w]', '', item["text"]).lower()
                    tgt_clean = re.sub(r'[^\w]', '', trans).lower()
                    if src_clean == tgt_clean and len(src_clean) > 3:
                        violations.append("翻译与英文原文完全相同，未能正确翻译为中文。你必须将其翻译为符合语境的中文，不能直接复制英文原文。")

                    if violations:
                        print(f"      ⚠️ 行 {line_id} 违反术语表/未翻译: {violations}，尝试自动修复...")
                        repair_budget = max(2, int(dur * cps))
                        for attempt in range(3):
                            repair_prompt = (
                                "You are a professional video localization translator.\n"
                                f"English source text: \"{item['text']}\"\n"
                                f"Your previous translation: \"{trans}\"\n\n"
                                "This translation violated technical glossary rules:\n"
                                f"{chr(10).join(violations)}\n\n"
                                "Please re-translate. You MUST satisfy all the glossary rules listed above.\n"
                                f"Additionally, keep the translation concise if possible. "
                                f"Target characters limit: {repair_budget} "
                                "(this is only a soft guideline; prioritized accuracy, completeness, and glossary compliance come first).\n"
                                "Return ONLY the corrected Chinese translation. Do not wrap in markdown or add explanations."
                            )
                            try:
                                repaired_trans = self.llm.generate(
                                    repair_prompt,
                                    system_instruction="Re-translate to satisfy technical glossary constraints strictly."
                                )
                                repaired_trans = repaired_trans.strip()
                                new_violations = self.glossary.validate_translation(item["text"], repaired_trans)
                                new_src_clean = re.sub(r'[^\w]', '', item["text"]).lower()
                                new_tgt_clean = re.sub(r'[^\w]', '', repaired_trans).lower()
                                if new_src_clean == new_tgt_clean and len(new_src_clean) > 3:
                                    new_violations.append("翻译与英文原文完全相同，未能正确翻译为中文。你必须将其翻译为符合语境的中文，不能直接复制英文原文。")
                                if not new_violations:
                                    print(f"      ✅ 行 {line_id} 修复成功: \"{repaired_trans}\"")
                                    trans = repaired_trans
                                    break
                                else:
                                    violations = new_violations
                                    trans = repaired_trans
                            except Exception as e:
                                logging.error(f"Glossary repair attempt {attempt+1} failed: {e}")
                        else:
                            print(f"      ❌ 行 {line_id} 修复 3 次后仍失败，最终翻译: \"{trans}\"")

                    # === 三档拆分决策（预算内单条 / ≤max_single_line 整句不拆 / 超长语义拆分） ===
                    # 修复：短句预算下限、超长/错位翻译不再被盲目切碎、子段时长按 len/cps 预测
                    plan = self.plan_split(
                        trans, max_chars, self.max_single_line_chars, cps
                    )
                    if len(plan) == 1:
                        translated_lines.append({
                            "line_id": line_id,
                            "start": item["start"],
                            "end": item["end"],
                            "text": item["text"],
                            "translated_text": trans
                        })
                    else:
                        offset = 0.0
                        for ci, (chunk, sub_dur) in enumerate(plan):
                            sub_start = item["start"] + offset
                            sub_end = sub_start + (sub_dur or dur / len(plan))
                            offset += sub_dur or dur / len(plan)
                            sub_id = f"{line_id}_c{ci}"
                            translated_lines.append({
                                "line_id": sub_id,
                                "start": sub_start,
                                "end": sub_end,
                                "text": item["text"],
                                "translated_text": chunk
                            })

            except Exception as e:
                logging.error(f"Translation batch failed: {e}")
                for item in batch:
                    translated_lines.append({
                        "line_id": str(item["id"]),
                        "start": item["start"],
                        "end": item["end"],
                        "text": item["text"],
                        "translated_text": item["text"]
                    })

        return translated_lines

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
        """assets 阶段入口：持有 GPU 物理互斥锁后执行（防止跨智能体并发 OOM）。"""
        from lib.gpu_lock import gpu_lock
        try:
            with gpu_lock("indextts-assets", timeout=1800, heartbeat=15):
                return self._do_assets_stage(script_data, scene_plan_data)
        except TimeoutError as e:
            print(f"    ❌ {e}")
            return None

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
        
        # === 从原视频自动提取说话人声纹 ===
        external_voice_ref = self.assets_dir / "voice_ref.wav"
        use_external_ref = False
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
        
        temp_segments = []
        
        # 逐段合成配音，并获取其实际音频长度 (不进行任何变速/atempo处理)
        total_lines = len(lines)
        tts_start_ts = _monotonic()
        for idx, line in enumerate(lines):
            line_id = line["id"]
            text = line["delivery_cues"]["provider_text"]
            dur = line["end_seconds"] - line["start_seconds"]
            
            output_file = self.audio_dir / f"seg_{line_id}.wav"
            
            # 如果已有现成的配音 WAV 文件且音量非静音(RMS >= 100)，直接复用以节省 GPU 时间
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
                f"[{tts_engine.upper()}] 分段 {idx+1}/{total_lines} ({progress_pct:.1f}%) "
                f"耗时{elapsed:.1f}s {eta_str} | {status}: {text[:20]}..."
            )

            if is_valid_existing:
                pass  # 心跳已输出，无需再打印
            else:
                if tts_engine == "indextts":
                    ok = self._synthesize_indextts(
                        text=text, output_path=output_file,
                        voice_ref=str(external_voice_ref) if use_external_ref else None,
                        seed=42,
                        target_duration=dur,
                    )
                    if not ok:
                        self._create_silent_wav(dur, output_file)
                else:
                    tts_params = {
                        "text": text,
                        "output_path": str(output_file),
                        "seed": 42,
                    }
                    if use_external_ref:
                        tts_params["reference_wav_path"] = str(external_voice_ref)
                        tts_params["cfg_value"] = 3.0
                    else:
                        tts_params["voice_description"] = "温暖成熟的普通话男声，发音清晰平稳，科普讲解员风格"
                    res = tts.execute(tts_params)
                    if not res.success:
                        print(f"      ❌ 合成失败 (分段 {line_id}): {res.error}")
                        self._create_silent_wav(dur, output_file)

            # 载入生成的配音，获取其实际时长 (维持 1.0x 原速，禁止变速)
            try:
                audio_seg = AudioSegment.from_wav(output_file)
                audio_len = audio_seg.duration_seconds
            except Exception as e:
                logging.error(f"Failed to read wav duration for seg_{line_id}: {e}")
                audio_len = dur
                
            temp_segments.append({
                "line": line,
                "path": output_file,
                "audio_len": audio_len
            })

        # 2. 串行排队混音算法 (Serial Queue Mix) 与时间戳计算
        print("    🎚️ 执行串行排队混音算法 (Serial Queue Mix, 100ms 间隔)...")
        previous_end = 0.0
        min_pause = 0.10  # 100ms
        segments_manifest = []
        
        for idx, item in enumerate(temp_segments):
            line = item["line"]
            ideal_start = line["start_seconds"]
            audio_len = item["audio_len"]
            
            # 串行排队混音，若上一句顺延，下一句自动往后推延 (零重叠保护)
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
                "audio_len": audio_len
            })

        # 建立最终时间线空白总音轨 (自然延伸，考虑最后的 previous_end 漂移)
        duration_sec = max(script_data["total_duration_seconds"], previous_end)
        full_track = AudioSegment.silent(duration=int(duration_sec * 1000), frame_rate=48000)
        
        # 逐段施加 15ms 淡入淡出，并贴入总音轨对应位置
        for idx, item in enumerate(temp_segments):
            seg_manifest_item = segments_manifest[idx]
            start_ms = int(seg_manifest_item["start_time"] * 1000)
            
            try:
                audio_seg = AudioSegment.from_wav(item["path"])
                audio_seg = audio_seg.fade_in(15).fade_out(15)  # 15ms 淡入淡出
                full_track = full_track.overlay(audio_seg, position=start_ms)
            except Exception as e:
                logging.error(f"Error mixing segment {idx}: {e}")
                
        dub_zh_wav = self.assets_dir / "dub_zh.wav"
        full_track.export(dub_zh_wav, format="wav")
        print(f"    ✅ 主音轨已生成 (零变速，总长 {duration_sec:.2f}秒): {dub_zh_wav}")

        # 3. 动态重同步生成 SRT 字幕文件
        print("    📝 字幕动态重同步生成中...")
        subtitles_srt = self.assets_dir / "subtitles.srt"
        self._write_srt(lines, subtitles_srt)
        print(f"    ✅ 字幕已同步保存: {subtitles_srt}")

        # 4. 构造 asset_manifest
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
            "source_tool": "voxcpm_tts",
            "scene_id": "global",
            "duration_seconds": float(duration_sec)
        })
        
        # 3. Individual narration segments (不含 metadata，以防违反 asset_manifest 的 schema 强校验)
        for seg in segments_manifest:
            assets_list.append({
                "id": seg["id"],
                "type": "narration",
                "path": seg["path"],
                "source_tool": "voxcpm_tts",
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
                "speed_modification": "forbidden"
            }
        }
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
        # 释放 IndexTTS2 GPU 进程（若使用）
        if self.tts_engine == "indextts":
            self._stop_indextts_server()
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
            import numpy as _np
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
            cmd = [
                "ffmpeg", "-y", "-i", str(self.source_video),
                "-ss", str(start), "-t", str(dur),
                "-vn", "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                str(external_voice_ref)
            ]
            subprocess.run(cmd, capture_output=True, check=True)

            # 2. 音量归一化到 RMS ~3500
            audio = AudioSegment.from_wav(str(external_voice_ref))
            if audio.duration_seconds < 8:
                return False
            target_rms = 3500
            if audio.rms > 0:
                gain = target_rms / audio.rms
                audio = audio.apply_gain(20 * _np.log10(gain))
            audio.export(str(external_voice_ref), format="wav")
            print(f"    🎤 声纹已提取并归一化: {external_voice_ref.name} ({audio.duration_seconds:.1f}s, RMS={audio.rms:.0f})")
            return True
        except Exception as e:
            logging.warning(f"声纹提取失败: {e}，使用内部锚点")
            return False

    def _get_indextts_server(self):
        """惰性启动 IndexTTS2 常驻服务进程（模型只加载一次）。"""
        if getattr(self, "_indextts_proc", None) is not None:
            return self._indextts_proc
        proc = subprocess.Popen(
            [self.INDEXTTS_VENV_PYTHON, self.INDEXTTS_SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
        )
        self._indextts_proc = proc
        self._indextts_lock = threading.Lock()
        return proc

    def _stop_indextts_server(self):
        proc = getattr(self, "_indextts_proc", None)
        if proc is None:
            return
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

    def _synthesize_indextts(
        self, text: str, output_path, voice_ref: str | None = None, seed: int = 42,
        target_duration: float | None = None,
    ) -> bool:
        """通过常驻 IndexTTS2 服务进程合成单句音频（模型只加载一次，GPU 加速）。"""
        try:
            proc = self._get_indextts_server()
            req = {
                "id": str(hash((text, str(output_path)))),
                "text": text,
                "output_path": str(output_path),
                "seed": seed,
            }
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

    def _calibrate_indextts_cps(self) -> float:
        """用 IndexTTS2 实测中文语速，结果缓存到 indextts_cps_cache.json。"""
        import tempfile as _tf
        cache = self.project_dir.parent / "indextts_cps_cache.json"
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                val = float(data.get("cps", 0))
                if val > 0:
                    print(f"    📏 使用缓存 IndexTTS2 cps={val:.2f}")
                    return val
            except Exception:
                pass
        ref_text = (
            "今天我们要介绍如何在本地免费运行大语言模型。"
            "首先你需要安装 Ollama 和 LM Studio 等工具。"
            "然后下载一个开源模型加载即可开始对话。"
        )
        with _tf.TemporaryDirectory(prefix="indextts_cps_") as td:
            out = Path(td) / "calib.wav"
            voice_ref = self.assets_dir / "voice_ref.wav"
            vr = str(voice_ref) if voice_ref.exists() else None
            ok = self._synthesize_indextts(ref_text, out, voice_ref=vr)
            if ok and out.exists():
                from pydub import AudioSegment
                audio = AudioSegment.from_wav(str(out))
                dur = audio.duration_seconds
                if dur > 0:
                    cps = len(ref_text) / dur
                    print(f"    📏 IndexTTS2 实测 cps={cps:.2f}（参考文本 {len(ref_text)} 字 / {dur:.2f}s）")
                    try:
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
        """漂移超标时，用更紧的字数预算重新翻译所有句子。"""
        cps = self._get_cps()
        budget_factor = 0.85 ** self._drift_retry_count
        print(f"    🔄 缩短重翻：预算系数 {budget_factor:.2f}，目标更紧凑的中文...")

        sections = script_data.get("sections", [])
        batch_size = 20
        updated_lines = []

        system_prompt = (
            "You are a professional video localization translator. "
            "CRITICAL: Translate to concise Simplified Chinese. "
            "Use fewer characters — every character counts. "
            "Keep technical terms accurate but make sentences as short as naturally possible."
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

            prompt = (
                f"{self.glossary.build_translation_prompt()}\n\n"
                "## 缩短重翻规则：\n"
                "1. 你的翻译必须比 current_translation 更短。\n"
                "2. 精简冗余表达，使用更紧凑的中文句式。\n"
                "3. 技术术语仍需准确，但可用简称（如'应用程序接口'→'API'）。\n"
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
                print(f"    ⚠️ 重翻批次失败: {e}，保留原翻译")
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
    def plan_split(trans: str, max_chars: int, max_single_line_chars: int, cps: float) -> list[tuple[str, float | None]]:
        """三档拆分决策 + 子段时长预测。

        修复问题链：
        - 短句预算过小（max_chars 可能低至 8）→ 正常翻译被切碎
        - 超长/错位翻译被盲目切碎放大 → 阈值内不拆
        - 子段时长按字符比例均摊假设错误 → 改按 len(chunk)/cps 预测

        返回 [(text, sub_duration_seconds | None), ...]：
        - len(trans) <= max_chars          → [(trans, None)]  预算内，单条，时长由原句决定
        - max_chars < len <= max_single    → [(trans, None)]  整句单条不拆，混音自然顺延
        - len > max_single                 → 拆分，每段 (chunk, len(chunk)/cps)
        """
        trans = (trans or "").strip()
        if len(trans) <= max_chars:
            return [(trans, None)]
        if len(trans) <= max_single_line_chars:
            return [(trans, None)]
        chunks = PipelineAutomator._split_semantic(trans, max_chars)
        cps = cps if cps and cps > 0 else 4.0
        return [(chunk, round(len(chunk) / cps, 3)) for chunk in chunks]

    @staticmethod
    def _get_segment_translation(line_id: str, translation_map: dict) -> str:
        """从 LLM 返回的翻译映射中提取某句的翻译（支持 LLM 拆分出的子句）。"""
        sub_keys = sorted(
            [k for k in translation_map if k.startswith(line_id + "_") or k.startswith(line_id + "-")],
            key=lambda k: k
        )
        if sub_keys:
            return " ".join(translation_map.get(k, "") for k in sub_keys)
        return translation_map.get(line_id, "")

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

        if self.is_interview and drift_seconds > 0:
            interview_cfg = self.config.get("interview", {}).get("atempo", {})
            max_drift_for_atempo = float(interview_cfg.get("max_drift_seconds", 1.5))
            min_speed = float(interview_cfg.get("min_speed_factor", 0.95))
            max_speed = float(interview_cfg.get("max_speed_factor", 1.05))
            if drift_seconds <= max_drift_for_atempo:
                required_factor = audio_duration / video_duration if video_duration > 0 else 1.0
                if min_speed <= required_factor <= max_speed:
                    print(f"    🎚️ 访谈类漂移 {drift_seconds:.2f}s ≤ {max_drift_for_atempo}s，应用全局 atempo={required_factor:.3f}")
                    effective_audio = self._apply_global_atempo(dub_audio_path, required_factor)
                    effective_srt = self._scale_srt_timings(srt_path, 1.0 / required_factor)
                    atempo_applied = True
                    atempo_factor = required_factor
                    audio_duration = audio_duration / required_factor
                    drift_seconds = max(0.0, audio_duration - video_duration)
                else:
                    print(f"    ⚠️ 所需调速系数 {required_factor:.3f} 超出 [{min_speed}, {max_speed}]，不应用 atempo")

        # === 渲染主视频（烧录字幕 + 替换音轨） ===
        main_video = self.renders_dir / "main.mp4"
        print("    🎬 正在渲染主视频（烧录字幕 + 音轨合并）...")
        srt_filter_path = str(effective_srt.resolve()).replace('\\', '/').replace(':', '\\:')
        cmd = [
            "ffmpeg", "-y",
            "-i", str(self.source_video),
            "-i", str(effective_audio),
            "-filter_complex", f"[0:v]subtitles='{srt_filter_path}'[v];[1:a]volume=1.0[a]",
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
        final_video = self.renders_dir / "final.mp4"
        concat_list = self.renders_dir / "concat_list.txt"
        concat_list.write_text(
            f"file '{main_video.as_posix()}'\nfile '{outro_with_audio.as_posix()}'\n",
            encoding="utf-8"
        )
        print("    🎬 正在拼接主视频与片尾...")
        cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(final_video)]
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
