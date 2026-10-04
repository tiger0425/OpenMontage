# -*- coding: utf-8 -*-
"""VOX Collage HyperFrames 时间线装配生成器 (generate_composition.py)

特性：
- 支持 16:9 横屏 (1920x1080) 与 9:16 竖屏 (1080x1920)
- 支持 Prompt 3/4 两种动效单位：
  * 成对片段 (Prompt 4)：两幕共用一条 H3 片段（含无缝转场），文件 assets/pair-<a><b>.mp4
  * 单幕片段 (Prompt 3)：一幕一条 H3 片段，文件 assets/gen-scene-<id>.mp4
  * 静态兜底：assets/gen-scene-<id>.png + 2% slow drift
- 成对片段的原生音轨是「纸质 ASMR」，会作为独立 <audio> 低音量铺底（旁白另轨）
- 读 WAV 精确秒数排布时间槽：slot = lead + vo + tail
- 0 帧硬切仅用于静态兜底；H3 片段自带无缝转场

合规说明（HyperFrames composition contract）：
- 根节点必须带 data-composition-id / data-width / data-height / data-duration
- 所有动效必须是「可 seek」的 GSAP paused timeline，注册到 window.__timelines["<composition-id>"]
- 严禁使用 CSS @keyframes 等不可 seek 的动画
- <video>/<audio> 必须是宿主根节点的直接子元素
- 素材引用走非点号目录 assets/（HyperFrames 静态服务不服务点号目录）
"""

import html
import shutil
from pathlib import Path

GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
ASMR_VOLUME = "0.28"
# 组与组之间按文档首选转场做「无缝纸擦除」（禁止硬切）：一层纸横扫过画面，扫过处即换幕
WIPE_SEC = 0.30            # 单侧（覆盖 / 揭开）时长
WIPE_PAPER = "#4A505C"     # 纸色：与拼贴纸底同族、略提亮，保证在深色纸上可见
WIPE_TRACK = 2             # 独立轨（不与视觉轨 1、旁白轨 10、ASMR 轨 11 冲突）


def torn_edge_clip_path(steps: int = 14, rough: float = 1.1, seed: int = 20261003) -> str:
    """生成左右两侧撕纸边的 clip-path（固定随机种子 → 每次渲染完全一致）。"""
    import random

    rnd = random.Random(seed)
    pts = []
    for i in range(steps + 1):
        pts.append(f"{rnd.uniform(0.0, rough):.2f}% {i / steps * 100:.2f}%")
    for i in range(steps, -1, -1):
        pts.append(f"{100.0 - rnd.uniform(0.0, rough):.2f}% {i / steps * 100:.2f}%")
    return "polygon(" + ", ".join(pts) + ")"


def fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None


def stage_assets(proj_dir: Path, episode_data: dict, voice_manifest: dict) -> Path:
    """把 .media 下的媒体镜像到非点号目录 assets/，供 HyperFrames 静态服务读取。"""
    proj_dir = Path(proj_dir)
    dst = proj_dir / "assets"
    dst.mkdir(parents=True, exist_ok=True)

    for s in episode_data.get("scenes", []):
        sid = s["id"]
        src_img = _first_existing([
            proj_dir / ".media" / "assets" / f"gen-scene-{sid}.png",
            proj_dir / ".media" / "dataliao" / f"scene-{sid}.png",
        ])
        if src_img:
            shutil.copy2(src_img, dst / f"gen-scene-{sid}.png")

        src_vid = proj_dir / ".media" / "video" / f"gen-scene-{sid}.mp4"
        if src_vid.exists():
            shutil.copy2(src_vid, dst / f"gen-scene-{sid}.mp4")

    # ASMR 音轨（每幕一条，来自 H3 原生纸质音轨）
    for f in (proj_dir / ".media" / "video").glob("asmr-*.m4a"):
        shutil.copy2(f, dst / f.name)

    for line in voice_manifest.get("lines", []):
        sid = line.get("frame")
        wav = proj_dir / str(line.get("wav", "")).replace("\\", "/")
        if sid and wav.exists():
            shutil.copy2(wav, dst / f"voice_{sid}.wav")

    return dst


