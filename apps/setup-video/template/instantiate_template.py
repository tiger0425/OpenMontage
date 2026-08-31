#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup-video 模板实例化生成器。

用法:
  python apps/setup-video/template/instantiate_template.py <episode.json> <assets_dir> <out_index.html> [--meta out_meta.json]

读 episode.json + ffprobe 实测 assets/s1..s6.wav 时长 → 输出完整 HyperFrames index.html。
幕边界由实测配音时长驱动（决策 D6）：总长硬闸 58-65s 由调用方（bin/setup_video.py）在脚本阶段保证，
本生成器只负责按实测值精确编排。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"

# 编排常量（秒）——v0.3（2026-08-28 中改）：s6 定格尾垫 1.6→4.2（给观众截图时间）
LEAD_IN = 0.20          # 首幕起播前静默
GAP = 0.25              # 幕间呼吸垫
TAIL = {"s1": 0.80, "s2": 0.90, "s3": 0.90, "s4": 0.90, "s5": 0.90, "s6": 4.20}
S5_FIRST_FADE = 1.50    # s5 第一张配置图切走的时刻（幕内相对）
S5_TAIL_HOLD = 1.20     # 最后一张配置图的停留


def ffprobe_dur(p: Path):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(p)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=60)
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return None


def f2(x):
    return f"{x:.2f}"


def parse_countup(text: str):
    """'13650'→int / '68/85'→双int / '32.0'→1位小数 / '-2.7°'→负小数+后缀。解析失败返回 None（静态数字）。"""
    t = text.strip()
    m = re.fullmatch(r"(-?\d+\.?\d*)", t)
    if m:
        v = m.group(1)
        if "." in v:
            return {"targets": [float(v)], "decs": [1], "suffix": "", "join": "direct"}
        return {"targets": [int(v)], "decs": [0], "suffix": "", "join": "direct"}
    m = re.fullmatch(r"(-?\d+)\s*/\s*(-?\d+)", t)
    if m:
        return {"targets": [int(m.group(1)), int(m.group(2))], "decs": [0, 0],
                "suffix": "", "join": "slash"}
    m = re.fullmatch(r"(-?\d+\.?\d*)(°|%)", t)
    if m:
        v = m.group(1)
        dec = 1 if "." in v else 0
        return {"targets": [float(v)], "decs": [dec], "suffix": m.group(2), "join": "direct"}
    return None


def countup_js(sel: str, cu: dict, at: float):
    """生成一行 countUp(...) 调用。join=direct 时单值+后缀；slash 时 a/b 复合。"""
    tg = ", ".join(repr(float(x)) if isinstance(x, float) else str(x) for x in cu["targets"])
    decs = ", ".join(str(d) for d in cu["decs"])
    if cu["join"] == "slash":
        fmt = (f"p => p.p0.toFixed({cu['decs'][0]}) + '/' + p.p1.toFixed({cu['decs'][1]})")
    else:
        fmt = (f"p => p.p0.toFixed({cu['decs'][0]}) + {cu['suffix']!r}")
    return f"countUp({sel!r}, {f2(at)}, 1.0, {fmt}, [{tg}]);  /* decs=[{decs}] */"


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stat_value_html(v) -> tuple[str, int]:
    """数值卡显示：长复合值（如 '64/70 · 45/75'、'-2.5°/-2.7°'、'50.0/70.0'）自动分行 + 自适应字号，
    防 132px 大字溢出卡片/右缘（v0.3 修正 QA F2-F5）。返回 (已转义 HTML 含 <br>, 字号 px)。"""
    s = str(v or "")
    if len(s) > 8:
        for sep in (" · ", "/"):
            if sep in s:
                head, _, tail = s.partition(sep)
                return f"{esc(head)}<br>{esc(sep.strip())}{esc(tail)}", 84
    n = len(s)
    return esc(s), (132 if n <= 6 else (104 if n <= 8 else 88))


def chip_cat(label: str) -> str:
    """'第一招 · 防倾杆 AXLES' → '防倾杆'（取末段的第一个词）。无 · 时取整个 label 的首词。"""
    last = (label or "").split("·")[-1].strip()
    return last.split()[0] if last.split() else last


