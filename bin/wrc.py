#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WRC 拉力 YouTube→中文抖音竖屏流水线 CLI（bin/wrc.py）

规格来源：
  apps/wrc/specs/pipeline-cli-spec.md   (形态/状态机/DB/轻重拆分)
  script-prompt.md / wrc_episode.schema.json               (脚本)
  frame-selection-spec.md                            (抽帧/截片)
  template/generate_composition.py                   (合成)
  package-spec.md                                    (成品包)
  #59/#60                                            (TTS 情绪 0.325)

用法:
  python bin/wrc.py new <url>                          # 轻：建项目 + 下载
  python bin/wrc.py script <id>                        # 轻：转录 → 停在脚本闸门
  python bin/wrc.py approve-script <id>                # 轻：校验集 JSON → 放行
  python bin/wrc.py render-assets <id> [--json]        # 重：TTS + 抽帧/截片（Compute Worker）
  python bin/wrc.py render-video <id> [--json]         # 重：合成 + 渲染 + BGM（Compute Worker）
  python bin/wrc.py package <id>                       # 轻：成品包
  python bin/wrc.py run <url>                          # 轻：new + script，停在闸门
  python bin/wrc.py run-heavy <id> [--json]            # 重：render-assets + render-video + package
  python bin/wrc.py status                             # 队列状态
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))

DB_PATH = OMO_ROOT / "projects" / "wrc" / "tracking.db"
PROJECTS_ROOT = OMO_ROOT / "projects"
GEN_COMPOSE = OMO_ROOT / "apps" / "wrc" / "template" / "generate_composition.py"
SCHEMA_PATH = OMO_ROOT / "schemas" / "artifacts" / "wrc_episode.schema.json"
FFMPEG = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"
TTS_TEXT_FIELDS = ["narration"]
TTS = dict(use_emo_text=True, emo_alpha=0.325, seed=42, speed=1.0,
           spk_audio_prompt="D:/index-tts/my_voice.wav")

STATUS_FLOW = ["pending", "downloading", "transcribing", "scripting",
               "awaiting_script_review", "tts", "frames", "composing",
               "rendering", "review", "packaged", "published"]
LIGHT = {"new", "script", "approve-script", "package", "run", "status"}
HEAVY = {"render-assets", "render-video", "run-heavy"}


# ---------------------------------------------------------------- helpers
def emit_json(obj: dict):
    print(json.dumps(obj, ensure_ascii=False))


