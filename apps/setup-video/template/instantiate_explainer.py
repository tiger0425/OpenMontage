#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup-video 原理特辑模板实例化生成器 v3（全新架构：单卡常驻 + word 级精确高亮）。

v3 重写（2026-08-29 用户定：不要修补，推倒重来；核心诉求=文本卡片与口播内容精确配合）：
  - 每幕【一张常驻信息卡】，位置固定，内容全部静态渲染（无堆叠/无轮换/无残影/无空卡）
  - 卡内每个数字/知识点绑定触发词（episode.highlights），用 whisper 字级时间戳（word_ts.json）
    精确对齐——口播念到该词瞬间，卡内对应元素金色高亮弹出
  - 高亮节奏：当前讲的最亮（opacity 1 + 金色），已讲过的回落（opacity 0.7），未讲的暗显（0.25）

用法:
  python apps/setup-video/template/instantiate_explainer.py <episode.json> <assets_dir> <out_index.html> [--meta out_meta.json]
  （可选 --word-ts <word_ts.json>；缺省读 <episode 同目录>/word_ts.json；无则按字数比例回退）
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"

LEAD_IN = 0.30
GAP = 0.30
TAIL = {"s1": 0.80, "s2": 0.90, "s3": 0.90, "s4": 0.90, "s5": 0.90, "s6": 5.00}

BG = "#0a0e1a"
GOLD = "#ffd60a"
RED = "#ff3b30"
BLUE = "#0058a8"


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


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hl_time(word_ts: list, narration: str, trigger: str, speech_dur: float, fallback_ratio: float):
    """触发词 → 高亮时刻（秒）。whisper 转写文本优先，找不到按 narration 字符比例回退。"""
    if word_ts:
        wt_text = "".join(w["w"] for w in word_ts)
        idx = wt_text.find(trigger)
        if idx >= 0:
            char_acc = 0
            for w in word_ts:
                if char_acc >= idx:
                    return w["t"]
                char_acc += len(w["w"])
            return word_ts[-1]["t"]
    if fallback_ratio > 0:
        return round(fallback_ratio * speech_dur, 2)
    return None


