#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOX 科技与 B 站极客口播 HyperFrames 模板生成器（apps/vox-course/template/generate_composition.py）

核心能力：
  1. 高保真音频烘焙 (bake_audio_tracks)：
     使用 ffmpeg 将旁白与物理音效（破空、键盘打字、弹窗、金币成功音、Pause点击、图章落盘）
     在精确的交互时间戳烘焙为单一的主音轨。
  2. 拟真桌面实操录屏与极客动态 UI：
     - 真实 OS 桌面 Chrome、真实 SVG 鼠标指针（移动、抓取、拖拽、点击波纹）
     - 镜头 01：Waitlist 灰度排队 vs DeepSeek 亮青色光效粒子炸开 + 100% MIT 开源
     - 镜头 02：画中画架构动画：左侧 Cache 瞬间归零+计数器狂飙飙红 vs 右侧系统指令追加+97%命中
     - 镜头 03：全屏实操录屏：鼠标抓取设计图与报错表拖入输入框，键盘快速敲击打字，Side Panel 抽屉式滑出实时渲染预览
     - 镜头 04：动态打断与 Headless：流式生成中点击 Pause 暂停并插队转向，终端跑 headless 自动化单测全部打绿勾
     - 镜头 05：性能与部署：赛博测速仪表盘指针甩至 260+ Tokens/s，显示 $0.12 成本，终端敲入命令本地启动
     - 镜头 06：结尾收官：代码艺术图、极客弹幕流、B 站一键三连（点赞/投币/收藏）弹性跳动与下期预告
  3. 精准毫秒级 GSAP 驱动与全屏高对比度长驻无闪烁字幕条。
