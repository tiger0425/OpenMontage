#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup-video 调校视频→抖音竖屏 批量流水线 CLI（bin/setup_video.py）

规格来源：
  apps/setup-video/specs/pipeline-cli-spec.md          (形态/状态机/轻重拆分)
  apps/setup-video/specs/script-prompt.md              (脚本工单)
  apps/setup-video/specs/banned-words.md               (违禁词表)
  schemas/artifacts/setup_video_episode.schema.json    (集 JSON schema)
  apps/setup-video/template/instantiate_template.py    (模板实例化，D6 幕边界=TTS 实测时长)
  projects/setup-video-template/TEMPLATE.md v0.2       (模板契约)

用法:
  python bin/setup_video.py scan <list.txt>            # 轻：导入 URL 列表（每行一条，可 `URL 备注`）
  python bin/setup_video.py fetch <id>|--all           # 轻：yt-dlp HD 梯度下载（2 并发）
  python bin/setup_video.py extract <id>               # 轻：采样帧 + MiniMax-M3 OCR + review.html
  python bin/setup_video.py review <id>                # 轻：重新生成/打开数值对照表
  python bin/setup_video.py approve-review <id> [--fix k=v ...]   # 轻：人核放行（修正写回 ocr.json）
  python bin/setup_video.py script <id>                # 轻：Whisper 转录 + 脚本工单（agent 写 episode.json）
  python bin/setup_video.py approve-script <id>        # 轻：schema + 违禁词 + 预算校验 → 放行
  python bin/setup_video.py assets <id> [--json]       # 重：TTS + 素材制备（Compute Worker, GPU 锁）
  python bin/setup_video.py render <id> [--json]       # 重：实例化 + 渲染 + QA + 封面 + 成品包（Worker）
  python bin/setup_video.py status [--json]            # 队列状态
  python bin/setup_video.py retry <id>                 # 从失败阶段续跑
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))

DB_PATH = OMO_ROOT / "projects" / "setup-video" / "tracking.db"
PROJECTS_ROOT = OMO_ROOT / "projects"
GEN_COMPOSE = OMO_ROOT / "apps" / "setup-video" / "template" / "instantiate_template.py"
SCHEMA_PATH = OMO_ROOT / "schemas" / "artifacts" / "setup_video_episode.schema.json"
SPEC_DIR = OMO_ROOT / "apps" / "setup-video" / "specs"
M3_SCRIPT = OMO_ROOT / ".agents" / "skills" / "minimax-m3-vision" / "scripts" / "analyze_media.py"
FALLBACK_BGM = OMO_ROOT / "projects" / "setup-video-template" / "assets" / "bgm.mp3"
FFMPEG = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"

# 2026-08-29 用户定：去 auto 情绪 → 固定 calm 情绪向量（段间语气一致、无拖腔）。
# use_emo_text=False → 工具 resolve_emotion_mode 走 fixed 模式，emo_vector=CALM_EMO_VECTOR，emo_alpha 强制 1.0。
TTS = dict(use_emo_text=False, emo_alpha=1.0, seed=42, speed=1.0,
           spk_audio_prompt="D:/index-tts/my_voice.wav")
YTDLP_FMT = "bv*[height>=1080]+ba/bv*[height>=720]+ba/b"

STATUS_FLOW = ["pending", "downloading", "extracting", "awaiting_review", "scripted",
               "awaiting_script", "ready", "assets", "ready_render", "rendering",
               "qa", "packaged", "failed"]
LIGHT = {"scan", "fetch", "extract", "review", "approve-review", "script",
         "approve-script", "status", "retry"}
HEAVY = {"assets", "render"}
TOTAL_MIN, TOTAL_MAX = 40.0, 67.0   # 成片时长硬闸（2026-08-28 实测校准：IndexTTS 2.5 语速≈5.0字/秒，
                                     # 6 段 179 字实长 34.4s → 成片约 42s；原 55s 下限过严）


# ---------------------------------------------------------------- helpers
def emit_json(obj):
    print(json.dumps(obj, ensure_ascii=False))


def run(cmd, cwd=None, env=None, timeout=None):
    """inherit/DEVNULL，避免沙箱管道 EPERM（wrc.py 同款）"""
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


def ffprobe_dur(p):
    r = sh([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], timeout=60)
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def slugify(s, fallback="video"):
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s, flags=re.UNICODE).strip("-")
    return s[:60] or fallback