def build(episode: dict, assets: Path, word_ts: dict) -> tuple[str, dict]:
    durs = {}
    for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        wav = assets / f"{k}.wav"
        d = ffprobe_dur(wav) if wav.exists() else None
        if d is None:
            d = round(len(episode["narration"].get(k, "")) / 5.0 + 0.8, 2)
        durs[k] = round(d, 2)

    windows = {k: round(durs[k] + TAIL[k], 2) for k in durs}
    keys = ["s1", "s2", "s3", "s4", "s5", "s6"]
    starts, t = {}, LEAD_IN
    for k in keys:
        starts[k] = round(t, 2)
        t = round(t + windows[k] + GAP, 2)
    total = round(starts["s6"] + windows["s6"], 2)

    v = episode["video"]
    scenes = episode["scenes"]
    cc = episode.get("cheatcard", {})
    nar = episode["narration"]
    hls = episode.get("highlights", {})

    # 素材存在性
    for slug in sorted({s for sc in scenes.values() for s in sc.get("bg", [])}):
        if not (assets / f"bg_{slug}.mp4").exists():
            print(f"[error] 缺素材 bg_{slug}.mp4（先跑 prepare_explainer_assets）", file=sys.stderr)
            sys.exit(2)

    H = []
    A = H.append
    A(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080, height=1920">
<title>{esc(v.get("title", ""))} — 原理特辑</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face {{ font-family: "Microsoft YaHei"; src: local("Microsoft YaHei"); }}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:{BG}}}
body{{font-family:"Microsoft YaHei",sans-serif}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:{BG}}}
.clip{{position:absolute}}
.hard{{text-shadow:-3px -3px 0 #000,3px -3px 0 #000,-3px 3px 0 #000,3px 3px 0 #000,0 5px 14px rgba(0,0,0,0.9)}}
.pill{{display:inline-block;background:{RED};color:#fff;font-size:28px;font-weight:900;padding:12px 30px;border-radius:100px;letter-spacing:3px;box-shadow:0 6px 18px rgba(0,0,0,0.45)}}
.pill-dark{{display:inline-block;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.28);color:#fff;font-size:28px;font-weight:800;padding:12px 26px;border-radius:100px;letter-spacing:2px}}
.pill-gold{{display:inline-block;background:rgba(10,14,26,0.9);border:2px solid {GOLD};color:{GOLD};font-size:30px;font-weight:900;padding:12px 30px;border-radius:100px;letter-spacing:3px}}
.tag{{position:absolute;top:140px;left:0;right:0;text-align:center}}
.stat{{flex:1;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.22);border-radius:24px;padding:26px 18px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.4)}}
.stat .k{{font-size:26px;color:#a8b2c7;font-weight:700;letter-spacing:2px}}
.stat .v{{font-size:120px;font-weight:900;color:{RED};line-height:1.05;margin-top:6px}}
.stat .u{{font-size:30px;color:#fff;font-weight:700;margin-top:4px}}
.info{{position:absolute;left:70px;width:940px;background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.22);border-radius:24px;padding:30px 36px;box-shadow:0 12px 34px rgba(0,0,0,0.45)}}
.hl{{opacity:0.25;transition:opacity 0.3s}}
.hl.on{{opacity:1 !important}}
.hl .v{{font-size:44px;font-weight:900;color:#fff}}
.hl .lab{{font-size:28px;color:#a8b2c7;font-weight:700;letter-spacing:2px}}
.evidence{{background:rgba(10,14,26,0.92);border:2px solid rgba(255,255,255,0.2);border-radius:22px;overflow:hidden;box-shadow:0 14px 40px rgba(0,0,0,0.5)}}
.evidence img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.evidence .evtag{{position:absolute;bottom:18px;right:18px;background:{RED};color:#fff;font-size:24px;font-weight:900;padding:8px 18px;border-radius:100px;letter-spacing:2px;z-index:3}}
.wm{{position:absolute;right:36px;bottom:30px;background:rgba(10,14,26,0.72);border:1px solid rgba(255,255,255,0.2);color:rgba(255,255,255,0.92);font-size:24px;font-weight:800;padding:10px 20px;border-radius:100px;letter-spacing:2px}}
.cheatcard{{position:absolute;top:215px;left:60px;width:960px;background:#fff;border-radius:30px;padding:54px 50px 46px;box-shadow:0 24px 70px rgba(0,0,0,0.65)}}
.cheatcard h1{{font-size:58px;font-weight:900;color:{BG};text-align:center;letter-spacing:6px;margin-bottom:40px}}
.sec{{margin-bottom:34px}}
.sec .sh{{font-size:42px;font-weight:900;color:{RED};letter-spacing:2px;margin-bottom:14px}}
.sec .sr{{font-size:34px;font-weight:700;color:#3a4150;line-height:1.8;border-left:8px solid {GOLD};padding-left:22px;margin-bottom:12px}}
.ccfoot{{text-align:center;font-size:34px;font-weight:900;color:{BLUE};letter-spacing:2px;margin-top:26px}}
.credit{{position:absolute;bottom:60px;left:0;right:0;text-align:center;color:#a8b2c7;font-size:26px;font-weight:700;letter-spacing:1px}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="1920" data-duration="{f2(total)}">

  <div id="bg-shade" class="clip" data-start="0" data-duration="{f2(total)}" data-track-index="2" style="width:1080px;height:1920px;background:radial-gradient(ellipse at 50% 40%,rgba(10,14,26,0.28) 0%,rgba(10,14,26,0.6) 55%,rgba(10,14,26,0.9) 100%);"></div>''')

    # 背景分段
    for k in keys:
        sc = scenes[k]
        slugs = sc.get("bg", [])
        split = sc.get("bg_split") or [1.0 / len(slugs)] * len(slugs)
        seg_abs = [starts[k]]
        t_acc = starts[k]
        for idx, ratio in enumerate(split):
            dur = windows[k] * ratio
            if idx == len(slugs) - 1:
                dur += GAP
            t_acc += dur
            seg_abs.append(t_acc)
        for idx, slug in enumerate(slugs):
            s_disp = round(seg_abs[idx], 2)
            e_disp = round(seg_abs[idx + 1], 2)
            d_disp = round(e_disp - s_disp, 2)
            if sc.get("bg_mode") == "drive_clips_mix":
                src = f"assets/drive_{slug}.mp4"
                style = "width:1080px;height:1920px;object-fit:cover;"
            else:
                src = f"assets/bg_{slug}.mp4"
                style = "width:1080px;height:1920px;object-fit:cover;filter:blur(24px) brightness(0.55) saturate(0.8);"
            A(f'''  <video id="bg-{k}-{idx}" class="clip" src="{src}" data-start="{f2(s_disp)}" data-duration="{f2(d_disp)}" data-track-index="0" muted playsinline loop style="{style}"></video>''')

    A(f'''
  <audio id="bgm" class="clip" src="assets/bgm.mp3" data-start="0" data-duration="{f2(total)}" data-track-index="5" data-volume="0.22"></audio>''')
    for k in keys:
        A(f'  <audio id="audio-{k}" class="clip" src="assets/{k}.wav" data-start="{f2(starts[k])}" data-duration="{f2(durs[k] + 0.3)}" data-track-index="6" data-volume="1"></audio>')
    A(f'''  <div id="watermark" class="clip wm" data-start="0" data-duration="{f2(total)}" data-track-index="7">调校原理 · 第 1 期</div>''')

    # ================= SCENE 1：金句 + 离地对比卡 =================
    st = starts["s1"]
    A(f'''
  <!-- SCENE 1 ({f2(st)} - {f2(st + windows["s1"])}) -->
  <section id="s1" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s1"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s1-game" class="pill">Assetto Corsa RALLY</span><span id="s1-sub" class="pill-dark">调校原理特辑 · 第 1 期</span></div>
    <div id="s1-hook" class="hard" style="position:absolute;top:560px;left:0;right:0;text-align:center;font-size:76px;font-weight:900;color:{GOLD};letter-spacing:8px;opacity:0;">看两个数就懂调校逻辑</div>
    <div id="s1-card" class="info" style="top:980px;height:560px;opacity:0;">
      <div style="display:flex;gap:26px;margin-top:10px;">
        <div class="stat hl" id="s1-v1"><div class="k">标致 208 · 威尔士碎石</div><div class="v">13 cm</div><div class="u">离地 · 防刮底</div></div>
        <div class="stat hl" id="s1-v2"><div class="k">标致 208 · 阿尔萨斯柏油</div><div class="v">贴地</div><div class="u">离地 · 压到最低</div></div>
      </div>
      <div class="hard" style="text-align:center;font-size:48px;font-weight:900;color:#fff;margin-top:46px;letter-spacing:3px;">同一台车 · 两套相反参数</div>
    </div>
  </section>''')

    # ================= SCENE 2：碎石卡 + 柏油卡 + 冰雪卡（说到谁谁亮）================
    st = starts["s2"]
    def mini_rows(items, gold):
        # 数字统一金色（用户反馈：碎石卡原为黑字看不清）；标题色由调用方/卡头控制
        return "\n".join(
            f'''        <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 2px;border-bottom:1px solid rgba(255,255,255,0.1);">
          <span style="font-size:27px;color:#a8b2c7;font-weight:800;width:140px;">{name}</span>
          <span style="font-size:32px;font-weight:900;color:{GOLD};text-align:right;white-space:nowrap;">{val}</span>
        </div>'''
            for name, val in items)
    g_rows = mini_rows([("悬挂弹簧", "41200 N/m"), ("防倾杆", "6200 / 15200"), ("胎压", "27 / 31 psi"), ("外倾", "-1.7° / -2.8°")], False)
    t_rows = mini_rows([("悬挂弹簧", "51400 N/m"), ("防倾杆", "17100 / 21500"), ("胎压", "34 psi"), ("外倾", "-2.3° / -2.5°")], True)
    ice_rows = mini_rows([("弹簧", "85000 N/m"), ("外倾", "-3.0° / -2.2°"), ("胎压", "32 ~ 36 psi")], True)
    A(f'''
  <!-- SCENE 2 ({f2(st)} - {f2(st + windows["s2"])}) -->
  <section id="s2" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s2"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s2-tag" class="pill-gold">① 先看路 · 路况定大方向</span></div>
    <div id="s2-ev" style="position:absolute;top:220px;left:70px;width:940px;height:380px;display:flex;gap:20px;">
      <div class="evidence" style="position:static;flex:1;height:380px;"><span class="evtag">碎石 · 威尔士</span><img src="assets/ev_208-rally4-wales_shot_s2.png"></img></div>
      <div class="evidence" style="position:static;flex:1;height:380px;"><span class="evtag">柏油 · 阿尔萨斯</span><img src="assets/ev_208-rally4-alsace_shot_s2.png"></img></div>
    </div>
    <div id="s2-ev-ice" style="position:absolute;top:220px;left:70px;width:940px;height:380px;opacity:0;">
      <div class="evidence" style="position:static;width:940px;height:380px;"><span class="evtag">冰雪 · 蒙特卡洛黑冰</span><img src="assets/ev_impreza-s3-monte-carlo_shot_s4.png"></img></div>
    </div>
    <div class="hl" id="s2-title" style="position:absolute;top:600px;left:70px;width:940px;text-align:center;font-size:34px;font-weight:900;color:{GOLD};letter-spacing:2px;opacity:0.25;">同款标致 208 · 两套相反参数</div>
    <div id="s2-gcard" class="hl info" style="top:660px;left:55px;width:470px;height:500px;border-color:rgba(255,255,255,0.15);">
      <div style="font-size:32px;font-weight:900;color:#8f9bb3;letter-spacing:2px;margin-bottom:10px;">碎石 · 威尔士</div>
{g_rows}
    </div>
    <div id="s2-tcard" class="hl info" style="top:660px;left:555px;width:470px;height:500px;border-color:rgba(255,255,255,0.15);">
      <div style="font-size:32px;font-weight:900;color:{GOLD};letter-spacing:2px;margin-bottom:10px;">柏油 · 阿尔萨斯</div>
{t_rows}
    </div>
    <div id="s2-icecard" class="hl info" style="top:660px;left:160px;width:760px;height:500px;border-color:rgba(255,255,255,0.15);opacity:0;text-align:center;">
      <div style="font-size:34px;font-weight:900;color:{GOLD};letter-spacing:2px;margin-bottom:12px;">冰雪 · 蒙特卡洛（翼豹 S3）</div>
{ice_rows}
    </div>
    <div id="s2-motto" class="hard" style="position:absolute;top:1220px;left:0;right:0;text-align:center;font-size:48px;font-weight:900;color:{GOLD};letter-spacing:3px;opacity:0.25;">参数不是抄来的<br>是从路况推出来的</div>
  </section>''')

    # ================= SCENE 3：悬挂三块卡 =================
    st = starts["s3"]
    blocks3 = [
        ("s3-a", "弹簧 · 吸颠簸", "碎石 41200 偏软，颠簸被弹簧吃掉；太软刮底失控 → 软中取平衡"),
        ("s3-b", "阻尼 · 管节奏", "慢压缩吃小起伏，快压缩吃大冲击；回弹低 → 压缩后快速回位贴地"),
        ("s3-c", "防倾杆 · 管左右", "软 → 左右轮独立行程，碎石接地好；硬 → 侧倾小。前驱后硬 · 四驱前硬"),
    ]
    blocks3_html = "\n".join(
        f'''      <div id="{cid}" class="hl" style="padding:20px 26px;margin-bottom:16px;border:2px solid rgba(255,255,255,0.14);border-radius:18px;background:rgba(255,255,255,0.04);">
        <div style="font-size:38px;font-weight:900;color:{GOLD};letter-spacing:2px;">{name}</div>
        <div style="font-size:30px;color:#e6ecf7;font-weight:700;margin-top:8px;line-height:1.4;">{desc}</div>
      </div>'''
        for cid, name, desc in blocks3)
    A(f'''
  <!-- SCENE 3 ({f2(st)} - {f2(st + windows["s3"])}) -->
  <section id="s3" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s3"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s3-tag" class="pill-gold">② 保贴地 · 悬挂三部件</span></div>
    <div id="s3-ev" style="position:absolute;top:230px;left:70px;width:940px;height:330px;display:flex;gap:20px;">
      <div class="evidence" style="position:static;flex:1;height:330px;"><span class="evtag">悬挂页 · 208 碎石</span><img src="assets/ev_208-rally4-wales_shot_s5_1.png"></img></div>
      <div class="evidence" style="position:static;flex:1;height:330px;"><span class="evtag">防倾杆 · Delta</span><img src="assets/ev_delta-hf-integrale-wales_shot_s2.png"></img></div>
    </div>
    <div id="s3-card" class="info" style="top:600px;height:900px;">
{blocks3_html}
    </div>
  </section>''')

    # ================= SCENE 4：差速器四块卡 =================
    st = starts["s4"]
    blocks4 = [
        ("s4-a", "角度定开放", "角度大 → 开放（易转向） · 角度小 → 锁（动力直给）"),
        ("s4-b", "四驱 · 前松后紧", "Delta 威尔士 55/85 · 45/70 ｜ Fabia 39/85 ｜ i20 50/70 · 45/75"),
        ("s4-c", "前驱 · 小角度强锁", "208 威尔士 27/57 · 出弯稳"),
        ("s4-d", "预载 · 片数", "Fabia 前 150 / 后 200 Nm · 前 6 后 8 片 · 后轴动力多更爱甩尾"),
    ]
    blocks4_html = "\n".join(
        f'''      <div id="{cid}" class="hl" style="padding:18px 26px;margin-bottom:14px;border:2px solid rgba(255,255,255,0.14);border-radius:18px;background:rgba(255,255,255,0.04);">
        <div style="font-size:36px;font-weight:900;color:{GOLD};letter-spacing:2px;">{name}</div>
        <div style="font-size:29px;color:#e6ecf7;font-weight:700;margin-top:6px;line-height:1.4;">{desc}</div>
      </div>'''
        for cid, name, desc in blocks4)
    A(f'''
  <!-- SCENE 4 ({f2(st)} - {f2(st + windows["s4"])}) -->
  <section id="s4" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s4"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s4-tag" class="pill-gold">③ 找平衡 · 差速器三数</span></div>
    <div id="s4-ev" style="position:absolute;top:220px;left:70px;width:940px;height:340px;display:flex;gap:20px;">
      <div class="evidence" style="position:static;flex:1;height:340px;"><span class="evtag">四驱差速器 · Delta</span><img src="assets/ev_delta-hf-integrale-wales_shot_s3.png"></img></div>
      <div class="evidence" style="position:static;flex:1;height:340px;"><span class="evtag">前驱差速器 · 208</span><img src="assets/ev_208-rally4-wales_shot_s3.png"></img></div>
    </div>
    <div id="s4-card" class="info" style="top:600px;height:860px;">
{blocks4_html}
    </div>
  </section>''')

    # ================= SCENE 5：轮胎三块卡 =================
    st = starts["s5"]
    blocks5 = [
        ("s5-a", "胎压看热压", "碎石冷压 27 → 热压 36-37 ｜ 柏油目标热压 38"),
        ("s5-b", "外倾分路况", "碎石小（Fabia -0.8°）· 柏油大（翼豹 -3.0°）· 208 麦弗逊后轮补 -2.8°"),
        ("s5-c", "收益实证", "有玩家外倾降到 -2 / -0.5 → 单圈快 5 秒（方向参考 · 数据自试）"),
    ]
    blocks5_html = "\n".join(
        f'''      <div id="{cid}" class="hl" style="padding:20px 26px;margin-bottom:16px;border:2px solid rgba(255,255,255,0.14);border-radius:18px;background:rgba(255,255,255,0.04);">
        <div style="font-size:38px;font-weight:900;color:{GOLD};letter-spacing:2px;">{name}</div>
        <div style="font-size:30px;color:#e6ecf7;font-weight:700;margin-top:8px;line-height:1.45;">{desc}</div>
      </div>'''
        for cid, name, desc in blocks5)
    A(f'''
  <!-- SCENE 5 ({f2(st)} - {f2(st + windows["s5"])}) -->
  <section id="s5" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s5"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div class="tag"><span id="s5-tag" class="pill-gold">轮胎 · 胎压看热压</span></div>
    <div id="s5-ev" style="position:absolute;top:220px;left:70px;width:940px;height:300px;display:flex;gap:20px;">
      <div class="evidence" style="position:static;flex:1;height:300px;"><span class="evtag">轮胎页 · 208 碎石</span><img src="assets/ev_208-rally4-wales_shot_s4.png"></img></div>
      <div class="evidence" style="position:static;flex:1;height:300px;"><span class="evtag">轮胎页 · 翼豹 MC</span><img src="assets/ev_impreza-s3-monte-carlo_shot_s4.png"></img></div>
    </div>
    <div id="s5-card" class="info" style="top:560px;height:780px;">
{blocks5_html}
    </div>
  </section>''')

    # ================= SCENE 6：速查卡 =================
    st = starts["s6"]
    secs = cc.get("sections", [])
    sec_html = "\n".join(
        f'''      <div id="{episode['highlights']['s6'][i]['id'] if i < len(episode['highlights'].get('s6', [])) else 's6-sec' + str(i)}" class="sec" style="opacity:0.35;"><div class="sh">{esc(s["head"])}</div>''' +
        "".join(f'<div class="sr">{esc(r)}</div>' for r in s.get("rows", [])) +
        "</div>"
        for i, s in enumerate(secs))
    footer = esc(cc.get("footer", ""))
    credit = esc(scenes["s6"].get("footer", ""))
    A(f'''
  <!-- SCENE 6 ({f2(st)} - {f2(st + windows["s6"])}) -->
  <section id="s6" class="clip" data-start="{f2(st)}" data-duration="{f2(windows["s6"])}" data-track-index="1" style="width:1080px;height:1920px;">
    <div id="s6-card" class="cheatcard" style="opacity:0;">
      <h1>{esc(cc.get("title", ""))}</h1>
{sec_html}
      <div class="ccfoot">{footer}</div>
    </div>
    <div id="s6-credit" class="credit" style="opacity:0;">{esc(credit)}</div>
  </section>''')

    # ================= GSAP：word 级高亮 =================
    JS = []
    J = JS.append
    J("window.__timelines = window.__timelines || {};")
    J("const root=document.getElementById('root');const tl=gsap.timeline();")

    def add_hl_js(k):
        """每幕：按 highlights 触发词 → word 时间戳高亮。当前唯一高亮（opacity1+金色光晕），
        已讲过的回落到 0.55（无光晕），未讲的 0.25。"""
        items = hls.get(k, [])
        speech_dur = durs[k]
        nar_text = nar[k]
        wt = word_ts.get(k, [])
        triggered = []
        for idx, hl in enumerate(items):
            trig = hl["trigger"]
            ni = nar_text.find(trig)
            ratio = (ni / max(1, len(nar_text))) if ni >= 0 else (idx / max(1, len(items)))
            t = hl_time(wt, nar_text, trig, speech_dur, ratio)
            if t is None:
                t = speech_dur * (idx + 0.5) / max(1, len(items))
            # word_ts 时间是单段 wav 内相对时间（0 起），必须加幕起点
            t = round(starts[k] + t, 2)
            J(f"tl.fromTo('#{hl['id']}',{{opacity:0.25,scale:0.97,borderColor:'rgba(255,255,255,0.15)'}},"
              f"{{opacity:1,scale:1.06,borderColor:'rgba(255,214,10,0.95)',duration:0.35,ease:'power2.out'}},{f2(t)});")
            for prev_id in triggered:
                J(f"tl.to('#{prev_id}',{{opacity:0.55,scale:1,borderColor:'rgba(255,255,255,0.15)',duration:0.3}},{f2(t)});")
            triggered.append(hl["id"])

    # s1：金句 + 卡（离地 13cm / 贴地 高亮）
    J(f"tl.fromTo('#s1-hook',{{opacity:0,scale:0.85}},{{opacity:1,scale:1,duration:0.5,ease:'back.out(1.6)'}},{f2(starts['s1'] + 0.4)});")
    J(f"tl.fromTo('#s1-card',{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.5}},{f2(starts['s1'] + 1.2)});")
    add_hl_js("s1")
    # s2 专用编排（三阶段卡级切换，完全手写控制显示状态）：
    #   标题(头一件事) → 碎石卡亮 → 柏油卡亮 → 冰雪(标题/双卡/双图隐藏, 冰雪卡+翼豹图) → 口诀(冰雪卡隐藏)
    _s2 = starts["s2"]
    def _s2t(trig, fallback_ratio):
        t = hl_time(word_ts.get("s2", []), nar["s2"], trig, durs["s2"], fallback_ratio)
        return round(_s2 + (t if t is not None else durs["s2"] * fallback_ratio), 2)
    _t2_title = _s2t("头一件事", 0.02)
    _t2_g = _s2t("完全相反的参数", 0.12)
    _t2_t = _s2t("二SARS", 0.5)
    _t2_ice = _s2t("第三种", 0.78)
    _t2_motto = _s2t("所以记住", 0.92)
    J(f"tl.fromTo('#s2-title',{{opacity:0.25,borderColor:'rgba(255,255,255,0.15)'}},{{opacity:0.85,borderColor:'rgba(255,214,10,0.95)',duration:0.4}},{f2(_t2_title)});")
    J(f"tl.fromTo('#s2-gcard',{{opacity:0.25,borderColor:'rgba(255,255,255,0.15)'}},{{opacity:1,borderColor:'rgba(255,214,10,0.95)',duration:0.4,ease:'power2.out'}},{f2(_t2_g)});")
    J(f"tl.fromTo('#s2-tcard',{{opacity:0.25,borderColor:'rgba(255,255,255,0.15)'}},{{opacity:1,borderColor:'rgba(255,214,10,0.95)',duration:0.4,ease:'power2.out'}},{f2(_t2_t)});")
    J(f"tl.to('#s2-gcard',{{opacity:0.55,borderColor:'rgba(255,255,255,0.15)',duration:0.3}},{f2(_t2_t)});")
    J(f"tl.to('#s2-title',{{opacity:0.55,borderColor:'rgba(255,255,255,0.15)',duration:0.3}},{f2(_t2_t)});")
    # 冰雪段：隐藏标题+双卡+双图 → 冰雪卡+翼豹图
    J(f"tl.to('#s2-title',{{opacity:0,duration:0.3}},{f2(_t2_ice)});")
    J(f"tl.to('#s2-gcard',{{opacity:0,duration:0.3}},{f2(_t2_ice)});")
    J(f"tl.to('#s2-tcard',{{opacity:0,duration:0.3}},{f2(_t2_ice)});")
    J(f"tl.to('#s2-ev',{{opacity:0,duration:0.3}},{f2(_t2_ice)});")
    J(f"tl.fromTo('#s2-ev-ice',{{opacity:0}},{{opacity:1,duration:0.35}},{f2(_t2_ice)});")
    J(f"tl.fromTo('#s2-icecard',{{opacity:0,scale:0.97,borderColor:'rgba(255,255,255,0.15)'}},{{opacity:1,scale:1.06,borderColor:'rgba(255,214,10,0.95)',duration:0.4,ease:'power2.out'}},{f2(_t2_ice + 0.05)});")
    # 口诀段：冰雪卡/翼豹图完全隐藏（不回弹），motto 高亮
    J(f"tl.to('#s2-icecard',{{opacity:0,duration:0.3}},{f2(_t2_motto)});")
    J(f"tl.to('#s2-ev-ice',{{opacity:0,duration:0.3}},{f2(_t2_motto)});")
    J(f"tl.fromTo('#s2-motto',{{opacity:0.25,scale:0.97,borderColor:'rgba(255,255,255,0.15)'}},{{opacity:1,scale:1.06,borderColor:'rgba(255,214,10,0.95)',duration:0.4,ease:'power2.out'}},{f2(_t2_motto)});")
    # s3
    add_hl_js("s3")
    J(f"tl.fromTo('#s3-card',{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.5}},{f2(starts['s3'] + 0.6)});")
    # s4
    add_hl_js("s4")
    J(f"tl.fromTo('#s4-card',{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.5}},{f2(starts['s4'] + 0.6)});")
    # s5
    add_hl_js("s5")
    J(f"tl.fromTo('#s5-card',{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.5}},{f2(starts['s5'] + 0.6)});")
    # s6：整卡 + 三节高亮
    J(f"tl.fromTo('#s6-card',{{opacity:0,scale:0.9}},{{opacity:1,scale:1,duration:0.6,ease:'back.out(1.4)'}},{f2(starts['s6'] + 0.4)});")
    add_hl_js("s6")
    J(f"tl.fromTo('#s6-credit',{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.5}},{f2(starts['s6'] + durs['s6'] * 0.8)});")

    A(f'''
<script>
{chr(10).join(JS)}
window.__timelines["main"] = tl;
</script>
</body>
</html>''')

    meta = {
        "composition_id": "main",
        "duration": total,
        "windows": windows,
        "starts": starts,
        "durs": durs,
        "narration_chars": {k: len(nar[k]) for k in keys},
        "title": v.get("title", ""),
        "cover_s1": round(starts["s1"] + min(4.0, windows["s1"] * 0.6), 2),
        "cover_s6": round(starts["s6"] + 2.5, 2),
        "qa_frames": {k: round(starts[k] + windows[k] * 0.5, 2) for k in keys},
    }
    return "\n".join(H), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("assets")
    ap.add_argument("out_index")
    ap.add_argument("--meta", default=None)
    ap.add_argument("--word-ts", default=None)
    args = ap.parse_args()
    ep = json.loads(Path(args.episode).read_text(encoding="utf-8"))
    wt_path = Path(args.word_ts) if args.word_ts else Path(args.episode).parent / "word_ts.json"
    word_ts = json.loads(wt_path.read_text(encoding="utf-8")) if wt_path.exists() else {}
    html, meta = build(ep, Path(args.assets), word_ts)
    Path(args.out_index).write_text(html, encoding="utf-8")
    if args.meta:
        Path(args.meta).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