"""

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def get_wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 20.0


def esc(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def bake_audio_tracks(scene_durations, assets_dir: Path, hf_dir: Path, total_duration: float):
    """使用 ffmpeg 将各幕独立旁白与物理音效在 Python 侧精准拼接为 master 音轨"""
    audio_dir = assets_dir / "audio"
    sfx_dir = assets_dir / "sfx"
    hf_audio_dir = hf_dir / "assets" / "audio"
    hf_audio_dir.mkdir(parents=True, exist_ok=True)

    master_vo = audio_dir / "narration_master.wav"
    master_sfx = audio_dir / "sfx_master.wav"

    # 1. 烘焙旁白主音轨
    inputs = []
    filter_parts = []
    mix_labels = []

    for idx, item in enumerate(scene_durations):
        wav_path = assets_dir.parent / item["audio_file"] if not Path(item["audio_file"]).is_absolute() else Path(item["audio_file"])
        if not wav_path.exists():
            wav_path = audio_dir / f"sec_{item['idx']:02d}.wav"

        inputs.extend(["-i", str(wav_path)])
        st_ms = int(round(item["start_time"] * 1000))
        filter_parts.append(
            f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={st_ms}|{st_ms},apad=whole_dur={int(total_duration*1000)}ms[v{idx}]"
        )
        mix_labels.append(f"[v{idx}]")

    filter_parts.append(f"{''.join(mix_labels)}amix=inputs={len(scene_durations)}:duration=first:normalize=0[vo_out]")

    cmd_vo = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vo_out]",
        "-t", str(total_duration),
        "-c:a", "pcm_s16le",
        str(master_vo)
    ]
    res_vo = subprocess.run(cmd_vo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_vo.returncode != 0:
        print(f">> [bake_audio] 旁白烘焙失败:\n{res_vo.stderr}")
        raise RuntimeError("旁白 master 音轨烘焙失败")

    # 2. 烘焙高精度交互音效主音轨 (SFX)
    sfx_events = []

    def add_sfx(wav_name, rel_time_s, vol=0.5):
        p = sfx_dir / wav_name
        if p.exists():
            sfx_events.append({"path": p, "time_s": rel_time_s, "volume": vol})

    # 为各幕特定的视觉动作添加精确 SFX 事件
    for item in scene_durations:
        idx = item["idx"]
        st = item["start_time"]

        if idx == 1:
            add_sfx("synthetic-ui-swipe.wav", st + 0.1, 0.45)
            add_sfx("stamp_thud.wav", st + 1.5, 0.6)
            add_sfx("synthetic-ui-swipe.wav", st + 2.8, 0.55)
        elif idx == 2:
            add_sfx("line-draw.wav", st + 0.2, 0.4)
            add_sfx("stamp_thud.wav", st + 3.0, 0.55)
            add_sfx("chime.wav", st + 5.0, 0.5)
        elif idx == 3:
            add_sfx("synthetic-ui-swipe.wav", st + 0.2, 0.4)
            add_sfx("pop.wav", st + 2.2, 0.55)
            add_sfx("keystroke.wav", st + 3.5, 0.4)
            add_sfx("soft-boop.wav", st + 7.5, 0.5)
            add_sfx("line-draw.wav", st + 8.5, 0.4)
        elif idx == 4:
            add_sfx("soft-boop.wav", st + 2.5, 0.55)
            add_sfx("keystroke.wav", st + 8.5, 0.4)
            add_sfx("chime.wav", st + 11.5, 0.45)
        elif idx == 5:
            add_sfx("synthetic-ui-swipe.wav", st + 0.5, 0.5)
            add_sfx("keystroke.wav", st + 4.5, 0.4)
            add_sfx("pop.wav", st + 6.0, 0.45)
        elif idx == 6:
            add_sfx("synthetic-ui-swipe.wav", st + 0.3, 0.45)
            add_sfx("pop.wav", st + 2.8, 0.5)
            add_sfx("chime.wav", st + 3.2, 0.5)
            add_sfx("pop.wav", st + 3.6, 0.5)

    sfx_inputs = []
    sfx_filters = []
    sfx_labels = []

    for s_idx, ev in enumerate(sfx_events):
        sfx_inputs.extend(["-i", str(ev["path"])])
        ms = int(round(ev["time_s"] * 1000))
        vol = ev["volume"]
        sfx_filters.append(
            f"[{s_idx}:a]volume={vol},aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},apad=whole_dur={int(total_duration*1000)}ms[s{s_idx}]"
        )
        sfx_labels.append(f"[s{s_idx}]")

    if sfx_labels:
        sfx_filters.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:duration=first:normalize=0[sfx_out]")
        cmd_sfx = [
            "ffmpeg", "-y",
            *sfx_inputs,
            "-filter_complex", ";".join(sfx_filters),
            "-map", "[sfx_out]",
            "-t", str(total_duration),
            "-c:a", "pcm_s16le",
            str(master_sfx)
        ]
        res_sfx = subprocess.run(cmd_sfx, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_sfx.returncode != 0:
            print(f">> [bake_audio] SFX 烘焙失败:\n{res_sfx.stderr}")
            raise RuntimeError("SFX master 音轨烘焙失败")

    shutil.copy2(master_vo, hf_audio_dir / "narration_master.wav")
    if master_sfx.exists():
        shutil.copy2(master_sfx, hf_audio_dir / "sfx_master.wav")

    print(f">> [bake_audio] 音频预混完成：旁白 {master_vo.stat().st_size} 字节，物理音效 {master_sfx.stat().st_size} 字节")


def build_composition(episode_json_path: Path, assets_dir: Path, output_html_path: Path, bgm_src: str = "assets/music/bgm_cyberpunk_city.mp3"):
    with open(episode_json_path, "r", encoding="utf-8") as f:
        ep = json.load(f)

    scenes = ep.get("scenes", [])
    if not scenes:
        raise ValueError("course_episode.json 中未找到任何 scenes！")

    # 1. 探查各幕实际音频时长
    scene_durations = []
    total_speech_duration = 0.0
    audio_assets = assets_dir / "audio"

    for i, sc in enumerate(scenes, 1):
        dur = sc.get("duration")
        cand = audio_assets / f"sec_{i:02d}.wav"
        if cand.exists():
            dur = get_wav_duration(cand)
            audio_file = f"assets/audio/sec_{i:02d}.wav"
        else:
            audio_file = sc.get("audio_file", f"assets/audio/sec_{i:02d}.wav")
            dur = dur or 18.0

        dur_rounded = round(float(dur) + 0.4, 2)
        scene_durations.append({
            "idx": i,
            "scene": sc,
            "audio_file": audio_file,
            "duration": dur_rounded,
            "speech_dur": dur
        })
        total_speech_duration += dur_rounded

    ending_buffer = 4.0
    total_composition_duration = round(total_speech_duration + ending_buffer, 1)

    current_time = 0.0
    for item in scene_durations:
        item["start_time"] = round(current_time, 2)
        current_time += item["duration"]

    # 2. 烘焙音效
    hf_dir = output_html_path.parent
    bake_audio_tracks(scene_durations, assets_dir, hf_dir, total_composition_duration)

    title = esc(ep.get("title", "DeepSeek Harness 2.0 深度评测"))
    html_parts = []

    # 3. 全局样式
    html_parts.append(f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1920, height=1080" />
  <title>{title}</title>
  <script src="assets/gsap.min.js"></script>
  <style>
    :root {{
      --bg-dark: #07090E;
      --panel-bg: #0E121A;
      --panel-border: #1E2636;
      --cyan-neon: #00E5FF;
      --green-neon: #00FF66;
      --orange-neon: #FF6600;
      --red-alert: #FF3344;
      --yellow-tag: #FFCC00;
      --font-mono: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: var(--bg-dark); color: #F0F4F8; font-family: var(--font-sans); }}
    #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: var(--bg-dark); }}
    .clip {{ position: absolute; inset: 0; }}

    /* 现代极客桌面网格背景 */
    .desktop-grid {{
      position: absolute; inset: 0; pointer-events: none; z-index: 1;
      background-image: 
        linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
      background-size: 60px 60px;
    }}

    /* 拟真 OS 顶栏 */
    .os-menubar {{
      position: absolute; left: 0; top: 0; width: 1920px; height: 36px;
      background: rgba(14, 18, 26, 0.85); backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(255,255,255,0.08);
      display: flex; justify-content: space-between; align-items: center;
      padding: 0 24px; font-family: var(--font-mono); font-size: 13px; color: #8E9CAE;
      z-index: 100;
    }}
    .os-menu-left {{ display: flex; gap: 20px; align-items: center; }}
    .os-menu-right {{ display: flex; gap: 16px; align-items: center; color: var(--cyan-neon); }}

    /* 拟真拟态鼠标指针 */
    #global-cursor {{
      position: absolute; left: 0; top: 0; width: 28px; height: 28px; z-index: 999; pointer-events: none;
      filter: drop-shadow(0 4px 10px rgba(0,0,0,0.7));
      opacity: 0;
    }}
    .cursor-ripple {{
      position: absolute; width: 44px; height: 44px; border: 2px solid var(--cyan-neon);
      border-radius: 50%; opacity: 0; pointer-events: none; transform: translate(-50%, -50%);
    }}

    /* 拟真现代桌面视窗容器 */
    .os-window {{
      position: absolute; background: var(--panel-bg);
      border: 1px solid var(--panel-border); border-radius: 8px;
      box-shadow: 0 30px 70px rgba(0,0,0,0.85), 0 0 40px rgba(0,229,255,0.06);
      overflow: hidden;
    }}
    .window-header {{
      height: 42px; background: #131722; border-bottom: 1px solid var(--panel-border);
      display: flex; justify-content: space-between; align-items: center; padding: 0 18px;
    }}
    .win-dots {{ display: flex; gap: 8px; }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    .dot-red {{ background: #FF5F56; }}
    .dot-yellow {{ background: #FFBD2E; }}
    .dot-green {{ background: #27C93F; }}

    .address-bar {{
      background: #090C12; border: 1px solid #232D3F; border-radius: 4px;
      padding: 4px 16px; font-family: var(--font-mono); font-size: 13px; color: #7B8FA6;
      display: flex; align-items: center; gap: 8px; width: 480px;
    }}

    /* 极客动态贴纸花字 */
    .geek-sticker {{
      position: absolute; z-index: 50;
      background: #090D14; border: 2px solid var(--cyan-neon);
      padding: 10px 24px; border-radius: 4px;
      font-family: var(--font-mono); font-weight: 900; font-size: 22px;
      box-shadow: 0 10px 30px rgba(0,229,255,0.3);
      display: inline-flex; align-items: center; gap: 10px;
    }}
    .sticker-yellow {{
      background: var(--yellow-tag); color: #000; border: none;
      font-weight: 900; font-size: 32px; padding: 14px 36px;
      box-shadow: 0 15px 40px rgba(255,204,0,0.5);
      transform: rotate(-2deg);
    }}

    /* 印章 */
    .stamp-badge {{
      position: absolute; font-family: var(--font-mono); font-weight: 900;
      text-transform: uppercase; letter-spacing: 2px; padding: 12px 28px;
      border-radius: 6px; z-index: 40; pointer-events: none;
    }}
    .stamp-red {{
      border: 5px solid var(--red-alert); color: var(--red-alert);
      background: rgba(255,51,68,0.15); text-shadow: 0 0 15px rgba(255,51,68,0.5);
    }}
    .stamp-green {{
      border: 5px solid var(--green-neon); color: var(--green-neon);
      background: rgba(0,255,102,0.15); text-shadow: 0 0 15px rgba(0,255,102,0.5);
    }}
    .stamp-cyan {{
      border: 5px solid var(--cyan-neon); color: var(--cyan-neon);
      background: rgba(0,229,255,0.15); text-shadow: 0 0 15px rgba(0,229,255,0.5);
    }}

    /* 赛博仪表盘 */
    .gauge-container {{
      position: relative; width: 260px; height: 260px; display: flex;
      flex-direction: column; align-items: center; justify-content: center;
      background: radial-gradient(circle, rgba(0,229,255,0.1) 0%, rgba(0,0,0,0) 70%);
      border: 2px solid #1E2838; border-radius: 50%;
    }}

    /* 全屏字幕条 */
    #vox-sub-container {{
      position: absolute; left: 50%; bottom: 38px; transform: translateX(-50%);
      z-index: 88; pointer-events: none; text-align: center; width: 1600px;
    }}
    .sub-box {{
      display: inline-block; max-width: 1500px;
      background: rgba(8, 10, 15, 0.95);
      border: 1px solid rgba(0, 229, 255, 0.45);
      border-left: 6px solid var(--cyan-neon);
      padding: 12px 38px; border-radius: 4px;
      box-shadow: 0 12px 36px rgba(0,0,0,0.92);
      font-size: 28px; font-weight: 800; color: #FFFFFF;
      letter-spacing: 0.8px; opacity: 0; transform: translateY(14px);
    }}
    .sub-hl {{ color: var(--cyan-neon); font-weight: 900; }}

    /* B站三连贴纸 */
    .bilibili-badge {{
      background: #141B28; border: 2px solid var(--cyan-neon);
      padding: 16px 36px; border-radius: 6px; font-size: 26px; font-weight: bold;
      display: flex; align-items: center; gap: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.6);
    }}

    /* 弹幕流 */
    .danmaku-item {{
      position: absolute; white-space: nowrap; font-family: var(--font-sans);
      font-size: 22px; font-weight: bold; color: rgba(255,255,255,0.85);
      text-shadow: 0 2px 8px #000; z-index: 45; pointer-events: none;
    }}
  </style>
</head>
<body>
<div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-duration="{total_composition_duration}" data-start="0">

  <div class="desktop-grid"></div>

  <!-- OS 顶栏 -->
  <div class="os-menubar">
    <div class="os-menu-left">
      <span style="color:#FFF; font-weight:bold;">⚡ DSH Runtime</span>
      <span>File</span><span>Edit</span><span>View</span><span>Terminal</span><span>Harness</span>
    </div>
    <div class="os-menu-right">
      <span>CPU 14%</span><span>RAM 8.4GB</span><span>RTX 3090: ACTIVE</span><span>09:41 AM</span>
    </div>
  </div>

  <!-- 模拟全局鼠标指针 -->
  <div id="global-cursor">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
      <path d="M4 2L20 12L12 14L8 22L4 2Z" fill="#00E5FF" stroke="#000" stroke-width="2" stroke-linejoin="round"/>
    </svg>
    <div class="cursor-ripple" id="cursor-ripple"></div>
  </div>

  <audio id="bgm" src="{bgm_src}" data-start="0" data-duration="{total_composition_duration}" data-volume="0.16"></audio>
  <audio id="vo-master" src="assets/audio/narration_master.wav" data-start="0" data-duration="{total_composition_duration}" data-volume="1.0"></audio>
  <audio id="sfx-master" src="assets/audio/sfx_master.wav" data-start="0" data-duration="{total_composition_duration}" data-volume="0.85"></audio>
""")

    first_sub = scenes[0].get("subtitles", [{}])[0].get("text", title)
    html_parts.append(f"""
  <div id="vox-sub-container">
    <div id="sub-box" class="sub-box">
      <span id="sub-text">{esc(first_sub)}</span>
    </div>
  </div>
""")

    all_subtitles = []

    for item in scene_durations:
        i = item["idx"]
        sc = item["scene"]
        st = item["start_time"]
        dur = item["duration"]
        disp = sc.get("display", {})
        tag = esc(sc.get("topic_tag", f"SHOT 0{i}"))
        headline_zh = esc(disp.get("headline", {}).get("zh", f"镜头 {i}"))

        subs = sc.get("subtitles", [])
        for sub in subs:
            sub_st = round(st + float(sub.get("start", 0)), 2)
            sub_et = round(st + float(sub.get("end", 5)), 2)
            all_subtitles.append({
                "start": sub_st,
                "end": sub_et,
                "text": sub.get("text", ""),
                "hl": sub.get("hl", False)
            })

        track_idx = (i - 1) % 2

        html_parts.append(f"""
  <!-- ================= SHOT {i} ({st}s - {st+dur}s) {headline_zh} ================= -->
  <section class="clip" id="scene-s{i}" data-start="{st}" data-duration="{dur}" data-track-index="{track_idx}">
    <div class="board" id="bd-s{i}" style="position:absolute; inset:0; opacity:0;">
""")

        # ---------------- 镜头 01：黄金3秒·对比冲击 ----------------
        if i == 1:
            html_parts.append(f"""
      <!-- 动态花字横幅 (屏幕正中) -->
      <div class="sticker-yellow" id="s1-banner" style="position:absolute; left:50%; top:58px; transform:translateX(-50%) rotate(-2deg); z-index:90;">
        别等内测了！开源全家桶直接用！
      </div>

      <!-- 左视窗：Claude Code Waitlist 真实排队界面 (820x840) -->
      <div class="os-window" id="s1-win-left" style="left:100px; top:130px; width:820px; height:840px;">
        <div class="window-header">
          <div class="win-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="address-bar">🔒 https://claude.ai/code/waitlist</div>
          <span style="font-size:12px; color:#A0AEC0; font-weight:bold;">Closed Beta</span>
        </div>
        <div id="s1-claude-page" style="padding:48px 40px; background:#12151B; height:calc(100% - 42px); position:relative; text-align:center;">
          <div style="font-size:64px; margin-top:40px; opacity:0.6;">⏳ 📧 🔒</div>
          <h2 style="font-size:38px; color:#DDD; font-weight:800; margin-top:24px;">You're on the Waitlist</h2>
          <p style="font-size:20px; color:#888; font-family:var(--font-mono); margin-top:16px; line-height:1.7;">
            Claude Code is currently available to a limited preview group.<br/>
            We will notify you by email when space becomes available.
          </p>
          <div style="background:#1B202A; border:1px solid #333C4E; border-radius:6px; padding:18px; max-width:440px; margin:36px auto 0; font-family:var(--font-mono); color:#AAA; font-size:16px;">
            Queue Status: #184,209 in line
          </div>
          <div class="stamp-badge stamp-red" id="s1-stamp-waitlist" data-layout-allow-overlap style="left:50%; top:50%; transform:translate(-50%, -50%) rotate(-12deg); font-size:54px;">
            WAITLIST 排队中...
          </div>
        </div>
      </div>

      <!-- 右视窗：DeepSeek Harness v0.1.5 官方开源 (860x840) -->
      <div class="os-window" id="s1-win-right" style="left:960px; top:130px; width:860px; height:840px; border:2px solid var(--cyan-neon);">
        <div class="window-header">
          <div class="win-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="address-bar">🌐 https://github.com/deepseek-ai/Harness/releases/tag/v0.1.5</div>
          <span style="font-size:12px; color:var(--cyan-neon); font-weight:bold;">100% Open Source</span>
        </div>
        <div style="padding:40px 48px; background:#0B0E14; height:calc(100% - 42px); position:relative; overflow:hidden;">
          <!-- 亮青色能量发散环 -->
          <div id="s1-glow-circle" style="position:absolute; left:50%; top:40%; transform:translate(-50%, -50%); width:380px; height:380px; background:radial-gradient(circle, rgba(0,229,255,0.45) 0%, rgba(0,229,255,0) 70%); border-radius:50%; filter:blur(24px); opacity:0;"></div>
          
          <div style="text-align:center; position:relative; z-index:10; margin-top:20px;">
            <!-- DeepSeek 矢量 Logo -->
            <div id="s1-logo-box" style="display:inline-block;">
              <svg width="120" height="120" viewBox="0 0 100 100" fill="none">
                <circle cx="50" cy="50" r="46" stroke="#00E5FF" stroke-width="4" fill="#0C1B2A"/>
                <path d="M25 55 Q 50 20 75 55 Q 50 80 25 55 Z" fill="#00E5FF"/>
                <circle cx="60" cy="48" r="4" fill="#000"/>
              </svg>
            </div>
            <h1 style="font-size:44px; color:#FFF; font-weight:900; margin-top:18px;">DeepSeek Harness v0.1.5</h1>
            <div style="display:flex; justify-content:center; gap:16px; margin-top:20px;">
              <span style="background:rgba(0,255,102,0.2); border:1px solid var(--green-neon); color:var(--green-neon); padding:6px 18px; border-radius:4px; font-family:var(--font-mono); font-weight:bold; font-size:16px;">MIT License 商业自由</span>
              <span style="background:rgba(0,229,255,0.2); border:1px solid var(--cyan-neon); color:var(--cyan-neon); padding:6px 18px; border-radius:4px; font-family:var(--font-mono); font-weight:bold; font-size:16px;">v0.1.5 官方 Release</span>
            </div>
          </div>

          <div style="background:#111622; border:1px solid #1E2B3E; border-radius:6px; padding:24px; margin-top:40px; font-family:var(--font-mono); font-size:19px; line-height:2.0; color:#DDD;">
            <div>$ git clone https://github.com/deepseek-ai/Harness.git (tag: v0.1.5)</div>
            <div style="color:var(--green-neon); margin-top:6px;">✔ Cloning complete: 所有人现在就能免内测免费用！</div>
            <div style="color:var(--cyan-neon);">✔ 告别闭源席位垄断，真正的开发者开源全家桶！</div>
          </div>

          <div class="stamp-badge stamp-cyan" id="s1-stamp-mit" data-layout-allow-overlap style="right:40px; bottom:40px; font-size:52px; transform:rotate(-6deg);">
            100% MIT 开源
          </div>
        </div>
      </div>
""")

        # ---------------- 镜头 02：痛点对比·架构原理动画 ----------------
        elif i == 2:
            html_parts.append(f"""
      <div class="sticker-yellow" id="s2-banner" style="position:absolute; left:50%; top:58px; transform:translateX(-50%) rotate(-1deg); z-index:90;">
        缓存命中率高达 97%！长对话费用暴降！
      </div>

      <!-- 左栏：旧版架构雪崩 (820x840) -->
      <div class="os-window" id="s2-win-old" style="left:100px; top:130px; width:820px; height:840px; border:2px solid var(--red-alert);">
        <div class="window-header">
          <div class="win-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <span style="font-family:var(--font-mono); font-size:14px; color:#FFA39E; font-weight:bold;">Legacy Architecture · 提示词失效</span>
        </div>
        <div style="padding:36px; background:#120B0B; height:calc(100% - 42px); position:relative;">
          <h3 style="font-size:30px; color:#FF7777; font-weight:bold;">旧版：修改 1 句提示词，缓存全部白算</h3>
          
          <!-- 对话管线 -->
          <div style="margin-top:24px; display:flex; flex-direction:column; gap:16px;">
            <div style="background:#1F1010; border:1px solid #3E1D1D; padding:16px; border-radius:4px; font-family:var(--font-mono); font-size:17px; color:#AAA;">
              [System Prompt v1.0] ➔ Context Round 1 ➔ Context Round 2
            </div>
            <div id="s2-alert-box" style="background:#2D1212; border:2px dashed var(--red-alert); padding:20px; border-radius:4px; font-family:var(--font-mono); color:#FF5555; font-size:18px;">
              ⚠️ 用户中途修改了一句系统提示词！<br/>
              ➔ Hash 校验不匹配，历史 18,432 Token 缓存瞬间清零！
            </div>
          </div>

          <!-- Token 狂飙计数器 -->
          <div style="background:#180A0A; border:2px solid var(--red-alert); border-radius:6px; padding:28px; margin-top:36px; text-align:center;">
            <div style="font-size:18px; color:#AAA; font-family:var(--font-mono);">TOKEN 重新计费消耗</div>
            <div id="s2-counter-num" style="font-size:68px; font-weight:900; color:var(--red-alert); font-family:var(--font-mono); margin-top:8px;">24,800</div>
            <div style="color:#FF8888; font-size:16px; font-family:var(--font-mono);">Token 费用瞬间崩溃，直接白花钱！</div>
          </div>

          <div class="stamp-badge stamp-red" id="s2-stamp-fail" data-layout-allow-overlap style="right:40px; bottom:40px; font-size:48px; transform:rotate(-10deg);">
            CACHE FAILED
          </div>
        </div>
      </div>

      <!-- 右栏：Harness v0.1.5 系统指令追加 (860x840) -->
      <div class="os-window" id="s2-win-new" style="left:960px; top:130px; width:860px; height:840px; border:2px solid var(--green-neon); box-shadow:0 0 50px rgba(0,255,102,0.18);">
        <div class="window-header">
          <div class="win-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <span style="font-family:var(--font-mono); font-size:14px; color:var(--green-neon);">Harness v0.1.5 · Append Instruction Engine</span>
        </div>
        <div style="padding:36px; background:#0A120E; height:calc(100% - 42px); position:relative;">
          <h3 style="font-size:30px; color:#FFF; font-weight:bold;">v0.1.5 黑科技：更新指令追加在历史末尾</h3>
          
          <div style="margin-top:24px; display:flex; flex-direction:column; gap:16px;">
            <div style="background:#0F2417; border:1px solid #1C4D2E; padding:16px; border-radius:4px; font-family:var(--font-mono); font-size:17px; color:#A7F3D0;">
              [History Context: 18,432 Tokens] ➔ <span style="color:var(--green-neon); font-weight:bold;">LOCKED (100% 保持)</span>
            </div>
            <div id="s2-append-box" style="background:#133320; border:2px solid var(--green-neon); padding:20px; border-radius:4px; font-family:var(--font-mono); color:#FFF; font-size:18px;">
              ⚡ [APPEND] 新指令作为增量挂载到历史记录末尾！<br/>
              ➔ 之前的长对话上下文依然完美复用，无需重算！
            </div>
          </div>

          <!-- 97% 缓存命中大字跳动 -->
          <div style="background:#0B1A11; border:2px solid var(--green-neon); border-radius:6px; padding:28px; margin-top:36px; text-align:center;">
            <div style="font-size:18px; color:#A7F3D0; font-family:var(--font-mono);">实测累计缓存命中率</div>
            <div id="s2-hit-rate" style="font-size:68px; font-weight:900; color:var(--green-neon); font-family:var(--font-mono); margin-top:8px;">97.4%</div>
            <div style="color:var(--cyan-neon); font-size:16px; font-family:var(--font-mono);">既省钱又省时间 · 效率暴增！</div>
          </div>

          <div class="stamp-badge stamp-green" id="s2-stamp-hit" data-layout-allow-overlap style="right:40px; bottom:40px; font-size:52px; transform:rotate(-6deg);">
            97% 缓存命中
          </div>
        </div>
      </div>
""")

        # ---------------- 镜头 03：实操 1：看图写代码 + 侧边栏实时渲染 ----------------
        elif i == 3:
            html_parts.append(f"""
      <div class="sticker-yellow" id="s3-banner" style="position:absolute; left:50%; top:58px; transform:translateX(-50%) rotate(1deg); z-index:90;">
        原生视觉加持 · 即写即看无需切换！
      </div>

      <!-- 全屏桌面工作台视窗 (1720x840) -->
      <div class="os-window" id="s3-main-win" style="left:100px; top:130px; width:1720px; height:840px;">
        <div class="window-header">
          <div class="win-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="address-bar">dsh web ~ V4.1 Flash 原生视觉分析工作区</div>
          <div style="display:flex; gap:10px;">
            <span style="background:var(--cyan-neon); color:#000; font-family:var(--font-mono); font-weight:bold; font-size:13px; padding:3px 10px; border-radius:3px;">Model: V4.1 Flash</span>
            <span style="background:#1E2B3E; color:#FFF; font-family:var(--font-mono); font-size:13px; padding:3px 10px; border-radius:3px;">Thinking: High</span>
          </div>
        </div>

        <div style="display:flex; height:calc(100% - 42px);">
          <!-- 左工作区：聊天交互与拖拽 (宽 960px) -->
          <div style="flex:1.2; padding:32px; background:#0B0E14; border-right:1px solid var(--panel-border); position:relative;">
            
            <!-- 待拖拽的设计稿与报错图浮动卡片 -->
            <div id="s3-file-card" data-layout-allow-overlap style="position:absolute; left:80px; top:60px; background:#182232; border:2px solid var(--cyan-neon); border-radius:8px; padding:20px; width:340px; z-index:30; box-shadow:0 15px 35px rgba(0,0,0,0.8);">
              <div style="font-size:36px;">📐 🖼️ 📊</div>
              <div style="font-family:var(--font-mono); font-size:17px; color:#FFF; font-weight:bold; margin-top:8px;">ui_design_error.png</div>
              <div style="font-size:13px; color:#CBD5E1; margin-top:4px;">UI 设计图 + 报错表格数据</div>
            </div>

            <!-- 聊天对话框区 -->
            <div style="margin-top:140px; display:flex; flex-direction:column; gap:20px;">
              <div style="background:#121722; border-radius:6px; padding:20px; color:#AAA; font-size:17px; line-height:1.7;">
                🤖 <strong>V4.1 Flash：</strong>我具备原生视觉多模态能力，请将设计截图或报错表格拖入下方输入框。
              </div>

              <!-- 输入框 (带 Drop 虚线边框) -->
              <div id="s3-input-box" style="background:#090C12; border:2px dashed #304058; border-radius:6px; padding:24px; min-height:140px; position:relative;">
                <div id="s3-typing-text" style="font-family:var(--font-mono); font-size:19px; color:#FFF; line-height:1.8;">
                  <span id="s3-typed-content"></span><span style="color:var(--cyan-neon); animation:blink 0.8s infinite;">|</span>
                </div>
                <div id="s3-attached-tag" style="display:none; position:absolute; left:20px; bottom:16px; background:#162538; border:1px solid var(--cyan-neon); color:var(--cyan-neon); font-family:var(--font-mono); font-size:14px; padding:4px 12px; border-radius:3px;">
                  [ATTACHED] ui_design_error.png (原生视觉就绪)
                </div>
              </div>
            </div>

            <div class="stamp-badge stamp-cyan" id="s3-stamp" data-layout-allow-overlap style="left:32px; bottom:32px; font-size:44px; transform:rotate(-5deg);">
              看图秒懂布局
            </div>
          </div>

          <!-- 右工作区：Side Panel 内嵌实时预览 (宽 760px) -->
          <div id="s3-side-panel" style="flex:1; padding:28px 32px; background:#10151F; position:relative; overflow:hidden;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #253144; padding-bottom:14px;">
              <span style="font-family:var(--font-mono); font-size:17px; color:#FFF; font-weight:bold;">内嵌侧边栏文件预览 (Side Panel)</span>
              <div style="display:flex; gap:10px;">
                <span id="s3-preview-btn" style="background:var(--cyan-neon); color:#000; font-family:var(--font-mono); font-size:13px; font-weight:900; padding:5px 14px; border-radius:3px;">Preview 预览按钮</span>
                <span style="background:#1B2332; color:#AAA; font-family:var(--font-mono); font-size:13px; padding:5px 14px; border-radius:3px;">分屏/全屏</span>
              </div>
            </div>

            <!-- 实时渲染出的现代网页组件 -->
            <div id="s3-rendered-view" style="margin-top:20px; background:#FAF9F5; color:#161513; border-radius:6px; padding:28px; box-shadow:0 15px 40px rgba(0,0,0,0.5); min-height:520px;">
              <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #E5DAC2; padding-bottom:14px;">
                <h4 style="font-size:26px; font-weight:900;">SaaS Dashboard 实时预览</h4>
                <span style="background:#00E676; color:#000; font-size:13px; font-weight:bold; padding:3px 10px; border-radius:3px;">RENDER SUCCESS</span>
              </div>
              <p style="font-size:18px; color:#444; margin-top:18px; line-height:1.7;">
                Markdown、代码、HTML 甚至 PDF 都能在内嵌侧边栏直接预览渲染！再也不用在本地文件夹到处翻找了！
              </p>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:28px;">
                <div style="background:#F0EAE1; padding:20px; border-radius:4px; font-weight:bold; font-size:16px;">⚡ 一键全屏 / 分屏切换</div>
                <div style="background:#F0EAE1; padding:20px; border-radius:4px; font-weight:bold; font-size:16px;">🔍 毫秒响应写完就能跑</div>
              </div>
            </div>
          </div>
        </div>
      </div>
""")

        # ---------------- 镜头 04：实操 2：实时控制与 Headless ----------------
        elif i == 4:
            html_parts.append(f"""
      <div class="sticker-yellow" id="s4-banner" style="position:absolute; left:50%; top:58px; transform:translateX(-50%) rotate(-1deg); z-index:90;">
        Agent 动态转向 / 实时打断 · CI/CD 绝配！
      </div>

      <div class="os-window" id="s4-main-win" style="left:100px; top:130px; width:1720px; height:840px; display:flex; gap:36px; padding:36px; background:#0B0E14;">
        
        <!-- 左半区：Pause 实时打断与插队 (宽 820px) -->
        <div style="flex:1; background:#101520; border:1px solid #233044; border-radius:6px; padding:32px; position:relative;">
          <div class="vox-label" style="color:var(--orange-neon);">// LIVE STEERING & INTERRUPT //</div>
          <h3 style="font-size:32px; color:#FFF; margin:14px 0 20px 0;">跑偏不用关，随时 Pause 插队新指令</h3>
          
          <div style="background:#161F2E; border-left:6px solid var(--red-alert); padding:20px; border-radius:4px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-family:var(--font-mono); color:#AAA; font-size:16px;">Agent 正在流式编写后端鉴权模块...</span>
              <span id="s4-pause-btn" style="background:var(--red-alert); color:#FFF; font-family:var(--font-mono); font-weight:900; font-size:15px; padding:6px 18px; border-radius:4px;">PAUSE 暂停</span>
            </div>
            <div style="font-family:var(--font-mono); font-size:17px; color:#DDD; margin-top:12px;">
              [STATUS] 会话无损冻结挂起，保留全部执行栈
            </div>
          </div>

          <div style="background:#0F241A; border:2px solid var(--green-neon); border-radius:6px; padding:22px; margin-top:28px;">
            <div style="color:var(--green-neon); font-family:var(--font-mono); font-weight:bold; font-size:17px;">
              [QUEUE INSERT] 排队插入新指令：
            </div>
            <p style="color:#FFF; font-size:18px; margin-top:10px; line-height:1.7;">
              “转向指令：改用 JWT 无状态鉴权，针对 Token 过期增加自动刷新逻辑。”
            </p>
            <div style="color:var(--cyan-neon); font-family:var(--font-mono); font-size:15px; margin-top:10px;">
              ✔ 子 Agent 实时动态转向，未丢失任何上下文！
            </div>
          </div>

          <div class="stamp-badge stamp-green" id="s4-stamp1" data-layout-allow-overlap style="left:32px; bottom:32px; font-size:44px; transform:rotate(-6deg);">
            实时打断不丢进度
          </div>
        </div>

        <!-- 右半区：纯黑 CRT 终端运行 Headless 模式 (宽 860px) -->
        <div style="flex:1.2; background:#07090C; border:1px solid #1A222E; border-radius:6px; padding:32px; font-family:var(--font-mono); position:relative;">
          <div class="vox-label" style="color:var(--cyan-neon);">// HEADLESS CLI AUTOMATION //</div>
          <h3 style="font-size:32px; color:#FFF; margin:14px 0 20px 0;">Headless 模式自动修代码跑单测</h3>

          <div style="font-size:19px; line-height:2.0; color:#888; margin-top:16px;">
            <div style="color:var(--cyan-neon); font-weight:bold;">$ dsh --headless 'fix unit tests in auth.py'</div>
            <div style="color:#BBB;">[ANALYZE] 抓取 pytest 报错堆栈，精确定位 src/auth.py:48</div>
            <div style="color:var(--green-neon); font-weight:bold;">[AUTOFIX] 应用局部代码补丁，通过测试隔离风险</div>
            <div style="color:var(--green-neon);">[TEST] pytest: 14 passed in 0.82s (100% 成功通过)</div>
            <div style="color:#888;">[SESSION] 会话完整持久化保存至 ~/.dsh/sessions/</div>
          </div>

          <div style="background:#101724; border-left:6px solid var(--cyan-neon); padding:18px 24px; border-radius:4px; margin-top:32px; font-size:18px; color:#DDD; line-height:1.7;">
            <strong>CI/CD 自动化绝配：</strong>一句命令放进流水线，自动修 Bug 保存会话！
          </div>

          <div class="stamp-badge stamp-cyan" id="s4-stamp2" data-layout-allow-overlap style="right:32px; bottom:32px; font-size:44px; transform:rotate(-5deg);">
            CI/CD 自动化绝配
          </div>
        </div>
      </div>
""")

        # ---------------- 镜头 05：数据统计与快速部署 ----------------
        elif i == 5:
            html_parts.append(f"""
      <div class="sticker-yellow" id="s5-banner" style="position:absolute; left:50%; top:58px; transform:translateX(-50%) rotate(-1deg); z-index:90;">
        npm i @deepseek-ai/DSH 零成本本地部署！
      </div>

      <div class="os-window" id="s5-main-win" style="left:100px; top:130px; width:1720px; height:840px; display:flex; gap:36px; padding:36px; background:#0B0E14;">
        
        <!-- 左半区：性能统计面板 (宽 820px) -->
        <div style="flex:1; background:#101520; border:1px solid #233044; border-radius:6px; padding:36px; position:relative;">
          <div class="vox-label" style="color:var(--cyan-neon);">// BENCHMARK & METRICS //</div>
          <h3 style="font-size:34px; color:#FFF; margin:14px 0 24px 0;">极速吐字率与超低成本面板</h3>

          <!-- 赛博风测速表盘 -->
          <div style="background:#09121B; border:2px solid var(--cyan-neon); border-radius:8px; padding:30px; text-align:center; box-shadow:0 0 40px rgba(0,229,255,0.18);">
            <div id="s5-speed-num" style="font-size:76px; font-weight:900; color:var(--cyan-neon); font-family:var(--font-mono);">264.8</div>
            <div style="font-size:20px; color:#A7F3D0; font-family:var(--font-mono); letter-spacing:3px; margin-top:4px;">TOKENS PER SECOND</div>
          </div>

          <div style="margin-top:28px; display:flex; flex-direction:column; gap:16px;">
            <div style="background:#131B28; padding:18px 24px; border-radius:4px; display:flex; justify-content:space-between; align-items:center;">
              <span style="color:#AAA; font-size:19px;">⚡ 全程端到端耗时</span>
              <strong style="color:#FFF; font-size:26px; font-family:var(--font-mono);">18 分钟</strong>
            </div>
            <div style="background:#131B28; padding:18px 24px; border-radius:4px; display:flex; justify-content:space-between; align-items:center;">
              <span style="color:#AAA; font-size:19px;">💰 实际 Token 消费</span>
              <strong style="color:var(--green-neon); font-size:26px; font-family:var(--font-mono);">$0.12 美元</strong>
            </div>
          </div>

          <div class="stamp-badge stamp-green" id="s5-stamp1" data-layout-allow-overlap style="left:36px; bottom:36px; font-size:44px; transform:rotate(-5deg);">
            260+ Tokens/s
          </div>
        </div>

        <!-- 右半区：一行命令本地部署 (宽 860px) -->
        <div style="flex:1.2; background:#07090C; border:1px solid #1A222E; border-radius:6px; padding:36px; font-family:var(--font-mono); position:relative;">
          <div class="vox-label" style="color:var(--orange-neon);">// ONE COMMAND LAUNCH //</div>
          <h3 style="font-size:34px; color:#FFF; margin:14px 0 24px 0;">一行命令启动本地 Web 界面</h3>

          <div style="background:#0D141F; border:1px solid #253347; border-radius:6px; padding:28px; font-size:22px; line-height:2.0; color:#DDD;">
            <div style="color:var(--orange-neon); font-weight:bold;">$ npm i @deepseek-ai/DSH</div>
            <div style="color:var(--cyan-neon); font-weight:bold; margin-top:8px;">$ dsh web</div>
            <div style="color:#888; margin-top:14px;">[READY] Server listening on http://localhost:3000</div>
            <div style="color:var(--green-neon); font-weight:bold;">[BROWSER] 浏览器已自动打开原生 Web 控制台！</div>
          </div>

          <div style="background:#131B26; border-left:6px solid var(--orange-neon); padding:20px 28px; border-radius:4px; margin-top:36px; font-size:20px; color:#CCC; line-height:1.7;">
            只要电脑安装了支持的 Node.js 环境，在终端运行一行命令，瞬间起飞！
          </div>

          <div class="stamp-badge stamp-cyan" id="s5-stamp2" data-layout-allow-overlap style="right:36px; bottom:36px; font-size:44px; transform:rotate(-6deg);">
            零成本本地部署
          </div>
        </div>
      </div>
""")

        # ---------------- 镜头 06：结尾·Call to Action 与一键三连 ----------------
        elif i == 6:
            hook = ep.get("next_episode_hook", {})
            html_parts.append(f"""
      <div class="os-window" id="s6-main-win" style="left:100px; top:110px; width:1720px; height:860px; background:#0B0E14; border:2px solid var(--cyan-neon); text-align:center; padding:44px; position:relative; overflow:hidden;">
        
        <!-- 弹幕流动层 -->
        <div id="s6-danmaku-1" class="danmaku-item" data-layout-allow-overlap data-layout-allow-overflow style="top:40px; right:-500px; color:var(--cyan-neon);">
          “这输出速度简直起飞了！！”
        </div>
        <div id="s6-danmaku-2" class="danmaku-item" data-layout-allow-overlap data-layout-allow-overflow style="top:85px; right:-500px; color:var(--green-neon);">
          “开源神中神，今晚就 clone 来用！”
        </div>
        <div id="s6-danmaku-3" class="danmaku-item" data-layout-allow-overlap data-layout-allow-overflow style="top:130px; right:-500px; color:#FFF;">
          “97% 缓存命中，终于不用天天等排队了”
        </div>

        <div class="vox-label" style="color:var(--cyan-neon); font-size:22px;">// CALL TO ACTION · 社区互动 //</div>
        
        <h1 style="font-size:52px; font-weight:900; color:#FFF; margin-top:20px; line-height:1.3;">
          完全开源、性能强劲的 AI 编程管家，能打动你吗？
        </h1>

        <p style="font-size:26px; color:#DDD; font-family:var(--font-mono); margin-top:14px;">
          把你的看法打在评论区！
        </p>

        <!-- 动态一键三连交互组件 -->
        <div style="margin-top:36px; display:flex; justify-content:center; gap:36px;">
          <div id="s6-btn-like" class="bilibili-badge" style="border-color:var(--cyan-neon); color:#FFF;">
            <span style="font-size:32px;">👍</span> 点赞支持
          </div>
          <div id="s6-btn-coin" class="bilibili-badge" style="border-color:var(--yellow-tag); color:#FFF;">
            <span style="font-size:32px;">🪙</span> 投币助威
          </div>
          <div id="s6-btn-fav" class="bilibili-badge" style="border-color:var(--orange-neon); color:#FFF;">
            <span style="font-size:32px;">⭐</span> 收藏分享
          </div>
        </div>

        <!-- 下集预告专属展板 -->
        <div style="background:#111724; border:1px dashed #31425C; border-radius:8px; padding:24px 36px; margin-top:36px; max-width:1100px; margin-left:auto; margin-right:auto;">
          <div style="color:var(--orange-neon); font-family:var(--font-mono); font-size:18px; font-weight:bold;">🔥 下期预告：</div>
          <div style="color:#FFF; font-size:28px; font-weight:bold; margin-top:6px;">
            {esc(hook.get("headline", "下期实战：手把手手搓多 Agent 团队协作与分布式执行"))}
          </div>
        </div>

        <div class="stamp-badge stamp-cyan" id="s6-stamp" data-layout-allow-overlap style="position:static; display:inline-block; margin-top:32px; font-size:50px; transform:rotate(-4deg); padding:12px 54px;">
          欢迎点赞·收藏·分享！
        </div>
      </div>
""")

        html_parts.append("""
    </div>
  </section>
""")

    # 4. GSAP 驱动脚本
    html_parts.append("""
<script>
window.__timelines = window.__timelines || {};
var tl = gsap.timeline({ paused: true });

/* 全局鼠标光标控制 */
tl.set("#global-cursor", { x: 960, y: 540 }, 0);
tl.set("#global-cursor", { opacity: 1 }, 39.5);
tl.set("#global-cursor", { opacity: 0 }, 79.5);

/* ================= 6 幕专属极客动效时间轴 ================= */
""")

    for item in scene_durations:
        i = item["idx"]
        st = item["start_time"]
        dur = item["duration"]
        et = st + dur
        html_parts.append(f"""/* 镜头 {i} 入场与退场 */
tl.fromTo("#bd-s{i}", {{opacity:0}}, {{opacity:1, duration:0.35, ease:"power1.out"}}, {st + 0.05:.2f});
tl.to("#bd-s{i}", {{opacity:0, duration:0.35, ease:"power1.in"}}, {et - 0.40:.2f});
tl.set("#bd-s{i}", {{opacity:0}}, {et:.2f});
""")

        if i == 1:
            html_parts.append(f"""
tl.fromTo("#s1-banner", {{scale:0.3, opacity:0, y:-30}}, {{scale:1, opacity:1, y:0, duration:0.5, ease:"back.out(1.8)"}}, {st + 0.4:.2f});
tl.fromTo("#s1-win-left", {{x:-80, opacity:0}}, {{x:0, opacity:1, duration:0.7, ease:"power2.out"}}, {st + 0.15:.2f});
tl.fromTo("#s1-win-right", {{x:80, opacity:0}}, {{x:0, opacity:1, duration:0.7, ease:"power2.out"}}, {st + 0.25:.2f});

/* 左侧变灰 + 盖上 WAITLIST 印章 */
tl.to("#s1-claude-page", {{filter:"grayscale(0.9) brightness(0.7)", duration:0.6}}, {st + 1.2:.2f});
tl.fromTo("#s1-stamp-waitlist", {{scale:3.5, opacity:0, rotate:-35}}, {{scale:1, opacity:1, rotate:-12, duration:0.4, ease:"power3.out"}}, {st + 1.5:.2f});

/* 右侧 DeepSeek Logo 爆发粒子亮光 */
tl.fromTo("#s1-glow-circle", {{scale:0.2, opacity:0}}, {{scale:1.4, opacity:0.8, duration:0.8, ease:"power2.out"}}, {st + 2.6:.2f});
tl.fromTo("#s1-logo-box", {{scale:0.6, rotate:-30}}, {{scale:1.2, rotate:0, duration:0.58, ease:"back.out(1.8)"}}, {st + 2.7:.2f});
tl.to("#s1-logo-box", {{scale:1, duration:0.3, ease:"power1.out"}}, {st + 3.32:.2f});
tl.fromTo("#s1-stamp-mit", {{scale:3.0, opacity:0, rotate:-25}}, {{scale:1, opacity:1, rotate:-6, duration:0.45, ease:"power3.out"}}, {st + 4.2:.2f});
""")
        elif i == 2:
            html_parts.append(f"""
tl.fromTo("#s2-banner", {{scale:0.3, opacity:0}}, {{scale:1, opacity:1, duration:0.5, ease:"back.out(1.8)"}}, {st + 0.4:.2f});
tl.fromTo("#s2-win-old", {{x:-60, opacity:0}}, {{x:0, opacity:1, duration:0.65, ease:"power2.out"}}, {st + 0.15:.2f});
tl.fromTo("#s2-win-new", {{x:60, opacity:0}}, {{x:0, opacity:1, duration:0.65, ease:"power2.out"}}, {st + 0.25:.2f});

/* 左侧警告跳出 + Token 计数器疯狂跳动 */
tl.fromTo("#s2-alert-box", {{scale:0.8, opacity:0}}, {{scale:1, opacity:1, duration:0.4, ease:"back.out(1.5)"}}, {st + 2.2:.2f});
tl.fromTo("#s2-counter-num", {{innerText:"1200"}}, {{innerText:"24800", snap:{{innerText:100}}, duration:1.5, ease:"power2.in"}}, {st + 2.4:.2f});
tl.fromTo("#s2-stamp-fail", {{scale:3.0, opacity:0, rotate:-30}}, {{scale:1, opacity:1, rotate:-10, duration:0.4, ease:"power3.out"}}, {st + 3.2:.2f});

/* 右侧 Append 挂载 + 97% 缓存命中大字跳动 */
tl.fromTo("#s2-append-box", {{y:-30, opacity:0}}, {{y:0, opacity:1, duration:0.5, ease:"back.out(1.6)"}}, {st + 4.5:.2f});
tl.fromTo("#s2-hit-rate", {{innerText:"50.0%"}}, {{innerText:"97.4%", snap:{{innerText:0.1}}, duration:1.2, ease:"power1.out"}}, {st + 4.8:.2f});
tl.fromTo("#s2-stamp-hit", {{scale:3.2, opacity:0, rotate:-22}}, {{scale:1, opacity:1, rotate:-6, duration:0.45, ease:"power3.out"}}, {st + 5.5:.2f});
""")
        elif i == 3:
            html_parts.append(f"""
tl.fromTo("#s3-banner", {{scale:0.3, opacity:0}}, {{scale:1, opacity:1, duration:0.5, ease:"back.out(1.8)"}}, {st + 0.4:.2f});
tl.fromTo("#s3-main-win", {{scale:0.95, opacity:0}}, {{scale:1, opacity:1, duration:0.65, ease:"power2.out"}}, {st + 0.15:.2f});

/* 鼠标指针移动到图片卡片 */
tl.fromTo("#global-cursor", {{x:500, y:200}}, {{x:250, y:120, duration:0.8, ease:"power2.out"}}, {st + 0.8:.2f});

/* 抓取并拖拽图片到输入框 */
tl.to("#global-cursor", {{x:250, y:300, duration:1.0, ease:"power1.inOut"}}, {st + 1.8:.2f});
tl.to("#s3-file-card", {{x:70, y:180, scale:0.7, opacity:0.8, duration:1.0, ease:"power1.inOut"}}, {st + 1.8:.2f});
tl.to("#s3-file-card", {{opacity:0, duration:0.2}}, {st + 2.8:.2f});
tl.set("#s3-attached-tag", {{display:"block"}}, {st + 2.9:.2f});

/* 打字机动画敲入提示词 */
var pTxt = "根据设计图生成 HTML 页面，并在内嵌侧边栏直接预览";
tl.to("#s3-typed-content", {{
  duration: 2.2,
  ease: "none",
  onUpdate: function() {{
    var progress = Math.floor(this.progress() * pTxt.length);
    document.getElementById("s3-typed-content").innerText = pTxt.substring(0, progress);
  }}
}}, {st + 3.2:.2f});

/* 鼠标移动到 Preview 按钮并点击 */
tl.to("#global-cursor", {{x:1560, y:185, duration:1.0, ease:"power2.out"}}, {st + 6.5:.2f});
tl.fromTo("#cursor-ripple", {{x:1560, y:185, scale:0.2, opacity:1}}, {{scale:2.5, opacity:0, duration:0.5}}, {st + 7.5:.2f});
tl.fromTo("#s3-preview-btn", {{scale:1.4, background:"#FF6600"}}, {{scale:1, background:"#00E5FF", duration:0.4, ease:"power2.out"}}, {st + 7.5:.2f});

/* 侧边栏展开与网页实时渲染 */
tl.fromTo("#s3-rendered-view", {{scale:0.85, opacity:0}}, {{scale:1, opacity:1, duration:0.65, ease:"back.out(1.4)"}}, {st + 8.2:.2f});
tl.fromTo("#s3-stamp", {{scale:2.8, opacity:0, rotate:-20}}, {{scale:1, opacity:1, rotate:-5, duration:0.4, ease:"power3.out"}}, {st + 10.0:.2f});
""")
        elif i == 4:
            html_parts.append(f"""
tl.fromTo("#s4-banner", {{scale:0.3, opacity:0}}, {{scale:1, opacity:1, duration:0.5, ease:"back.out(1.8)"}}, {st + 0.4:.2f});
tl.fromTo("#s4-main-win", {{scale:0.95, opacity:0}}, {{scale:1, opacity:1, duration:0.65, ease:"power2.out"}}, {st + 0.15:.2f});

/* 鼠标指针移动到 Pause 按钮并点击 */
tl.to("#global-cursor", {{x:820, y:260, duration:0.8, ease:"power2.out"}}, {st + 1.5:.2f});
tl.fromTo("#cursor-ripple", {{x:820, y:260, scale:0.2, opacity:1}}, {{scale:2.5, opacity:0, duration:0.5}}, {st + 2.3:.2f});
tl.fromTo("#s4-pause-btn", {{scale:1.5, background:"#FFF", color:"#000"}}, {{scale:1, background:"#FF3344", color:"#FFF", duration:0.4}}, {st + 2.3:.2f});
tl.fromTo("#s4-stamp1", {{scale:2.8, opacity:0, rotate:-25}}, {{scale:1, opacity:1, rotate:-6, duration:0.4, ease:"power3.out"}}, {st + 4.5:.2f});
tl.fromTo("#s4-stamp2", {{scale:2.8, opacity:0, rotate:-20}}, {{scale:1, opacity:1, rotate:-5, duration:0.4, ease:"power3.out"}}, {st + 8.5:.2f});
""")
        elif i == 5:
            html_parts.append(f"""
tl.fromTo("#s5-banner", {{scale:0.3, opacity:0}}, {{scale:1, opacity:1, duration:0.5, ease:"back.out(1.8)"}}, {st + 0.4:.2f});
tl.fromTo("#s5-main-win", {{scale:0.95, opacity:0}}, {{scale:1, opacity:1, duration:0.65, ease:"power2.out"}}, {st + 0.15:.2f});

/* 速度数字疯狂飙车 */
tl.fromTo("#s5-speed-num", {{innerText:"0.0"}}, {{innerText:"264.8", snap:{{innerText:0.1}}, duration:1.4, ease:"power2.out"}}, {st + 0.8:.2f});
tl.fromTo("#s5-stamp1", {{scale:2.8, opacity:0, rotate:-20}}, {{scale:1, opacity:1, rotate:-5, duration:0.4, ease:"power3.out"}}, {st + 3.0:.2f});
tl.fromTo("#s5-stamp2", {{scale:2.8, opacity:0, rotate:-22}}, {{scale:1, opacity:1, rotate:-6, duration:0.4, ease:"power3.out"}}, {st + 5.0:.2f});
""")
        elif i == 6:
            html_parts.append(f"""
tl.fromTo("#s6-main-win", {{y:40, opacity:0}}, {{y:0, opacity:1, duration:0.7, ease:"power2.out"}}, {st + 0.15:.2f});

/* 弹幕流依次飘过 */
tl.to("#s6-danmaku-1", {{x:-2400, duration:8.0, ease:"none"}}, {st + 0.5:.2f});
tl.to("#s6-danmaku-2", {{x:-2400, duration:7.5, ease:"none"}}, {st + 1.2:.2f});
tl.to("#s6-danmaku-3", {{x:-2400, duration:8.2, ease:"none"}}, {st + 2.0:.2f});

/* B站三连按钮弹性跳出 */
tl.fromTo("#s6-btn-like", {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.4, ease:"back.out(2.0)"}}, {st + 2.5:.2f});
tl.fromTo("#s6-btn-coin", {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.4, ease:"back.out(2.0)"}}, {st + 2.9:.2f});
tl.fromTo("#s6-btn-fav", {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.4, ease:"back.out(2.0)"}}, {st + 3.3:.2f});
tl.fromTo("#s6-stamp", {{scale:2.8, opacity:0, rotate:-25}}, {{scale:1, opacity:1, rotate:-4, duration:0.45, ease:"power3.out"}}, {st + 4.2:.2f});
""")

    # 5. 字幕驱动逻辑
    html_parts.append("""
/* ================= 字幕驱动 ================= */
function setSub(text, isHl) {
  var el = document.getElementById("sub-text");
  if (!el) return;
  el.innerHTML = isHl ? '<span class="sub-hl">' + text + '</span>' : text;
}

var subtitles = [
""")

    for sub in all_subtitles:
        hl_str = "true" if sub["hl"] else "false"
        safe_txt = sub["text"].replace('"', '\\"')
        html_parts.append(f'  {{ start: {sub["start"]}, end: {sub["end"]}, text: "{safe_txt}", hl: {hl_str} }},')

    html_parts.append(f"""
];

if (subtitles.length > 0) {{
  tl.fromTo("#sub-box", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.28, ease: "power2.out"}}, subtitles[0].start);

  for (var k = 0; k < subtitles.length; k++) {{
    (function(idx) {{
      var sub = subtitles[idx];
      var nextSub = (idx + 1 < subtitles.length) ? subtitles[idx + 1] : null;

      tl.call(function() {{
        setSub(sub.text, sub.hl);
      }}, null, sub.start);

      tl.fromTo("#sub-text", {{opacity: 0.35}}, {{opacity: 1, duration: 0.12, ease: "power1.out"}}, sub.start);

      if (nextSub) {{
        var gap = nextSub.start - sub.end;
        if (gap >= 0.25) {{
          tl.to("#sub-box", {{opacity: 0, y: -6, duration: 0.18, ease: "power2.in"}}, sub.end);
          tl.fromTo("#sub-box", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.25, ease: "power2.out"}}, nextSub.start);
        }}
      }} else {{
        tl.to("#sub-box", {{opacity: 0, y: -8, duration: 0.35, ease: "power2.in"}}, sub.end);
      }}
    }})(k);
  }}
}}

/* 片尾 {total_composition_duration - 4.0:.1f}s ~ {total_composition_duration:.1f}s BGM 优雅淡出 */
tl.to("#bgm", {{volume:0, duration:4.0, ease:"power1.in"}}, {total_composition_duration - 4.0:.2f});

window.__timelines["main"] = tl;
</script>
</body>
</html>
""")

    full_html = "\n".join(html_parts)
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f">> [generate_composition] 成功生成高能极客风实操 HyperFrames HTML: {output_html_path} (时长: {total_composition_duration}s, 大小: {len(full_html)} 字节)")
    return total_composition_duration


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python generate_composition.py <episode.json> <assets_dir> <output_html> [--bgm <bgm_path>]")
        sys.exit(1)

    ep_p = Path(sys.argv[1])
    assets_p = Path(sys.argv[2])
    out_p = Path(sys.argv[3])
    bgm_p = "assets/music/bgm_cyberpunk_city.mp3"
    if not (assets_p / "music" / "bgm_cyberpunk_city.mp3").exists():
        # 若不存在则查找其他非旧版候选
        cand = list((assets_p / "music").glob("bgm_*.mp3"))
        cand = [c for c in cand if c.name != "bgm_tech.mp3"]
        if cand:
            bgm_p = f"assets/music/{cand[0].name}"
        else:
            bgm_p = "assets/music/bgm_tech.mp3"

    if "--bgm" in sys.argv:
        idx = sys.argv.index("--bgm")
        if idx + 1 < len(sys.argv):
            bgm_p = sys.argv[idx + 1]

    build_composition(ep_p, assets_p, out_p, bgm_p)