# ---------------------------------------------------------------- DB
def db_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""CREATE TABLE IF NOT EXISTS videos(
        video_id TEXT PRIMARY KEY, url TEXT, title TEXT, game TEXT, slug TEXT,
        status TEXT, failed_stage TEXT, last_error TEXT,
        project_dir TEXT, created_at TEXT)""")
    return c


def set_status(video_id, status, err=None, failed_stage=None):
    c = db_conn()
    c.execute("UPDATE videos SET status=?, last_error=?, failed_stage=? WHERE video_id=?",
              (status, err, failed_stage, video_id))
    c.commit()
    c.close()


def get_video(video_id):
    c = db_conn()
    row = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    c.close()
    if not row:
        return None
    cols = ["video_id", "url", "title", "game", "slug", "status", "failed_stage",
            "last_error", "project_dir", "created_at"]
    return dict(zip(cols, row))


def fail(video_id, stage, err):
    set_status(video_id, "failed", err=err, failed_stage=stage)
    return {"ok": False, "error": err, "failed_stage": stage}


# ---------------------------------------------------------------- scan
def stage_scan(args):
    list_file = Path(args.list)
    if not list_file.exists():
        return {"ok": False, "error": f"列表不存在: {list_file}"}
    added, skipped = [], []
    c = db_conn()
    for line in list_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        url, note = parts[0], (parts[1].strip() if len(parts) > 1 else "")
        m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
        vid = m.group(1) if m else slugify(url)[:20]
        if c.execute("SELECT 1 FROM videos WHERE video_id=?", (vid,)).fetchone():
            skipped.append(vid)
            continue
        proj = PROJECTS_ROOT / "setup-video" / "_incoming" / vid
        c.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (vid, url, note, "", "", "pending", None, None, str(proj),
                   time.strftime("%Y-%m-%dT%H:%M:%S")))
        added.append(vid)
    c.commit()
    c.close()
    return {"ok": True, "added": added, "skipped_existing": skipped}


# ---------------------------------------------------------------- fetch
def fetch_one(vid):
    v = get_video(vid)
    if not v:
        return vid, False, "未找到"
    if v["status"] not in ("pending", "failed", "downloading"):
        return vid, True, f"跳过（状态 {v['status']}）"
    proj = Path(v["project_dir"])
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    set_status(vid, "downloading")
    r = run(["yt-dlp", "--no-warnings", "-f", YTDLP_FMT, "--merge-output-format", "mp4",
             "-o", str(proj / "assets" / "original.%(ext)s"), v["url"]], timeout=1800)
    src = proj / "assets" / "original.mp4"
    if r.returncode != 0 or not src.exists():
        fail(vid, "downloading", "yt-dlp 下载失败（HD 梯度全空？）")
        return vid, False, "下载失败"
    # 取最后一个非空行——避开 Python 导入期 warning 混入 stdout（sh 合并了 stderr）
    title_lines = [x.strip() for x in sh(
        ["yt-dlp", "--no-warnings", "--print", "%(title)s", v["url"]],
        timeout=120).stdout.splitlines() if x.strip()]
    title = title_lines[-1] if title_lines else v["title"]
    c = db_conn()
    c.execute("UPDATE videos SET title=? WHERE video_id=?", (title or v["title"], vid))
    c.commit()
    c.close()
    set_status(vid, "pending")   # 等下一阶段 extract
    return vid, True, title


def stage_fetch(args):
    if getattr(args, "all", False):
        c = db_conn()
        vids = [r[0] for r in c.execute(
            "SELECT video_id FROM videos WHERE status IN ('pending','failed')").fetchall()]
        c.close()
    else:
        vids = [args.video_id]
    results = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(fetch_one, v) for v in vids]
        for f in as_completed(futs):
            vid, ok, note = f.result()
            results[vid] = {"ok": ok, "note": note}
    bad = [k for k, v in results.items() if not v["ok"]]
    return {"ok": not bad, "results": results, "failed": bad}


# ---------------------------------------------------------------- extract
EXTRACT_PROMPT = (
    "这是赛车游戏调校视频里的一帧画面。请判断并输出 JSON（只输出 JSON，不要其他文字）：\n"
    '{"kind": "config|diagram|other", '
    '"page": "当前页面名", '
    '"settings": [{"name": "...", "value": "...", "unit": "..."}]}\n'
    "kind 判定：config=游戏内调校界面（顶部tab栏+车视角+参数面板）；diagram=标题卡/零件示意图；"
    "other=比赛/回放/排行榜/其他。\n"
    "page：当前页面名，**唯一依据是顶部 tab 栏中当前选中（高亮）的 tab 名（tab 在上方/左上区域）；"
    "红框/高亮的参数行只是光标正在调的项，不代表页面。**\n"
    "settings：若 kind=config，精确转写画面上所有可见调校参数（数字原样转写，不要推测）；"
    "否则返回空数组。"
)


def _m3_analysis(paths, prompt, tag):
    """跑 analyze_media.py（-o 落盘），返回 analysis dict；失败返回 None。"""
    out = Path("tmp") / "setup-video-queue" / f"m3_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = sh([sys.executable, str(M3_SCRIPT), *[str(p) for p in paths],
            "-p", prompt, "-q", "-o", str(out)], timeout=900)
    if r.returncode != 0 or not out.exists():
        return None
    try:
        return json.loads(out.read_text(encoding="utf-8")).get("analysis") or {}
    except Exception:
        return None


def _json_block(text, key=None):
    """从模型文本里抠平衡的 {...} 块；key 给定时返回第一个含该键的块。"""
    text = text or ""
    starts = [m.start() for m in re.finditer(r"\{", text)]
    for start in starts:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        blk = json.loads(text[start:i + 1])
                    except Exception:
                        break
                    if key is None or key in blk:
                        return blk
                    break
    return None


def stage_extract(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    src = proj / "assets" / "original.mp4"
    if not src.exists():
        return fail(video_id, "extracting", "缺 original.mp4（先 fetch）")
    set_status(video_id, "extracting")
    frames_dir = proj / "artifacts" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f_*.jpg"):
        old.unlink()
    for old in frames_dir.glob("_s_*.jpg"):
        old.unlink()
    dur = ffprobe_dur(src)
    if not dur:
        return fail(video_id, "extracting", "ffprobe 失败")
    # 采样 = 画面稳定性检测（用户洞察：设置界面背景静止）：
    # 每秒 1 帧全量抽取 → 相邻帧哈希分组 → 静止段(≥2s)取段尾最后帧（=调完的落定值）；
    # 短段是转场/行车镜头，直接丢弃。数字微调不影响 8x8 哈希，整段保持稳定。
    run([FFMPEG, "-y", "-ss", "2", "-i", str(src), "-vf", "fps=1,scale=320:-2",
         "-q:v", "5", str(frames_dir / "_s_%04d.jpg")], timeout=1800)
    seq = sorted(frames_dir.glob("_s_*.jpg"))
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        Image = ImageFilter = None
    if Image is None:
        return fail(video_id, "extracting", "缺 Pillow，无法做稳定性采样/聚类")

    def _hash(p):
        img = Image.open(p).convert("L").resize((8, 8))
        px = [img.getpixel((x, y)) for y in range(8) for x in range(8)]
        avg = sum(px) / 64.0
        return "".join("1" if v >= avg else "0" for v in px)

    def _ham(a, b):
        return sum(x != y for x, y in zip(a, b))

    runs = []   # [(start_i, end_i)] 含端点，帧下标（0 基，对应时间 2+i 秒）
    if Image is not None and seq:
        start = 0
        for i in range(1, len(seq) + 1):
            unstable = (i == len(seq)) or (_ham(_hash(seq[i - 1]), _hash(seq[i])) > 10)
            if unstable:
                runs.append((start, i - 1))
                start = i
    else:
        runs = [(0, len(seq) - 1)] if seq else []

    kept = []
    for s, e in runs:
        # 任何稳定段都保留段尾帧（页面可能只闪现 1-2s，不能设最短停留门槛）；
        # 去重不靠画面哈希（会误并同布局不同页面），靠读出的内容折叠
        t = round(2 + e, 1)     # 段尾最后帧 = 落定值
        dst = frames_dir / f"f_{len(kept):03d}.jpg"
        # 关键：落盘帧必须按原分辨率重抽（1280 宽）——320px 缩略图喂 M3 读不出 UI 小字号数值
        r = run([FFMPEG, "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                 "-q:v", "2", "-vf", "scale=1280:-2", str(dst)], timeout=120)
        if r.returncode != 0 or not dst.exists():
            continue
        kept.append((dst, t))
        if len(kept) >= 250:
            break
    for old in seq:
        old.unlink()
    frames = kept
    if not frames:
        return fail(video_id, "extracting", "抽帧为空")

    # ---- 逐帧读数：每个稳定段尾帧一次 M3（不做任何画面归并，覆盖完整）----
    # 去重交给读出内容：同类别连续帧留最后一张；（类别,数值）完全相同也只留最后出现——"最后页"
    CAT_KEYWORDS = [("gearbox", ["gearbox", "变速箱", "齿轮"]),
                    ("suspensions", ["suspension", "悬挂"]),
                    ("dampers", ["damper", "阻尼"]),
                    ("axles", ["axle", "防倾杆"]),
                    ("differentials", ["differential", "差速"]),
                    ("wheels", ["wheel", "轮胎", "tyre"]),
                    ("brakes", ["brake", "刹车"]),
                    ("electronics", ["electronic", "电子", "abs", "tcs"])]

    records = [_read_frame_record(src, p, t) for p, t in frames]
    records.sort(key=lambda r: r["ts"])
    records = _collapse_final(records)
    # 自动召回审计：网格图对账 → 缺页定点补读 → 仍缺则 needs_review（人核兜底，绝不静默）
    gaps = _recall_audit(proj, frames, records, video_id, src)
    records = _collapse_final(records)
    extracted = sum(len(r["values"]) for r in records
                    if r["kind"] == "config" and not r.get("superseded"))

    ocr = {"video_id": video_id, "duration": dur, "frames": records,
           "human_fixed": {}, "needs_review": gaps}
    ocr_path = proj / "artifacts" / "ocr.json"
    ocr_path.write_text(json.dumps(ocr, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review_html(v, ocr)
    set_status(video_id, "awaiting_review")
    n_conf = sum(1 for x in records if x["kind"] == "config")
    return {"ok": True, "video_id": video_id, "frames": len(frames),
            "config_frames": n_conf, "values_extracted": extracted, "ocr": str(ocr_path),
            "next": f"人工核对 {ocr_path.parent / 'review.html'} 后: approve-review {video_id} [--fix 参数=值]"}


CAT_KEYWORDS = [("gearbox", ["gearbox", "变速箱", "齿轮", "gear"]),
                ("suspensions", ["suspension", "悬挂", "spring", "弹簧", "ride height", "adjuster"]),
                ("dampers", ["damper", "阻尼", "rebound", "回弹", "bump"]),
                ("axles", ["axle", "防倾杆", "anti-roll", "sway bar"]),
                ("differentials", ["differential", "差速", "lsd", "preload", "ramp", "plates"]),
                ("wheels", ["wheel", "轮胎", "tyre", "tire", "pressure", "psi", "camber", "toe",
                            "alignment", "定位"]),
                ("brakes", ["brake", "刹车", "bias", "handbrake", "pad", "caliper",
                            "master cylinder"]),
                ("electronics", ["electronic", "电子", "abs", "tcs", "lights"])]


def _assign_categories(records):
    """空类别 config 页按参数名关键词反推类别（如 Anti-roll→axles、Spring→suspensions）。"""
    for r in records:
        if r["kind"] != "config" or r.get("category"):
            continue
        hay = " ".join(r["values"].keys()).lower()
        for c, kws in CAT_KEYWORDS:
            if any(k in hay for k in kws):
                r["category"] = c
                break
    return records


RECALL_PROMPT = (
    "这是赛车游戏视频稳定画面的网格图，每格上方有黄色秒标。"
    "找出所有显示【游戏内调校/设置界面】的格子（特征：有参数面板/数值/滑块/确认按钮）。"
    '输出 JSON：{"seconds": [整数值秒标列表]}。只输出 JSON，不要其他文字。'
)


def _grid_cells(frames, idx):
    """[(path, ts)...]（<=80 格）→ 带秒标网格图。"""
    from PIL import Image, ImageDraw, ImageFont
    CELL_W, CELL_H, LABEL, COLS = 240, 135, 20, 8
    n = len(frames)
    rows = (n + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL_W, rows * (CELL_H + LABEL)), (18, 18, 24))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, (p, ts) in enumerate(frames):
        cx, cy = (i % COLS) * CELL_W, (i // COLS) * (CELL_H + LABEL)
        img = Image.open(p).convert("RGB").resize((CELL_W, CELL_H))
        sheet.paste(img, (cx, cy + LABEL))
        d.text((cx + 4, cy + 3), f"{int(ts)}s", fill=(255, 214, 10), font=font)
    out = Path("tmp") / "setup-video-queue" / f"audit_{idx}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


def _read_frame_record(src, p, t, prompt=None):
    """对已抽帧 p（ts=t）做一次 M3 读数，返回记录 dict（含 kind/category/values）。"""
    an = _m3_analysis([p], prompt or EXTRACT_PROMPT, f"fr_{t}")
    dump = json.dumps(an, ensure_ascii=False) if an else ""
    blk = _json_block(dump, key="settings")
    if blk is None and an:
        blk = _json_block(str(an.get("summary", "")), key="settings")
    page = str((blk or {}).get("page", "")).strip().lower()
    vals = {}
    for s in ((blk or {}).get("settings") or []):
        nm, vv = str(s.get("name", "")).strip(), str(s.get("value", "")).strip()
        un = str(s.get("unit", "")).strip()
        if nm and vv:
            vals[f"{nm} {un}".strip()] = vv
    kind = "config" if vals else "other"
    cat = ""
    hay = page + " " + " ".join(vals.keys())
    for c, kws in CAT_KEYWORDS:
        if any(k in hay for k in kws):
            cat = c
            break
    return {"frame": str(p), "ts": t, "kind": kind, "category": cat, "values": vals}


def _recall_audit(proj, frames, records, video_id, src):
    """自动召回审计（2026-08-28，机器版"人眼盯漏页"）：
    稳定画面网格图 → M3 数出设置界面秒数 → 与提取结果对账 → 缺的定点补读 →
    补读仍无参数则记为 gap。返回 residual_gaps（非空 → ocr 标 needs_review，人核兜底）。"""
    if not frames:
        return []
    extracted = {r["ts"] for r in records if r.get("kind") == "config"}
    gaps = []
    for ci in range(0, len(frames), 80):
        chunk = frames[ci:ci + 80]
        grid = _grid_cells(chunk, ci // 80)
        an = _m3_analysis([grid], RECALL_PROMPT, f"audit_{video_id}_{ci // 80}")
        dump = json.dumps(an, ensure_ascii=False) if an else ""
        blk = _json_block(dump, key="seconds")
        for s in ((blk or {}).get("seconds") or []):
            try:
                sec = float(s)
            except Exception:
                continue
            if any(abs(sec - e) <= 4 for e in extracted):
                continue
            # 定点补读（全分辨率）
            p = proj / "artifacts" / "frames" / f"rt_{int(sec)}.jpg"
            r = run([FFMPEG, "-y", "-ss", str(max(0.0, sec)), "-i", str(src),
                     "-frames:v", "1", "-q:v", "2", "-vf", "scale=1280:-2", str(p)],
                    timeout=120)
            if r.returncode != 0 or not p.exists():
                continue
            rec = _read_frame_record(src, p, round(sec, 1))
            if rec["kind"] == "config":
                records.append(rec)
            else:
                gaps.append(round(sec, 1))
    records.sort(key=lambda r: r["ts"])
    return sorted(set(gaps))


def _collapse_final(records):
    """用户规则（2026-08-28）：同一配置项多次出现（逐次调整 300/312/322）→ 只保留最后一次出现。
    同一配置项 = 同类别 + 同参数名集合（数值会随调整变化，参数名不变）。
    不同参数名的同类别页（如 ALIGNMENT 与 WHEELS）互不吞并。"""
    _assign_categories(records)
    last = {}
    for i, r in enumerate(records):
        if r["kind"] != "config":
            continue
        key = (r.get("category", ""), tuple(sorted(r["values"].keys())))
        last[key] = i
    for i, r in enumerate(records):
        if r["kind"] != "config":
            continue
        key = (r.get("category", ""), tuple(sorted(r["values"].keys())))
        if last.get(key) != i:
            r["superseded"] = True
    return records


def _collapse_progressive(records):
    """同一类别连续出现的 config 帧视为"正在调整"的中间态，只保留组内最后一帧（落定值）。
    其余标记 superseded=true，保留在 ocr.json 里但不再上对照表。"""
    runs, cur = [], []
    for r in records:
        if r.get("kind") == "config" and cur and cur[-1].get("category") == r.get("category"):
            cur.append(r)
        else:
            if cur:
                runs.append(cur)
            cur = [r] if r.get("kind") == "config" else []
    if cur:
        runs.append(cur)
    for run in runs:
        for r in run[:-1]:
            r["superseded"] = True
    return records


def write_review_html(v, ocr):
    proj = Path(v["project_dir"])
    rows = []
    for rec in ocr["frames"]:
        if rec.get("superseded"):
            continue
        vals = json.dumps(rec["values"], ensure_ascii=False) if rec["values"] else "-"
        flag = "✅" if rec["kind"] == "config" else ("⚠️" if rec["kind"] == "diagram" else "")
        rows.append(f"""<tr><td>{rec['ts']}s {flag}</td>
