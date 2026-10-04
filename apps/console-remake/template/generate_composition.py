#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console-remake 装配器（apps/console-remake/template/generate_composition.py）

职责（compose 阶段，纯 CPU）：
  1. 读取 artifacts/episode.json（创作契约：幕/句/零件）与 artifacts/tts_results.json（逐句实测时长）
  2. 计算全局时间轴（timings.json）：逐句起点、幕窗口、字幕窗、总时长
  3. ffmpeg 烘焙旁白 master（逐句 adelay+amix）与 BGM master（循环裁剪+淡出）
  4. 生成 hyperframes/index.html：
     - 静态幕壳（lint 可见）+ 内联 console.css / console.js + 数据注入
     - GSAP 本地库、音频直挂 root
  5. 资产拷贝（gsap.min.js / 音频 / BGM）

用法：
  python apps/console-remake/template/generate_composition.py --project projects/<slug>
  python apps/console-remake/template/generate_composition.py --project projects/<slug> --no-audio   # 无配音预览（估时长）
  python apps/console-remake/template/generate_composition.py --project projects/<slug> --scenes s01,s02

契约来源：apps/console-remake/specs/design-system.md
"""
import argparse
import html as _html
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OMO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = Path(__file__).resolve().parent
CJK_CPS = 4.6          # 中文口播速度（字/秒）——仅无配音估算用
ELEMENT_TYPES = {"frame", "grid", "pill", "hairline", "bignum", "arrow", "leader", "bracket", "slot",
                 "paper", "toast", "panel", "text", "source", "seal",
                 "win", "term", "rows", "repocard", "mark", "bars", "shape", "image"}


# ---------------------------------------------------------------- helpers
def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def wav_duration(p: Path) -> float:
    with wave.open(str(p), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def ffmpeg(cmd, timeout=1800):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def esc_script_embed(s: str) -> str:
    return s.replace("</", "<\\/")


# ---------------------------------------------------------------- timing
def compute_timing(episode: dict, tts: dict, use_est: bool = False) -> dict:
    cfg = episode.get("timing", {})
    line_gap = float(cfg.get("line_gap", 0.35))
    scene_gap = float(cfg.get("scene_gap", 0.6))
    lead_in = float(cfg.get("scene_lead_in", 0.35))
    tail = float(cfg.get("tail", 2.2))
    subs_on = bool(episode.get("subtitles", True))

    cursor = 0.0
    scenes_t, lines_t, subs = [], [], []

    for si, sc in enumerate(episode["scenes"]):
        if si > 0:
            cursor += float(sc.get("gap_in", scene_gap))
        content_start = cursor
        lines = sc.get("lines", [])
        for li, ln in enumerate(lines):
            dur = tts.get(ln["id"])
            if dur is None:
                if not use_est and tts:
                    raise ValueError(f"tts_results 缺少句 {ln['id']} 的实测时长")
                dur = len(ln["text"]) / CJK_CPS + 0.25
            dur = float(dur)
            lines_t.append({"id": ln["id"], "scene": sc["id"],
                            "start": round(cursor, 3), "dur": round(dur, 3),
                            "end": round(cursor + dur, 3)})
            if subs_on and ln.get("sub", True):
                subs.append({"start": round(max(0.0, cursor - 0.05), 3),
                             "end": round(cursor + dur + 0.12, 3),
                             "text": ln["text"]})
            gap = float(ln.get("gap_after", line_gap if li < len(lines) - 1 else 0.2))
            cursor += dur + gap
        end = cursor + float(sc.get("hold_after", 0.15))
        s_start = max(0.0, content_start - lead_in)
        scenes_t.append({"id": sc["id"], "start": round(s_start, 3),
                         "end": round(end, 3), "dur": round(end - s_start, 3)})
        cursor = end

    total = round(cursor + tail, 3)
    return {"total": total, "scenes": scenes_t, "lines": lines_t, "subs": subs}


# ---------------------------------------------------------------- audio baking
def bake_audio(project: Path, episode: dict, timing: dict) -> dict:
    audio_dir = project / "assets" / "audio"
    hf_audio = project / "hyperframes" / "assets" / "audio"
    hf_audio.mkdir(parents=True, exist_ok=True)
    out = {}

    line_files = []
    for lt in timing["lines"]:
        wav = audio_dir / f"{lt['id']}.wav"
        if wav.exists():
            line_files.append((lt, wav))
    if not line_files:
        return out

    total = timing["total"]
    inputs, filters, labels = [], [], []
    for i, (lt, wav) in enumerate(line_files):
        inputs += ["-i", str(wav)]
        ms = int(round(lt["start"] * 1000))
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,"
                       f"adelay={ms}|{ms},apad=whole_dur={int(total * 1000) + 500}ms[v{i}]")
        labels.append(f"[v{i}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[vo]")

    vo_out = hf_audio / "narration_master.wav"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[vo]", "-t", str(total + 0.5), "-c:a", "pcm_s16le", str(vo_out)]
    r = ffmpeg(cmd)
    if r.returncode != 0 or not vo_out.exists():
        raise RuntimeError(f"旁白烘焙失败: {r.stdout[-2000:]}")
    out["narration"] = str(vo_out)

    bgm_rel = (episode.get("audio") or {}).get("bgm")
    if bgm_rel:
        bgm_src = Path(bgm_rel)
        if not bgm_src.is_absolute():
            bgm_src = OMO_ROOT / bgm_rel
        if bgm_src.exists():
            bgm_out = hf_audio / "bgm_master.mp3"
            fade_st = max(0.0, total - 3.5)
            vol = float((episode.get("audio") or {}).get("bgm_volume", 0.12))
            cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(bgm_src),
                   "-t", str(total), "-af",
                   f"volume={vol},afade=t=in:st=0:d=1.5,afade=t=out:st={fade_st:.2f}:d=3.5",
                   "-c:a", "libmp3lame", "-b:a", "192k", str(bgm_out)]
            r = ffmpeg(cmd)
            if r.returncode == 0 and bgm_out.exists():
                out["bgm"] = str(bgm_out)
    return out


# ---------------------------------------------------------------- sfx baking
def bake_sfx(project: Path, episode: dict, timing: dict):
    """音效轨：episode.sfx = [{src, at(行 id 或 scene:xx), off, gain}] → sfx_master.wav"""
    cues = episode.get("sfx") or []
    if not cues:
        return None
    src_dir = project / "assets" / "sfx"
    hf_audio = project / "hyperframes" / "assets" / "audio"
    hf_audio.mkdir(parents=True, exist_ok=True)
    line_start = {lt["id"]: lt["start"] for lt in timing["lines"]}
    scene_start = {s["id"]: s["start"] for s in timing["scenes"]}
    inputs, filters, labels = [], [], []
    n = 0
    for c in cues:
        at = str(c.get("at", ""))
        t = scene_start.get(at[6:]) if at.startswith("scene:") else line_start.get(at)
        if t is None:
            continue
        t += float(c.get("off", 0))
        src = src_dir / str(c.get("src", ""))
        if not src.exists():
            continue
        gain = float(c.get("gain", 0.5))
        inputs += ["-i", str(src)]
        ms = int(round(max(0.0, t) * 1000))
        filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=mono,volume={gain},"
                       f"adelay={ms}|{ms}[s{n}]")
        labels.append(f"[s{n}]")
        n += 1
    if not labels:
        return None
    filters.append(f"{''.join(labels)}amix=inputs={n}:duration=longest:normalize=0[so]")
    out = hf_audio / "sfx_master.wav"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[so]",
           "-t", str(timing["total"] + 0.5), "-c:a", "pcm_s16le", str(out)]
    r = ffmpeg(cmd)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"SFX 烘焙失败: {r.stdout[-1500:]}")
    return str(out)


# ---------------------------------------------------------------- html build
# HyperFrames 官方 modular 架构：
#   index.html        —— 薄宿主：槽位（data-composition-src）+ 音频 + 字幕条（宿主 timeline "main"）
#   compositions/*.html —— 每一幕独立子合成：<template> 内自带样式/脚本/自有 timeline（键 = 幕 id）
HOST_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<title>{title}</title>
<script src="assets/gsap.min.js"></script>
<link rel="stylesheet" href="assets/console.css" />
<script src="assets/console.js"></script>
<style>
/* registry 组件 token 对齐（console-v2 token → HyperFrames 组件契约 token） */
:root {{
  --fg: var(--ink);
  --muted: var(--ink-dim);
  --border: var(--line);
  --radius: var(--radius-win);
  --brand: var(--accent);
  --accent-2: var(--accent);
  --font-body: var(--font-sans);
}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="{total}">
{slots}
  <div id="hud-frame"></div>
  <div class="hud-corner hud-corner--tl"></div>
  <div class="hud-corner hud-corner--tr"></div>
  <div class="hud-corner hud-corner--bl"></div>
  <div class="hud-corner hud-corner--br"></div>
  <div id="hud-topline"></div>
  <div id="hud-brand"><span class="hb-en">{brand_en}</span><span class="hb-sep">·</span><span class="hb-cn">{brand_cn}</span></div>
  <div id="hud-chapter"><span id="hud-ch-id">CH 01 / {n_ch}</span><span class="hb-sep">·</span><span id="hud-ch-name">{ch0}</span></div>
  <div id="hud-progress">
    <div class="hud-track"></div>
    <div id="hud-progress-fill"></div>
{ticks}
    <div id="hud-progress-head"></div>
  </div>
  <div id="sub-bar">
    <div class="sub-rule"></div>
    <div class="sub-inner">
      <span class="sub-mark">&#9615;</span>
      <span class="sub-time" id="sub-time">00:00</span>
      <span class="sub-text" id="sub-text"></span>
    </div>
  </div>
{audio_tags}
{slot_templates}
</div>
<script>
window.__timelines = window.__timelines || {{}};
window.__CW_HOST__ = {host_data};
(function () {{
  var tl = gsap.timeline({{ paused: true }});
  ConsoleWorld.buildHost(tl, window.__CW_HOST__);
  window.__timelines["main"] = tl;
}})();
</script>
</body>
</html>
"""

