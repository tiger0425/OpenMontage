# -*- coding: utf-8 -*-
"""VOX Collage ASS 3D 挤出立体字幕生成与烧录工具 (subtitle_burner.py)

特性：
- 支持 16:9 (1920x1080) 与 9:16 (1080x1920) 自动适配字号、位置与行宽
- 3D 堆叠阴影：多层深色实心向后下方挤出 + 粗描边纯白字
- 智能 CJK 标点断行，彻底消灭孤字与标点单独成行
- 基于已渲染好的无字幕纯净母版，通过 FFmpeg 极速硬字幕烧录
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PUNCT = "，。、：；？！,.:;?!"


def _is_word_char(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def wrap_text(text: str, max_chars: int) -> str:
    """按标点/长度智能断行，返回 ASS 的 \\N 连接串。

    中文按字数断行；遇到连续的 ASCII 单词（如 Token、OpenRouter）时不得从
    中间劈开，否则会出现 "T / oken" 这种断词。
    """
    lines, cur = [], ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        cur += ch
        should_break = len(cur) >= max_chars or (ch in PUNCT and len(cur) >= max_chars * 0.6)
        if should_break:
            # 断点落在 ASCII 单词内部时，先把整个单词吃完再断
            if _is_word_char(ch):
                j = i + 1
                while j < n and _is_word_char(text[j]):
                    cur += text[j]
                    j += 1
                i = j
            else:
                i += 1
            lines.append(cur)
            cur = ""
            continue
        i += 1
    if cur:
        lines.append(cur)
    # 避免句末标点单独成行
    while len(lines) >= 2 and len(lines[-1]) <= 1 and lines[-1] in PUNCT:
        lines[-2] += lines[-1]
        lines.pop()
    # 上面的合并会把标点粘回上一行，可能把该行顶出 max_chars（9:16 规格 15 字）
    # —— 之前会产出 16 字行，超出安全区。这里对超长行按标点/中点重新均分。
    balanced = []
    for ln in lines:
        while len(ln) > max_chars:
            cut = max(1, len(ln) // 2)
            for k in range(cut, min(len(ln), cut + 6)):
                if ln[k - 1] in PUNCT:
                    cut = k
                    break
            balanced.append(ln[:cut])
            ln = ln[cut:]
        balanced.append(ln)
    lines = balanced
    return "\\N".join(lines)


def fmt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(episode_data: dict, voice_manifest: dict, out_ass: Path):
    ratio = episode_data.get("ratio", "16:9")
    scenes = episode_data.get("scenes", [])
    voice_lines = {l["frame"]: l for l in voice_manifest.get("lines", [])}

    if ratio == "16:9":
        res_x, res_y = 1920, 1080
        font_size = 46
        max_chars = 26
        front_y = 960
        extrude = (12, 8, 4)
    else:
        res_x, res_y = 1080, 1920
        font_size = 56
        max_chars = 15
        front_y = 1600
        extrude = (18, 12, 6)

    font_name = "SimHei"
    front_color = "&H00FFFFFF"
    dark_color = "&H00141414"
    outline = 5

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: VO,{font_name},{font_size},{front_color},{front_color},{dark_color},&H96000000,-1,0,0,0,100,100,2,0,1,{outline},0,2,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    t = 0.0
    lead, tail = 0.30, 0.25

    center_x = res_x // 2

    for s in scenes:
        sid = s["id"]
        vinfo = voice_lines.get(sid, {})
        vo_dur = vinfo.get("seconds", 3.0)
        start_t = t + lead
        end_t = start_t + vo_dur
        narration = s.get("voiceover", {}).get("text", "")
        text = wrap_text(narration, max_chars)

        # 3D 挤出深色底层
        for dy in extrude:
            events.append(
                f"Dialogue: 0,{fmt_time(start_t)},{fmt_time(end_t)},VO,,0,0,0,,"
                f"{{\\pos({center_x},{front_y + dy})\\bord2\\shad0\\c{dark_color}\\3c{dark_color}}}{text}"
            )
        # 上层白字
        events.append(
            f"Dialogue: 1,{fmt_time(start_t)},{fmt_time(end_t)},VO,,0,0,0,,"
            f"{{\\pos({center_x},{front_y})}}{text}"
        )
        # 来源署名（版权受限素材的合规标注，左下角小字）
        credit = (s.get("visual", {}) or {}).get("credit")
        if credit:
            events.append(
                f"Dialogue: 2,{fmt_time(start_t)},{fmt_time(end_t)},VO,,0,0,0,,"
                f"{{\\pos(30,{res_y - 60})\\fs28\\bord2\\shad0\\c{dark_color}\\3c{dark_color}\\alpha&H40&}}{credit}"
            )
        t += lead + vo_dur + tail

    content = header + "\n".join(events) + "\n"
    out_ass.parent.mkdir(parents=True, exist_ok=True)
    out_ass.write_text(content, encoding="utf-8")
    return out_ass


def burn_subtitles(video_in: Path, ass_file: Path, video_out: Path) -> bool:
    """调用 ffmpeg 烧录 ASS 字幕"""
    video_out.parent.mkdir(parents=True, exist_ok=True)
    # 转义 Windows 路径中的冒号与反斜杠
    ass_path_escaped = str(ass_file.resolve()).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_in),
        "-vf", f"subtitles='{ass_path_escaped}'",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy",
        str(video_out)
    ]
    print(f"[subtitle_burner] Burning subtitles via FFmpeg -> {video_out}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"[subtitle_burner] FFmpeg error: {res.stderr}", file=sys.stderr)
        return False
    return True
