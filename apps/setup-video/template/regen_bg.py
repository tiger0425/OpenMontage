#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑 v4：背景重截 v2（快）——避开广告/人物段。

策略：从源视频"避开广告窗"的干净区间里取最长连续段，ffmpeg 抽帧验证有运动（C3）。
用法:
  python apps/setup-video/template/regen_bg.py <episode.json> <assets_dir>
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(OMO_ROOT))

FFMPEG = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"
SRC_ROOT = OMO_ROOT / "projects" / "setup-video" / "assetto-corsa-rally"

AD_WINDOWS = {
    "208-rally4-wales": [(252, 298)],
    "208-rally4-alsace": [(228, 235)],
    "delta-hf-integrale-wales": [(283, 288)],
    "delta-hf-integrale-alsace": [(105, 111)],
    "fabia-rs-rally2-wales": [(111, 126), (320, 334)],
    "fabia-rs-rally2-greece": [(100, 114), (476, 493)],
    "impreza-s3-monte-carlo": [(105, 119), (250, 270)],
    "i20n-rally2-monte-carlo": [(106, 115)],
    "i20-n-wales": [(105, 119), (327, 340)],
    "fabia-rs-rally2-greece-2": [],
}


def ffprobe_dur(p):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def clean_ranges(dur, ad_windows):
    """避开广告窗的干净区间列表。"""
    bounds = [(0, dur)]
    for a, b in ad_windows:
        new = []
        for lo, hi in bounds:
            if a >= hi or b <= lo:
                new.append((lo, hi))
            else:
                if lo < a:
                    new.append((lo, a))
                if b < hi:
                    new.append((b, hi))
        bounds = new
    return sorted(bounds)


def has_motion(src, t0, t1, n=5):
    """区间内均布抽 n 帧，相邻帧灰度差均值 > 阈值 = 有运动。"""
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        frames = []
        for i in range(n):
            t = t0 + (t1 - t0) * (i + 0.5) / n
            out = Path(td) / f"f{i}.jpg"
            subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=96:54", "-q:v", "6", str(out)],
                           capture_output=True, timeout=120)
            if out.exists():
                frames.append(Image.open(out).convert("L"))
        if len(frames) < 3:
            return False
        diffs = []
        for i in range(len(frames) - 1):
            a, b = frames[i], frames[i + 1]
            diff = sum(abs(pa - pb) for pa, pb in zip(a.tobytes(), b.tobytes()))
            diffs.append(diff / (96 * 54))
        return sum(diffs) / len(diffs) > 3.0


def main():
    ep_path, assets_dir = Path(sys.argv[1]), Path(sys.argv[2])
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    scenes = ep["scenes"]
    durs = {k: len(ep["narration"][k]) / 5.0 + 1.0 for k in ["s1", "s2", "s3", "s4", "s5", "s6"]}
    TAIL = {"s1": 0.8, "s2": 0.9, "s3": 0.9, "s4": 0.9, "s5": 0.9, "s6": 5.0}
    need_by_slug = {}
    for k, sc in scenes.items():
        slugs = sc.get("bg", [])
        split = sc.get("bg_split") or [1.0 / len(slugs)] * len(slugs)
        win = durs[k] + TAIL[k]
        for slug, ratio in zip(slugs, split):
            need_by_slug[slug] = max(need_by_slug.get(slug, 0), win * ratio)

    results = {}
    for slug, need in need_by_slug.items():
        src = SRC_ROOT / slug / "assets" / "original.mp4"
        out = assets_dir / f"bg_{slug}.mp4"
        if not src.exists():
            results[slug] = "NO_SOURCE"
            continue
        src_dur = ffprobe_dur(src) or 600
        ranges = [r for r in clean_ranges(src_dur, AD_WINDOWS.get(slug, [])) if r[1] - r[0] >= need + 2]
        picked = None
        for lo, hi in ranges:
            # 从中段取 need 秒，偏移试探
            for offset in (0.0, -0.15, 0.15):
                t0 = lo + (hi - lo - need) * (0.3 + offset)
                t0 = max(lo + 0.5, min(t0, hi - need - 0.5))
                t1 = t0 + need
                if has_motion(str(src), t0, t1):
                    picked = (t0, t1)
                    break
            if picked:
                break
        if picked is None:
            results[slug] = "NO_MOTION"
            print(f"[bg] {slug}: NO_MOTION need={need:.0f}s", flush=True)
            continue
        t0, t1 = picked
        r = subprocess.run([FFMPEG, "-y", "-ss", str(t0), "-to", str(t1), "-i", str(src),
                            "-vf", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,fps=30",
                            "-an", "-c:v", "libx264", "-crf", "23", "-g", "30", str(out)],
                           capture_output=True, timeout=1800)
        results[slug] = "OK" if (r.returncode == 0 and out.exists()) else f"FAIL({r.returncode})"
        print(f"[bg] {slug}: {results[slug]} {round(t0,1)}-{round(t1,1)}s need={round(need,1)}s", flush=True)
    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
