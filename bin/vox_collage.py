#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOX Collage 纸质拼贴科普/纪录片自动化管线 CLI (bin/vox_collage.py)

规范来源：
  apps/vox-collage/specs/design-system.md           (视觉系统宪法：色板、6零件、6构图、动效)
  apps/vox-collage/specs/LESSONS.md                 (实战避坑与中长视频性能治理)
  apps/vox-collage/specs/collage_episode.schema.json (分幕契约)
  apps/vox-collage/specs/script-spec.md             (剧本规范与去AI化)

核心定位：
  - 双画幅原生支持：16:9 横屏 (1920x1080) / 9:16 竖屏 (1080x1920)
  - 真实摄影素材入画（真车/真装备/Logo/档案照），拒绝 AI 伪造
  - 覆盖 90 秒短解说到 10 分钟中长专题纪录片
  - 动静混编策略（hero_motion + 2% slow drift）
  - 读 WAV 头真实秒数排布时间轴，母版无字幕 + FFmpeg 3D 挤出立体字幕快速烧录

用法：
  python bin/vox_collage.py new <topic> [--ratio 16:9|9:16] [--theme archival-red] [--duration 90s|3m|5m]
  python bin/vox_collage.py refs <id>
  python bin/vox_collage.py script <id>
  python bin/vox_collage.py approve-script <id>
  python bin/vox_collage.py synth <id> [--json]
  python bin/vox_collage.py dataliao <id> [--only "01,02"]
  python bin/vox_collage.py stills <id> [--only "01,02"] [--json]
  python bin/vox_collage.py motion <id> [--only "01,02"] [--json]
  python bin/vox_collage.py compose <id>
  python bin/vox_collage.py render <id> [--json]
  python bin/vox_collage.py subtitle <id>
  python bin/vox_collage.py run <topic>
  python bin/vox_collage.py run-heavy <id> [--json]
  python bin/vox_collage.py status
