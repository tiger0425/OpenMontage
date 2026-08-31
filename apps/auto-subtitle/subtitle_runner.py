#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文硬字幕工具核心逻辑：给视频加中文字幕（不配音、不替换音轨）。

流程：下载(可选) -> 转录 -> 翻译 -> SRT -> FFmpeg 烧录（保留原音轨）。

与 auto-dub 的区别：
- 不生成 TTS 配音（无需 GPU、无需 GPU 锁）
- 不替换音轨（-c:a copy 保留原音轨）
- 字幕时间轴 = 原句（Utterance）时间戳，无需对配音对齐
- 单视频处理，无数据库/队列
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Windows 控制台 UTF-8（避免 GBK 下 emoji/中文打印崩溃）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OMO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parent
AUTO_DUB_APP_ROOT = OMO_ROOT / "apps" / "auto-dub"

if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(AUTO_DUB_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTO_DUB_APP_ROOT))


def _resolve_config(config: dict) -> dict:
    """配置兜底：若配置缺少 glossary，自动从 auto-dub config.yaml 读取（保证翻译术语质量）。"""
    if config.get("glossary"):
        return config
    auto_dub_cfg = AUTO_DUB_APP_ROOT / "config.yaml"
    if auto_dub_cfg.exists():
        try:
            import yaml

            data = yaml.safe_load(auto_dub_cfg.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("glossary"):
                cfg = dict(config)
                cfg["glossary"] = data["glossary"]
                return cfg
        except Exception:
            pass
    return config


class SubtitleRunner:
    """给视频加中文字幕的执行器。

    参数：
        config: dict 配置（pipeline/model_size/whisper_model/glossary/burn 等）
        quiet: bool 是否抑制进度输出（仍保留错误/摘要）
    """

    def __init__(self, config: dict, quiet: bool = False):
        self.config = _resolve_config(config)
        self.quiet = quiet
        self.project_dir: Optional[Path] = None
        self.source_video: Optional[Path] = None

        # 延迟导入 LLM 与术语表（保留 import 失败的友好报错）
        from batch.llm_client import LLMClient
        from batch.glossary import Glossary

        self.llm = LLMClient()
        self.glossary = Glossary.from_config(self.config.get("glossary", {}))

    # ---------- 输出 ----------
    def _out(self, msg: str, force: bool = False):
        if not self.quiet or force:
            print(msg, flush=True)

    def _err(self, msg: str):
        print(msg, flush=True)

    # ---------- 输入解析 ----------
    def _is_url(self, raw: str) -> bool:
        return raw.startswith("http://") or raw.startswith("https://")

    def _extract_video_id(self, url: str) -> str:
        """从 YouTube URL 提取 video_id；其他 URL 用哈希片段。"""
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
        if m:
            return m.group(1)
        m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", url)
        if m:
            return m.group(1)
        return "video"

    def _prepare_source(self, raw_input: str) -> Path:
        """下载（URL）或定位（本地文件）源视频。返回 source.mp4 路径。"""
        if self._is_url(raw_input):
            video_id = self._extract_video_id(raw_input)
            self.project_dir = OMO_ROOT / "projects" / "auto-subtitle" / video_id
            self.project_dir.mkdir(parents=True, exist_ok=True)
            target = self.project_dir / "source.mp4"
            if target.exists() and target.stat().st_size > 0:
                self._out(f"  ✅ 已存在源视频，跳过下载: {target}")
                return target
            self._out(f"  📥 下载视频: {raw_input}")
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", str(target),
                "--no-playlist",
                raw_input,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if res.returncode != 0:
                raise RuntimeError(f"yt-dlp 下载失败: {res.stderr[:300]}")
            if not target.exists() or target.stat().st_size == 0:
                raise RuntimeError("yt-dlp 下载完成但未生成有效文件")
            self._out(f"  ✅ 视频已下载: {target}")
            return target

        # 本地文件
        path = Path(raw_input).resolve()
        if not path.exists():
            raise FileNotFoundError(f"输入文件不存在: {path}")
        self.project_dir = OMO_ROOT / "projects" / "auto-subtitle" / path.stem
        self.project_dir.mkdir(parents=True, exist_ok=True)
        target = self.project_dir / "source.mp4"
        if path.suffix.lower() == ".mp4" and path.parent == self.project_dir:
            return path
        if target.exists() and target.stat().st_size == path.stat().st_size:
            self._out(f"  ✅ 已存在源视频，跳过复制: {target}")
            return target
        shutil.copy2(path, target)
        self._out(f"  ✅ 源视频就绪: {target}")
        return target

    # ---------- 转录 ----------
    def _transcribe(self, video_path: Path) -> dict:
        """转录视频，返回 raw_transcript（含 utterances）。"""
        self._out("  🎙️ 开始语音转录 (faster-whisper)...")
        from tools.analysis.transcriber import Transcriber

        model_size = self.config.get("pipeline", {}).get(
            "whisper_model", self.config.get("whisper_model", "large-v3")
        )
        language = self.config.get("pipeline", {}).get(
            "source_language", self.config.get("source_language")
        )
        res = Transcriber().execute({
            "input_path": str(video_path),
            "model_size": model_size,
            "language": language,
            "diarize": False,
            "merge_gap": 0.5,
            "max_utterance_seconds": 15.0,
            "segment_postprocess": True,
        })
        if not res.success:
            raise RuntimeError(f"转录失败: {res.error}")
        raw = res.data
        utterances = raw.get("utterances") or []
        if not utterances:
            from tools.analysis.transcriber import (
                merge_into_utterances,
                assign_utterance_speakers,
            )

            utterances = merge_into_utterances(
                raw["segments"], merge_gap=0.5, max_seconds=15.0
            )
            utterances = assign_utterance_speakers(utterances)
        self._out(
            f"  ✅ 转录完成：{len(utterances)} 句，时长 {raw['duration_seconds']:.1f}s "
            f"(model={model_size}, lang={raw.get('language')})"
        )
        (self.project_dir / "transcript.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return raw

    # ---------- 翻译 ----------
    def _translate_utterance(self, item: dict, preceding: str) -> str:
        """翻译单个原句，返回中文译文。失败保留原文。"""
        src = (item.get("text") or "").strip()
        if not src:
            return ""
        dur = max(0.0, float(item.get("end", 0)) - float(item.get("start", 0)))
        # 字幕阅读软约束：约 4 字/秒，宽松处理（可读性而非硬截断）
        max_chars = max(15, int(dur * 4.5))
        prompt = self.glossary.build_translation_prompt(source_text=src)
        prompt += (
            "\n\n## 翻译指导规则：\n"
            "1. 意思准确、口语化、自然，适合作为视频字幕阅读。\n"
            "2. 技术术语（GPU/API/模型名等）按术语表保留英文原文。\n"
            "3. 人名/专有名词统一音译且全片一致。\n"
            "4. 跳过 OK/Yeah/Mm-hm/Umm 等语气填充词，除非承载语义（如独立回答 Yes/No）。\n"
            f"5. 译文建议控制在 {max_chars} 字以内（字幕单屏可读），不要冗长。\n"
            "6. 只返回中文译文本身，不要解释、不要 JSON、不要 Markdown 包装。\n"
        )
        if preceding:
            prompt += (
                "\n## 前文对话（仅作连续性参考：保持人名/代词/称谓一致；不要重译这些行）：\n"
                f"{preceding}\n"
            )
        prompt += (
            "\n## 输入（一句英文）：\n"
            + json.dumps({"id": item.get("id"), "text": src}, ensure_ascii=False)
        )
        try:
            resp = self.llm.generate(
                prompt,
                system_instruction=(
                    "You are a professional video subtitle translator. "
                    "Translate ONE English sentence to natural Simplified Chinese (zh-CN)."
                ),
            )
            return (resp or "").strip().strip('"').strip() or src
        except Exception as e:
            self._err(f"  ⚠️ 翻译失败 ({item.get('id')}): {e}，保留原文")
            return src

    def _translate_utterances(self, utterances: list[dict]) -> dict:
        """逐句翻译，注入前文上下文（最近 4 条，600 字符预算）保证一致性。返回 script dict。"""
        self._out(f"  ✍️ 开始翻译 {len(utterances)} 句为中文...")
        total = len(utterances)
        translated: list[dict] = []
        for idx, item in enumerate(utterances):
            preceding = self._build_preceding_context(translated)
            zh = self._translate_utterance(item, preceding)
            out = dict(item)
            out["zh"] = zh
            translated.append(out)
            if (idx + 1) % 20 == 0 or idx == total - 1:
                self._out(f"    - 逐句翻译 {idx + 1}/{total}...")
        script = {
            "version": "1.0",
            "title": self.config.get("title", self.project_dir.name),
            "total_duration_seconds": float(
                (utterances[-1]["end"] if utterances else 0)
            ),
            "sections": [
                {
                    "id": u.get("id"),
                    "text": u.get("text", ""),
                    "start_seconds": float(u["start"]),
                    "end_seconds": float(u["end"]),
                    "delivery_cues": {"provider_text": u["zh"]},
                    "speaker": u.get("speaker"),
                }
                for u in translated
            ],
            "metadata": {
                "source_language": self.config.get("pipeline", {}).get(
                    "source_language", "auto"
                ),
                "target_language": "zh-CN",
            },
        }
        (self.project_dir / "script.json").write_text(
            json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return script

    @staticmethod
    def _build_preceding_context(
        translated: list[dict], max_pairs: int = 4, char_budget: int = 600
    ) -> str:
        """构造翻译前文上下文（与 auto-dub 保持一致）。"""
        pairs: list[str] = []
        budget = char_budget
        for item in reversed(translated):
            src = (item.get("text") or "").strip()
            tgt = (item.get("zh") or "").strip()
            if not src or not tgt:
                continue
            cost = len(src) + len(tgt)
            if cost > budget and pairs:
                break
            pairs.append(f"  {src}  ->  {tgt}")
            budget -= cost
            if len(pairs) >= max_pairs:
                break
        if not pairs:
            return ""
        pairs.reverse()
        return "\n".join(pairs)

    # ---------- SRT ----------
    @staticmethod
    def _format_time(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int(round((seconds % 1) * 1000))
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

    def _write_srt(self, sections: list[dict], output_path: Path, min_display: float = 0.8):
        """生成 SRT：时间轴 = 原句 start/end；过短显示补齐到 min_display 秒。"""
        lines: list[str] = []
        for idx, sec in enumerate(sections, 1):
            start = float(sec["start_seconds"])
            end = float(sec["end_seconds"])
            if end - start < min_display:
                end = start + min_display
            zh = (sec.get("delivery_cues") or {}).get("provider_text", "").strip()
            if not zh:
                continue
            lines.append(str(idx))
            lines.append(
                f"{self._format_time(start)} --> {self._format_time(end)}"
            )
            lines.append(zh)
            lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        self._out(f"  ✅ 中文字幕已生成: {output_path}")

    # ---------- FFmpeg 烧录 ----------
    def _burn_subtitles(
        self,
        source_video: Path,
        srt_path: Path,
        output_path: Path,
        font: str = "Microsoft YaHei",
        font_size: int = 20,
        margin_v: int = 28,
    ):
        """FFmpeg 烧录中文字幕到画面，保留原音轨（-c:a copy）。"""
        self._out("  🎬 正在烧录中文字幕（保留原音轨）...")
        srt_filter = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
        force_style = (
            f"FontName={font},FontSize={font_size},MarginV={margin_v},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,"
            "BorderStyle=1,Alignment=2"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_video),
            "-vf", f"subtitles='{srt_filter}':force_style='{force_style}'",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "copy",
            "-map_metadata", "0",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg 烧录失败: {res.stderr[-500:]}")
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg 烧录完成但未生成有效文件")
        self._out(f"  ✅ 成品已生成: {output_path}")

    # ---------- 主流程 ----------
    def run(self, raw_input: str) -> dict:
        """执行完整流程。返回摘要 dict。"""
        self._out("=" * 60)
        self._out("  中文硬字幕：给视频加中文字幕（保留原音轨）")
        self._out("=" * 60)

        self.source_video = self._prepare_source(raw_input)

        # 转录
        raw_transcript = self._transcribe(self.source_video)
        utterances = raw_transcript.get("utterances") or []
        if not utterances:
            raise RuntimeError("转录未产出任何句子")

        # 翻译
        script = self._translate_utterances(utterances)
        sections = script["sections"]

        # SRT
        srt_path = self.project_dir / "subtitles.srt"
        self._write_srt(sections, srt_path)

        # 烧录（默认开启；burn=False 时只产出 SRT）
        burn_cfg = self.config.get("burn", {})
        burn_enabled = burn_cfg.get("enabled", True)
        final_path = None
        if burn_enabled:
            renders_dir = self.project_dir / "renders"
            renders_dir.mkdir(parents=True, exist_ok=True)
            final_path = renders_dir / "subtitled.mp4"
            self._burn_subtitles(
                self.source_video,
                srt_path,
                final_path,
                font=burn_cfg.get("font", "Microsoft YaHei"),
                font_size=int(burn_cfg.get("font_size", 20)),
                margin_v=int(burn_cfg.get("margin_v", 28)),
            )

        self._out("")
        self._out("  🎉 完成！输出：")
        self._out(f"    - 项目目录: {self.project_dir}")
        self._out(f"    - 中文字幕: {srt_path}")
        if final_path:
            self._out(f"    - 成品视频: {final_path}")

        return {
            "project_dir": str(self.project_dir),
            "source_video": str(self.source_video),
            "subtitles_srt": str(srt_path),
            "final_video": str(final_path) if final_path else None,
            "utterance_count": len(sections),
        }