<td><img src="../{Path(rec['frame']).relative_to(proj).as_posix()}" loading="lazy"></td>
<td><b>{rec['kind']}</b> / {rec['category']}<br><code>{vals}</code></td></tr>""")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>数值对照 — {v['video_id']}</title><style>
body{{font-family:'Microsoft YaHei';background:#111;color:#eee;margin:20px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #444;padding:8px;vertical-align:top}}
img{{width:420px}}code{{color:#8ef}}h1{{font-size:20px}}
.warn{{background:#3a1f1f;border:1px solid #ff5c5c;color:#ffb3b3;padding:12px 16px;border-radius:8px;margin-bottom:14px}}
</style></head><body>
<h1>数值对照表 — {v['video_id']}（{v['title']}）</h1>"""
    if ocr.get("needs_review"):
        html += (f'<div class="warn">⚠️ 自动召回审计发现 {len(ocr["needs_review"])} 个时间点疑似设置界面'
                 f'但读数无参数：{ocr["needs_review"]} —— 请人工确认这几秒画面，数值可手动核对。</div>')
    html += f"""
<p>✅=配置界面 ⚠️=标题卡/示意图（模板禁用）。核对后：<code>python bin/setup_video.py approve-review {v['video_id']} --fix "参数=值"</code></p>
<table><tr><th>时间</th><th>截图</th><th>OCR</th></tr>{''.join(rows)}</table></body></html>"""
    out = proj / "artifacts" / "review.html"
    out.write_text(html, encoding="utf-8")
    return out