def run(cmd, cwd=None, env=None, timeout=None):
    """subprocess 包装（inherit/无管道捕获，避免沙箱 EPERM）"""
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sh(cmd, cwd=None, env=None, timeout=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- DB
def db_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""CREATE TABLE IF NOT EXISTS videos(
        video_id TEXT PRIMARY KEY, url TEXT, title TEXT, status TEXT,
        project_dir TEXT, created_at TEXT)""")
    return c


def set_status(video_id, status):
    c = db_conn()
    c.execute("UPDATE videos SET status=? WHERE video_id=?", (status, video_id))
    c.commit()
    c.close()


def get_video(video_id):
    c = db_conn()
    row = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    c.close()
    if not row:
        return None
    cols = ["video_id", "url", "title", "status", "project_dir", "created_at"]
    return dict(zip(cols, row))


def project_dir(video_id):
    return PROJECTS_ROOT / f"wrc-{video_id}"


# ---------------------------------------------------------------- stages
def stage_new(url, args):
    """下载源视频"""
    vid = sh(["yt-dlp", "--no-warnings", "--print", "%(id)s", url], timeout=120)
    if vid.returncode != 0:
        return {"ok": False, "error": "yt-dlp 无法解析 URL"}
    video_id = vid.stdout.strip().splitlines()[-1]
    if get_video(video_id):
        return {"ok": True, "video_id": video_id, "note": "已存在"}
    proj = project_dir(video_id)
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    (proj / "artifacts" / "episodes").mkdir(parents=True, exist_ok=True)
    (proj / "artifacts" / "frames").mkdir(parents=True, exist_ok=True)
    (proj / "renders").mkdir(parents=True, exist_ok=True)
    r = run(["yt-dlp", "--no-warnings", "-f", "bv*[height<=1080]+ba/b[height<=1080]",
             "--merge-output-format", "mp4",
             "-o", str(proj / "assets" / "original.%(ext)s"), url])
    if r.returncode != 0:
        return {"ok": False, "error": "下载失败"}
    title = sh(["yt-dlp", "--no-warnings", "--print", "%(title)s", url], timeout=120).stdout.strip()
    c = db_conn()
    c.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?)",
              (video_id, url, title, "downloading", str(proj), time.strftime("%Y-%m-%dT%H:%M:%S")))
    c.commit()
    c.close()
    set_status(video_id, "transcribing")
    return {"ok": True, "video_id": video_id, "title": title, "project_dir": str(proj)}


def stage_script(video_id, args):
    """转录（Whisper）→ transcript.json → 停在脚本闸门（agent 写集 JSON）"""
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    src = proj / "assets" / "original.mp4"
    if not src.exists():
        return {"ok": False, "error": "缺 original.mp4"}
    audio = proj / "assets" / "original.wav"
    run([FFMPEG, "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)], timeout=1800)
    from tools.analysis.transcriber import Transcriber
    res = Transcriber().execute({"input_path": str(audio), "output_dir": str(proj / "artifacts")})
    if not res.success:
        return {"ok": False, "error": f"转录失败: {res.error}"}
    # transcriber 按输入文件名命名输出（original.wav -> original_transcript.json）；统一为 transcript.json
    out_files = list((proj / "artifacts").glob("*_transcript.json"))
    if not out_files:
        return {"ok": False, "error": "转录未产出文件"}
    transcript_path = proj / "artifacts" / "transcript.json"
    if out_files[0] != transcript_path:
        import shutil
        shutil.copy2(out_files[0], transcript_path)
    set_status(video_id, "scripting")
    return {"ok": True, "video_id": video_id, "transcript": str(transcript_path),
            "next": "请按 apps/wrc/specs/script-prompt.md 生成 artifacts/episodes/<n>.json（含 display 块），"
                    "然后运行 approve-script"}


def stage_approve_script(video_id, args):
    """校验集 JSON（存在 + 基本结构 + 钩子规则）→ 放行 tts"""
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    eps = sorted((proj / "artifacts" / "episodes").glob("*.json"))
    if not eps:
        return {"ok": False, "error": "没有集 JSON（先 script 后生成）"}
    problems = []
    for p in eps:
        d = json.loads(p.read_text(encoding="utf-8"))
        scenes = d.get("episode", {}).get("scenes", [])
        if not scenes:
            problems.append(f"{p.name}: 无 scenes")
        if scenes and scenes[0].get("hook_type") != "open_conflict":
            problems.append(f"{p.name}: s0 钩子非 open_conflict")
        if scenes and scenes[-1].get("hook_type") != "follow":
            problems.append(f"{p.name}: 末幕钩子非 follow")
        for sc in scenes:
            if not sc.get("narration"):
                problems.append(f"{p.name} {sc.get('id')}: 缺 narration")
            if not sc.get("display"):
                problems.append(f"{p.name} {sc.get('id')}: 缺 display（模板必需）")
            for i, vis in enumerate(sc.get("visuals", [])):
                if not vis.get("asset_path"):
                    problems.append(f"{p.name} {sc.get('id')} v{i}: 缺 asset_path（先 render-assets？）")
    if problems:
        return {"ok": False, "error": "校验未通过", "problems": problems[:20]}
    set_status(video_id, "tts")
    return {"ok": True, "video_id": video_id, "episodes": [p.name for p in eps]}


def stage_render_assets(video_id, args):
    """重：IndexTTS 配音（情绪 0.325）+ 抽帧/截片（frames.json）"""
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    assets = proj / "assets"
    frames_json = proj / "artifacts" / "frames" / "frames.json"
    if not frames_json.exists():
        return {"ok": False, "error": "缺 frames.json（agent 按 frame-selection-spec.md 生成时间戳提案）"}
    eps = sorted((proj / "artifacts" / "episodes").glob("*.json"))
    os.environ.setdefault("INDEXTTS_USE_QWEN_EMO", "1")
    from lib.gpu_lock import gpu_lock
    from tools.audio.indextts_tts import IndexTTS2TTS
    tool = IndexTTS2TTS()
    set_status(video_id, "tts")
    with gpu_lock(label=f"wrc-tts-{video_id}", timeout=1800, heartbeat=30):
        for p in eps:
            d = json.loads(p.read_text(encoding="utf-8"))
            scenes = d["episode"]["scenes"]
            for si, sc in enumerate(scenes):
                out = assets / f"s{si}.wav"
                if out.exists():
                    continue
                res = tool.execute({"text": sc["narration"], "output_path": str(out),
                                    "spk_audio_prompt": TTS["spk_audio_prompt"],
                                    "use_emo_text": TTS["use_emo_text"],
                                    "emo_alpha": TTS["emo_alpha"], "seed": TTS["seed"],
                                    "speed": TTS["speed"]})
                if not res.success:
                    return {"ok": False, "error": f"{p.name} s{si} TTS 失败: {res.error}"}
    # 抽帧/截片
    set_status(video_id, "frames")
    fm = json.loads(frames_json.read_text(encoding="utf-8"))
    for item in fm.get("frames", []):
        t = item["timestamp"]
        vis_type = item.get("type", "image")
        out = assets / item["asset_path"]
        if vis_type == "clip":
            run([FFMPEG, "-y", "-ss", str(t), "-i", str(proj / "assets" / "original.mp4"),
                 "-t", str(item.get("clip_duration_s", 8)), "-c:v", "libx264", "-crf", "20",
                 str(out)], timeout=600)
        else:
            run([FFMPEG, "-y", "-ss", str(t), "-i", str(proj / "assets" / "original.mp4"),
                 "-frames:v", "1", str(out)], timeout=120)
    set_status(video_id, "composing")
    return {"ok": True, "video_id": video_id, "tts": "done", "frames": len(fm.get("frames", []))}


def _ffprobe_dur(p):
    r = sh([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of",
            "csv=p=0", str(p)], timeout=60)
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def stage_render_video(video_id, args):
    """重：模板生成 + hyperframes 渲染 + BGM 混音"""
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    assets = proj / "assets"
    eps = sorted((proj / "artifacts" / "episodes").glob("*.json"))
    if not eps:
        return {"ok": False, "error": "没有集 JSON"}
    set_status(video_id, "composing")
    # 回填 audio_s + 每幕 asset_path（从 frames.json 映射 visuals）
    frames_json = proj / "artifacts" / "frames" / "frames.json"
    fm = json.loads(frames_json.read_text(encoding="utf-8")) if frames_json.exists() else {"frames": []}
    fmap = {}
    for item in fm.get("frames", []):
        fmap.setdefault(item.get("scene"), []).append(item)
    for p in eps:
        d = json.loads(p.read_text(encoding="utf-8"))
        scenes = d["episode"]["scenes"]
        for si, sc in enumerate(scenes):
            wav = assets / f"s{si}.wav"
            if wav.exists():
                sc["audio_s"] = _ffprobe_dur(wav)
            for i, vis in enumerate(sc.get("visuals", [])):
                if not vis.get("asset_path"):
                    cands = fmap.get(sc["id"], [])
                    if i < len(cands):
                        vis["asset_path"] = cands[i]["asset_path"]
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    # 逐集合成 + 渲染
    env = dict(os.environ)
    env["npm_config_cache"] = str(OMO_ROOT / ".npm-cache")
    for p in eps:
        ep_proj = proj / "compose" / p.stem
        (ep_proj / "assets").mkdir(parents=True, exist_ok=True)
        import shutil
        for f in assets.iterdir():
            if f.is_file():
                # 总是覆盖复制：避免 compose/ 残留旧版资产（如重抽的片段/帧）导致渲染用旧文件
                shutil.copy2(f, ep_proj / "assets" / f.name)
        (ep_proj / "meta.json").write_text(json.dumps({"id": p.stem, "name": p.stem}), encoding="utf-8")
        (ep_proj / "package.json").write_text(json.dumps({
            "name": p.stem, "private": True, "type": "module",
            "scripts": {"render": "npx --yes hyperframes@0.7.109 render"}}), encoding="utf-8")
        r = run([sys.executable, str(GEN_COMPOSE), str(p), str(ep_proj / "assets"), str(ep_proj / "index.html")],
                env=env, timeout=120)
        if r.returncode != 0:
            return {"ok": False, "error": f"{p.name} 模板生成失败"}
        (ep_proj / "renders").mkdir(exist_ok=True)
        for old in (ep_proj / "renders").glob("*.mp4"):
            old.unlink(missing_ok=True)  # 清旧渲染，避免 glob 累积
        r = run(["npm.cmd", "run", "render"], cwd=ep_proj, env=env, timeout=3600)
        if r.returncode != 0:
            return {"ok": False, "error": f"{p.name} hyperframes 渲染失败"}
    # BGM 混音 + 汇总到 renders/（每集取最新产物）
    set_status(video_id, "rendering")
    rendered = []
    for rd in sorted((proj / "compose").glob("*/renders")):
        mps = sorted(rd.glob("*.mp4"))
        if mps:
            rendered.append(mps[-1])
    out_dir = proj / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not rendered:
        return {"ok": False, "error": "没有渲染产物"}
    final = []
    for i, mp4 in enumerate(rendered):
        dur = _ffprobe_dur(mp4) or 60.0
        out = out_dir / (f"episode{i + 1}.mp4" if len(rendered) > 1 else "final.mp4")
        bgm = assets / "bgm_epic.mp3"
        if bgm.exists():
            fade_out = max(0.0, dur - 1.5)
            fc = (f"[1:a]aloop=loop=10:size=0,atrim=duration={dur},volume=0.25,"
                  f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out}:d=1.5[bgm];"
                  f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]")
            r = run([FFMPEG, "-y", "-i", mp4, "-stream_loop", "1", "-i", str(bgm),
                     "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                     "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)], timeout=1800)
        else:
            run([FFMPEG, "-y", "-i", mp4, "-c", "copy", str(out)], timeout=600)
        final.append(str(out))
    set_status(video_id, "review")
    return {"ok": True, "video_id": video_id, "renders": final}


def stage_package(video_id, args):
    """成品包：封面 + 标题/简介 + 目录组装"""
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    meta = proj / "artifacts" / "package-meta.json"
    if not meta.exists():
        return {"ok": False, "error": "缺 package-meta.json（agent 生成 title/desc）"}
    pm = json.loads(meta.read_text(encoding="utf-8"))
    renders = sorted((proj / "renders").glob("*.mp4"))
    if not renders:
        return {"ok": False, "error": "没有定版渲染"}
    out_list = []
    for i, mp4 in enumerate(renders):
        info = pm.get(str(i + 1)) or pm.get(mp4.stem) or {}
        pkg = proj / "package" / f"{i + 1}"
        pkg.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(mp4, pkg / "video.mp4")
        (pkg / "title.txt").write_text(info.get("title", ""), encoding="utf-8")
        if info.get("title_alt"):
            (pkg / "title_alt.txt").write_text(info["title_alt"], encoding="utf-8")
        (pkg / "desc.txt").write_text(info.get("desc", ""), encoding="utf-8")
        # 封面：ffmpeg 抽帧 + PIL 绘制（黑底压底 + 标题大字 + 红字角标）
        cover_frame = pkg / "_frame.jpg"
        run([FFMPEG, "-y", "-ss", str(info.get("cover_second", 1.0)), "-i", str(mp4),
             "-frames:v", "1", str(cover_frame)], timeout=120)
        try:
            from PIL import Image, ImageDraw, ImageFont
            frame = Image.open(cover_frame).convert("RGB")
            W, H = frame.size
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(overlay)
            d.rectangle([0, int(H * 0.62), W, H], fill=(10, 14, 26, 217))
            title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 72)
            badge_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 40)
            title = info.get("title", "") or ""
            max_w = W - 96
            lines, cur = [], ""
            for ch in title:
                if cur and d.textlength(cur + ch, font=title_font) > max_w:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            if cur:
                lines.append(cur)
            y = int(H * 0.64)
            for line in lines[:2]:
                tw = d.textlength(line, font=title_font)
                d.text(((W - tw) / 2, y), line, font=title_font, fill=(255, 255, 255))
                y += 92
            badge = f"第{info.get('index', i + 1)}集"
            btw = d.textlength(badge, font=badge_font)
            d.text((W - btw - 48, 48), badge, font=badge_font, fill=(255, 59, 48))
            Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB").save(
                pkg / "cover.jpg", quality=92)
        except Exception as ex:
            return {"ok": False, "error": f"封面生成失败: {ex}"}
        cover_frame.unlink(missing_ok=True)
        out_list.append(str(pkg))
    set_status(video_id, "packaged")
    return {"ok": True, "video_id": video_id, "packages": out_list}


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(
        description="WRC 拉力 YouTube→中文抖音竖屏流水线 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出单行 JSON 摘要")
    common.add_argument("--quiet", action="store_true", help="抑制进度输出")
    sub = parser.add_subparsers(dest="command", title="子命令")

    p_new = sub.add_parser("new", parents=[common], help="轻：建项目 + 下载")
    p_new.add_argument("url")
    p_script = sub.add_parser("script", parents=[common], help="轻：转录 → 停在脚本闸门")
    p_script.add_argument("video_id")
    p_app = sub.add_parser("approve-script", parents=[common], help="轻：校验集 JSON → 放行")
    p_app.add_argument("video_id")
    p_ra = sub.add_parser("render-assets", parents=[common], help="重：TTS + 抽帧/截片（Worker）")
    p_ra.add_argument("video_id")
    p_rv = sub.add_parser("render-video", parents=[common], help="重：合成 + 渲染 + BGM（Worker）")
    p_rv.add_argument("video_id")
    p_pkg = sub.add_parser("package", parents=[common], help="轻：成品包")
    p_pkg.add_argument("video_id")
    p_run = sub.add_parser("run", parents=[common], help="轻：new + script，停在闸门")
    p_run.add_argument("url")
    p_rh = sub.add_parser("run-heavy", parents=[common], help="重：assets+video+package（Worker）")
    p_rh.add_argument("video_id")
    sub.add_parser("status", parents=[common], help="队列状态")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        c = db_conn()
        rows = c.execute("SELECT status, COUNT(*) FROM videos GROUP BY status").fetchall()
        c.close()
        summary = {s: 0 for s in STATUS_FLOW}
        for s, n in rows:
            summary[s] = n
        if args.json:
            emit_json(summary)
        else:
            for s in STATUS_FLOW:
                if summary[s]:
                    print(f"{s}: {summary[s]}")
        sys.exit(0)

    if args.command == "new":
        res = stage_new(args.url, args)
    elif args.command == "script":
        res = stage_script(args.video_id, args)
    elif args.command == "approve-script":
        res = stage_approve_script(args.video_id, args)
    elif args.command == "render-assets":
        res = stage_render_assets(args.video_id, args)
    elif args.command == "render-video":
        res = stage_render_video(args.video_id, args)
    elif args.command == "package":
        res = stage_package(args.video_id, args)
    elif args.command == "run":
        r1 = stage_new(args.url, args)
        if not r1.get("ok"):
            res = r1
        else:
            res = stage_script(r1["video_id"], args)
            res["video_id"] = r1["video_id"]
    elif args.command == "run-heavy":
        res = stage_render_assets(args.video_id, args)
        if res.get("ok"):
            res = stage_render_video(args.video_id, args)
        if res.get("ok"):
            res = stage_package(args.video_id, args)
    else:
        res = {"ok": False, "error": f"未知命令 {args.command}"}

    if args.json or res.get("heavy"):
        emit_json(res)
    elif not args.quiet:
        if res.get("ok"):
            print(f"OK {args.command}: {json.dumps({k: v for k, v in res.items() if k != 'ok'}, ensure_ascii=False)}")
        else:
            print(f"FAIL {args.command}: {res.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