SCENE_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<title>{scene_id}</title>
</head>
<body>
<template id="{scene_id}-template">
<div id="root" data-composition-id="{scene_id}" data-width="1920" data-height="1080" data-duration="{dur}" style="position:absolute;inset:0;width:1920px;height:1080px;overflow:hidden;background:transparent">
  <div class="scene-inner" data-layout-allow-overflow data-layout-allow-overlap>
{footage_html}</div>
<script>
window.__timelines = window.__timelines || {{}};
(function () {{
  var tl = gsap.timeline({{ paused: true }});
  ConsoleWorld.buildScene(tl, {scene_data});
  window.__timelines["{scene_id}"] = tl;
}})();
</script>
</template>
</body>
</html>
"""


def _embed_safe(s: str) -> str:
    """防止 `</script` / `<!--` 提前终止 script/style 块（大小写不敏感）。"""
    return re.sub(r"</(script)", r"<\\/\1", s, flags=re.IGNORECASE).replace("<!--", "<\\!--")


def _resolve_at(line_text: str, words: list, at: str):
    """语音驱动锚定：元素 `at`（字/词）→ 该词被说出的时刻（相对句首秒数）。
    优先用 whisper 词级时间戳做字符映射；失败时按字符比例退化。"""
    if not words or not at:
        return None
    full, idx_map = "", []
    for wi, w in enumerate(words):
        for _ch in w.get("w", ""):
            full += _ch
            idx_map.append(wi)
    pos = full.find(at)
    if pos >= 0:
        return round(float(words[idx_map[pos]]["s"]) + 0.05, 3)
    raw = line_text.find(at)
    if raw >= 0 and words[-1].get("e"):
        return round(max(0.0, (raw / max(1, len(line_text))) * float(words[-1]["e"])), 3)
    return None


def build_html(project: Path, episode: dict, timing: dict, bake: dict, scenes_subset=None):
    hf_dir = project / "hyperframes"
    hf_dir.mkdir(parents=True, exist_ok=True)
    comp_dir = hf_dir / "compositions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    # 语音驱动词级时间戳（synth 后由 `align` 生成；缺省则 at 锚定退化为比例估计）
    line_words = {}
    lw_path = project / "artifacts" / "line_words.json"
    if lw_path.exists():
        try:
            line_words = json.loads(lw_path.read_text(encoding="utf-8"))
        except Exception:
            line_words = {}

    subset = set(scenes_subset) if scenes_subset else None
    scenes = [s for s in timing["scenes"] if not (subset and s["id"] not in subset)]

    # 场景 → footprint 定义（真实素材窗口；见 design-system §11）
    scene_meta = {sc["id"]: sc for sc in episode["scenes"]}
    footage_files = []
    footage_dir_src = project / "assets" / "footage"
    footage_dir_dst = hf_dir / "assets" / "footage"
    footage_dir_dst.mkdir(parents=True, exist_ok=True)

    # 真实图片素材（image 零件 + registry slot 图片）：assets/images → hyperframes/assets/images
    image_dir_src = project / "assets" / "images"
    image_dir_dst = hf_dir / "assets" / "images"
    image_dir_dst.mkdir(parents=True, exist_ok=True)
    images_copied, images_missing = [], []

    def _collect_image_names():
        names = []
        for sc in episode["scenes"]:
            for ln in sc.get("lines", []):
                for e in ln.get("elements", []):
                    if e.get("type") == "image" and e.get("src"):
                        names.append(Path(e["src"]).name)
            for _sn, sdef in ((sc.get("registry") or {}).get("slots") or {}).items():
                if (sdef or {}).get("img"):
                    names.append(Path(sdef["img"]).name)
        return names

    for fname in _collect_image_names():
        if fname in images_copied or fname in images_missing:
            continue
        src_p = image_dir_src / fname
        if src_p.exists():
            shutil.copy2(src_p, image_dir_dst / fname)
            images_copied.append(fname)
        else:
            images_missing.append(fname)

    def build_footage_html(sc_id: str, dur: float) -> str:
        ft = (scene_meta.get(sc_id) or {}).get("footage")
        if not ft:
            return ""
        src = ft.get("src")
        if not src:
            return ""
        fname = Path(src).name
        source = footage_dir_src / fname
        if source.exists():
            shutil.copy2(source, footage_dir_dst / fname)
            footage_files.append(fname)
        style = ("left:%dpx;top:%dpx;width:%dpx;height:%dpx;%s" % (
            ft.get("x", 0), ft.get("y", 0), ft.get("w", 1920), ft.get("h", 1080),
            ("border-radius:%dpx;" % ft["radius"]) if ft.get("radius") is not None else "",
        ))
        cls = "footage-wrap" + (" footage-wrap--dim" if ft.get("dim") else "") + \
              (" footage-wrap--bare" if ft.get("bare") else "")
        vstyle = ""
        if ft.get("focus"):
            vstyle = "object-position:%s;" % ft["focus"]
        grade = ""
        if ft.get("grading"):
            grade = ' data-color-grading="%s"' % _html.escape(
                json.dumps(ft["grading"], ensure_ascii=False), quote=True)
        return (f'    <div class="{cls}" style="{style}">\n'
                f'      <div class="footage-inner">\n'
                f'      <video id="{sc_id}-footage" class="footage" src="assets/footage/{fname}"{grade} '
                f'data-start="0" data-duration="{round(dur, 3)}" data-track-index="2" '
                f'muted playsinline style="{vstyle}"></video>\n'
                f'      </div>\n'
                f'    </div>\n')

    # 清理旧幕文件（避免残留）
    for old in comp_dir.glob("*.html"):
        old.unlink()

    slots, scene_files = [], []
    slot_templates, registry_missing, videos_missing = [], [], []
    for st in scenes:
        # ---- registry 组件幕：整幕交给注册表组件（hyperframes add 安装）----
        reg = (scene_meta.get(st["id"]) or {}).get("registry") or {}
        if reg:
            comp = str(reg.get("component") or "").strip()
            comp_path = comp_dir / "components" / f"{comp}.html"
            if not comp_path.exists():
                registry_missing.append(comp)
            else:
                _adapt_registry_component(comp_path, float(st["dur"]))
            vars_json = json.dumps(reg.get("vars") or {}, ensure_ascii=False).replace("'", "\\u0027")
            slots.append(
                f'  <div id="scene-{st["id"]}" data-composition-id="{comp}" '
                f'data-composition-src="compositions/components/{comp}.html" '
                f'data-start="{st["start"]}" data-duration="{st["dur"]}" '
                f'data-track-index="1" data-width="1920" data-height="1080" '
                f"data-variable-values='{vars_json}'></div>")
            for sn, sdef in (reg.get("slots") or {}).items():
                sdef = sdef or {}
                g = sdef.get("grading")
                g_attr = (' data-color-grading="%s"' % _html.escape(
                    json.dumps(g, ensure_ascii=False), quote=True)) if g else ""
                if sdef.get("img"):
                    fname = Path(sdef["img"]).name
                    alt = _html.escape(str(sdef.get("alt") or ""), quote=True)
                    slot_templates.append(
                        f'  <template data-slot="{comp}-{sn}">'
                        f'<img src="assets/images/{fname}" alt="{alt}"{g_attr} '
                        f'style="display:block;width:100%;height:100%;object-fit:cover;"></template>')
                elif sdef.get("video"):
                    fname = Path(sdef["video"]).name
                    if (footage_dir_src / fname).exists():
                        shutil.copy2(footage_dir_src / fname, footage_dir_dst / fname)
                    else:
                        videos_missing.append(fname)
                    slot_templates.append(
                        f'  <template data-slot="{comp}-{sn}">'
                        f'<video id="{comp}-{sn}-vid" src="assets/footage/{fname}"{g_attr} muted playsinline data-start="0" '
                        f'style="display:block;width:100%;height:100%;object-fit:cover;"></video></template>')
            continue

        slots.append(
            f'  <div id="scene-{st["id"]}" data-composition-id="{st["id"]}" '
            f'data-composition-src="compositions/{st["id"]}.html" '
            f'data-start="{st["start"]}" data-duration="{st["dur"]}" '
            f'data-track-index="1" data-width="1920" data-height="1080"></div>')

        lines_rel = []
        for lt in timing["lines"]:
            if lt["scene"] != st["id"]:
                continue
            ln_meta = None
            for sc in episode["scenes"]:
                if sc["id"] == st["id"]:
                    for ln in sc["lines"]:
                        if ln["id"] == lt["id"]:
                            ln_meta = ln
            if ln_meta is None:
                continue
            words = (line_words.get(lt["id"]) or {}).get("words") or []
            els = []
            for e in ln_meta.get("elements", []):
                if e.get("at"):
                    tr = _resolve_at(ln_meta.get("text", ""), words, e["at"])
                    if tr is not None:
                        e = dict(e)
                        e["enter_offset"] = round(tr + float(e.get("enter_offset") or 0), 3)
                els.append(e)
            lines_rel.append({
                "id": lt["id"],
                "start": round(lt["start"] - st["start"], 3),
                "elements": els,
            })

        scene_data = {
            "scene": {"id": st["id"]},
            "duration": st["dur"],
            "lines": lines_rel,
            "footage": (scene_meta.get(st["id"]) or {}).get("footage") or {},
            "transition": (scene_meta.get(st["id"]) or {}).get("transition") or {},
        }
        scene_html = SCENE_TMPL.format(
            scene_id=st["id"],
            dur=st["dur"],
            footage_html=build_footage_html(st["id"], st["dur"]),
            scene_data=_embed_safe(json.dumps(scene_data, ensure_ascii=False)),
        )
        fp = comp_dir / f"{st['id']}.html"
        fp.write_text(scene_html, encoding="utf-8")
        scene_files.append(str(fp))

    audio_tags = []
    if bake.get("narration"):
        audio_tags.append(
            f'  <audio id="vo-master" src="assets/audio/narration_master.wav" '
            f'data-start="0" data-duration="{timing["total"]}" data-track-index="10" data-volume="1.0"></audio>')
    if bake.get("bgm"):
        audio_tags.append(
            f'  <audio id="bgm" src="assets/audio/bgm_master.mp3" '
            f'data-start="0" data-duration="{timing["total"]}" data-track-index="11" data-volume="1.0"></audio>')
    if bake.get("sfx"):
        audio_tags.append(
            f'  <audio id="sfx" src="assets/audio/sfx_master.wav" '
            f'data-start="0" data-duration="{timing["total"]}" data-track-index="12" data-volume="0.9"></audio>')

    # 章节（HUD 顶栏指示 + 进度轨刻痕）
    total = timing["total"]
    scene_start = {s["id"]: s["start"] for s in timing["scenes"]}
    chapters = []
    for ch in (episode.get("chapters") or []):
        st = scene_start.get(ch.get("scene"))
        if st is None:
            continue
        chapters.append({"title": ch.get("title", ""), "start": round(st, 3)})
    if not chapters:
        chapters = [{"title": episode.get("title", ""), "start": 0.0}]
    ticks = []
    for ch in chapters[1:]:
        pct = max(0.0, min(100.0, ch["start"] / total * 100.0 if total else 0.0))
        ticks.append(f'    <i class="hud-tick" style="left:{pct:.3f}%"></i>')

    host_data = {
        "subs": timing["subs"],
        "total": total,
        "bgm": bool(bake.get("bgm")),
        "chapters": chapters,
    }

    brand = episode.get("hud") or {}
    html = HOST_TMPL.format(
        title=episode.get("title", "console-remake"),
        total=total,
        brand_en=brand.get("brand_en", "AGENT HARNESS"),
        brand_cn=brand.get("brand_cn", "智能体运行框架"),
        n_ch=f"{len(chapters):02d}",
        ch0=chapters[0]["title"],
        ticks="\n".join(ticks),
        slots="\n".join(slots),
        audio_tags="\n".join(audio_tags),
        slot_templates="\n".join(slot_templates),
        host_data=_embed_safe(json.dumps(host_data, ensure_ascii=False)),
    )
    out = hf_dir / "index.html"
    out.write_text(html, encoding="utf-8")

    assets_dir = hf_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE_DIR / "console.css", assets_dir / "console.css")
    shutil.copy2(TEMPLATE_DIR / "console.js", assets_dir / "console.js")
    gsap_src = OMO_ROOT / "background_library" / "vox" / "gsap.min.js"
    if gsap_src.exists():
        shutil.copy2(gsap_src, assets_dir / "gsap.min.js")
    # 颗粒层（确定性噪声，固定种子 42）
    try:
        from PIL import Image as _Img
        import random as _random
        rng = _random.Random(42)
        g = _Img.new("L", (256, 256))
        g.putdata([rng.randint(98, 158) for _ in range(256 * 256)])
        g.convert("RGB").save(assets_dir / "grain.png")
    except Exception:
        pass
    return out, {"images_copied": images_copied, "images_missing": images_missing,
                 "videos_missing": videos_missing, "registry_missing": registry_missing}


def _adapt_registry_component(comp_path: Path, dur: float) -> bool:
    """registry 组件时长适配（v1）：
    实测（v0.7.109 / v0.8.40）：组件内部 timed 元素（.clip）的 data-duration 会把
    可见窗口截断在声明值上（>5s 后整幕空白），且内部 JS 读 root.dataset.duration 恒为
    undefined。装配期把组件内所有 data-duration 与 parseFloat 默认值对齐槽位时长。
    """
    t = comp_path.read_text(encoding="utf-8")
    t2 = re.sub(r'data-duration="[\d.]+"', f'data-duration="{round(dur, 3)}"', t)
    t2 = re.sub(r'(parseFloat\(root\.dataset\.duration \|\| ")[\d.]+("\))',
                rf"\g<1>{round(dur, 3)}\g<2>", t2)
    if "console-remake:duration-adapter" not in t2:
        t2 = re.sub(r"<!doctype html>",
                    "<!doctype html>\n<!-- console-remake:duration-adapter v1"
                    "（组件内部 data-duration 必须等于槽位时长，见 LESSONS） -->",
                    t2, count=1, flags=re.I)
    if t2 != t:
        comp_path.write_text(t2, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------- validate
def _check_provenance(obj: dict, where: str, errs: list):
    pv = obj.get("provenance") or {}
    if not pv.get("url") or not pv.get("license"):
        errs.append(f"provenance 缺 url/license（{where}）——真实素材必须登记出处与许可；"
                    f"自产素材填 url:\"self\" + license:\"自有素材\"")


def validate_episode(episode: dict):
    errs, warns = [], []
    seen = set()
    elem_ids = set()
    for sc in episode.get("scenes", []):
        for ln in sc.get("lines", []):
            for e in ln.get("elements", []):
                et = e.get("type")
                if et not in ELEMENT_TYPES:
                    errs.append(f"未知零件类型 {et!r}（幕 {sc['id']} 句 {ln['id']}）")
                if et == "image":
                    if not e.get("src"):
                        errs.append(f"image 零件缺 src（幕 {sc['id']} 句 {ln['id']}）")
                    _check_provenance(e, f"幕 {sc['id']} / image {e.get('id') or ln['id']}", errs)
                elif e.get("real"):
                    errs.append(f"real:true 必须用 image 零件引用真实素材，禁止 CSS 假扮"
                                f"（幕 {sc['id']} 句 {ln['id']}）")
                eid = e.get("id")
                if eid:
                    if eid in seen:
                        errs.append(f"元素 id 重复: {eid}")
                    seen.add(eid)
                    elem_ids.add(eid)
    # 箭头引用校验
    for sc in episode.get("scenes", []):
        for ln in sc.get("lines", []):
            for e in ln.get("elements", []):
                if e.get("type") == "arrow":
                    for k in ("from", "to"):
                        ref = e.get(k)
                        if ref and ref not in elem_ids:
                            errs.append(f"箭头 {k}={ref} 引用不存在（检查元素 id）")
    # footage 出处（外部来源需登记；自录可免填）
    for sc in episode.get("scenes", []):
        ft = sc.get("footage") or {}
        if ft.get("provenance") is not None:
            _check_provenance(ft, f"幕 {sc['id']} / footage", errs)
    # registry 组件幕：每集同组件最多一次；组件幕由组件接管画面（elements 会被忽略）
    reg_seen = {}
    for sc in episode.get("scenes", []):
        reg = sc.get("registry") or {}
        if not reg:
            continue
        comp = str(reg.get("component") or "").strip()
        if not comp:
            errs.append(f"registry 缺 component 名（幕 {sc['id']}）")
            continue
        if comp in reg_seen:
            errs.append(f"registry 组件 {comp} 被多幕使用（{reg_seen[comp]} / {sc['id']}）："
                        f"每集同组件最多实例化一次（timeline 键会冲突）")
        reg_seen[comp] = sc["id"]
        if any((ln.get("elements") or []) for ln in sc.get("lines", [])):
            warns.append(f"registry 幕 {sc['id']} 声明了 elements，但组件会接管画面（elements 不会渲染）；请留空")
        for sn, sdef in (reg.get("slots") or {}).items():
            sdef = sdef or {}
            if not sdef.get("img") and not sdef.get("video"):
                warns.append(f"registry 槽位 {comp}-{sn} 未提供 img/video（幕 {sc['id']}）")
            if sdef.get("provenance") is not None:
                _check_provenance(sdef, f"幕 {sc['id']} / slot {comp}-{sn}", errs)
    # 坐标 8 倍数（仅提醒）
    for sc in episode.get("scenes", []):
        for ln in sc.get("lines", []):
            for e in ln.get("elements", []):
                for k in ("x", "y", "x1", "y1", "x2", "y2"):
                    if k in e and isinstance(e[k], (int, float)) and e[k] % 8 != 0:
                        warns.append(f"坐标 {k}={e[k]} 非 8 倍数（{sc['id']}/{ln['id']}）")
    return errs, warns


def assign_ids(episode: dict) -> None:
    for sc in episode.get("scenes", []):
        i = 0
        for ln in sc.get("lines", []):
            for e in ln.get("elements", []):
                if not e.get("id"):
                    e["id"] = f"{sc['id']}-e{i}"
                i += 1


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="console-remake 装配器")
    ap.add_argument("--project", required=True, help="projects/<slug> 路径")
    ap.add_argument("--no-audio", action="store_true", help="无配音预览（用字数估算时长）")
    ap.add_argument("--scenes", default=None, help="仅装配指定幕，逗号分隔（样片用）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = (OMO_ROOT / project).resolve()
    ep_path = project / "artifacts" / "episode.json"
    if not ep_path.exists():
        emit({"ok": False, "error": f"缺少 {ep_path}（episode.json 创作契约）"})
        sys.exit(2)

    episode = json.loads(ep_path.read_text(encoding="utf-8"))
    assign_ids(episode)
    errs, warns = validate_episode(episode)
    if errs:
        emit({"ok": False, "errors": errs, "warnings": warns})
        sys.exit(2)

    tts = {}
    tts_path = project / "artifacts" / "tts_results.json"
    if tts_path.exists():
        tts_raw = json.loads(tts_path.read_text(encoding="utf-8"))
        tts = {r["id"]: r["dur"] for r in tts_raw.get("lines", tts_raw if isinstance(tts_raw, list) else [])}

    use_est = args.no_audio or not tts
    timing = compute_timing(episode, tts, use_est=use_est)

    subset = [s.strip() for s in args.scenes.split(",")] if args.scenes else None
    if subset:
        keep = set(subset)
        timing["scenes"] = [s for s in timing["scenes"] if s["id"] in keep]
        timing["lines"] = [lt for lt in timing["lines"] if lt["scene"] in keep]
        if timing["scenes"]:
            offset = timing["scenes"][0]["start"]
            for s in timing["scenes"]:
                s["start"] = round(s["start"] - offset, 3)
                s["end"] = round(s["end"] - offset, 3)
            for lt in timing["lines"]:
                lt["start"] = round(lt["start"] - offset, 3)
                lt["end"] = round(lt["end"] - offset, 3)
            # 字幕按子集句重建
            subs_on = bool(episode.get("subtitles", True))
            line_meta = {}
            for sc in episode["scenes"]:
                for ln in sc["lines"]:
                    line_meta[ln["id"]] = ln
            subs = []
            for lt in timing["lines"]:
                ln = line_meta.get(lt["id"], {})
                if subs_on and ln.get("sub", True):
                    subs.append({"start": round(max(0.0, lt["start"] - 0.05), 3),
                                 "end": round(lt["end"] + 0.12, 3), "text": ln["text"]})
            timing["subs"] = subs
            timing["total"] = round(timing["scenes"][-1]["end"] + 2.0, 3)
            # 子集预览：把尾 2s 并入最后一幕，避免 lint 报"幕尾空档"
            if timing["scenes"]:
                last = timing["scenes"][-1]
                last["dur"] = round(last["dur"] + 2.0, 3)
                last["end"] = round(last["end"] + 2.0, 3)

    bake = {"narration": None, "bgm": None, "sfx": None}
    if not args.no_audio and tts:
        bake = bake_audio(project, episode, timing)
        bake["sfx"] = bake_sfx(project, episode, timing)

    out, asset_info = build_html(project, episode, timing, bake, scenes_subset=subset)

    timing_path = project / "artifacts" / "timings.json"
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")

    warns_all = list(warns)
    if asset_info.get("images_missing"):
        warns_all.append(f"缺少真实图片素材（assets/images/）: {', '.join(asset_info['images_missing'])}")
    if asset_info.get("videos_missing"):
        warns_all.append(f"缺少素材视频（assets/footage/）: {', '.join(asset_info['videos_missing'])}")
    if asset_info.get("registry_missing"):
        warns_all.append(
            "registry 组件未安装（先 npx hyperframes add <name> --dir <项目>/hyperframes）: "
            + ", ".join(asset_info["registry_missing"]))

    result = {"ok": True, "index_html": str(out), "timings": str(timing_path),
              "total": timing["total"], "scenes": len(timing["scenes"]),
              "lines": len(timing["lines"]), "warnings": warns_all,
              "assets": asset_info,
              "audio": {"narration": bake.get("narration"), "bgm": bake.get("bgm")}}
    emit(result)
    print(f">> compose 完成: {timing['total']:.1f}s / {len(timing['scenes'])} 幕 / {len(timing['lines'])} 句", flush=True)


if __name__ == "__main__":
    main()