def stage_review(args):
    v = get_video(args.video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    ocr_path = proj / "artifacts" / "ocr.json"
    if not ocr_path.exists():
        return {"ok": False, "error": "缺 ocr.json（先 extract）"}
    out = write_review_html(v, json.loads(ocr_path.read_text(encoding="utf-8")))
    run(["cmd", "/c", "start", "", str(out)])
    return {"ok": True, "opened": str(out)}


def stage_approve_review(args):
    v = get_video(args.video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    ocr_path = proj / "artifacts" / "ocr.json"
    if not ocr_path.exists():
        return {"ok": False, "error": "缺 ocr.json"}
    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    fixes = {}
    for fx in (args.fix or []):
        if "=" not in fx:
            return {"ok": False, "error": f"--fix 格式应为 参数=值: {fx}"}
        kk, vv = fx.split("=", 1)
        fixes[kk.strip()] = vv.strip()
    ocr["human_fixed"].update(fixes)
    ocr["reviewed"] = True
    ocr_path.write_text(json.dumps(ocr, ensure_ascii=False, indent=2), encoding="utf-8")
    set_status(args.video_id, "scripted")
    return {"ok": True, "video_id": args.video_id, "fixes": fixes,
            "next": f"python bin/setup_video.py script {args.video_id}"}


# 违禁词白名单复合词（模板固定结构词，先剥除再匹配）
BANNED_ALLOWED_COMPOUNDS = ["第一招", "第二招", "第三招", "第一幕", "第一次", "第一个", "第一名场面"]


def _scan_banned(joined: str, hard, warn):
    scannable = joined
    for a in BANNED_ALLOWED_COMPOUNDS:
        scannable = scannable.replace(a, "")
    hits = sorted({w for w in hard if w in scannable})
    warns = sorted({w for w in warn if w in scannable})
    return hits, warns


# ---------------------------------------------------------------- script
def stage_script(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    if v["status"] not in ("scripted", "awaiting_script", "failed"):
        return {"ok": False, "error": f"状态 {v['status']} 未过数值人核（先 approve-review）"}
    proj = Path(v["project_dir"])
    src = proj / "assets" / "original.mp4"
    audio = proj / "assets" / "original.wav"
    run([FFMPEG, "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)], timeout=1800)
    transcript = proj / "artifacts" / "transcript.json"
    if audio.exists() and not transcript.exists():
        from tools.analysis.transcriber import Transcriber
        res = Transcriber().execute({"input_path": str(audio), "output_dir": str(proj / "artifacts")})
        outs = list((proj / "artifacts").glob("*_transcript.json"))
        if res.success and outs:
            if outs[0] != transcript:
                shutil.copy2(outs[0], transcript)
    ocr = json.loads((proj / "artifacts" / "ocr.json").read_text(encoding="utf-8"))
    workorder = {
        "video_id": video_id,
        "ocr": ocr,
        "transcript": str(transcript) if transcript.exists() else None,
        "instructions": str(SPEC_DIR / "script-prompt.md"),
        "schema": str(SCHEMA_PATH),
        "output": str(proj / "artifacts" / "episode.json"),
    }
    wo_path = proj / "artifacts" / "script_workorder.json"
    wo_path.write_text(json.dumps(workorder, ensure_ascii=False, indent=2), encoding="utf-8")
    set_status(video_id, "awaiting_script")
    return {"ok": True, "video_id": video_id, "workorder": str(wo_path),
            "transcript": transcript.exists(),
            "next": f"agent 按 {SPEC_DIR / 'script-prompt.md'} 写 {proj / 'artifacts' / 'episode.json'}，然后 approve-script {video_id}"}


def _load_banned():
    """解析 banned-words.md 的机器可读段：## 硬词 → hard，## 警告词 → warn。"""
    hard, warn = [], []
    section = None
    for ln in (SPEC_DIR / "banned-words.md").read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s.startswith("## "):
            title = s[3:].strip()
            section = "hard" if title.startswith("硬词") else ("warn" if title.startswith("警告词") else None)
            continue
        if not s or s.startswith(("#", ">", "|", "-")) or not section:
            continue
        bucket = hard if section == "hard" else warn
        bucket.extend(w.strip() for w in re.split(r"[、，,]", s) if w.strip())
    return sorted(set(hard)), sorted(set(warn))


def stage_approve_script(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    proj = Path(v["project_dir"])
    ep_path = proj / "artifacts" / "episode.json"
    if not ep_path.exists():
        return {"ok": False, "error": f"缺 episode.json（agent 按 script-prompt.md 生成）"}
    try:
        ep = json.loads(ep_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"episode.json 解析失败: {e}"}
    # schema 校验
    try:
        import jsonschema
        jsonschema.validate(ep, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    except ImportError:
        problems = []
        if len(ep.get("points", [])) != 3:
            problems.append("points 必须 3 项")
        if len(ep.get("flash", [])) != 4:
            problems.append("flash 必须 4 项")
        if len(ep.get("table", [])) != 8:
            problems.append("table 必须 8 行")
        if set(ep.get("narration", {}).keys()) != {"s1", "s2", "s3", "s4", "s5", "s6"}:
            problems.append("narration 必须 s1..s6")
        if problems:
            return {"ok": False, "error": "schema 校验未过（缺 jsonschema 包，走内置检查）", "problems": problems}
    except Exception as e:
        return {"ok": False, "error": f"schema 校验未过: {e}"}
    # 违禁词
    hard, warn = _load_banned()
    texts = list(ep["narration"].values()) + ep.get("chips", []) + \
        [p.get("renhua", "") for p in ep["points"]] + \
        [ep.get("package", {}).get("title", ""), ep.get("package", {}).get("desc", "")]
    joined = " ".join(t for t in texts if t)
    hits, warns = _scan_banned(joined, hard, warn)
    if hits:
        return {"ok": False, "error": "违禁词命中（改词后重提）", "hits": hits}
    # 预算（规划值：字数 / 3.4cps + 尾垫；s6 尾垫 4.2 与模板 v0.3 定格加长一致）
    plan = {k: round(len(tx) / 3.4 + {"s1": 0.8, "s2": 0.9, "s3": 0.9, "s4": 0.9,
                                      "s5": 0.9, "s6": 4.2}[k] + 0.25, 1)
            for k, tx in ep["narration"].items()}
    total_plan = round(sum(plan.values()), 1)
    if not (TOTAL_MIN <= total_plan <= TOTAL_MAX):
        return {"ok": False, "error": f"规划时长 {total_plan}s 超出 [{TOTAL_MIN},{TOTAL_MAX}]（目标 58-65s，按 script-prompt 字数预算删/补句）",
                "per_scene": plan}
    # 引用完整性（护栏 3）：table/points 里每个数字必须能在 ocr.json（含人核修正）里找到出处
    ocr_path = proj / "artifacts" / "ocr.json"
    ocr_pool = []
    if ocr_path.exists():
        ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
        for r in ocr.get("frames", []):
            ocr_pool.extend(str(v) for v in r.get("values", {}).values())
        ocr_pool.extend(str(v) for v in ocr.get("human_fixed", {}).values())
    ocr_pool = " | ".join(ocr_pool)
    orphan_nums = []
    for row in ep.get("table", []):
        for tok in re.findall(r"[\d.]+", str(row.get("value", ""))):
            if tok and tok not in ocr_pool:
                orphan_nums.append(f"{row.get('name')}={tok}")
    for pt in ep.get("points", []):
        for fld in ("v1", "v2"):
            vv = str(pt.get(fld, ""))
            if not vv:
                continue
            for tok in re.findall(r"[\d.]+", vv):
                if tok and tok not in ocr_pool:
                    orphan_nums.append(f"{pt.get('label')}/{fld}={tok}")
    if orphan_nums:
        return {"ok": False, "error": "引用完整性未过：以下数字在 OCR 提取中找不到出处（先核对数值人核表，或修正后重提）",
                "orphans": sorted(set(orphan_nums))[:20]}
    # 落库 slug（E5 防复发 2026-08-29：同车同赛道两条 slug 碰撞时，绝不迁移/覆盖现有目录）
    game_slug = slugify(ep["video"].get("game", "game"))
    new_slug = slugify(f'{ep["video"].get("title", "")}-{ep["video"].get("track", "")}')
    new_dir = PROJECTS_ROOT / "setup-video" / game_slug / new_slug
    cur = Path(v["project_dir"])
    cur_ok = cur.exists() and (cur / "artifacts" / "episode.json").exists()
    if new_dir.resolve() == cur.resolve():
        final_dir, final_slug = cur, v["slug"] or new_slug
    elif cur_ok and new_dir.exists():
        # 当前项目完整且目标 slug 目录已被占用 → 保留现有 project_dir/slug（冲突目录已人工解析过），
        # 不迁移不覆盖；否则两条同 slug 记录会互相踩目录（uZKE/8bll 实测两轮复发）
        final_dir, final_slug = cur, v["slug"] or new_slug
    elif not new_dir.exists():
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(cur), str(new_dir))
        except Exception:
            pass  # 目录非空冲突时保留原地，render 仍可用
        final_dir = new_dir if new_dir.exists() else cur
        final_slug = new_slug
    else:
        final_dir, final_slug = cur, v["slug"] or new_slug
    c = db_conn()
    c.execute("UPDATE videos SET project_dir=?, game=?, slug=? WHERE video_id=?",
              (str(final_dir), ep["video"].get("game", ""), final_slug, video_id))
    c.commit()
    c.close()
    set_status(video_id, "ready")
    return {"ok": True, "video_id": video_id, "plan_total_s": total_plan,
            "per_scene": plan, "warnings": warns,
            "next": f"Compute Worker: python bin/setup_video.py assets {video_id} --json"}


# ---------------------------------------------------------------- assets (HEAVY)
def _projected_total(proj: Path, episode: dict) -> float:
    sys.path.insert(0, str(OMO_ROOT / "apps" / "setup-video" / "template"))
    import instantiate_template as gen
    total = gen.LEAD_IN
    for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        d = ffprobe_dur(proj / "assets" / f"{k}.wav") or (len(episode["narration"][k]) / 3.4 + 0.8)
        total += d + gen.TAIL[k] + gen.GAP
    return round(total, 2)


# G1 防复发（2026-08-29 代码化）：wav 缓存必须匹配 narration 文本指纹 + TTS 参数签名，
# 不一致自动重录——改口播/改参数后直接重跑 assets 即可，不再靠手动删 wav。
# 指纹落 artifacts/tts_manifest.json（{k: {md5, params, wav}}）。
def _narration_md5(ep: dict, k: str) -> str:
    return hashlib.md5(ep["narration"][k].encode("utf-8")).hexdigest()


def _tts_params_sig() -> dict:
    return {kk: TTS[kk] for kk in ("spk_audio_prompt", "use_emo_text", "emo_alpha", "seed", "speed")}


def _load_tts_manifest(proj: Path) -> dict:
    p = proj / "artifacts" / "tts_manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_tts_manifest(proj: Path, manifest: dict):
    p = proj / "artifacts" / "tts_manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def stage_assets(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    if v["status"] not in ("ready", "failed"):
        return {"ok": False, "error": f"状态 {v['status']} 未放行（先 approve-script）"}
    proj = Path(v["project_dir"])
    assets = proj / "assets"
    ep = json.loads((proj / "artifacts" / "episode.json").read_text(encoding="utf-8"))
    src = assets / "original.mp4"
    if not src.exists():
        return fail(video_id, "assets", "缺 original.mp4")
    set_status(video_id, "assets")

    # 1) TTS（GPU 锁贯穿；缺段才合成）。fixed 情绪模式，不需要 QWEN 文本情绪（2026-08-29 用户定）
    #    G1 防复发（2026-08-29 代码化）：缓存命中 = 文件存在 + 时长>0.5s + 文本指纹一致 + TTS 参数签名一致；
    #    无 tts_manifest.json（旧项目）一律视为缓存无效全量重录，保证不会把旧配音混进新口播。
    from lib.gpu_lock import gpu_lock
    from tools.audio.indextts_tts import IndexTTS2TTS
    tool = IndexTTS2TTS()
    made = 0
    params_sig = _tts_params_sig()
    manifest = _load_tts_manifest(proj)
    with gpu_lock(label=f"setup-tts-{video_id}", timeout=1800, heartbeat=30):
        for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
            out = assets / f"{k}.wav"
            ent = manifest.get(k) or {}
            cached = (out.exists() and (ffprobe_dur(out) or 0) > 0.5
                      and ent.get("md5") == _narration_md5(ep, k)
                      and ent.get("params") == params_sig)
            if cached:
                continue
            res = tool.execute({"text": ep["narration"][k], "output_path": str(out),
                                "spk_audio_prompt": TTS["spk_audio_prompt"],
                                "use_emo_text": TTS["use_emo_text"], "emo_alpha": TTS["emo_alpha"],
                                "seed": TTS["seed"], "speed": TTS["speed"]})
            if not res.success:
                return fail(video_id, "assets", f"{k} TTS 失败: {res.error}")
            made += 1
            manifest[k] = {"md5": _narration_md5(ep, k), "params": params_sig,
                           "wav": f"{k}.wav"}
    _save_tts_manifest(proj, manifest)
    # 静音伪文件检测
    for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        d = ffprobe_dur(assets / f"{k}.wav")
        if not d or d < 0.5:
            return fail(video_id, "assets", f"{k}.wav 静音伪文件/缺失")

    total = _projected_total(proj, ep)

    # 2) 第一幕行驶片段：外部追车视角自动探测（2026-08-28 修复车内视角）
    drv_cfg = ep.get("drive", {})
    crop = drv_cfg.get("crop", "810:1440:875:0")
    window1 = durs_for_total(proj)["s1_window"]
    need = window1 + 0.3
    src_dur = dur0(src)
    auto_t = None
    if drv_cfg.get("auto", True):
        auto_t = _find_exterior_span(src, src_dur)
    if auto_t is not None:
        tin = max(2.0, auto_t - 3.5)
        tout = min(src_dur - 0.5, auto_t + 4.5)
    else:
        tin = float(drv_cfg.get("in", src_dur * 0.75))
        tout = float(drv_cfg.get("out", src_dur * 0.75 + 5))
    src_len = max(0.5, tout - tin)
    # 源片段不足整幕 → 自动延长取景窗口（否则尾段只能定格等配音，用户反馈 2026-08-28）
    if src_len < need:
        tout = min(src_dur - 0.5, tin + need)
        src_len = max(0.5, tout - tin)
    slow_target = src_len / max(0.4, window1 - 0.4)
    slow = max(1.0, min(2.0, slow_target))
    est = src_len * slow
    pad = max(0.0, need - est)
    vf = (f"crop={crop},setpts={slow}*PTS,fps=30,scale=1080:1920,"
          f"tpad=stop_mode=clone:stop_duration={pad:.2f}")
    r = run([FFMPEG, "-y", "-ss", str(tin), "-to", str(tout), "-i", str(src),
             "-vf", vf, "-an", "-c:v", "libx264", "-crf", "20", "-g", "30",
             str(assets / "s1_drive.mp4")], timeout=1200)
    if r.returncode != 0:
        fb = drv_cfg.get("fallback_image")
        if fb:
            (assets / "s1_drive.mp4").unlink(missing_ok=True)
        else:
            return fail(video_id, "assets", "行驶片段提取失败且无 fallback_image")

    # 3) 背景 = 原视频连续截取成片长度画面段（2026-08-28 用户定：直接截取，替代 ping-pong）
    need_total = total + 2.0
    #    取景必须全程有运动：优先外部追车探针区；探针失败用本地运动检测窗口（菜单/标题卡
    #    静止区会让某几幕背景像图片——用户反馈第二幕静止/第三幕运动）
    if auto_t is not None:
        bt = max(3.0, auto_t - 3.5)
    else:
        bt = _find_motion_span(src, src_dur, need_s=need_total)
    if bt + need_total > src_dur - 0.5:
        bt = max(3.0, src_dur - 0.5 - need_total)
    bg_vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,fps=30"
    r = run([FFMPEG, "-y", "-ss", str(bt), "-t", str(need_total), "-i", str(src),
             "-vf", bg_vf, "-an", "-c:v", "libx264", "-crf", "23", "-g", "30",
             str(assets / "bg_loop.mp4")], timeout=1800)
    if r.returncode != 0 or not (assets / "bg_loop.mp4").exists():
        return fail(video_id, "assets", "背景截取失败")

    # 4) BGM = 去除人声的纯环境声段（第一集同款：whisper 验声 + highpass55 + loudnorm；
    #    2026-08-28 用户确认"要去除人声"，且背景取景已独立为整段画面，BGM 不再绑定背景段）
    bgm_flag = None
    if make_bgm(proj, ep, src, total):
        bgm_flag = "extracted"
    elif FALLBACK_BGM.exists():
        shutil.copy2(FALLBACK_BGM, assets / "bgm.mp3")
        (proj / "artifacts" / "bgm_fallback.txt").write_text("公共备用 BGM（第一集同款引擎声）", encoding="utf-8")
        bgm_flag = "fallback"
    else:
        return fail(video_id, "assets", "BGM 提取失败且无备用")

    # 5) 品牌徽章映射（2026-08-28 修复：优先模板验证过的 <brand>_badge 徽标，
    #    再落模板 logos/品牌库；brand_logos/skoda.png 是文字字标，不是徽标）
    brand = slugify(ep["video"].get("brand", ""), fallback="")
    if brand:
        cand = None
        bb = ep.get("video", {}).get("brand_badge", "")
        if bb:
            cand = Path(bb) if Path(bb).exists() else OMO_ROOT / bb
        if cand is None or not cand.exists():
            logos_dir = OMO_ROOT / "projects" / "setup-video-template" / "assets" / "logos"
            bl_dir = OMO_ROOT / "assets" / "brand_logos"
            cand = (next(iter(logos_dir.glob(f"{brand}_badge.*")), None)
                    or next(iter(logos_dir.glob(f"{brand}.*")), None)
                    or next(iter(bl_dir.glob(f"{brand}*.png")), None))
        if cand and Path(cand).exists():
            (assets / "badges").mkdir(exist_ok=True)
            shutil.copy2(cand, assets / "badges" / f"{slugify(ep['video'].get('brand', 'x'))}.png")

    # 6) 配置图截屏（s2-s4 各一张 + s5 四张，时间戳来自 episode）
    shots = {f"shot_s2.png": pts0(ep, 0), "shot_s3.png": pts0(ep, 1), "shot_s4.png": pts0(ep, 2)}
    for i, fl in enumerate(ep["flash"]):
        shots[f"shot_s5_{i + 1}.png"] = fl["img_ts"]
    for name, ts in shots.items():
        r = run([FFMPEG, "-y", "-ss", str(max(0.0, float(ts))), "-i", str(src),
                 "-frames:v", "1", str(assets / name)], timeout=120)
        if r.returncode != 0 or not (assets / name).exists():
            return fail(video_id, "assets", f"配置图截屏失败: {name}@{ts}")

    # 7) 证据截图聚焦裁剪（2026-08-29 定案，G7 通用矩形：去右栏截断说明栏+底部模糊；
    #    仅 ACR 调校界面布局适用，其他游戏需另定矩形组）
    if str(ep["video"].get("game", "")).lower().startswith("assetto corsa"):
        SHOT_CROPS = {
            "shot_s2.png": "2200:1230:0:0", "shot_s3.png": "2200:1230:0:0",
            "shot_s4.png": "2240:1430:0:0", "shot_s5_1.png": "2200:950:0:0",
            "shot_s5_2.png": "2240:1370:0:0", "shot_s5_3.png": "2240:1440:0:0",
            "shot_s5_4.png": "2250:1320:0:0",
        }
        for name, rect in SHOT_CROPS.items():
            sp = assets / name
            if not sp.exists():
                continue
            tmp = assets / (name + ".crop.png")
            r = run([FFMPEG, "-y", "-i", str(sp), "-vf", f"crop={rect}", "-q:v", "2", str(tmp)], timeout=120)
            if r.returncode == 0 and tmp.exists():
                tmp.replace(sp)
            else:
                tmp.unlink(missing_ok=True)
                return fail(video_id, "assets", f"截图裁剪失败: {name}")

    set_status(video_id, "ready_render")
    return {"ok": True, "video_id": video_id, "tts_made": made, "total_projected": total,
            "bgm": bgm_flag or "extracted"}


def dur0(src):
    return ffprobe_dur(src) or 120.0


def pts0(ep, i):
    return float(ep["points"][i].get("evidence_ts", 0))


def durs_for_total(proj):
    """给 assets 阶段用的 s1 窗口估算（与生成器同公式）"""
    sys.path.insert(0, str(OMO_ROOT / "apps" / "setup-video" / "template"))
    import instantiate_template as gen
    d1 = ffprobe_dur(proj / "assets" / "s1.wav") or 7.0
    return {"s1_window": round(d1 + gen.TAIL["s1"], 2)}


def _find_motion_span(src, dur, need_s=46.0):
    """本地运动检测：每 2s 采样小帧 → 连续帧差异比 → 找最长持续运动窗口（作背景取景）。
    2026-08-28：背景段必须全程有运动（菜单/标题卡静止区会让某几幕背景像图片）。零 API。"""
    tmp = Path("tmp") / "setup-video-queue" / "motion"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("m_*.jpg"):
        f.unlink()
    run([FFMPEG, "-y", "-ss", "3", "-i", str(src), "-vf", "fps=1/2,scale=160:-2",
         "-q:v", "8", str(tmp / "m_%04d.jpg")], timeout=1200)
    seq = sorted(tmp.glob("m_*.jpg"))
    if len(seq) < 4:
        return max(2.0, dur * 0.4)
    try:
        from PIL import Image
    except ImportError:
        return max(2.0, dur * 0.4)

    def _sig(p):
        img = Image.open(p).convert("L").resize((32, 18))
        return list(img.getdata())

    sigs = [_sig(p) for p in seq]
    moving = [False] * len(sigs)
    for i in range(1, len(sigs)):
        a, b = sigs[i - 1], sigs[i]
        diff = sum(1 for x, y in zip(a, b) if abs(x - y) > 14) / len(a)
        moving[i] = diff > 0.03
    best, best_len = 0, 0
    cur, cur_len = 0, 0
    need_samples = int(need_s / 2)
    for i in range(1, len(moving)):
        if moving[i]:
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best = i - cur_len + 1
        else:
            cur_len = 0
    if best_len < need_samples - 1:
        return max(2.0, dur * 0.4)
    t = 3 + best * 2.0
    return max(2.0, min(dur - need_s - 1.0, t))


DRIVE_PROBE_PROMPT = (
    "这是赛车游戏视频等距采样的画面网格图，每格上方有黄色秒标。"
    "找出所有【车外追车视角】的格子：能看到整辆赛车在行驶的外部镜头（不是车内驾驶舱视角、"
    "不是静止车库/维修区、不是菜单/排行榜/标题卡）。"
    '输出 JSON：{"seconds": [整数值秒标列表]}。只输出 JSON，不要其他文字。'
)


def _find_exterior_span(src, dur):
    """条带探针：等距采样 12 帧 → M3 挑外部追车视角 → 返回起点秒数（None=未找到）。
    2026-08-28 用户反馈首幕用了车内视角 → 取景必须外部追车镜头。"""
    strip_dir = Path("tmp") / "setup-video-queue" / "probe"
    strip_dir.mkdir(parents=True, exist_ok=True)
    for f in strip_dir.glob("*.jpg"):
        f.unlink()
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    cells = []
    for idx in range(1, 13):
        t = max(3.0, round(dur * idx / 12, 1))
        p = strip_dir / f"p{idx:02d}.jpg"
        r = run([FFMPEG, "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                 "-q:v", "4", "-vf", "scale=480:-2", str(p)], timeout=120)
        if r.returncode == 0 and p.exists():
            cells.append((p, t))
    if not cells:
        return None
    COLS, CW, CH, LBL = 4, 300, 169, 22
    rows = (len(cells) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CW, rows * (CH + LBL)), (18, 18, 24))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    for i, (p, t) in enumerate(cells):
        cx, cy = (i % COLS) * CW, (i // COLS) * (CH + LBL)
        img = Image.open(p).convert("RGB").resize((CW, CH))
        sheet.paste(img, (cx, cy + LBL))
        d.text((cx + 4, cy + 3), f"{int(t)}s", fill=(255, 214, 10), font=font)
    grid = strip_dir / "grid.jpg"
    sheet.save(grid, quality=88)
    an = _m3_analysis([grid], DRIVE_PROBE_PROMPT, f"drive_probe_{Path(src).stem}")
    dump = json.dumps(an, ensure_ascii=False) if an else ""
    blk = _json_block(dump, key="seconds")
    secs = []
    for s in ((blk or {}).get("seconds") or []):
        try:
            secs.append(float(s))
        except Exception:
            pass
    return min(secs) if secs else None


def _slice_has_voice(wav: Path) -> bool:
    """whisper 验声：8s 切片转写，有词即判含人声（BGM 候选必须无语音）。"""
    tmp = Path("tmp") / "setup-video-queue"
    tmp.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", "-i", str(wav), "-t", "8", "-ar", "16000", "-ac", "1",
         str(tmp / "_vad.wav")], timeout=120)
    from tools.analysis.transcriber import Transcriber
    res = Transcriber().execute({"input_path": str(tmp / "_vad.wav"),
                                 "output_dir": str(tmp)})
    if not res.success:
        return False   # 转写失败不武断判定（宁可放行再靠人耳）
    outs = sorted(tmp.glob("*_transcript.json"), key=lambda p: p.stat().st_mtime)
    if not outs:
        return False
    try:
        d = json.loads(outs[-1].read_text(encoding="utf-8"))
        segs = d.get("segments", d if isinstance(d, list) else [])
        text = " ".join(str(s.get("text", "")) for s in segs)
    except Exception:
        return False
    return len(text.strip()) >= 3


def make_bgm(proj: Path, ep: dict, src: Path, total: float) -> bool:
    """避开人声段取 10s 纯环境声 → highpass55+loudnorm → aloop 铺满。
    2026-08-28 修复：候选段 whisper 验声（取到领航员播报的坑），最多试 5 个，全含人声返回 False（上层兜底引擎声）。"""
    assets = proj / "assets"
    dur = dur0(src)
    speech = []
    tp = proj / "artifacts" / "transcript.json"
    if tp.exists():
        try:
            tjson = json.loads(tp.read_text(encoding="utf-8"))
            segs = tjson.get("segments", tjson if isinstance(tjson, list) else [])
            for sgm in segs:
                speech.append((float(sgm.get("start", 0)), float(sgm.get("end", 0))))
        except Exception:
            pass
    core = assets / "bgm_core.mp3"
    lo, hi = dur * 0.15, dur * 0.92
    picked = None
    for attempt in range(5):
        t = hi - 10.0 - attempt * 5.0
        if t < lo:
            break
        if any(s - 1.0 < t + 10.0 and e + 1.0 > t for s, e in speech):
            continue
        r = run([FFMPEG, "-y", "-ss", str(t), "-t", "10", "-i", str(src), "-vn",
                 "-af", "highpass=f=55,loudnorm=I=-15:TP=-1.5:LRA=11",
                 "-c:a", "libmp3lame", "-q:a", "4", str(core)], timeout=600)
        if r.returncode != 0 or not core.exists():
            continue
        if not _slice_has_voice(core):
            # 2026-08-29 修复：必须"有声音"（引擎/环境声），防取到静音段 → 全片无 BGM（MC 实测 -91dB）
            vd = sh([FFMPEG, "-i", str(core), "-af", "volumedetect", "-f", "null", "-"], timeout=300)
            m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", vd.stdout or "")
            if m and float(m.group(1)) > -40.0:
                picked = core
                break
    if picked is None:
        return False
    r = run([FFMPEG, "-y", "-stream_loop", "40", "-i", str(core), "-t", str(total + 2),
             "-c:a", "libmp3lame", "-q:a", "4", str(assets / "bgm.mp3")], timeout=600)
    core.unlink(missing_ok=True)
    return r.returncode == 0


# ---------------------------------------------------------------- render (HEAVY)
def stage_render(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    if v["status"] not in ("ready_render", "failed"):
        return {"ok": False, "error": f"状态 {v['status']} 未过 assets（先跑 assets）"}
    proj = Path(v["project_dir"])
    assets = proj / "assets"
    ep_path = proj / "artifacts" / "episode.json"
    set_status(video_id, "rendering")

    compose = proj / "compose"
    (compose / "assets").mkdir(parents=True, exist_ok=True)
    for f in assets.iterdir():
        if f.is_file():
            shutil.copy2(f, compose / "assets" / f.name)
    if (assets / "badges").exists():
        shutil.copytree(assets / "badges", compose / "assets" / "badges", dirs_exist_ok=True)

    env = dict(os.environ)
    env["npm_config_cache"] = str(OMO_ROOT / ".npm-cache")
    meta_path = proj / "artifacts" / "timings.json"
    r = run([sys.executable, str(GEN_COMPOSE), str(ep_path), str(compose / "assets"),
             str(compose / "index.html"), "--meta", str(meta_path)], env=env, timeout=300)
    if r.returncode != 0:
        return fail(video_id, "rendering", "模板实例化失败")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    (compose / "package.json").write_text(json.dumps({
        "name": f"setup-{v['video_id']}", "private": True, "type": "module",
        "scripts": {"render": "npx --yes hyperframes@0.7.109 render"}}), encoding="utf-8")
    (compose / "renders").mkdir(exist_ok=True)
    for old in (compose / "renders").glob("*.mp4"):
        old.unlink()
    r = run(["npm.cmd", "run", "render"], cwd=compose, env=env, timeout=3600)
    mps = sorted((compose / "renders").glob("*.mp4"))
    if r.returncode != 0 or not mps:
        return fail(video_id, "rendering", "hyperframes 渲染失败")
    raw = mps[-1]

    # ---- 基础 QA ----
    set_status(video_id, "qa")
    qa_dir = proj / "artifacts" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    final_dur = ffprobe_dur(raw)
    qa = {"duration": final_dur, "ok_duration": bool(final_dur and TOTAL_MIN <= final_dur <= TOTAL_MAX)}
    sd = sh([FFMPEG, "-i", str(raw), "-af", "silencedetect=noise=-38dB:d=2.5",
             "-f", "null", "-"], timeout=900)
    holes = re.findall(r"silence_start: ([\d.]+)", sd.stdout or "")
    qa["silence_holes_gt2.5s"] = [round(float(x), 1) for x in holes]
    qa["ok"] = qa["ok_duration"]
    (qa_dir / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    if not qa["ok"]:
        return fail(video_id, "qa", f"QA 未过: {qa}")
    # QA 抽帧（视觉核验/抽检用）
    for k, ts in meta["qa_frames"].items():
        run([FFMPEG, "-y", "-ss", str(ts), "-i", str(raw), "-frames:v", "1",
             str(qa_dir / f"qa_{k}.jpg")], timeout=120)

    # ---- 定版 + 封面 + 成品包 ----
    out_dir = proj / "renders"
    out_dir.mkdir(exist_ok=True)
    final = out_dir / "final.mp4"
    shutil.copy2(raw, final)
    pkg = proj / "package"
    pkg.mkdir(exist_ok=True)
    shutil.copy2(final, pkg / "video.mp4")
    for name, ts in (("cover_s1.jpg", meta["cover_s1"]), ("cover_s6.jpg", meta["cover_s6"])):
        run([FFMPEG, "-y", "-ss", str(ts), "-i", str(final), "-frames:v", "1",
             str(pkg / name)], timeout=120)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    pd = ep.get("package", {})
    (pkg / "title.txt").write_text(pd.get("title", ""), encoding="utf-8")
    (pkg / "desc.txt").write_text(pd.get("desc", ""), encoding="utf-8")
    # 合并发布文本（2026-08-29 用户定）：标题 + 简介 + 推荐标签 一个文件，抖音发布直接整段贴
    tags = pd.get("tags") or ["#AssettoCorsaRally", "#赛车调校", "#模拟赛车"]
    (pkg / "publish.txt").write_text(
        f"{pd.get('title', '')}\n\n{pd.get('desc', '')}\n\n{' '.join(tags)}\n",
        encoding="utf-8")
    if (proj / "artifacts" / "bgm_fallback.txt").exists():
        (pkg / "bgm_fallback.txt").write_text("备用BGM（源视频无干净环境声段）", encoding="utf-8")
    set_status(video_id, "packaged")

    # 每 10 条抽 1 的视觉核验工单标记（agent 侧消费）
    c = db_conn()
    n = c.execute("SELECT COUNT(*) FROM videos WHERE status='packaged'").fetchone()[0]
    c.close()
    needs_visual = (n % 10 == 0)
    return {"ok": True, "video_id": video_id, "final": str(final),
            "package": str(pkg), "duration": final_dur,
            "needs_visual_qa": needs_visual, "qa_frames": str(qa_dir)}


# ---------------------------------------------------------------- status / retry
def stage_status(args):
    c = db_conn()
    rows = c.execute("SELECT status, COUNT(*) FROM videos GROUP BY status").fetchall()
    detail = c.execute("SELECT video_id, status, failed_stage, last_error, title FROM videos").fetchall()
    c.close()
    summary = {s: 0 for s in STATUS_FLOW}
    for s, n in rows:
        summary[s] = n
    if args.json:
        emit_json({"summary": summary, "videos": [
            {"id": r[0], "status": r[1], "failed_stage": r[2], "error": r[3], "title": r[4]} for r in detail]})
    else:
        for s in STATUS_FLOW:
            if summary[s]:
                print(f"{s}: {summary[s]}")
        for r in detail:
            mark = f"  ← {r[2]}: {r[3]}" if r[1] == "failed" else ""
            print(f"  {r[0]} [{r[1]}] {r[4] or ''}{mark}")


def stage_retry(video_id):
    v = get_video(video_id)
    if not v:
        return {"ok": False, "error": "未找到项目"}
    if v["status"] != "failed":
        return {"ok": False, "error": f"状态 {v['status']}，无需 retry"}
    prev = {"downloading": "pending", "extracting": "downloading",
            "assets": "ready", "rendering": "ready_render", "qa": "ready_render"}.get(
        v["failed_stage"], "pending")
    set_status(video_id, prev)
    return {"ok": True, "video_id": video_id, "resumed_from": prev}


# ---------------------------------------------------------------- main
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="setup-video 调校视频→抖音竖屏 批量流水线 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    common.add_argument("--quiet", action="store_true")
    sub = parser.add_subparsers(dest="command", title="子命令")

    p = sub.add_parser("scan", parents=[common], help="轻：导入 URL 列表")
    p.add_argument("list")
    p = sub.add_parser("fetch", parents=[common], help="轻：下载（2 并发）")
    p.add_argument("video_id", nargs="?", default=None)
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("extract", parents=[common], help="轻：抽帧 + OCR + review.html")
    p.add_argument("video_id")
    p = sub.add_parser("review", parents=[common], help="轻：打开数值对照表")
    p.add_argument("video_id")
    p = sub.add_parser("approve-review", parents=[common], help="轻：数值人核放行")
    p.add_argument("video_id")
    p.add_argument("--fix", nargs="*", default=[], help='修正项: "参数=值"')
    p = sub.add_parser("script", parents=[common], help="轻：转录 + 脚本工单")
    p.add_argument("video_id")
    p = sub.add_parser("approve-script", parents=[common], help="轻：校验 episode.json → 放行")
    p.add_argument("video_id")
    p = sub.add_parser("assets", parents=[common], help="重：TTS + 素材（Worker）")
    p.add_argument("video_id")
    p = sub.add_parser("render", parents=[common], help="重：实例化+渲染+QA+成品包（Worker）")
    p.add_argument("video_id")
    sub.add_parser("status", parents=[common], help="队列状态")
    p = sub.add_parser("retry", parents=[common], help="从失败阶段续跑")
    p.add_argument("video_id")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        stage_status(args)
        sys.exit(0)
    elif args.command == "scan":
        res = stage_scan(args)
    elif args.command == "fetch":
        res = stage_fetch(args)
    elif args.command == "extract":
        res = stage_extract(args.video_id)
    elif args.command == "review":
        res = stage_review(args)
    elif args.command == "approve-review":
        res = stage_approve_review(args)
    elif args.command == "script":
        res = stage_script(args.video_id)
    elif args.command == "approve-script":
        res = stage_approve_script(args.video_id)
    elif args.command == "assets":
        res = stage_assets(args.video_id)
    elif args.command == "render":
        res = stage_render(args.video_id)
    elif args.command == "retry":
        res = stage_retry(args.video_id)
    else:
        res = {"ok": False, "error": f"未知命令 {args.command}"}

    if getattr(args, "json", False) or args.command in HEAVY:
        emit_json(res)
    elif not getattr(args, "quiet", False):
        if res.get("ok"):
            print(f"OK {args.command}: {json.dumps({k: v for k, v in res.items() if k != 'ok'}, ensure_ascii=False)}")
        else:
            print(f"FAIL {args.command}: {res.get('error')}"
                  + (f" {res.get('problems') or res.get('hits') or ''}" if isinstance(res, dict) else ""))
            sys.exit(1)


if __name__ == "__main__":
    main()
