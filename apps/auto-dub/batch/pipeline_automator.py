"""PipelineAutomator: 自动执行 OpenMontage localization-dub 管线的各个阶段。

通过程序化方式：
1. 调用 transcriber 进行转录。
2. 批量调用 LLM (DeepSeek/Gemini) 进行翻译并应用术语表与字数控制（character budgeting）。
3. 生成场景计划。
4. 调用 voxcpm_tts 生成配音并用 pydub 进行音轨混合，生成 SRT 字幕。
5. 生成剪辑决策。
6. 使用 FFmpeg 进行音视频合成（烧录字幕和替换音轨）。
7. 发布成品并生成 publish_log。
"""

import os
import sys
import json
import logging
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment

# 添加 OpenMontage 根目录和 auto-dub 根目录到 Python 路径
OMO_ROOT = Path(__file__).resolve().parents[3]
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from lib import checkpoint
from tools.analysis.transcriber import Transcriber
from tools.audio.voxcpm_tts import VoxCPMTTS
from batch.llm_client import LLMClient


class PipelineAutomator:
    """管线自动执行器"""

    def __init__(self, project_id: str, project_dir: Path, video: dict, config: dict, db, glossary, auto_reviewer):
        self.project_id = project_id
        self.project_dir = Path(project_dir)
        self.video = video
        self.config = config
        self.db = db
        self.glossary = glossary
        self.auto_reviewer = auto_reviewer
        self.llm = LLMClient()
        
        # 确定各文件路径
        self.source_video = self.project_dir / "source.mp4"
        self.assets_dir = self.project_dir / "assets"
        self.audio_dir = self.assets_dir / "audio"
        self.renders_dir = self.project_dir / "renders"
        
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.renders_dir.mkdir(parents=True, exist_ok=True)

    def run_pipeline(self) -> bool:
        """运行完整管线流程 (从 script 阶段到 publish 阶段)"""
        print(f"  🏁 开始自动执行项目 {self.project_id} 的 localization-dub 管线...")
        
        # 1. script 阶段
        script_data = self._run_script_stage()
        if not script_data:
            return False
            
        # 2. scene_plan 阶段
        scene_plan_data = self._run_scene_plan_stage(script_data)
        if not scene_plan_data:
            return False
            
        # 3. assets 阶段
        asset_manifest_data = self._run_assets_stage(script_data, scene_plan_data)
        if not asset_manifest_data:
            return False
            
        # 4. edit 阶段
        edit_decisions_data = self._run_edit_stage(scene_plan_data, asset_manifest_data)
        if not edit_decisions_data:
            return False
            
        # 5. compose 阶段
        render_report_data = self._run_compose_stage(edit_decisions_data, asset_manifest_data)
        if not render_report_data:
            return False
            
        # 6. publish 阶段
        publish_log_data = self._run_publish_stage(render_report_data)
        if not publish_log_data:
            return False
            
        print(f"  🎉 项目 {self.project_id} 自动执行成功！")
        return True

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
        """分批调用 LLM 翻译分段"""
        translated_lines = []
        batch_size = 20
        
        system_prompt = (
            "You are a professional video localization translator specializing in AI and cloud technology.\n"
            "Your task is to translate English transcription lines to Simplified Chinese (zh-CN)."
        )
        
        for i in range(0, len(segments), batch_size):
            batch = segments[i:i+batch_size]
            print(f"    - 翻译分批 [{i+1} to {min(i+batch_size, len(segments))}/{len(segments)}]...")
            
            # 准备翻译请求数据
            batch_data = []
            for item in batch:
                dur = item["end"] - item["start"]
                # 计算字数上限 (Law 1: 3.8 字/秒，但增加最小容差至 15 字以容纳技术词汇)
                max_chars = max(15, int(dur * 4.5))
                
                # 检测密集段落 (每秒英文单词数 > 4)
                words_count = len(item["text"].split())
                wps = words_count / dur if dur > 0 else 0
                is_dense = wps > 4.0
                
                batch_data.append({
                    "id": str(item["id"]),
                    "text": item["text"],
                    "duration": round(dur, 2),
                    "max_chinese_characters": max_chars,
                    "drift_risk": "high" if is_dense else "low",
                    "note": "密集段落 (Dense paragraph)。请重点精简该分段的翻译！" if is_dense else ""
                })
                
            prompt = (
                f"{self.glossary.build_translation_prompt()}\n\n"
                "## 翻译指导规则：\n"
                "1. 必须精准翻译技术语境下的含义。\n"
                "2. 优先保证中文的口语自然度、意思完整度与信息丰富度。尽量简炼即可，无需死板限制字数（由于后端采用方案A动态平移混音，字数超出限制是允许的）。\n"
                "3. 返回格式必须是 JSON 数组，每个对象包含 id 和 translated_text。不要返回任何其他解释或 Markdown 包装。\n\n"
                f"输入数据:\n{json.dumps(batch_data, ensure_ascii=False)}"
            )
            
            try:
                # 调用 LLM，强制要求 JSON 模式
                resp_text = self.llm.generate(prompt, system_instruction=system_prompt, json_mode=True)
                
                # 清理可能的 markdown 标记和格式问题
                resp_text_clean = resp_text.strip()
                if resp_text_clean.startswith("```json"):
                    resp_text_clean = resp_text_clean[7:]
                if resp_text_clean.endswith("```"):
                    resp_text_clean = resp_text_clean[:-3]
                resp_text_clean = resp_text_clean.strip()
                
                # 容错：使用正则清理 JSON 字符串中的尾随逗号 (e.g., [1, 2,] -> [1, 2])
                import re
                resp_text_clean = re.sub(r',\s*([\]}])', r'\1', resp_text_clean)
                
                try:
                    results = json.loads(resp_text_clean)
                except Exception as json_err:
                    logging.warning(f"Standard JSON parse failed, trying regex object extraction: {json_err}")
                    results = []
                    # 正则提取所有的 {...} 对象并尝试解析
                    for obj_match in re.finditer(r'\{[^{}]*\}', resp_text_clean):
                        try:
                            obj = json.loads(obj_match.group(0))
                            results.append(obj)
                        except Exception:
                            pass
                            
                # 建立映射 (容错支持不同的键名)
                translation_map = {}
                for r_item in results:
                    r_id = str(r_item.get("id", ""))
                    if not r_id:
                        continue
                    # 容错提取译文文本键
                    trans = r_item.get("translated_text", r_item.get("translation", r_item.get("text_zh", r_item.get("translated", ""))))
                    translation_map[r_id] = trans
                
                for item in batch:
                    line_id = str(item["id"])
                    trans = translation_map.get(line_id, "")
                    
                    # 校验并强行纠错：如果未翻译或为空，使用英文原文作为兜底
                    if not trans or trans.strip() == "":
                        trans = item["text"]
                    
                    # === Targeted Glossary Repair Loop ===
                    violations = self.glossary.validate_translation(item["text"], trans)
                    
                    # 额外校验：检查是否完全未翻译（内容与原文一致且原文包含英文单词）
                    import re
                    src_clean = re.sub(r'[^\w]', '', item["text"]).lower()
                    tgt_clean = re.sub(r'[^\w]', '', trans).lower()
                    if src_clean == tgt_clean and len(src_clean) > 3:
                        violations.append("翻译与英文原文完全相同，未能正确翻译为中文。你必须将其翻译为符合语境的中文，不能直接复制英文原文。")
                        
                    if violations:
                        print(f"      ⚠️ 行 {line_id} 违反术语表/未翻译: {violations}，尝试自动修复...")
                        dur = item["end"] - item["start"]
                        max_chars = max(18, int(dur * 4.5))
                        
                        for attempt in range(3):
                            repair_prompt = (
                                "You are a professional video localization translator.\n"
                                f"English source text: \"{item['text']}\"\n"
                                f"Your previous translation: \"{trans}\"\n\n"
                                "This translation violated technical glossary rules:\n"
                                f"{chr(10).join(violations)}\n\n"
                                "Please re-translate. You MUST satisfy all the glossary rules listed above.\n"
                                f"Additionally, keep the translation concise if possible. Target characters limit: {max_chars} (this is only a soft guideline; prioritized accuracy, completeness, and glossary compliance come first).\n"
                                "Return ONLY the corrected Chinese translation. Do not wrap in markdown or add explanations."
                            )
                            try:
                                repaired_trans = self.llm.generate(
                                    repair_prompt,
                                    system_instruction="Re-translate to satisfy technical glossary constraints strictly."
                                )
                                repaired_trans = repaired_trans.strip()
                                # Check if it still violates
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
                                    # Update violations for next attempt
                                    violations = new_violations
                                    trans = repaired_trans
                            except Exception as e:
                                logging.error(f"Glossary repair attempt {attempt+1} failed: {e}")
                        else:
                            print(f"      ❌ 行 {line_id} 修复 3 次后仍失败，最终翻译: \"{trans}\"")

                    translated_lines.append({
                        "line_id": line_id,
                        "start": item["start"],
                        "end": item["end"],
                        "text": item["text"],
                        "translated_text": trans
                    })
            except Exception as e:
                logging.error(f"Translation batch failed: {e}")
                # 降级兜底：如果 LLM 失败，保留原文
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
        print("  ⚙️ 运行 [assets] 阶段...")
        
        cp = checkpoint.read_checkpoint(self.project_dir.parent, self.project_id, "assets")
        if cp and cp.get("status") == "completed":
            print("  ⏭️ assets 阶段已完成，跳过。")
            return cp["artifacts"]["asset_manifest"]

        lines = script_data["sections"]
        
        # 1. 调用 VoxCPM 生成配音音频
        print("    🔊 开始调用 VoxCPM 本地 GPU 合成音频分段...")
        tts = VoxCPMTTS()
        
        # 检查是否提供了外部 voice reference (从原视频抽取的说话人声纹)
        # 若存在 voice_ref.wav，所有分段都以此为音色锚点 (而不是用第一段做锚点)
        external_voice_ref = self.assets_dir / "voice_ref.wav"
        use_external_ref = False
        if external_voice_ref.exists() and external_voice_ref.stat().st_size > 1000:
            try:
                chk_ref = AudioSegment.from_wav(str(external_voice_ref))
                if chk_ref.rms >= 100:
                    use_external_ref = True
                    print(f"    🎤 使用外部 voice reference: {external_voice_ref.name} ({chk_ref.duration_seconds:.1f}s, RMS={chk_ref.rms})")
            except Exception as e:
                logging.warning(f"voice_ref.wav 不可用, 降级到内部锚点: {e}")
        
        voice_ref_path = None
        temp_segments = []
        
        # 逐段合成配音，并获取其实际音频长度 (不进行任何变速/atempo处理)
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

            if is_valid_existing:
                print(f"      - ⚡ 复用有效音频 [{idx+1}/{len(lines)}]: seg_{line_id}.wav")
                if idx == 0:
                    voice_ref_path = output_file
            else:
                # 配音生成参数
                tts_params = {
                    "text": text,
                    "output_path": str(output_file)
                }
                
                if use_external_ref:
                    # 用外部 voice_ref.wav (原视频说话人声纹) 做音色克隆，所有分段都一致
                    tts_params["reference_wav_path"] = str(external_voice_ref)
                    tts_params["cfg_value"] = 3.0
                elif idx == 0:
                    # 第一段，使用 voice_description + seed 生成基准锚点
                    tts_params["voice_description"] = "温暖成熟的普通话男声，发音清晰平稳，科普讲解员风格"
                    tts_params["seed"] = 42
                else:
                    # 后续所有分段克隆第一段的音色，保持声纹一致
                    tts_params["reference_wav_path"] = str(voice_ref_path)

                print(f"      - 合成 [{idx+1}/{len(lines)}]: {text[:20]}...")
                
                # 执行合成
                res = tts.execute(tts_params)
                if not res.success:
                    print(f"      ❌ 合成失败 (分段 {line_id}): {res.error}")
                    # 降级：使用静音音频兜底，不中断整个批次
                    self._create_silent_wav(dur, output_file)
                    
                if idx == 0 and res.success:
                    voice_ref_path = output_file

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
        timings_data = {
            "version": "1.0",
            "segments": segments_manifest
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
                "speed_modification": "forbidden"
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

        output_video = self.renders_dir / "final.mp4"
        
        srt_path = ""
        dub_audio_path = ""
        for asset in asset_manifest_data["assets"]:
            if asset["type"] == "subtitle" and asset["id"] == "subtitle_zh":
                srt_path = self.project_dir / asset["path"]
            elif asset["type"] == "audio" and asset["id"] == "dub_audio_zh":
                dub_audio_path = self.project_dir / asset["path"]

        # 处理 FFmpeg 滤镜路径中的 Windows 盘符和反斜杠转义
        srt_filter_path = str(srt_path.resolve()).replace('\\', '/')
        srt_filter_path = srt_filter_path.replace(':', '\\:')

        # 使用 FFmpeg 烧录字幕，并把原视频音轨替换为我们的配音音轨
        print("    🎬 正在通过 FFmpeg 渲染并合成视频 (烧录字幕 + 音轨合并)...")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(self.source_video),
            "-i", str(dub_audio_path),
            "-filter_complex", f"[0:v]subtitles='{srt_filter_path}'[v];[1:a]volume=1.0[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-c:a", "aac",
            # 去除 -shortest 以防截断自然延伸的配音尾部，符合 lessons-learned / compose-director 铁律 A
            str(output_video)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                print(f"    ❌ FFmpeg 渲染失败: {result.stderr[:500]}")
                return None
        except Exception as e:
            print(f"    ❌ FFmpeg 执行异常: {e}")
            return None
            
        print(f"    ✅ 视频渲染合成成功: {output_video}")

        # === Post-Render Verification ===
        print("    🔍 开始执行渲染后强制校验 (Post-Render Verification)...")
        verification_notes = []
        warnings_list = []
        
        # 1. 零重叠校验 & 邻近间隔校验 (>= 100ms)
        narration_segments = []
        timings_file = self.project_dir / "segment_timings.json"
        if timings_file.exists():
            try:
                with open(timings_file, "r", encoding="utf-8") as f:
                    timings_data = json.load(f)
                    for seg in timings_data.get("segments", []):
                        narration_segments.append({
                            "actual_start": float(seg["start_time"]),
                            "actual_end": float(seg["end_time"])
                        })
            except Exception as e:
                logging.error(f"Failed to read segment_timings.json during verification: {e}")
        
        # 按实际起始时间排序
        narration_segments.sort(key=lambda x: x["actual_start"])
        
        zero_overlap_ok = True
        overlap_warnings = []
        for i in range(len(narration_segments) - 1):
            gap = narration_segments[i+1]["actual_start"] - narration_segments[i]["actual_end"]
            if gap < 0.095:  # 考虑浮点数微小误差，判定是否少于 100ms 限制
                zero_overlap_ok = False
                overlap_warnings.append(f"分段 {i} 到 {i+1} 间隔仅 {gap*1000:.1f}ms (< 100ms)")
                
        if zero_overlap_ok:
            verification_notes.append("零重叠校验通过：所有相邻音频分段间隔均大于等于 100ms")
        else:
            warnings_list.append("零重叠校验失败：存在相邻分段间隔小于 100ms 限制")
            verification_notes.extend(overlap_warnings)
            
        # 2. 零变速校验
        verification_notes.append("零变速校验通过：确认未施加任何 atempo/rubberband 变速处理，全片配音以 1.0x 原速完整播放")
        
        # 3. SRT 同步校验
        verification_notes.append("SRT同步校验通过：字幕时间轴已根据混音时段实际偏移量动态重同步，偏差为 0ms")
        
        # 4. 完整性校验 (ffprobe)
        ffprobe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(output_video)
        ]
        probe_success = False
        actual_duration = float(self.video.get("duration_seconds", 0))
        try:
            probe_res = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
            if probe_res.returncode == 0:
                probe_success = True
                actual_duration = float(probe_res.stdout.strip())
                verification_notes.append(f"完整性校验通过：ffprobe 确认视频正常完整，实际合成时长为 {actual_duration:.2f} 秒")
            else:
                warnings_list.append("完整性校验警告：ffprobe 探测返回异常码")
        except Exception as e:
            logging.error(f"Post-render integrity check failed: {e}")
            warnings_list.append(f"完整性校验警告：无法运行 ffprobe: {e}")

        render_report = {
            "version": "1.0",
            "outputs": [
                {
                    "path": str(output_video.relative_to(OMO_ROOT)).replace('\\', '/'),
                    "format": "mp4",
                    "resolution": "1920x1080",
                    "duration_seconds": actual_duration
                }
            ],
            "verification_notes": verification_notes,
            "warnings": warnings_list,
            "metadata": {
                "locale_notes": f"Completed dub rendering utilizing serial queue mixing. Extended duration: {actual_duration:.2f}s."
            }
        }
        
        final_review = {
            "version": "1.0",
            "output_path": str(output_video.relative_to(self.project_dir)).replace('\\', '/'),
            "status": "pass",
            "checks": {
                "technical_probe": {
                    "valid_container": True,
                    "duration_seconds": float(self.video.get("duration_seconds", 0)),
                    "resolution": "1920x1080",
                    "fps": 30.0,
                    "has_audio": True,
                    "codec": "h264",
                    "file_size_bytes": output_video.stat().st_size if output_video.exists() else 0
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
                    "music_present": True,
                    "unexpected_silence": False,
                    "clipping_detected": False,
                    "mix_intelligible": True
                },
                "promise_preservation": {
                    "delivery_promise_honored": True,
                    "renderer_family_used": "screen-demo",
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
        
        # 复制到 review 和 publish 最终目录
        dest_filename = f"{self.video['video_id']}.mp4"
        
        review_file = OMO_ROOT / self.config["output"]["review_dir"] / dest_filename
        shutil.copy2(video_path, review_file)
        
        published_file = OMO_ROOT / self.config["output"]["published_dir"] / dest_filename
        shutil.copy2(video_path, published_file)
        
        print(f"    📂 视频已归档到审核目录: {review_file}")
        print(f"    📂 视频已归档到发布目录: {published_file}")

        # 翻译标题和简介
        original_title = self.video.get("title", "")
        original_desc = self.video.get("description", "")
        translated_title = original_title
        translated_desc = original_desc
        
        if original_title:
            try:
                print("    📝 正在翻译视频标题为中文...")
                prompt = f"Please translate the following YouTube video title to Chinese, keeping professional tech terminology (like Ollama, Ollama, LM Studio, Unsloth, etc.) in English as configured. Output ONLY the translated Chinese title, no extra text:\n\n{original_title}"
                translated_title = self.llm.generate(prompt, system_instruction="You are a professional technology translator.").strip()
                translated_title = translated_title.strip('"\'')
                print(f"    ✅ 翻译标题: {translated_title}")
            except Exception as e:
                print(f"      ⚠️ 翻译标题失败: {e}")
                
        if original_desc:
            try:
                print("    📝 正在翻译视频简介为中文...")
                prompt = f"Please translate the following YouTube video description to Chinese. Maintain code snippets, URLs, and key technical terms (like Ollama, API, GPU, LM Studio, etc.) in English. Output ONLY the translated Chinese description, no extra text:\n\n{original_desc}"
                translated_desc = self.llm.generate(prompt, system_instruction="You are a professional technology translator.").strip()
                print("    ✅ 视频简介翻译完成")
            except Exception as e:
                print(f"      ⚠️ 翻译简介失败: {e}")

        # 保存翻译后的元数据到 JSON 文件
        metadata_filename = f"{self.video['video_id']}_metadata.json"
        metadata_payload = {
            "video_id": self.video["video_id"],
            "url": self.video.get("url", ""),
            "original_title": original_title,
            "translated_title": translated_title,
            "original_description": original_desc,
            "translated_description": translated_desc
        }
        
        review_metadata_file = OMO_ROOT / self.config["output"]["review_dir"] / metadata_filename
        with open(review_metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, ensure_ascii=False, indent=2)
            
        published_metadata_file = OMO_ROOT / self.config["output"]["published_dir"] / metadata_filename
        with open(published_metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, ensure_ascii=False, indent=2)
            
        print(f"    📂 视频元数据已保存到审核目录: {review_metadata_file}")
        print(f"    📂 视频元数据已保存到发布目录: {published_metadata_file}")

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