def generate_index_html(episode_data: dict, voice_manifest: dict, out_html: Path, lead: float = 0.30, tail: float = 0.25):
    ratio = episode_data.get("ratio", "16:9")
    scenes = episode_data.get("scenes", [])
    voice_lines = {l["frame"]: l for l in voice_manifest.get("lines", [])}

    stage_assets(out_html.parent, episode_data, voice_manifest)

    if ratio == "16:9":
        vw, vh = 1920, 1080
        res_attr = 'data-resolution="1920x1080"'
    else:
        vw, vh = 1080, 1920
        res_attr = 'data-resolution="portrait"'

    proj = out_html.parent

    # 预计算每幕槽位
    slots = {}
    for s in scenes:
        vo = float(voice_lines.get(s["id"], {}).get("seconds", 3.0))
        slots[s["id"]] = lead + vo + tail

    t = 0.0
    visual_clips, audio_clips, tl_lines = [], [], []
    boundaries = []

    i = 0
    while i < len(scenes):
        s = scenes[i]
        sid = s["id"]
        dur = slots[sid]
        media_start = float(s.get("timing", {}).get("media_start_sec", 0.5))

        # 换幕点 → 记下来，稍后用「纸擦除」盖住接缝（文档禁止硬切）
        if t > 0.01:
            boundaries.append(t)

        # 单幕视频：H3 只负责逐层搭建，换幕一律由下面的「纸擦除」统一负责
        vid_p = proj / ".media" / "video" / f"gen-scene-{sid}.mp4"
        if vid_p.exists():
            clip_id = f"v{sid}"
            visual_clips.append(
                f'      <video id="{clip_id}" class="clip visual-media" src="assets/gen-scene-{sid}.mp4" '
                f'data-start="{fmt(t)}" data-duration="{fmt(dur)}" '
                f'data-media-start="{fmt(media_start)}" data-track-index="1" muted playsinline></video>'
            )
            asmr_p = proj / ".media" / "video" / f"asmr-{sid}.m4a"
            if asmr_p.exists():
                audio_clips.append(
                    f'      <audio id="asmr{sid}" class="clip" src="assets/asmr-{sid}.m4a" '
                    f'data-start="{fmt(t)}" data-duration="{fmt(dur)}" '
                    f'data-media-start="{fmt(media_start)}" '
                    f'data-track-index="11" data-volume="{ASMR_VOLUME}"></audio>'
                )
            # 接缝已由「纸擦除」覆盖，这里不再叠加淡入（避免双转场打架）
        else:
            # 静态兜底：仅 ≤1% 呼吸微动（文档 Prompt 3 要求相机完全静止）
            clip_id = f"v{sid}"
            visual_clips.append(
                f'      <img id="{clip_id}" class="clip visual-media" src="assets/gen-scene-{sid}.png" '
                f'data-start="{fmt(t)}" data-duration="{fmt(dur)}" data-track-index="1" alt="Scene {sid}" />'
            )
            tl_lines.append(
                f'tl.fromTo("#{clip_id}", {{scale:1.0}}, '
                f'{{scale:1.01, yoyo:true, repeat:1, duration:{fmt(max(0.8, dur / 2))}, ease:"sine.inOut"}}, {fmt(t)});'
            )

        vo_dur = float(voice_lines.get(sid, {}).get("seconds", 3.0))
        audio_clips.append(
            f'      <audio id="vo{sid}" class="clip" src="assets/voice_{sid}.wav" '
            f'data-start="{fmt(t + lead)}" data-duration="{fmt(vo_dur)}" '
            f'data-track-index="10" data-volume="1"></audio>'
        )
        t += dur
        i += 1

    total_duration = t

    # 纸擦除层：在每个换幕点用一层纸横扫过画面（覆盖 → 换幕 → 揭开），彻底消除硬切
    wipe_el, wipe_lines = "", []
    if boundaries:
        wipe_el = (
            f'      <div id="paperwipe" class="clip paper-wipe" data-start="0" '
            f'data-duration="{fmt(total_duration)}" data-track-index="{WIPE_TRACK}" aria-hidden="true"></div>'
        )
        last_end = -99.0
        # t=0 必须先把它推到画外——否则元素默认 xPercent:0 会整屏盖住第一幕
        wipe_lines.append('tl.set("#paperwipe", {xPercent:-100}, 0);')
        for tb in boundaries:
            t0 = max(0.0, tb - WIPE_SEC)
            if t0 < last_end + 0.15:      # 换幕过密时跳过，避免同一属性上的补间打架
                continue
            cover = tb - t0
            wipe_lines.append(f'tl.set("#paperwipe", {{xPercent:-100}}, {fmt(t0)});')
            wipe_lines.append(
                f'tl.to("#paperwipe", {{xPercent:0, duration:{fmt(cover)}, ease:"power2.inOut"}}, {fmt(t0)});'
            )
            wipe_lines.append(
                f'tl.to("#paperwipe", {{xPercent:100, duration:{fmt(WIPE_SEC)}, ease:"power2.inOut"}}, {fmt(tb)});'
            )
            last_end = tb + WIPE_SEC
        tl_lines.extend(wipe_lines)

    doc = f"""<!doctype html>
<html lang="zh-CN" {res_attr}>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={vw}, height={vh}" />
    <title>{html.escape(episode_data.get('title', 'VOX Collage Documentary'))}</title>
    <script src="{GSAP_CDN}"></script>
    <style>
      * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }}
      html, body {{
        width: {vw}px;
        height: {vh}px;
        background: #111;
        overflow: hidden;
        position: relative;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }}
      #root {{
        position: relative;
        width: {vw}px;
        height: {vh}px;
        overflow: hidden;
      }}
      .clip {{
        position: absolute;
      }}
      .visual-media {{
        top: 0;
        left: 0;
        width: {vw}px;
        height: {vh}px;
        object-fit: cover;
      }}
      /* 纸擦除转场：一层撕边纸横扫过画面，扫过处即换幕（文档首选转场，替代硬切） */
      .paper-wipe {{
        top: 0;
        left: 0;
        width: {vw}px;
        height: {vh}px;
        z-index: 50;
        pointer-events: none;
        background-color: {WIPE_PAPER};
        background-image:
          repeating-linear-gradient(0deg,
            rgba(255, 255, 255, 0.035) 0px,
            rgba(255, 255, 255, 0.035) 1px,
            rgba(0, 0, 0, 0.04) 1px,
            rgba(0, 0, 0, 0.04) 3px),
          radial-gradient(120% 90% at 50% 45%, rgba(255, 255, 255, 0.07), rgba(0, 0, 0, 0.12));
        box-shadow: 0 0 90px rgba(0, 0, 0, 0.55);
        clip-path: {torn_edge_clip_path()};
        will-change: transform;
      }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{fmt(total_duration)}" data-width="{vw}" data-height="{vh}">
      <!-- 视觉层 (Track 1) -->
{chr(10).join(visual_clips)}
{wipe_el}

      <!-- 旁白层 (Track 10) + 纸质 ASMR 层 (Track 11) -->
{chr(10).join(audio_clips)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join('      ' + line for line in tl_lines)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    print(f"[generate_composition] Assembled HyperFrames composition -> {out_html} (Total: {fmt(total_duration)}s)")
    return out_html


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 4:
        print("usage: generate_composition.py <episode.json> <voice-manifest.json> <out_index.html>")
        sys.exit(2)
    ep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    vm = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    generate_index_html(ep, vm, Path(sys.argv[3]))
