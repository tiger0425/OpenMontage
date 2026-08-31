# -*- coding: utf-8 -*-
"""ref-remake 合成模板：从 timeline.json 生成 HyperFrames index.html（V2 点缀式）。

用法（workdir 必须在 OpenMontage 根目录！路径相对根目录，否则渲染 10s 模板）：
    python apps/ref-remake/scripts/build_index.py --config projects/<slug>/artifacts/index_config.json

index_config.json 格式：
{
  "project": "projects/<slug>",
  "title": "看 4 分钟比 90% 的人更聪明",
  "output_index": "projects/<slug>/index.html",
  "rank_labels": {"s0_0": ["①", "别为赢而争辩"]},   # 可选：场景徽章+标题
  "opening_scene": "s0_0",     # 可选：开场特殊场景
  "ending_scene": "sN_0",      # 可选：结尾特殊场景
  "audio_segments": [          # 音频轨（实测段长）
    {"name": "00_open", "start_s": 0.0, "duration_s": 27.7}
  ]
}
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.getcwd())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="index_config.json 路径")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    project = cfg["project"]
    with open(os.path.join(project, "artifacts", "timeline.json"), encoding="utf-8") as f:
        data = json.load(f)
    tl = data["timeline"]
    total = data["total"]

    rank_labels = cfg.get("rank_labels", {})
    opening_scene = cfg.get("opening_scene")
    ending_scene = cfg.get("ending_scene")
    title_map = cfg.get("title_map", {})

    def scene_html(item):
        name = item["file"]
        start = item["start"]
        dur = round(item["end"] - item["start"], 2)
        if name == opening_scene:
            inner = f'''<img class="bg" src="assets/images/{name}.png" alt="" />
        <div class="opening-title" id="open-title">{cfg["title"]}</div>
        <div class="sparkle" id="spk1" style="top: 130px; left: 90px">✦</div>
        <div class="sparkle" id="spk2" style="top: 130px; right: 90px">✦</div>'''
            return name, start, dur, "opening", inner
        if name == ending_scene:
            inner = f'''<img class="bg" src="assets/images/{name}.png" alt="" />
        <div class="end-title" id="end-title">点赞 · 评论 · 订阅<br />我们下期见！</div>
        <div class="end-sparkle" id="espk1" style="top: 150px; left: 100px">✦</div>'''
            return name, start, dur, "ending", inner
        badge, title = rank_labels.get(name, ("", ""))
        if badge or title:
            # 有 rank 徽章：带徽章 + 标题，pushWithRank
            inner = f'''<img class="bg" src="assets/images/{name}.png" alt="" />
        <div class="rank-badge">{badge}</div>
        <div class="rank-title">{title}</div>'''
            return name, start, dur, "rank", inner
        # 无 rank 徽章：纯无字图 + HTML 副标题（普通 push，无黑块）
        sub = title_map.get(name, "")
        sub_div = f'\n        <div class="scene-sub">{sub}</div>' if sub else ""
        inner = f'''<img class="bg" src="assets/images/{name}.png" alt="" />{sub_div}'''
        return name, start, dur, "normal", inner

    scenes = [scene_html(item) for item in tl]

    lines = []
    lines.append('<!DOCTYPE html>')
    lines.append('<html lang="zh-CN" data-resolution="portrait">')
    lines.append('  <head>')
    lines.append('    <meta charset="UTF-8" />')
    lines.append('    <meta name="viewport" content="width=1080, height=1920" />')
    lines.append(f'    <title>{cfg["title"]}</title>')
    lines.append('    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>')
    lines.append('    <style>')
    lines.append('      * { margin: 0; padding: 0; box-sizing: border-box; }')
    lines.append('      html, body { width: 1080px; height: 1920px; overflow: hidden; background: #fcfbf7; }')
    lines.append('      @font-face { font-family: "Noto Sans SC"; src: local("Noto Sans SC"); }')
    lines.append('      @font-face { font-family: "PingFang SC"; src: local("PingFang SC"); }')
    lines.append('      @font-face { font-family: "Microsoft YaHei"; src: local("Microsoft YaHei"); }')
    lines.append('      body { font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }')
    lines.append('      .scene { position: absolute; top: 0; left: 0; width: 1080px; height: 1920px; overflow: hidden; }')
    lines.append('      #scene1 { z-index: 1; }')
    for i in range(2, len(scenes) + 1):
        lines.append(f'      #scene{i} {{ z-index: 2; opacity: 0; }}')
    lines.append('      .bg { position: absolute; top: 0; left: 0; width: 1080px; height: 1920px; object-fit: cover; }')
    lines.append('      .rank-badge { position: absolute; top: 90px; left: 60px; background: #050505; color: #f9e63c; font-weight: 900; font-size: 72px; line-height: 1; padding: 26px 40px; border-radius: 24px; box-shadow: 0 8px 0 rgba(5,5,5,0.25); }')
    lines.append('      .rank-title { position: absolute; top: 210px; left: 60px; color: #050505; font-weight: 900; font-size: 64px; line-height: 1.2; background: rgba(252,251,247,0.85); padding: 16px 32px; border-radius: 18px; display: inline-block; }')
    lines.append('      .scene-sub { position: absolute; bottom: 90px; left: 60px; right: 60px; color: #050505; font-weight: 700; font-size: 52px; line-height: 1.3; background: rgba(252,251,247,0.85); padding: 18px 32px; border-radius: 18px; display: inline-block; }')
    lines.append('      .opening-title { position: absolute; top: 240px; left: 0; width: 1080px; text-align: center; color: #050505; font-weight: 900; font-size: 96px; line-height: 1.35; letter-spacing: 6px; }')
    lines.append('      .sparkle { position: absolute; color: #ffd45a; font-size: 90px; }')
    lines.append('      .end-title { position: absolute; top: 140px; left: 0; width: 1080px; text-align: center; color: #050505; font-weight: 900; font-size: 80px; line-height: 1.4; }')
    lines.append('      .end-sparkle { position: absolute; color: #ffd45a; font-size: 90px; }')
    lines.append('    </style>')
    lines.append('  </head>')
    lines.append('  <body>')
    lines.append(f'    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1080" data-height="1920">')

    for i, (name, start, dur, kind, inner) in enumerate(scenes, 1):
        lines.append(f'      <!-- {name} {start}s-{round(start+dur,2)}s -->')
        lines.append(f'      <div id="scene{i}" class="scene" data-layout-allow-overflow>{inner}')
        lines.append('      </div>')

    # 音频轨（data-duration 向下钳制到下一段 start，避免同轨 clip 重叠触发 lint）
    lines.append('      <!-- 音频轨 -->')
    segs = cfg.get("audio_segments", [])
    for i, seg in enumerate(segs):
        start = seg["start_s"]
        dur = seg["duration_s"]
        if i + 1 < len(segs):
            nxt = segs[i + 1]["start_s"]
            if start + dur > nxt:
                dur = max(0.0, round(nxt - start, 3))
        lines.append(f'      <audio id="a{i:02d}" src="assets/audio/seg_{seg["name"]}.wav" data-start="{start}" data-duration="{dur}" data-track-index="50" data-volume="1"></audio>')

    lines.append('    </div>')
    lines.append('    <script>')
    lines.append('      window.__timelines = window.__timelines || {};')
    lines.append('      var tl = gsap.timeline({ paused: true });')
    lines.append('      var DUR = 0.4;')

    transitions = [(i + 1, item["start"]) for i, item in enumerate(tl) if item["start"] > 0]
    lines.append('      function push(oldId, newId, T) {')
    lines.append('        tl.to(oldId, { x: -1080, duration: DUR, ease: "power3.in" }, T);')
    lines.append('        tl.fromTo(newId, { x: 1080, opacity: 1 }, { x: 0, opacity: 1, duration: DUR, ease: "power3.out" }, T);')
    lines.append('        tl.set(oldId, { opacity: 0 }, T + DUR + 0.05);')
    lines.append('      }')
    lines.append('      function pushWithRank(oldId, newId, T) {')
    lines.append('        push(oldId, newId, T);')
    lines.append('        tl.fromTo(newId + " .rank-badge", { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }, T + 0.12);')
    lines.append('        tl.fromTo(newId + " .rank-title", { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, ease: "power3.out" }, T + 0.2);')
    lines.append('      }')

    if opening_scene:
        lines.append('      tl.fromTo("#open-title", { y: 80, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" }, 0.3);')
        for sid in ["spk1", "spk2"]:
            lines.append(f'      tl.fromTo("#{sid}", {{ scale: 0, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.4, ease: "back.out(2)" }}, 1.0);')

    scene_kinds = [s[3] for s in scenes]
    for i, (next_idx, T) in enumerate(transitions):
        prev_idx = i + 1
        kind = scene_kinds[next_idx - 1]
        if kind == "rank":
            lines.append(f'      pushWithRank("#scene{prev_idx}", "#scene{next_idx}", {T});')
        else:
            lines.append(f'      push("#scene{prev_idx}", "#scene{next_idx}", {T});')

    if ending_scene:
        end_idx = len(scenes)
        lines.append('      tl.fromTo("#end-title", { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, ease: "power3.out" }, ' + str(total - 8) + ');')
        for sid in ["espk1"]:
            lines.append(f'      tl.fromTo("#{sid}", {{ scale: 0, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.4, ease: "back.out(2)" }}, {total - 6});')
        lines.append('      tl.to("#scene' + str(end_idx) + '", { opacity: 0, duration: 0.8, ease: "sine.inOut" }, ' + str(total - 1.0) + ');')
        lines.append('      tl.set("#scene' + str(end_idx) + '", { visibility: "hidden" }, ' + str(round(total - 0.2, 2)) + ');')
    lines.append('      window.__timelines["main"] = tl;')
    lines.append('    </script>')
    lines.append('  </body>')
    lines.append('</html>')

    out_path = cfg["output_index"]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("written", out_path, "scenes:", len(scenes), "total:", total)


if __name__ == "__main__":
    main()