"""

import argparse
import copy
import json
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))

APPS_ROOT = OMO_ROOT / "apps" / "vox-collage"
PRESETS_ROOT = APPS_ROOT / "presets"
SPECS_ROOT = APPS_ROOT / "specs"
TEMPLATES_ROOT = APPS_ROOT / "template"
TOOLS_ROOT = TEMPLATES_ROOT / "tools"

PROJECTS_DIR = OMO_ROOT / "projects" / "vox-collage"
DB_PATH = PROJECTS_DIR / "tracking.db"

# 动态引用内部工具
sys.path.insert(0, str(TOOLS_ROOT))
sys.path.insert(0, str(TEMPLATES_ROOT))
try:
    from commons_fetcher import fetch_queries
    from dataliao_builder import DataliaoEngine
    from subtitle_burner import build_ass, burn_subtitles
    from master_sheet_theme import build_theme_master_sheet
    from hyperframes.generate_composition import generate_index_html
    import comfyui_client
except Exception:
    pass

COMFY_DIR = TEMPLATES_ROOT / "comfyui"

# ---- Qwen-Image-Edit 2.1 风格化 prompt（单图编辑）----
# 注意 1：给风格参考图（master_sheet）会「图生图融合」，把母版里的色卡 / THE DEAL / $123
#         抄进画面（LESSONS 记录过的污染）。因此只用单图 <image1>（资料图），风格用文字描述。
# 注意 2：不要强行压成纯黑背景 / 只准单色描边——那会把纸张肌理与套印错位质感抹平，
#         变成扁平廉价。保留“冷色舞台纸感 + 错位套印描边”的原始质感（用户验收通过的那版）。
STYLE_PROMPT = (
    "把 <image1> 重绘为 VOX 调查纪录片纸质拼贴风格：半调网点纹理、粗糙相纸白边、"
    "右下错位强调色描边、纸张翘起投影、哑光纸张颗粒，冷色调极客舞台背景。"
    "必须严格保持 <image1> 的构图布局、每个元素的位置与大小、全部文字内容与真实照片内容完全不变，"
    "只统一材质、印刷质感与配色。"
)
STYLE_NEG = (
    "不要新增或删除任何元素；不要改变或重写任何文字、数字与排版位置；"
    "不要引入任何色卡色块、示例文字或示例数字（例如 THE DEAL、$123、Trade Route）；"
    "不要照片写实摄影质感；不要 3D 渲染；不要水印。"
)

# ---- MiniMax H3 图层组装 prompt（镜头静止、图层逐一入场、首帧全亮）----
MOTION_PROMPT = (
    "VOX-style editorial documentary PAPER COLLAGE layer-assembly animation, horizontal 16:9.\n\n"
    "Preserve the EXACT original composition, layout, palette, torn paper edges and object positions of the "
    "source illustration. This is a LAYER ASSEMBLY animation, NOT a redesign. "
    "Nothing is added, nothing is removed, nothing is moved, nothing is rearranged.\n\n"
    "CANVAS: cool dark tech stage (#16181D) with coarse halftone grain and faint print blotches. "
    "Camera is COMPLETELY STATIC - no zoom, no pan, no tilt, no orbit, no handheld, no shake.\n\n"
    "The FIRST FRAME already shows the fully lit paper background; there is NO fade from black.\n\n"
    "LAYER BUILD ORDER: the torn-paper headline strip slides in first; then the archival photo / cut-out "
    "subject drops in with a tiny placement bounce; then the cyan underline stroke wipes in; then the big "
    "stat number scales up; then everything holds still. Each layer enters one at a time, never two at once. "
    "No photorealistic environment, no cinematic lighting."
)

# ---- Prompt 2 视觉规范：统一负向约束 ----
VOX_NEG = (
    "No clutter, no unnecessary objects, no excessive icons, no visual noise, no random decorations, "
    "no fantasy elements, no sci-fi elements unless required, no anime, no cartoon style, no CGI look, "
    "no glossy 3D rendering, no photorealistic background, no oversaturated colors, no poor composition, "
    "no flat solid black background, no large empty void, no monotonous empty frame, "
    "no small garbled caption text, no fake or corrupted characters, no invented CJK glyphs, "
    "no body copy, no paragraphs or sentences of text, no captions other than the single specified headline, "
    "no distorted anatomy, no blurry details, no watermark, no extra logos, "
    "maintain a clean premium VOX-style editorial collage with layered paper textures and documentary-quality composition."
)

# 文字硬护栏：只有 editorial headline 可以出现在画面上（2026-10 修：core_idea 曾被模型照抄成正文并乱码）
VOX_TEXT_RULE = (
    "TEXT RULE (strict, highest priority): the ONLY text allowed anywhere in this image is (a) the single editorial "
    "headline quoted above, (b) any label whose exact wording is explicitly quoted in this brief, and (c) the one "
    "hand-written signature if this brief specifies one. The editorial headline must appear EXACTLY ONCE in the "
    "entire image: never repeat, duplicate, mirror, re-draw or paraphrase it anywhere else. Do NOT render "
    "any other words, sentences, captions, body copy, paragraphs, filler or placeholder text, and do NOT print this "
    "brief itself. Never write the core idea or the visual metaphor as visible text. Every area that is not a "
    "headline, a specified label or the specified signature stays as clean paper texture, cut paper, halftone or "
    "photographic content.\n"
)

VOX_LAYER_ORDER = (
    "Layer order: paper background -> geometric shape -> editorial typography -> main subject "
    "-> supporting objects -> paper shadows -> texture."
)


def _pal(tokens):
    p = (tokens or {}).get("palette", {})
    return (
        p.get("stage_tan", "#16181D"),
        p.get("ink_black", "#E0E6ED"),
        p.get("accent_red", "#00D2FF"),
        p.get("tag_mustard", "#FF5F1F"),
    )


def _paper_stage(tokens):
    """把主题 stage 提亮成「有纸质感的深色调」：避免近纯黑的空屏感。
    保留主题冷调，但抬到中深灰蓝，Qwen 会在其上画纤维/网点/暗角。"""
    stage, _ink, _a, _t = _pal(tokens)
    h = stage.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return "#2A3038"
    # 抬到中深调，避免纯黑；同色相保持主题气质。
    # 太暗会让 Qwen 直接画成平黑、不画纸纹，因此这里抬到「中深石板灰」档。
    def lift(c, floor):
        return max(c, floor)
    r = lift(r, 74)
    g = lift(g, 80)
    b = lift(b, 92)
    return f"#{r:02X}{g:02X}{b:02X}"


VOX_PAPER_NOTE = (
    "The background MUST read as a real piece of textured paper, never a flat screen or a black void. "
    "Paint visible paper fiber grain, an uneven mottled surface, faint fold lines, tiny specks, "
    "coarse printed halftone dots and a soft darkened vignette toward the corners, so the surface clearly "
    "looks like physical stock that light falls across. Keep the mid-tone cool grey-blue paper colour, "
    "but the texture must be obvious and tactile."
)

VOX_ELEMENTS = (
    "Build a RICH, layered collage, not an empty frame. Besides the main subject and the headline, include "
    "3 to 5 supporting paper elements chosen from: a torn paper strip, a round halftone badge, "
    "a thin hand-drawn arrow, two or three thin horizontal guide lines, a small rectangular label tag, "
    "a strip of translucent tape, a small ink stamp. Arrange them with intent, leaving no large empty void.\n"
    "ALL supporting elements must be completely BLANK: no text, no letters, no numbers, no captions on tape, "
    "tags, badges or stamps. The ONLY text anywhere in the image is the headline."
)


def _orient(ratio: str) -> str:
    """画面方向词：竖屏项目必须与画布一致，否则模型会按横屏构图。"""
    return "vertical 9:16, portrait" if str(ratio).startswith("9") else "horizontal 16:9, landscape"


def _canvas(ratio: str) -> tuple:
    """Qwen 原生尺寸：16:9 = 1664x928，9:16 = 928x1664。"""
    return (928, 1664) if str(ratio).startswith("9") else (1664, 928)


def build_image_prompt(scene: dict, tokens: dict, ratio: str = "16:9") -> str:
    """Prompt 2 · 纯 AI 象征图：Core Idea + Visual Metaphor + Editorial Title 三要素出图。"""
    v = scene.get("visual", {})
    _stage, ink, accent, tag = _pal(tokens)
    stage = _paper_stage(tokens)
    return (
        f"VOX-style editorial documentary paper collage, {_orient(ratio)}.\n"
        f"BRIEF (composition guidance only, NEVER rendered as visible text): {v.get('core_idea', '')}.\n"
        f"Visual metaphor: {v.get('visual_metaphor', '')} — render this as ONE clear, dominant, "
        "recognizable black-and-white paper cut-out that a viewer understands in under two seconds. "
        "Make it LARGE and central enough to fill most of the frame; it must not be a tiny icon.\n"
        f"The background is a mid-tone textured paper in {stage} with the paper feel described below.\n"
        + VOX_PAPER_NOTE + "\n"
        f"Give the cut-out a rough white keyline, an offset {accent} stroke and a soft paper drop shadow.\n"
        f"Add the editorial headline \"{v.get('editorial_title', '')}\" in large bold condensed display type "
        f"in {ink}, placed prominently and underlined by a hand-drawn {accent} stroke, readable and integrated into the layout.\n"
        + VOX_ELEMENTS + "\n"
        f"Accent colours allowed: {accent} and {tag} only, used sparingly.\n"
        "Composition: one dominant subject filling the frame, strong hierarchy, magazine-editorial balance. "
        "Everything flat like cut paper, never photorealistic, never 3D.\n" + VOX_LAYER_ORDER + VOX_TEXT_RULE
    )


def _extra_notes(v: dict) -> str:
    """每幕可选附加约束：frame_note = 整幅不裁切；signature = 便签上的手写英文签名。"""
    out = ""
    fn = v.get("frame_note")
    if fn:
        out += fn.rstrip() + "\n"
    sig = v.get("signature")
    if sig:
        out += (f'Write exactly ONE hand-written cursive signature in dark ink reading "{sig}", placed once on the '
                f'blank paper note or label tag. It must appear EXACTLY ONCE in the whole image: never duplicate, '
                f'repeat, mirror or re-draw it anywhere else, and do not add a second copy on the background. '
                f'That signature is the only hand-written text allowed anywhere in this image.\n')
    return out


def _real_layout(v: dict, accent: str, photo_half: str, cut_half: str) -> str:
    """单参考：照片占一半 + 隐喻抠图占另一半；双参考：两张照片并排 + 各自类型标注。"""
    pd2 = v.get("photo_desc_2", "")
    if pd2:
        lab1, lab2 = v.get("label_1", ""), v.get("label_2", "")
        lab = ""
        if lab1 and lab2:
            lab = (f'Under photo 1 print exactly the label "{lab1}", and under photo 2 print exactly the label '
                   f'"{lab2}", in bold condensed type on small torn paper strips. Those two labels are the only '
                   "additional text allowed anywhere.\n")
        return (
            f"TWO reference photos are supplied. Photo 1 shows {v.get('photo_desc', '')}. Photo 2 shows {pd2}. "
            "Place BOTH as separate, slightly tilted archival prints of EQUAL size, side by side and clearly "
            f"separated, each with a rough white keyline, torn paper edge and an offset {accent} stroke. "
            "Preserve both photos' real content exactly: do not redraw, replace or invent what they show. "
            "Do NOT draw any car of your own in this image.\n" + lab
        )
    return (
        "KEEP THE REFERENCE PHOTO's real content fully recognizable. Do not redraw, replace or invent what it shows. "
        "Do not add any small garbled caption text over the photo.\n"
        f"Place the reference photo as a slightly tilted archival print with a rough white keyline, torn paper edge, "
        f"an offset {accent} stroke and a soft paper drop shadow, occupying the {photo_half} of the frame.\n"
        + ("" if v.get("no_metaphor") else
           f"Add the visual metaphor \"{v.get('visual_metaphor', '')}\" as a SEPARATE, LARGE, clear black-and-white "
           f"paper cut-out on the {cut_half} (big enough to be understood at a glance), never overlapping the photo.\n")
        + ("Do NOT add any large black-and-white cut-out and do NOT repeat the main subject anywhere; decorate only "
           "with small torn-paper strips, a halftone dot badge, a stamp and paper tape.\n" if v.get("no_metaphor") else "")
        + _extra_notes(v)
    )


def build_collage_prompt_real(scene: dict, tokens: dict, ratio: str = "16:9") -> str:
    """Prompt 2 · 真实证据图：保留真实照片内容，外围补齐 VOX 拼贴元素与隐喻。"""
    v = scene.get("visual", {})
    _stage, ink, accent, tag = _pal(tokens)
    stage = _paper_stage(tokens)
    photo_half, cut_half = (("upper half", "lower half") if str(ratio).startswith("9")
                            else ("right half", "left half"))
    return (
        f"Turn the reference photo into a VOX-style editorial documentary paper collage, {_orient(ratio)}.\n"
        f"BRIEF (composition guidance only, NEVER rendered as visible text): {v.get('core_idea', '')}.\n"
        + _real_layout(v, accent, photo_half, cut_half)
        +
        f"The background is a mid-tone textured paper in {stage} with the paper feel described below.\n"
        + VOX_PAPER_NOTE + "\n"
        f"Add the editorial headline \"{v.get('editorial_title', '')}\" in large bold condensed display type in {ink} "
        f"on a torn paper strip, with a hand-drawn {accent} underline.\n"
        + VOX_ELEMENTS + "\n"
        f"Accent colours allowed: {accent} and {tag} only, used sparingly.\n"
        "Keep every element flat like cut paper; no photorealism, no 3D, no glow.\n" + VOX_LAYER_ORDER + VOX_TEXT_RULE
    )


def build_video_prompt(scene: dict, total_sec: float = None,
                       media_start: float = 0.0, visible_sec: float = None,
                       ratio: str = "16:9") -> str:
    """Prompt 3 · 单张拼贴的逐层组装（严格按文档 Prompt 3 的规范与时刻表）。

    文档的时刻表以「观众实际看到的时长」为准，因此这里把 0–70% 搭建 / 70–100% 停留
    映射到【可见窗口】（media_start → media_start + visible_sec），而不是整条片段长度。
    """
    v = scene.get("visual", {})
    T = float(total_sec or 10.0)
    V = float(visible_sec or T)
    off = float(media_start)

    def ts(frac: float) -> str:
        return f"{off + V * frac:.1f}"

    # 注意：不要把中文内容描述喂进来 —— H3 会把可读的中文直接念成旁白（2026-10 实测事故）
    photo_txt = (
        "Any photographic print already present in the source illustration MUST be preserved exactly as it is; "
        "do NOT replace it, do NOT invent a different photograph, do NOT add any person or creature into it.\n\n"
    )
    return (
        f"VOX-style editorial documentary PAPER COLLAGE layer-assembly animation, {_orient(ratio)}.\n\n"
        "Preserve the EXACT original composition, layout, palette, torn paper edges and object positions of the "
        "source illustration. This is a LAYER ASSEMBLY animation, NOT a redesign. "
        "Nothing is added, nothing is removed, nothing is moved, nothing is rearranged. "
        "The animation must feel as if an editor is assembling the illustration piece by piece.\n\n"
        "The source illustration already carries all of its own content, headline and cut-outs; replicate it "
        "faithfully and do not introduce new subject matter.\n\n"
        + photo_txt +
        f"ANIMATION DURATION - total clip length exactly {T:.1f} seconds. "
        f"The finished composition must be on screen from {ts(0.70)}s onwards.\n"
        f"{off:.1f}s to {ts(0.10)}s : the textured paper background is already there and holds.\n"
        f"{ts(0.10)}s to {ts(0.25)}s : the torn-paper headline strip appears with its hand-drawn underline.\n"
        f"{ts(0.25)}s to {ts(0.45)}s : the main paper cut-out appears.\n"
        f"{ts(0.45)}s to {ts(0.62)}s : the supporting paper elements appear one at a time "
        "(tape strips, badge, arrow, rule lines).\n"
        f"{ts(0.62)}s to {ts(0.70)}s : the last small accents and the paper texture settle.\n"
        f"{ts(0.70)}s to {T:.1f}s : the composition is complete - only subtle secondary motion is allowed while "
        "every element remains fixed in its original position.\n\n"
        "MOST IMPORTANT RULE: every object becomes permanently locked after it appears. Nothing drifts, nothing "
        "slides away, nothing floats around, nothing repositions itself, nothing extends or grows, nothing changes "
        "scale or shape. Every element remains anchored exactly where it was placed.\n\n"
        "LAYER BUILD: reveal the illustration one element at a time, in exactly that order. Each layer enters "
        "individually and locks permanently into place. Never reveal multiple major objects simultaneously.\n\n"
        "ENTRY SIZE: every element enters at its FINAL size and in its FINAL position, exactly as in the source "
        "illustration. Never appear oversized, never start as a giant shape and shrink down into place, never "
        "unfold, never curl, never stretch. The very first frame shows only the flat textured paper background - "
        "a large white paper shape must never fill the frame at any moment. Every element enters already fully "
        "printed and complete: never show a blank, white or unprinted paper version of an element before its "
        "final version, and never show a headline strip before its text is on it.\n\n"
        "ENTRY ANIMATIONS: use only subtle editorial animations - paper slide, paper drop, soft pop, small fade, "
        "gentle scale from 95 percent to 100 percent, a small paper unfold, a mask reveal, a simple wipe, a small "
        "rotation under 3 degrees, a short paper placement bounce. Never use dramatic motion. The animation should "
        "feel handcrafted.\n\n"
        "CAMERA: the camera must remain completely static. No zoom, no pan, no tilt, no orbit, no handheld movement, "
        "no shake, no cinematic camera moves. The illustration itself tells the story.\n\n"
        "MOVEMENT AFTER APPEARING: once an object has entered it remains perfectly fixed. Only extremely subtle idle "
        "motion is allowed - tiny paper texture breathing, micro shadow breathing, a soft glow pulse, light dust "
        "particles, a tiny paper vibration. Maximum movement 2 to 5 pixels, maximum rotation 2 degrees, maximum scale "
        "pulse 2 percent, maximum opacity pulse 5 percent. Motion must be almost unnoticeable: the viewer should feel "
        "the image is alive without noticing obvious animation.\n\n"
        "TYPOGRAPHY: if typography exists in the image, treat it like paper - reveal it during the layer build as ONE "
        "complete paper strip in a single move, and keep it perfectly fixed afterwards. Never animate letters "
        "individually, never show a partial word, never distort typography.\n\n"
        "BACKGROUND: keep the original paper texture. Do not replace the background, do not create new scenery. "
        "The FIRST FRAME already shows the fully lit textured paper background; there is NO fade from black.\n\n"
        "SOUND: ABSOLUTELY NO SPEECH OF ANY KIND. Do not speak, do not read any text aloud, do not voice any "
        "language, do not generate narration, dialogue, whispering or singing. There is no human voice in this "
        "audio at all. Only premium documentary ASMR - soft paper movement, page sliding, cardboard placement, "
        "gentle whooshes, pencil scratches, soft paper rustle, quiet room ambience.\n\n"
        "DO NOT: no camera movement, no object drifting, no flying objects, no spinning elements, no excessive "
        "parallax, no explosions, no morphing, no warping, no stretching, no squash, no bounce loops, no cartoon "
        "effects, no exaggerated easing, no flashy transitions, no unnecessary motion, no cinematic lighting, "
        "no depth of field, no photorealistic environment."
    )


def build_pair_prompt(group: list, total_sec: float) -> str:
    """Prompt 4 · 两图 → 一条无缝片段（严格按文档 Prompt 4 的时刻表、转场、相机与微动规范）。

    注：当前架构已改为「单幕 + HyperFrames 统一纸擦除」——转场只能由一个引擎负责，
    H3 不再做任何转场，因此本函数暂不参与生产，保留为文档 Prompt 4 的完整实现备用。
    """
    def desc(s):
        v = s.get("visual", {})
        d = (f"headline \"{v.get('editorial_title', '')}\", core idea: {v.get('core_idea', '')}, "
             f"main paper cut-out: {v.get('visual_metaphor', '')}")
        if v.get("photo_desc"):
            d += (f". Its archival photo shows {v['photo_desc']} and that photo must stay exactly as it is")
        return d

    a = group[0]
    b = group[1] if len(group) > 1 else None
    if not b:
        return build_video_prompt(a, total_sec)
    img2 = f"IMAGE 2 (second half): {desc(b)}.\n"

    # 文档 Prompt 4 时刻表：图1 0–3s 搭建 · 3–5s 停留预备转场；图2 5–8s 搭建 · 8–10s 停留（按真实片段时长等比缩放）
    T = float(total_sec)
    t_build1 = T * 0.30
    t_hold1 = T * 0.50
    t_build2 = T * 0.80
    timeline = (
        "IMAGE TIMELINE - follow these timings exactly.\n"
        f"IMAGE 1 - 0.0s to {t_build1:.1f}s : build the composition layer-by-layer. Reveal elements one at a "
        "time. Every revealed element locks permanently into place. "
        f"By {t_build1:.1f} seconds the complete composition is visible.\n"
        f"IMAGE 1 - {t_build1:.1f}s to {t_hold1:.1f}s : hold the completed composition with only subtle "
        "micro-animations, and slowly prepare for the transition.\n"
        f"IMAGE 2 - {t_hold1:.1f}s to {t_build2:.1f}s : continue with the exact same editing rhythm. Reveal image 2 "
        "layer-by-layer. Keep every revealed element fixed.\n"
        f"IMAGE 2 - {t_build2:.1f}s to {T:.1f}s : hold image 2 and maintain subtle life-like movement only.\n\n"
        "LAYER-BY-LAYER ANIMATION: reveal elements individually, in this order - background paper, large geometric "
        "shape, editorial title, main subject, supporting object, second supporting object, icons, map, charts, "
        "lines, texture, final emphasis. Never reveal multiple important objects simultaneously.\n\n"
        "ENTRY ANIMATIONS: use only subtle editorial motion - paper slide, paper drop, mask reveal, soft fade, "
        "gentle scale from 95 percent to 100 percent, a small paper unfold, a slight rotation under 2 degrees, a "
        "short paper placement bounce, a smooth wipe, a directional reveal. The animation should feel handcrafted.\n\n"
        f"TRANSITION BETWEEN THE TWO IMAGES: it happens once, at {t_hold1:.1f} seconds, and it must preserve visual "
        "continuity so the viewer feels that the documentary never stops. Never use a hard cut. Use a seamless "
        "paper wipe that follows the direction of the composition - one plain paper layer sweeps across the frame "
        "from one edge to the other with minimal movement and minimal parallax, and as it passes image 2 is already "
        "fully in place behind it: a mask transition where one paper layer reveals the next scene. "
        "The sweeping layer is a plain paper sheet travelling across the frame; the first composition itself must "
        "NOT travel, slide or flip away as a block, and nothing of it may still be visible once the wipe has passed. "
        "No element of image 2 may appear before the wipe reaches it, no element of image 2 may land on top of an "
        "element of image 1, and the two compositions must never be visible in the same area at the same time.\n\n"
        "CAMERA: keep one consistent camera language - a very subtle digital documentary camera. Allowed: a tiny "
        "push-in, a tiny pull-back, a gentle editorial zoom, a slow camera drift less than 3 percent, minimal "
        "parallax between paper layers. Never use dramatic movement, never rotate the camera, never shake, never "
        "orbit, never handheld, never cinematic sweeping shots. The camera should almost disappear.\n\n"
        "OBJECT BEHAVIOR: after appearing, every object remains permanently locked. Never drift, never float, never "
        "slide, never change scale, never change position, never extend or grow, never rearrange the composition.\n\n"
        "MICRO ANIMATION: after all layers are complete, only extremely subtle movement is allowed - tiny paper "
        "texture breathing, micro shadow breathing, a light glow pulsing, dust particles, a tiny paper vibration. "
        "Maximum movement 2 to 4 pixels, maximum rotation 1 degree, maximum scale 1 percent. Movement should be "
        "almost invisible.\n\n"
        "TYPOGRAPHY: treat typography like paper - reveal each headline during the layer build as ONE complete "
        "paper strip in a single move, and keep it perfectly fixed afterwards. Never animate letters individually, "
        "never show a partial word, never distort typography.\n\n"
        "BACKGROUND: maintain the original paper texture, do not replace backgrounds, do not create new scenery, "
        "keep both images visually consistent. The FIRST FRAME already shows the fully lit textured paper "
        "background; there is NO fade from black.\n\n"
        "SOUND DESIGN: no narration, no dialogue, no music. Use only premium documentary ASMR - soft paper movement, "
        "page sliding, cardboard placement, gentle whooshes, pencil scratches, soft paper rustle, quiet room "
        "ambience. The transition includes elegant paper swishes and subtle air movement, never loud cinematic "
        "impacts.\n\n"
        "DO NOT: no hard cuts, no flashy transitions, no overlapping of the two compositions, no camera shake, no "
        "excessive zoom, no spinning objects, no morphing, no warping, no stretching, no squash, no bouncing loops, "
        "no exaggerated easing, no object teleportation, no color changes, no new objects, no clutter, no cinematic "
        "lighting, no photorealistic environment."
    )
    return (
        "VOX-style editorial documentary PAPER COLLAGE animation, horizontal 16:9, "
        "TWO images combined into ONE seamless documentary clip.\n\n"
        + f"IMAGE 1 (first half): {desc(a)}.\n"
        + img2
        + "Each uploaded image already contains a complete visual composition. DO NOT redesign the images, DO NOT add "
        "new objects, DO NOT remove objects, DO NOT change the layout - animate only what already exists inside each "
        "image. Preserve each image's EXACT composition, layout, palette, torn paper edges and object positions. "
        "Do not invent any person, object, logo or text.\n\n"
        + f"VIDEO LENGTH: exactly {T:.1f} seconds. The animation must feel like one continuous documentary "
        "sequence.\n\n"
        + timeline + "\n\n"
        "The final result must feel like a professionally edited VOX documentary in which paper-cut editorial "
        "illustrations are assembled in real time."
    )


STATUS_FLOW = [
    "pending", "scripting", "awaiting_script_review", "script_approved",
    "refs_done", "tts_done", "dataliao_done", "stills_done",
    "motion_done", "composed", "rendered", "subtitled", "packaged"
]


# ---------------------------------------------------------------- DB Helpers
def init_db():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            ratio TEXT NOT NULL,
            theme TEXT NOT NULL,
            target_duration TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def set_status(pid: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", (status, now, pid))
    conn.commit()
    conn.close()


def get_project_record(pid: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, topic, ratio, theme, target_duration, status FROM projects WHERE id = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "topic": row[1], "ratio": row[2], "theme": row[3], "target_duration": row[4], "status": row[5]}


def emit_json(obj: dict):
    print(json.dumps(obj, ensure_ascii=False))


def get_wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 3.0


# ---------------------------------------------------------------- Subcommands
def cmd_new(args):
    init_db()
    pid = args.id or re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-")
    if not pid:
        pid = f"vox-col-{int(time.time())}"

    proj_dir = PROJECTS_DIR / pid
    if proj_dir.exists():
        print(f"[!] Project directory already exists: {proj_dir}")
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 1. 拷贝主题基准图与设计代币
    theme_dir = PRESETS_ROOT / args.theme
    if not theme_dir.exists():
        theme_dir = PRESETS_ROOT / "archival-red"

    # 复制 tokens.json
    tokens_src = theme_dir / "tokens.json"
    tokens = {}
    if tokens_src.exists():
        shutil.copy2(tokens_src, proj_dir / "tokens.json")
        try:
            tokens = json.loads(tokens_src.read_text(encoding="utf-8"))
        except Exception:
            tokens = {}

    # 复制 master sheet；主题缺失时按调色板生成主题母版，禁止静默串色回退
    ms_src = theme_dir / "master_sheet_16_9.png"
    if not ms_src.exists():
        base_ms = PRESETS_ROOT / "archival-red" / "master_sheet_16_9.png"
        try:
            build_theme_master_sheet(base_ms, tokens, ms_src)
            print(f"[new] Generated themed master sheet for '{args.theme}' -> {ms_src}")
        except Exception as e:
            print(f"[!] Could not build themed master sheet ({e}); using archival-red base.")
            ms_src = base_ms
    if ms_src.exists():
        shutil.copy2(ms_src, proj_dir / "master_sheet.png")

    # 2. 建立目录骨架
    media_dir = proj_dir / ".media"
    for sub in ["refs", "dataliao", "assets", "video", "audio/voice"]:
        (media_dir / sub).mkdir(parents=True, exist_ok=True)
    (proj_dir / "renders").mkdir(exist_ok=True)

    # 3. 动态确定幕数与章节（支持 90 秒至 10 分钟全跨度）
    dur_str = str(args.duration).lower()
    if getattr(args, "scenes", None):
        target_scene_count = args.scenes
    elif "10m" in dur_str or "600" in dur_str:
        target_scene_count = 65
    elif "5m" in dur_str or "300" in dur_str:
        target_scene_count = 35
    elif "3m" in dur_str or "180" in dur_str:
        target_scene_count = 20
    else:  # 90s 或默认短片
        target_scene_count = 10

    # 循环轮转 6 种构图模式，契约级确保相邻两幕绝不雷同
    MODES_CYCLE = ["stat_hero", "archival_mat", "exploded_blueprint", "map_pin", "versus_clash", "macro_halftone"]

    # 动态划分章节（短片单章，中长片 3~5 章）
    chapters = []
    if target_scene_count <= 12:
        chapters = [{"chapter_index": 1, "title": "核心调查与反差", "scene_ids": [f"{i:02d}" for i in range(1, target_scene_count + 1)]}]
    else:
        num_ch = 3 if target_scene_count <= 25 else (4 if target_scene_count <= 45 else 5)
        ch_names = ["第一章·序幕与导火索", "第二章·历史档案与旧秩序", "第三章·核心技术与资本机制", "第四章·双雄对抗与博弈", "第五章·终局与时代遗产"]
        step = math.ceil(target_scene_count / num_ch)
        for c_idx in range(num_ch):
            s_start = c_idx * step + 1
            s_end = min((c_idx + 1) * step, target_scene_count)
            if s_start <= target_scene_count:
                sc_ids = [f"{i:02d}" for i in range(s_start, s_end + 1)]
                chapters.append({"chapter_index": c_idx + 1, "title": ch_names[c_idx % len(ch_names)], "scene_ids": sc_ids})

    # 为各幕映射所属章节名称
    scene_chapter_map = {}
    for ch in chapters:
        for sid in ch["scene_ids"]:
            scene_chapter_map[sid] = ch["title"]

    scenes = []
    sample_stats = ["100%", "420HP", "$300B", "85%", "0.2s", "1/1000"]
    for i in range(1, target_scene_count + 1):
        sid = f"{i:02d}"
        mode = MODES_CYCLE[(i - 1) % len(MODES_CYCLE)]
        # 动静混编策略：开场及每隔 3 幕为 hero_motion（H3 图层组装），其余为 drift_only（2% 呼吸慢漂移）
        motion_type = "hero_motion" if (i == 1 or i % 3 == 0) else "drift_only"
        ch_title = scene_chapter_map.get(sid, "深度调查")

        scene_obj = {
            "id": sid,
            "order": i,
            "chapter": ch_title,
            "mode": mode,
            "motion_type": motion_type,
            "voiceover": {
                "text": f"关于{args.topic}的第{i}个事实，在这里隐藏着至关重要的逻辑线索。"
            },
            "visual": {
                "headline": f"事实 {i}",
                "annotation": f"Fig. {i} - 调查取证",
                "real_asset_refs": ["topic_subject"]
            },
            "timing": {"lead_sec": 0.3, "tail_sec": 0.25, "media_start_sec": 1.0}
        }
        if mode == "stat_hero":
            scene_obj["visual"]["stat_number"] = sample_stats[(i - 1) % len(sample_stats)]

        scenes.append(scene_obj)

    ep_data = {
        "id": pid,
        "title": args.topic,
        "topic": args.topic,
        "ratio": args.ratio,
        "theme": args.theme,
        "target_duration_sec": 90 if "90" in dur_str else (180 if "3m" in dur_str else (300 if "5m" in dur_str else 600)),
        "chapters": chapters,
        "scenes": scenes,
        "refs_manifest": {}
    }

    (proj_dir / "episode.json").write_text(json.dumps(ep_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 记录到 DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT OR REPLACE INTO projects (id, topic, ratio, theme, target_duration, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (pid, args.topic, args.ratio, args.theme, args.duration, "pending", now, now))
    conn.commit()
    conn.close()

    print(f"[OK] Project created: {pid} ({args.ratio}, theme={args.theme}) at {proj_dir}")


def cmd_script(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    if not ep_file.exists():
        sys.exit(f"[!] Project {pid} episode.json not found.")

    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))
    script_md = proj_dir / "SCRIPT.md"

    # 生成 SCRIPT.md 供人工审查与去AI化扫描
    lines = [f"# {ep_data.get('title', pid)} · VOX Collage 分幕解说稿\n"]
    for s in ep_data.get("scenes", []):
        sid = s["id"]
        nar = s.get("voiceover", {}).get("text", "")
        mode = s.get("mode", "stat_hero")
        motion = s.get("motion_type", "drift_only")
        lines.append(f"## {sid} · 场景（voice_{sid}.wav）")
        lines.append(f"- 构图范式: {mode}")
        lines.append(f"- 动效方案: {motion}")
        lines.append(f"> 锁定稿: {nar}\n")

    script_md.write_text("\n".join(lines), encoding="utf-8")
    set_status(pid, "awaiting_script_review")
    print(f"[OK] Generated {script_md}. Pipeline PAUSED at script review gate.")
    print("     Please review script for AI patterns & dashes (——), then run:")
    print(f"     python bin/vox_collage.py approve-script {pid}")


def cmd_approve_script(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))

    # 检查红线：严禁破折号
    for s in ep_data.get("scenes", []):
        txt = s.get("voiceover", {}).get("text", "")
        if "——" in txt or "--" in txt:
            sys.exit(f"[X] Red line violation in scene {s['id']}: found dash '——' or '--'. Replace with comma or period.")

    set_status(pid, "script_approved")
    print(f"[OK] Script for {pid} APPROVED. Gate released.")


def cmd_refs(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))
    refs_dir = proj_dir / ".media" / "refs"

    # 抽取需要抓取的关键词。
    # 注意：不要用「主题词 + ref键」硬拼检索词，Wikimedia Commons 对长中文/虚构专名几乎零命中。
    # 优先读 episode.json 的 ref_query_map（内容相关的英文检索词），否则退回 key 本身的可读形式。
    override = ep_data.get("ref_query_map", {}) or {}
    topic = ep_data.get("topic", pid)

    def query_for(key: str) -> str:
        q = override.get(key)
        if q:
            return q
        return key.replace("_", " ").strip()

    queries = []
    seen = set()
    queries.append({"key": "topic_subject", "query": query_for("topic_subject") or topic, "limit": 6})
    seen.add("topic_subject")
    for s in ep_data.get("scenes", []):
        for rk in s.get("visual", {}).get("real_asset_refs", []):
            if rk not in seen:
                seen.add(rk)
                queries.append({"key": rk, "query": query_for(rk), "limit": 4})

    print(f"[refs] Fetching {len(queries)} asset groups from Wikimedia Commons...")
    manifest = fetch_queries(queries, refs_dir)
    ep_data["refs_manifest"] = manifest
    ep_file.write_text(json.dumps(ep_data, ensure_ascii=False, indent=2), encoding="utf-8")
    set_status(pid, "refs_done")
    print(f"[OK] True photography refs gathered in {refs_dir}")


def cmd_synth(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))

    voice_dir = proj_dir / ".media" / "audio" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = proj_dir / ".media" / "voice-manifest.json"

    # 调用 IndexTTS 2.5 客户端，并带有高质量回退机制
    voice_lines = []
    print(f"[synth] Synthesizing narration for {len(ep_data.get('scenes', []))} scenes...")

    indextts_session = None
    try:
        import importlib.util
        bridge_path = OMO_ROOT / "apps" / "indextts-bridge" / "client.py"
        if bridge_path.exists():
            spec = importlib.util.spec_from_file_location("indextts_client", str(bridge_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            indextts_session = mod.IndexTTSSession(
                voice_ref="D:/index-tts/my_voice.wav",
                model_version="2.5",
                lang="ZH",
                emotion="calm",
                project_dir=str(proj_dir)
            )
            indextts_session.start()
    except Exception as e:
        print(f"[synth] IndexTTS init note: {e}")
        indextts_session = None

    for s in ep_data.get("scenes", []):
        sid = s["id"]
        nar = s.get("voiceover", {}).get("text", "")
        wav_file = voice_dir / f"voice_{sid}.wav"

        if not wav_file.exists():
            success = False
            if indextts_session:
                try:
                    success = indextts_session.synthesize(nar, str(wav_file))
                except Exception as ex:
                    print(f"[synth] IndexTTS synth failed on scene {sid}: {ex}")
                    success = False
            if not success or not wav_file.exists() or wav_file.stat().st_size < 100:
                # 稳态回退：Edge-TTS 纪录片男声
                import asyncio
                import edge_tts
                async def _gen_edge(txt, out_p):
                    comm = edge_tts.Communicate(txt, "zh-CN-YunxiNeural")
                    mp3_tmp = out_p.with_suffix(".tmp.mp3")
                    await comm.save(str(mp3_tmp))
                    subprocess.run(["ffmpeg", "-y", "-i", str(mp3_tmp), "-ar", "24000", "-ac", "1", str(out_p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if mp3_tmp.exists():
                        mp3_tmp.unlink()
                asyncio.run(_gen_edge(nar, wav_file))

        dur = get_wav_duration(wav_file)
        voice_lines.append({
            "frame": sid,
            "wav": str(wav_file.relative_to(proj_dir)),
            "seconds": round(dur, 3),
            "text": nar
        })

    if indextts_session:
        try:
            indextts_session.close()
        except Exception:
            pass

    vm_data = {
        "project": pid,
        "sample_rate": 24000,
        "lines": voice_lines
    }
    manifest_file.write_text(json.dumps(vm_data, ensure_ascii=False, indent=2), encoding="utf-8")
    set_status(pid, "tts_done")

    if args.json:
        emit_json({"status": "tts_done", "project": pid, "lines": len(voice_lines)})
    else:
        print(f"[OK] Synthesized and measured wav headers -> {manifest_file}")


def cmd_dataliao(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))

    tokens_file = proj_dir / "tokens.json"
    tokens = {}
    if tokens_file.exists():
        tokens = json.loads(tokens_file.read_text(encoding="utf-8"))

    engine = DataliaoEngine(
        ratio=ep_data.get("ratio", "16:9"),
        tokens=tokens,
        cache_dir=proj_dir / ".media" / "refs" / "_cutouts"
    )

    out_dir = proj_dir / ".media" / "dataliao"
    out_dir.mkdir(parents=True, exist_ok=True)
    refs_dir = proj_dir / ".media" / "refs"

    only = set(x.strip() for x in args.only.split(",")) if args.only else None

    for s in ep_data.get("scenes", []):
        sid = s["id"]
        if only and sid not in only:
            continue
        print(f"[dataliao] Building plate for scene {sid} ({s.get('mode')})...")
        plate = engine.build_scene(s, refs_dir)
        dest = out_dir / f"scene-{sid}.png"
        plate.save(dest)

    set_status(pid, "dataliao_done")
    print(f"[OK] Dataliao plates ready in {out_dir}")


def cmd_stills(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_data = json.loads((proj_dir / "episode.json").read_text(encoding="utf-8"))
    stills_dir = proj_dir / ".media" / "assets"
    stills_dir.mkdir(parents=True, exist_ok=True)
    dataliao_dir = proj_dir / ".media" / "dataliao"
    master_sheet = proj_dir / "master_sheet.png"
    only = set(x.strip() for x in args.only.split(",")) if args.only else None

    # 画幅：静帧画布、Qwen 原生尺寸与输出尺寸都必须跟随 ratio（竖屏项目曾整体走横屏）
    ratio = ep_data.get("ratio", "16:9")
    img_w, img_h = _canvas(ratio)
    out_w, out_h = (1080, 1920) if str(ratio).startswith("9") else (1920, 1080)
    refs_dir = proj_dir / ".media" / "refs"   # 双参考图（ref_file_2）解析需要

    tmpl_file = COMFY_DIR / "wf_edit.json"

    def fallback_copy():
        for s in ep_data.get("scenes", []):
            sid = s["id"]
            if only and sid not in only:
                continue
            src = dataliao_dir / f"scene-{sid}.png"
            dst = stills_dir / f"gen-scene-{sid}.png"
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

    if not comfyui_client.is_up() or not tmpl_file.exists():
        print("[stills] ComfyUI 不在线或缺 wf_edit.json，回退为资料图直通（未风格化）。")
        fallback_copy()
        set_status(pid, "stills_done")
        if args.json:
            emit_json({"status": "stills_done", "project": pid, "mode": "fallback_copy"})
        else:
            print(f"[OK] Stills (fallback copy) ready in {stills_dir}")
        return

    from PIL import Image

    template_real = json.loads(tmpl_file.read_text(encoding="utf-8"))
    txt2img_file = OMO_ROOT / "tools" / "_comfyui" / "workflows" / "Qwen21-txt2img.json"
    template_ai = json.loads(txt2img_file.read_text(encoding="utf-8")) if txt2img_file.exists() else None
    tokens_file = proj_dir / "tokens.json"
    tokens = json.loads(tokens_file.read_text(encoding="utf-8")) if tokens_file.exists() else {}

    def pick_ref(scene):
        """为「真实内容」幕挑一张语义最贴的候选图（refs 目录第一张 = Commons 相关性首位）。"""
        v = scene.get("visual", {})
        refs_dir = proj_dir / ".media" / "refs"
        explicit = v.get("ref_file")
        if explicit:
            for k in v.get("real_asset_refs", []):
                p = refs_dir / k / explicit
                if p.exists():
                    return p
        for k in v.get("real_asset_refs", []):
            d = refs_dir / k
            if not d.is_dir():
                continue
            imgs = sorted([p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
            if imgs:
                return imgs[0]
        return None

    comfyui_client.free_memory()
    done, skipped = [], []
    for s in ep_data.get("scenes", []):
        sid = s["id"]
        if only and sid not in only:
            continue
        v = s.get("visual", {})
        is_real = v.get("asset_source") == "real"
        seed = random.randint(1, 2 ** 31)

        if is_real:
            plate_path = pick_ref(s)
            if not plate_path:
                print(f"[stills] scene {sid} 找不到真实图候选，跳过")
                skipped.append(sid)
                continue
            plate2_path = None
            rf2 = v.get("ref_file_2")
            if rf2:
                for k in (v.get("real_asset_refs_2") or v.get("real_asset_refs", [])):
                    cand = refs_dir / k / rf2
                    if cand.exists():
                        plate2_path = cand
                        break
            img_name = comfyui_client.upload_image(plate_path, f"vox_{sid}_plate.png")
            wf = copy.deepcopy(template_real)
            wf["459:456"]["inputs"]["width"] = img_w
            wf["459:456"]["inputs"]["height"] = img_h
            wf["459:474"]["inputs"]["prompt"] = build_collage_prompt_real(s, tokens, ratio)
            wf["459:474"]["inputs"]["negative_prompt"] = VOX_NEG
            wf["470"]["inputs"]["image"] = img_name
            if plate2_path is not None:
                # 必须走【链接】：模板 node 475 是 LoadImage，images.image_2 保持 ["475", 0]。
                # 直接写文件名字符串会被 ComfyUI 当 widget 值 → 节点收到 str 而非 IMAGE 张量。
                wf["475"]["inputs"]["image"] = comfyui_client.upload_image(
                    plate2_path, f"vox_{sid}_plate2.png")
            else:
                wf["459:474"]["inputs"].pop("images.image_2", None)
            wf["461"]["inputs"]["filename_prefix"] = f"VOX/still-{sid}"
            wf["459:458"]["inputs"]["seed"] = seed
            label = "真实证据拼贴"
            src_desc = plate_path.name
        else:
            if template_ai is None:
                print(f"[stills] 缺 txt2img 模板，跳过 AI 幕 {sid}")
                skipped.append(sid)
                continue
            wf = copy.deepcopy(template_ai)
            wf["7"]["inputs"]["width"] = img_w
            wf["7"]["inputs"]["height"] = img_h
            wf["5"]["inputs"]["text"] = build_image_prompt(s, tokens, ratio)
            wf["6"]["inputs"]["text"] = VOX_NEG
            wf["8"]["inputs"]["seed"] = seed
            wf["10"]["inputs"]["filename_prefix"] = f"VOX/still-{sid}"
            label = "纯 AI 象征图"
            src_desc = v.get("visual_metaphor", "")

        print(f"[stills] scene {sid} · {label} · 源={src_desc} ...")
        qid = comfyui_client.queue_prompt(wf)
        hist = comfyui_client.wait_prompt(qid, timeout=2400)
        outs = [
            o for o in comfyui_client.outputs_of(hist)
            if str(o["filename"]).lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
        if not outs:
            print(f"[stills] scene {sid} 无图像产物，跳过")
            skipped.append(sid)
            continue
        raw = stills_dir / f"_raw-{sid}.png"
        comfyui_client.download_output(outs[-1], raw)
        Image.open(raw).convert("RGB").resize((out_w, out_h), Image.LANCZOS).save(
            stills_dir / f"gen-scene-{sid}.png"
        )
        try:
            raw.unlink()
        except Exception:
            pass
        done.append(sid)

    set_status(pid, "stills_done")
    if args.json:
        emit_json({"status": "stills_done", "project": pid, "mode": "dual", "scenes": done, "skipped": skipped})
    else:
        print(f"[OK] 拼贴图完成 {done}（跳过 {skipped}）-> {stills_dir}")


def cmd_motion(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_data = json.loads((proj_dir / "episode.json").read_text(encoding="utf-8"))
    vm_file = proj_dir / ".media" / "voice-manifest.json"
    voice = {}
    if vm_file.exists():
        vm = json.loads(vm_file.read_text(encoding="utf-8"))
        voice = {l["frame"]: l for l in vm.get("lines", [])}
    stills_dir = proj_dir / ".media" / "assets"
    dataliao_dir = proj_dir / ".media" / "dataliao"
    video_dir = proj_dir / ".media" / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    only = set(x.strip() for x in args.only.split(",")) if args.only else None

    hero = [s for s in ep_data.get("scenes", []) if s.get("motion_type") == "hero_motion"]
    drift_count = sum(1 for s in ep_data.get("scenes", []) if s.get("motion_type") == "drift_only")
    if only:
        hero = [s for s in hero if s["id"] in only]
    print(f"[motion] Plan: {len(hero)} Hero Motion (H3) + {drift_count} Drift Only (静帧 + 2% Slow Drift)")

    tmpl_file = COMFY_DIR / "wf_vid.json"
    if not comfyui_client.is_up() or not tmpl_file.exists():
        print("[motion] ComfyUI 不在线或缺 wf_vid.json，跳过 hero 动效（保留静帧 drift）。")
        set_status(pid, "motion_done")
        if args.json:
            emit_json({"status": "motion_done", "project": pid, "mode": "skipped", "hero": len(hero)})
        else:
            print(f"[OK] Motion skipped; drift stills remain in {stills_dir}")
        return

    template = json.loads(tmpl_file.read_text(encoding="utf-8"))
    comfyui_client.free_memory()
    done = []
    ratio = ep_data.get("ratio", "16:9")
    if ratio == "16:9":
        vid_w, vid_h = 1024, 576
    else:
        vid_w, vid_h = 576, 1024

    slot_of = lambda sid: 0.30 + float(voice.get(sid, {}).get("seconds", 3.0)) + 0.25

    # 文档 Prompt 3：一幕一条片段。H3 只做「逐层搭建」，相机完全静止、不做任何转场；
    # 所有换幕统一交给 HyperFrames 的「无缝纸擦除」，保证全片转场 100% 一致。
    print(f"[motion] 单幕模式：{len(hero)} 条片段（H3 不做转场；转场由 HyperFrames 统一负责）")

    for sc in hero:
        sid = sc["id"]
        ref = stills_dir / f"gen-scene-{sid}.png"
        if not ref.exists():
            ref = dataliao_dir / f"scene-{sid}.png"
        if not ref.exists():
            print(f"[motion] 缺参考图 scene-{sid}，跳过")
            continue

        up = comfyui_client.upload_image(ref, f"vox_{sid}_ref.png")
        span = slot_of(sid)
        media_start = float(sc.get("timing", {}).get("media_start_sec", 0.5))
        # 动态帧：131 表达式按 132(秒) 自动换算 17n+5 帧
        gen_sec = round(min(15.0, max(5.2, span + media_start + 0.4)), 2)

        wf = copy.deepcopy(template)
        wf["137"]["inputs"]["image"] = up
        wf["136"]["inputs"].pop("ref_images.ref_image_1", None)
        wf["136"]["inputs"].pop("ref_images.ref_image_2", None)
        if "ref_image_size" in wf["136"]["inputs"]:
            wf["136"]["inputs"]["ref_image_size"] = "max"  # 更高保真，显著降低内容漂移/臆造
        wf["138"]["inputs"]["value"] = build_video_prompt(sc, gen_sec, media_start=media_start, visible_sec=span, ratio=ratio)
        wf["136"]["inputs"]["width"] = vid_w
        wf["136"]["inputs"]["height"] = vid_h
        wf["132"]["inputs"]["value"] = gen_sec
        if "124" in wf and "inputs" in wf["124"]:
            wf["124"]["inputs"]["steps"] = 4
        wf["92"]["inputs"]["filename_prefix"] = f"VOX/{pid}-single/scene{sid}"
        wf["129"]["inputs"]["noise_seed"] = random.randint(1, 2 ** 31)
        print(f"[motion] H3 单幕 {sid}: {gen_sec}s, 1 张参考图, 4 步, {vid_w}x{vid_h} ...")
        qid = comfyui_client.queue_prompt(wf)
        hist = comfyui_client.wait_prompt(qid, timeout=3600)
        outs = [
            o for o in comfyui_client.outputs_of(hist)
            if str(o["filename"]).lower().endswith((".mp4", ".webm", ".mkv", ".mov"))
        ]
        if not outs:
            print(f"[motion] 幕 {sid} 无视频产物，跳过")
            continue
        raw = video_dir / f"_raw-{sid}.mp4"
        comfyui_client.download_output(outs[-1], raw)

        # 保留 H3 原生音轨（纸质 ASMR）；统一 h264/yuv420p + aac 便于逐帧 seek
        out = video_dir / f"gen-scene-{sid}.mp4"
        ff = ["ffmpeg", "-y", "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(out)]
        r = subprocess.run(ff, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not out.exists():
            shutil.copy2(raw, out)

        # 抽出独立 ASMR 音轨，供 compose 作为低音量铺底
        asmr = video_dir / f"asmr-{sid}.m4a"
        fa = ["ffmpeg", "-y", "-i", str(out), "-vn", "-c:a", "aac", "-b:a", "192k", str(asmr)]
        subprocess.run(fa, capture_output=True, text=True, encoding="utf-8", errors="replace")

        try:
            raw.unlink()
        except Exception:
            pass
        done.append(sid)

    set_status(pid, "motion_done")
    if args.json:
        emit_json({"status": "motion_done", "project": pid, "mode": "h3_single", "scenes": done})
    else:
        print(f"[OK] H3 单幕动效完成 {done} -> {video_dir}")


def cmd_compose(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))
    vm_file = proj_dir / ".media" / "voice-manifest.json"
    if not vm_file.exists():
        sys.exit(f"[!] voice-manifest.json not found for {pid}. Run synth first.")
    vm_data = json.loads(vm_file.read_text(encoding="utf-8"))

    # --only：只合成指定幕（用于章节预览；不带参数则合成全片）
    only = set(x.strip() for x in args.only.split(",")) if getattr(args, "only", None) else None
    if only:
        ep_data = dict(ep_data)
        ep_data["scenes"] = [s for s in ep_data.get("scenes", []) if s["id"] in only]
        vm_data = dict(vm_data)
        vm_data["lines"] = [l for l in vm_data.get("lines", []) if l["frame"] in only]
        print(f"[compose] 章节预览模式：仅合成 {sorted(only)}")

    out_html = proj_dir / "index.html"
    generate_index_html(ep_data, vm_data, out_html)
    set_status(pid, "composed")
    print(f"[OK] HyperFrames index.html created: {out_html}")


def _hf_run(hf_args, cwd, env, timeout):
    """Windows 安全的 hyperframes 调用：用 shutil.which 解析 npx(.cmd)，避免 WinError2。"""
    cmd = ["npx", "--yes", "hyperframes@latest", *hf_args]
    exe = shutil.which(cmd[0], path=env.get("PATH") or env.get("Path"))
    if exe:
        cmd[0] = exe
    # HyperFrames 输出含 UTF-8/emoji，Windows 默认 GBK 解码会崩；显式指定编码
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def cmd_render(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    index_html = proj_dir / "index.html"
    if not index_html.exists():
        sys.exit(f"[!] index.html not found for {pid}. Run compose first.")
    renders_dir = proj_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    out_mp4 = renders_dir / f"{pid}_{ts}.mp4"

    # 运行时统一 @latest（本地知识会漂移，运行时永远最新；siblings 管线同规）
    env = dict(os.environ)
    npm_cache = OMO_ROOT / ".npm-cache"
    npm_cache.mkdir(parents=True, exist_ok=True)
    env["npm_config_cache"] = str(npm_cache)
    hf_tmp = OMO_ROOT / ".hf-tmp"
    hf_tmp.mkdir(exist_ok=True)
    env["TEMP"] = str(hf_tmp)
    env["TMP"] = str(hf_tmp)
    env["HYPERFRAMES_EXTRACT_CACHE_DIR"] = str(OMO_ROOT / ".hf-cache")
    (OMO_ROOT / ".hf-cache").mkdir(exist_ok=True)
    env["PRODUCER_LOW_MEMORY_MODE"] = "1"
    env["PRODUCER_STREAMING_ENCODE_MAX_DURATION_SECONDS"] = "7200"

    # 1. lint 闸门：0 错误才渲染
    print("[render] lint gate via HyperFrames ...")
    lint = _hf_run(["lint", str(proj_dir)], proj_dir, env, 900)
    if lint.returncode != 0:
        sys.exit(f"[X] HyperFrames lint failed:\n{(lint.stdout or '')[-1500:]}\n{(lint.stderr or '')[-1500:]}")

    # 2. render
    print(f"[render] Rendering clean master via HyperFrames -> {out_mp4}")
    res = _hf_run(["render", str(proj_dir), "-o", str(out_mp4), "--low-memory-mode"], proj_dir, env, 7200)

    # 3. 后置校验：退出码 0 且产物存在且非空，否则视为失败（禁止静默假成功）
    if res.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size < 1024:
        sys.exit(f"[X] HyperFrames render failed:\n{(res.stdout or '')[-1500:]}\n{(res.stderr or '')[-1500:]}")

    set_status(pid, "rendered")
    if args.json:
        emit_json({"status": "rendered", "output": str(out_mp4), "bytes": out_mp4.stat().st_size})
    else:
        print(f"[OK] Clean master rendered -> {out_mp4}")


def cmd_subtitle(args):
    pid = args.id
    proj_dir = PROJECTS_DIR / pid
    ep_file = proj_dir / "episode.json"
    ep_data = json.loads(ep_file.read_text(encoding="utf-8"))
    vm_file = proj_dir / ".media" / "voice-manifest.json"
    vm_data = json.loads(vm_file.read_text(encoding="utf-8"))

    # 1. 查找最新母版
    renders_dir = proj_dir / "renders"
    candidates = sorted(renders_dir.glob(f"{pid}_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if not p.name.endswith("_subtitled.mp4")]
    if not candidates:
        sys.exit("[!] No rendered master video found. Run render first.")
    master_video = candidates[0]

    # 2. 生成 ASS 字幕
    ass_file = proj_dir / ".media" / "subs.ass"
    build_ass(ep_data, vm_data, ass_file)

    # 3. 烧录成片
    subtitled_video = renders_dir / f"{master_video.stem}_subtitled.mp4"
    burn_subtitles(master_video, ass_file, subtitled_video)
    set_status(pid, "subtitled")
    print(f"[OK] Subtitled 3D delivery package ready -> {subtitled_video}")


def cmd_run(args):
    cmd_new(args)
    cmd_refs(args)
    cmd_script(args)


def cmd_run_heavy(args):
    cmd_synth(args)
    cmd_dataliao(args)
    cmd_stills(args)
    cmd_motion(args)
    cmd_compose(args)
    cmd_render(args)
    cmd_subtitle(args)


def cmd_status(args):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, topic, ratio, theme, target_duration, status, updated_at FROM projects ORDER BY updated_at DESC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No VOX Collage projects tracked yet.")
        return

    print(f"{'PROJECT ID':<22} {'RATIO':<6} {'THEME':<15} {'STATUS':<20} {'TOPIC'}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<22} {r[2]:<8} {r[3]:<16} {r[5]:<22} {r[1]}")


# ---------------------------------------------------------------- Main Entry
def main():
    parser = argparse.ArgumentParser(description="VOX Collage Documentary Video Pipeline CLI")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # new
    p_new = sub.add_parser("new", help="Create new project")
    p_new.add_argument("topic", help="Video topic or title")
    p_new.add_argument("--id", help="Explicit project ID")
    p_new.add_argument("--ratio", choices=["16:9", "9:16"], default="16:9", help="Aspect ratio")
    p_new.add_argument("--theme", choices=["archival-red", "racing-orange", "tech-cyan", "finance-green"], default="archival-red")
    p_new.add_argument("--duration", default="90s", help="Target duration (e.g. 90s, 3m, 5m, 10m)")
    p_new.add_argument("--scenes", type=int, default=None, help="Explicit scene count (overrides duration defaults)")
    p_new.set_defaults(func=cmd_new)

    # script & approve
    p_script = sub.add_parser("script", help="Generate script and stop at gate")
    p_script.add_argument("id")
    p_script.set_defaults(func=cmd_script)

    p_app = sub.add_parser("approve-script", help="Approve script and release gate")
    p_app.add_argument("id")
    p_app.set_defaults(func=cmd_approve_script)

    # refs
    p_refs = sub.add_parser("refs", help="Gather real photography refs")
    p_refs.add_argument("id")
    p_refs.set_defaults(func=cmd_refs)

    # synth
    p_synth = sub.add_parser("synth", help="Synthesize narration with IndexTTS")
    p_synth.add_argument("id")
    p_synth.add_argument("--json", action="store_true")
    p_synth.set_defaults(func=cmd_synth)

    # dataliao
    p_data = sub.add_parser("dataliao", help="Build procedural dataliao plates")
    p_data.add_argument("id")
    p_data.add_argument("--only", help="Filter scene IDs (quoted)")
    p_data.set_defaults(func=cmd_dataliao)

    # stills
    p_stills = sub.add_parser("stills", help="Style stills with Qwen-Image-Edit")
    p_stills.add_argument("id")
    p_stills.add_argument("--only", help="Filter scene IDs (quoted)")
    p_stills.add_argument("--json", action="store_true")
    p_stills.set_defaults(func=cmd_stills)

    # motion
    p_motion = sub.add_parser("motion", help="Generate layer motion videos with MiniMax H3")
    p_motion.add_argument("id")
    p_motion.add_argument("--only", help="Filter scene IDs (quoted)")
    p_motion.add_argument("--json", action="store_true")
    p_motion.set_defaults(func=cmd_motion)

    # compose
    p_comp = sub.add_parser("compose", help="Assemble HyperFrames composition")
    p_comp.add_argument("id")
    p_comp.add_argument("--only", help="Only compose these scene IDs (quoted), for chapter preview")
    p_comp.set_defaults(func=cmd_compose)

    # render
    p_rend = sub.add_parser("render", help="Render clean master MP4")
    p_rend.add_argument("id")
    p_rend.add_argument("--json", action="store_true")
    p_rend.set_defaults(func=cmd_render)

    # subtitle
    p_sub = sub.add_parser("subtitle", help="Burn 3D extruded ASS subtitles")
    p_sub.add_argument("id")
    p_sub.set_defaults(func=cmd_subtitle)

    # run & run-heavy
    p_run = sub.add_parser("run", help="Quick setup (new + refs + script)")
    p_run.add_argument("topic")
    p_run.add_argument("--id")
    p_run.add_argument("--ratio", choices=["16:9", "9:16"], default="16:9")
    p_run.add_argument("--theme", choices=["archival-red", "racing-orange", "tech-cyan", "finance-green"], default="archival-red")
    p_run.add_argument("--duration", default="90s")
    p_run.add_argument("--scenes", type=int, default=None, help="Explicit scene count (overrides duration defaults)")
    p_run.set_defaults(func=cmd_run)

    p_heavy = sub.add_parser("run-heavy", help="Compute intensive production flow")
    p_heavy.add_argument("id")
    p_heavy.add_argument("--json", action="store_true")
    p_heavy.set_defaults(func=cmd_run_heavy)

    # status
    p_stat = sub.add_parser("status", help="List all tracked VOX Collage projects")
    p_stat.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