def build(episode: dict, assets: Path) -> tuple[str, dict]:
    # ---- 实测配音时长（缺失则按字数估算 3.4 字/秒）----
    durs, missing = {}, []
    for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        wav = assets / f"{k}.wav"
        d = ffprobe_dur(wav) if wav.exists() else None
        if d is None:
            est = round(len(episode["narration"].get(k, "")) / 3.4 + 0.8, 2)
            missing.append(f"{k}(估{est})")
            d = est
        durs[k] = round(d, 2)
    if missing:
        print(f"[warn] 缺实测时长，按估算: {', '.join(missing)}", file=sys.stderr)

    # ---- 幕边界 ----
    windows = {k: round(durs[k] + TAIL[k], 2) for k in durs}
    keys = ["s1", "s2", "s3", "s4", "s5", "s6"]
    starts, t = {}, LEAD_IN
    for k in keys:
        starts[k] = round(t, 2)
        t = round(t + windows[k] + GAP, 2)
    total = round(starts["s6"] + windows["s6"], 2)

    # ---- s5 内部交叉切换时刻 ----
    s5 = starts["s5"]
    w5 = windows["s5"]
    step = (w5 - S5_FIRST_FADE - S5_TAIL_HOLD) / 3.0
    fade = [round(s5 + S5_FIRST_FADE + i * step, 2) for i in range(3)]  # v2/v3/v4 出现时刻

    v = episode["video"]
    pts = episode["points"]
    flash = episode["flash"]
    chips = episode["chips"]
    table = episode["table"]
    nar = episode["narration"]
    hook = v.get("hook", "")                    # v0.3: s1 收益钩子大字
    promise = v.get("promise", "全参数片尾定格 · 长按保存")  # v0.3: s1-s5 提醒条（可覆盖；避开违禁词"最"）

    # ---- 片段化 HTML ----
    H = []
    A = H.append
    A(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080, height=1920">
<title>setup-video — {esc(v.get("title", ""))}</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face {{ font-family: "Microsoft YaHei"; src: local("Microsoft YaHei"); }}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#0a0e1a}}
body{{font-family:"Microsoft YaHei",sans-serif}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0a0e1a}}
.clip{{position:absolute}}
.stroke{{text-shadow:0 0 10px rgba(0,0,0,0.9),0 2px 6px rgba(0,0,0,0.85),0 0 30px rgba(0,0,0,0.55)}}
.hard{{text-shadow:-3px -3px 0 #000,3px -3px 0 #000,-3px 3px 0 #000,3px 3px 0 #000,0 5px 14px rgba(0,0,0,0.9)}}
.block{{display:block}}
.pill{{display:inline-block;background:#ff3b30;color:#fff;font-size:28px;font-weight:900;padding:12px 30px;border-radius:100px;letter-spacing:3px;box-shadow:0 6px 18px rgba(0,0,0,0.45)}}
.pill-dark{{display:inline-block;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.28);color:#fff;font-size:28px;font-weight:800;padding:12px 26px;border-radius:100px;letter-spacing:2px}}
.tag{{position:absolute;top:150px;left:0;right:0;text-align:center}}
.stat{{flex:1;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.22);border-radius:24px;padding:26px 18px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.4)}}
.stat .k{{font-size:26px;color:#a8b2c7;font-weight:700;letter-spacing:2px}}
.stat .v{{font-size:132px;font-weight:900;color:#ff3b30;line-height:1.05;margin-top:6px}}
.stat .u{{font-size:30px;color:#fff;font-weight:700;margin-top:4px}}
.renhua{{position:absolute;left:0;right:0;text-align:center;font-size:42px;font-weight:900;color:#ffd166}}
.renhua-chip{{display:inline-block;background:rgba(10,14,26,0.88);border:2px solid #ffd60a;color:#ffd60a;font-size:36px;font-weight:900;padding:14px 30px;border-radius:100px;letter-spacing:2px;white-space:nowrap}}
.promise{{display:inline-block;background:rgba(10,14,26,0.85);border:2px solid rgba(255,214,10,0.6);color:#ffd166;font-size:32px;font-weight:900;padding:14px 36px;border-radius:100px;letter-spacing:2px;box-shadow:0 8px 22px rgba(0,0,0,0.45);white-space:nowrap}}
.evidence{{position:absolute;left:70px;width:940px;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.2);border-radius:22px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,0.5)}}
.evidence img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.evidence .evtag{{position:absolute;top:18px;left:18px;background:#ff3b30;color:#fff;font-size:24px;font-weight:900;padding:8px 18px;border-radius:100px;letter-spacing:2px;z-index:3}}
.wm{{position:absolute;right:36px;bottom:30px;background:rgba(10,14,26,0.72);border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.92);font-size:24px;font-weight:800;padding:10px 20px;border-radius:100px;letter-spacing:2px}}
.row{{display:flex;justify-content:space-between;align-items:center;padding:15px 6px;border-bottom:1px solid #e8e8ee;font-size:26px;color:#3a4150;font-weight:600}}
.row:last-child{{border-bottom:none}}
.row b{{font-size:30px;font-weight:900;color:#0a0e1a}}
.row:nth-child(odd) b{{color:#ff3b30}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="1920" data-duration="{f2(total)}">

  <!-- MEDIA (root direct children) -->
  <video id="bg-video" class="clip" src="assets/bg_loop.mp4" data-start="0" data-duration="{f2(total)}" data-track-index="0" muted playsinline loop style="width:1080px;height:1920px;object-fit:cover;filter:blur(26px) brightness(0.5) saturate(0.78);"></video>''')

    # 第一幕：行驶片段优先，静止图兜底
    drv = assets / "s1_drive.mp4"
    if drv.exists():
        A(f'''  <video id="s1-video" class="clip" src="assets/s1_drive.mp4" data-start="0" data-duration="{f2(windows["s1"])}" data-track-index="4" muted playsinline style="width:1080px;height:1920px;object-fit:cover;"></video>''')
        drive_scale = True
    else:
        fb = episode.get("drive", {}).get("fallback_image") or "assets/hero_fallback.png"
        A(f'''  <img id="s1-video" class="clip" src="{esc(fb)}" data-start="0" data-duration="{f2(windows["s1"])}" data-track-index="4" style="width:1080px;height:1920px;object-fit:cover;">''')
        drive_scale = False
    A(f'''  <div id="bg-shade" class="clip" data-start="0" data-duration="{f2(total)}" data-track-index="3" style="width:1080px;height:1920px;background:radial-gradient(ellipse at 50% 42%,rgba(10,14,26,0.25) 0%,rgba(10,14,26,0.62) 55%,rgba(10,14,26,0.88) 100%);"></div>

  <audio id="bgm" class="clip" src="assets/bgm.mp3" data-start="0" data-duration="{f2(total)}" data-track-index="5" data-volume="0.22"></audio>''')
    for i, k in enumerate(keys):
        A(f'  <audio id="audio-{k}" class="clip" src="assets/{k}.wav" data-start="{f2(starts[k])}" data-duration="{f2(durs[k] + 0.3)}" data-track-index="6" data-volume="1"></audio>')
    A('''  <div id="watermark" class="clip wm" data-start="0" data-duration="''' + f2(total) + '''" data-track-index="2">调校手册 · 抄作业</div>''')

    # ---- SCENE 1 ----
    badge = v.get("badge", "")
    hook_html = f'''
    <div id="s1-hook" class="hard" style="position:absolute;top:1150px;left:0;right:0;text-align:center;font-size:64px;font-weight:900;color:#ffd60a;letter-spacing:6px;">{esc(hook)}</div>''' if hook else ""
    A(f'''
  <!-- SCENE 1: HOOK ({f2(starts["s1"])} - {f2(starts["s1"] + windows["s1"])}) -->
  <section id="s1" class="clip" data-start="{f2(starts["s1"])}" data-duration="{f2(windows["s1"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div id="s1-mask" style="position:absolute;inset:0;opacity:0;background:linear-gradient(180deg,rgba(10,14,26,0.25) 0%,rgba(10,14,26,0.04) 30%,rgba(10,14,26,0.12) 58%,rgba(10,14,26,0.9) 100%);"></div>
    <div id="s1-meta" style="position:absolute;top:150px;left:0;right:0;display:flex;justify-content:center;gap:18px;">
      <span id="s1-game" class="pill">{esc(v["game"])}</span>
      <span id="s1-badge" class="pill-dark">{esc(badge)}</span>
    </div>
    <div id="s1-logo" style="position:absolute;top:430px;left:0;right:0;display:flex;justify-content:center;">
      <img src="assets/badges/{esc(v.get("brand", ""))}.png" onerror="this.style.display='none'" style="display:block;max-height:260px;max-width:520px;height:auto;width:auto;filter:drop-shadow(0 10px 30px rgba(0,0,0,0.7));"></img>
    </div>
    <div id="s1-name" class="hard" style="position:absolute;top:700px;left:0;right:0;text-align:center;">
      <span style="display:inline-block;background:rgba(10,14,26,0.66);border-radius:100px;padding:14px 40px;font-size:72px;font-weight:900;color:{esc(v.get("team_primary") or "#d42a7d")};letter-spacing:3px;">{esc(v["title"])}</span>
    </div>{hook_html}
    <div id="s1-promise" style="position:absolute;top:1500px;left:0;right:0;text-align:center;">
      <span class="promise">⏳ {esc(promise)}</span>
    </div>
  </section>''')

    # ---- SCENES 2-4 ----
    for i, (k, pt) in enumerate(zip(["s2", "s3", "s4"], pts)):
        st = starts[k]
        cu1, cu2 = parse_countup(pt["v1"]), parse_countup(pt.get("v2", ""))
        h1, sz1 = stat_value_html(pt["v1"])
        h2, sz2 = stat_value_html(pt.get("v2", ""))
        A(f'''
  <!-- SCENE {i + 2} ({f2(st)} - {f2(st + windows[k])}) -->
  <section id="{k}" class="clip" data-start="{f2(st)}" data-duration="{f2(windows[k])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="{k}-tag" class="pill">{esc(pt["label"])}</span></div>
    <div id="{k}-stats" style="position:absolute;top:220px;left:80px;width:920px;display:flex;gap:26px;">
      <div class="stat"><div class="k">{esc(pt["k1"])}</div><div class="v" id="{k}-v1" style="font-size:{sz1}px">{h1}</div><div class="u">{esc(pt.get("u1", ""))}</div></div>
      <div class="stat"><div class="k">{esc(pt.get("k2", ""))}</div><div class="v" id="{k}-v2" style="font-size:{sz2}px">{h2}</div><div class="u">{esc(pt.get("u2", ""))}</div></div>
    </div>
    <div id="{k}-renhua" class="renhua hard" style="top:640px;">{esc(pt["renhua"])}</div>
    <div id="{k}-ev" class="evidence" style="top:730px;height:680px;">
      <span class="evtag">游戏内原图</span>
      <img src="assets/shot_{k}.png"></img>
    </div>
    <div id="{k}-promise" style="position:absolute;top:1460px;left:0;right:0;text-align:center;">
      <span class="promise">⏳ {esc(promise)}</span>
    </div>
  </section>''')

    # ---- SCENE 5 ----
    st = starts["s5"]
    imgs, labs = [], []
    for i, fl in enumerate(flash):
        op = "" if i == 0 else "opacity:0;"
        imgs.append(f'      <img id="s5-v{i + 1}" src="assets/shot_s5_{i + 1}.png" style="position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#0a0e1a;{op}"></img>')
        op2 = "" if i == 0 else "opacity:0;"
        labs.append(f'      <div id="s5-lab{i + 1}" class="evtag" style="position:absolute;top:18px;left:18px;background:#ff3b30;color:#fff;font-size:24px;font-weight:900;padding:8px 18px;border-radius:100px;z-index:3;{op2}">{esc(fl["label"])}</div>')
    chip_html = "\n".join(
        f'      <span id="s5-chip{i + 1}" class="renhua-chip hard">{esc(c)}</span>'
        for i, c in enumerate(chips))
    A(f'''
  <!-- SCENE 5: QUICK FLASH ({f2(st)} - {f2(st + windows["s5"])}) -->
  <section id="s5" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s5"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s5-tag" class="pill">其余照抄 · 别纠结</span></div>
    <div style="position:absolute;top:220px;left:90px;width:900px;height:900px;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.2);border-radius:22px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,0.5);">
{chr(10).join(imgs)}
{chr(10).join(labs)}
    </div>
    <div id="s5-renhua" style="position:absolute;top:1150px;left:30px;right:30px;display:flex;flex-wrap:wrap;justify-content:center;gap:16px;">
{chip_html}
    </div>
    <div id="s5-promise" style="position:absolute;top:1340px;left:0;right:0;text-align:center;">
      <span class="promise">⏳ {esc(promise)}</span>
    </div>
  </section>''')

    # ---- SCENE 6 ----
    st = starts["s6"]
    rows = "\n".join(f'        <div class="row"><span>{esc(r["name"])}</span><b>{esc(r["value"])}</b></div>' for r in table)
    pkg = episode.get("package", {})
    cta = esc(pkg.get("cta", "评论区晒圈速 🏁"))
    hint = esc(pkg.get("hint", "长按保存 · 抄作业就绪"))
    A(f'''
  <!-- SCENE 6: FREEZE WHITE CARD ({f2(st)} - {f2(total)}) -->
  <section id="s6" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s6"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div id="s6-card" style="position:absolute;top:200px;left:78px;width:924px;height:1330px;background:#fff;border-radius:30px;padding:52px 48px 40px;box-shadow:0 24px 70px rgba(0,0,0,0.65);display:flex;flex-direction:column;">
      <div style="text-align:center;">
        <div id="s6-title" style="font-size:56px;font-weight:900;color:#0a0e1a;letter-spacing:2px;">全套参数 · 暂停抄作业</div>
        <div id="s6-sub" style="font-size:26px;font-weight:700;color:#ff3b30;margin-top:10px;letter-spacing:1px;">{esc(v["game"])} · {esc(v["title"])}{(" · " + esc(v["track"])) if v.get("track") else ""}</div>
      </div>
      <div id="s6-rows" style="margin-top:30px;flex:1;display:flex;flex-direction:column;justify-content:center;gap:0;">
{rows}
      </div>
      <div id="s6-cta" style="text-align:center;background:#ff3b30;color:#fff;font-size:36px;font-weight:900;padding:20px 0;border-radius:100px;letter-spacing:3px;box-shadow:0 10px 26px rgba(255,59,48,0.45);">{cta}</div>
      <div id="s6-hint" style="text-align:center;font-size:26px;font-weight:700;color:#5a6580;margin-top:18px;letter-spacing:2px;">{hint}</div>
    </div>
  </section>

</div>

<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});

/* Stat-card number count-up (seek-safe: value is a pure function of timeline time) */
function countUp(sel, at, dur, fmt, targets) {{
  const el = document.querySelector(sel);
  if (!el) return;
  const proxy = {{}};
  targets.forEach((t, i) => {{ proxy["p" + i] = 0; }});
  const write = () => {{ el.textContent = fmt(proxy); }};
  write();
  const vars = {{ duration: dur, ease: "power1.out", onUpdate: write }};
  targets.forEach((t, i) => {{ vars["p" + i] = t; }});
  tl.to(proxy, vars, at);
}}''')

    # ---- 时间线（相对定稿实例的节奏，起点全部参数化）----
    s1 = starts["s1"]
    if drive_scale:
        A(f'tl.fromTo("#s1-video", {{ scale: 1.0 }}, {{ scale: 1.08, duration: {f2(windows["s1"] - 0.3)}, ease: "power1.out" }}, {f2(s1 + 0.1)});')
    A(f'''tl.to("#s1-mask", {{ opacity: 1, duration: 0.7 }}, {f2(s1 + 0.25)});
tl.from("#s1-meta", {{ y: -30, opacity: 0, duration: 0.5, ease: "power3.out" }}, {f2(s1 + 0.55)});''')
    if hook:
        A(f'tl.from("#s1-hook", {{ scale: 0.8, opacity: 0, duration: 0.5, ease: "back.out(1.7)" }}, {f2(s1 + 0.8)});')
    A(f'''tl.from("#s1-promise", {{ y: 20, opacity: 0, duration: 0.4 }}, {f2(s1 + 1.8)});
tl.from("#s1-logo", {{ scale: 0.5, opacity: 0, duration: 0.6, ease: "back.out(1.6)" }}, {f2(s1 + 3.0)});
tl.from("#s1-name", {{ y: -40, opacity: 0, duration: 0.55, ease: "power3.out" }}, {f2(s1 + 3.3)});''')

    for k in ["s2", "s3", "s4"]:
        st = starts[k]
        A(f'''
/* ---- Scene {k} ---- */
tl.from("#{k}-tag", {{ scale: 0.7, opacity: 0, duration: 0.4, ease: "back.out(1.5)" }}, {f2(st + 0.15)});
tl.from("#{k}-stats .stat", {{ y: 60, opacity: 0, duration: 0.5, ease: "back.out(1.5)", stagger: 0.1 }}, {f2(st + 0.35)});
tl.from("#{k}-renhua", {{ y: 30, opacity: 0, duration: 0.45 }}, {f2(st + 0.8)});
tl.from("#{k}-ev", {{ y: 60, opacity: 0, duration: 0.5, ease: "power2.out" }}, {f2(st + 0.9)});
tl.from("#{k}-promise", {{ y: 20, opacity: 0, duration: 0.4 }}, {f2(st + 1.1)});''')
        for j, vid in enumerate(["v1", "v2"]):
            cu = parse_countup(episode["points"][{"s2": 0, "s3": 1, "s4": 2}[k]].get(vid, "") or "")
            if cu and cu["targets"] and cu["targets"][0] != 0:
                A(countup_js(f"#{k}-{vid}", cu, st + 0.45 + j * 0.12))

    st = starts["s5"]
    A(f'''
/* ---- Scene 5: 4 crossfades, chips pop one-by-one in sync ---- */
tl.from("#s5-tag", {{ scale: 0.7, opacity: 0, duration: 0.4, ease: "back.out(1.5)" }}, {f2(st + 0.2)});''')
    A(f'tl.from("#s5-chip1", {{ scale: 0.5, opacity: 0, duration: 0.45, ease: "back.out(1.8)" }}, {f2(st + 0.43)});')
    A(f'tl.from("#s5-promise", {{ y: 20, opacity: 0, duration: 0.4 }}, {f2(st + 0.6)});')
    for i, ft in enumerate(fade):  # v2/v3/v4
        n = i + 2
        A(f'''tl.to("#s5-v{i + 1}", {{ opacity: 0, duration: 0.35 }}, {f2(ft)});
tl.to("#s5-lab{i + 1}", {{ opacity: 0, duration: 0.25 }}, {f2(ft)});
tl.to("#s5-v{n}", {{ opacity: 1, duration: 0.35 }}, {f2(ft)});
tl.to("#s5-lab{n}", {{ opacity: 1, duration: 0.25 }}, {f2(ft)});''')
        if n <= len(chips):   # 第 4 张图（电子）无对应胶囊——定稿设计
            A(f'tl.from("#s5-chip{n}", {{ scale: 0.5, opacity: 0, duration: 0.45, ease: "back.out(1.8)" }}, {f2(ft + 0.1)});')

    st = starts["s6"]
    A(f'''
/* ---- Scene 6: freeze white card ---- */
tl.from("#s6-card", {{ scale: 0.88, y: 80, opacity: 0, duration: 0.7, ease: "back.out(1.4)" }}, {f2(st + 0.2)});
tl.from("#s6-title", {{ y: 30, opacity: 0, duration: 0.5 }}, {f2(st + 0.7)});
tl.from("#s6-sub", {{ y: 20, opacity: 0, duration: 0.4 }}, {f2(st + 0.95)});
tl.from("#s6-rows .row", {{ x: -40, opacity: 0, duration: 0.35, stagger: 0.09, ease: "power2.out" }}, {f2(st + 1.2)});
tl.from("#s6-cta", {{ scale: 0.5, opacity: 0, duration: 0.5, ease: "back.out(1.8)" }}, {f2(st + 2.15)});
tl.to("#s6-cta", {{ scale: 1.04, duration: 0.4, yoyo: true, repeat: 3, ease: "sine.inOut" }}, {f2(st + 2.75)});
tl.from("#s6-hint", {{ y: 16, opacity: 0, duration: 0.4 }}, {f2(st + 2.55)});

/* BGM fade in / out */
/* 背景遮罩：第一幕不淡化，第二幕起淡入压暗（2026-08-28 用户定） */
tl.fromTo("#bg-shade", {{ opacity: 0 }}, {{ opacity: 1, duration: 1.0, ease: "power1.out" }}, {f2(starts["s2"] - 0.4)});
/* BGM：首幕不淡入（全音量起），仅片尾淡出 */
tl.to("#bgm", {{ volume: 0, duration: 2, ease: "power1.in" }}, {f2(total - 2)});

window.__timelines["main"] = tl;
</script>
</body>
</html>''')

    meta = {
        "total": total,
        "starts": starts,
        "windows": windows,
        "narration_durs": durs,
        "s5_fades": fade,
        "qa_frames": {k: round(starts[k] + windows[k] * 0.6, 2) for k in keys},
        "cover_s6": round(starts["s6"] + 3.2, 2),
        "cover_s1": round(starts["s1"] + min(4.0, windows["s1"] - 1.0), 2),
    }
    return "\n".join(H), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("assets_dir")
    ap.add_argument("out_html")
    ap.add_argument("--meta", default=None)
    a = ap.parse_args()
    ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
    html, meta = build(ep, Path(a.assets_dir))
    out = Path(a.out_html)
    out.write_text(html, encoding="utf-8")
    if a.meta:
        Path(a.meta).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "total": meta["total"], "starts": meta["starts"],
                      "out": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
