#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑渲染 + QA + 成品包（重命令，Compute Worker danger-full-access 执行）。

用法:
  python apps/setup-video/template/render_explainer.py <project_dir> [--json]

流程：实测 wav 时长重新实例化 → hyperframes 渲染 → 基础 QA（时长/静音洞/非静音 BGM）
→ 定版 final.mp4 → 封面两张（s1 首幕 / s6 速查卡）→ 成品包（video/title/desc/publish/cover）
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(OMO_ROOT))

FFMPEG = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffprobe.exe"
GEN = OMO_ROOT / "apps" / "setup-video" / "template" / "instantiate_explainer.py"

# 特辑时长 QA 闸：口播 ~430s，成片预估 420-480s（不控时长，但用宽闸拦异常）
TOTAL_MIN, TOTAL_MAX = 300.0, 600.0


def run(cmd, cwd=None, env=None, timeout=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sh(cmd, timeout=120):
    return subprocess.run(cmd, timeout=timeout, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")


def ffprobe_dur(p):
    r = sh([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)])
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def main():
    proj = Path(sys.argv[1])
    use_json = "--json" in sys.argv
    compose = proj / "compose"
    assets = compose / "assets"
    ep_path = proj / "artifacts" / "episode.json"
    meta_path = proj / "artifacts" / "timings.json"

    # 1) 重新实例化（TTS 实测时长）
    env = dict(os.environ)
    env["npm_config_cache"] = str(OMO_ROOT / ".npm-cache")
    r = run([sys.executable, str(GEN), str(ep_path), str(assets),
             str(compose / "index.html"), "--meta", str(meta_path)], env=env, timeout=300)
    if r.returncode != 0:
        print(json.dumps({"ok": False, "stage": "instantiate", "error": "模板实例化失败"}, ensure_ascii=False))
        sys.exit(1)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # 1.5) BGM 必须铺满全片：源 bgm.mp3 是批量版短循环（~50-70s），不足成片长度 → 循环扩展
    #      （否则定格尾垫无 BGM → QA 静音洞，原理特辑第 1 期实测踩坑）
    bgm_src = assets / "bgm.mp3"
    bgm_len = ffprobe_dur(bgm_src) or 0
    need = meta["duration"] + 2.0
    if bgm_len < need:
        r = run([FFMPEG, "-y", "-stream_loop", "100", "-i", str(bgm_src),
                 "-t", f"{need:.1f}", "-c:a", "libmp3lame", "-q:a", "4",
                 str(assets / "bgm_full.mp3")], timeout=600)
        if r.returncode == 0 and (assets / "bgm_full.mp3").exists():
            (assets / "bgm_full.mp3").replace(bgm_src)
            print(f"[bgm] extended {bgm_len:.0f}s -> {need:.0f}s", flush=True)
        else:
            print(json.dumps({"ok": False, "stage": "bgm", "error": "BGM 循环扩展失败"}, ensure_ascii=False))
            sys.exit(1)

    # 2) 渲染（npm run render → hyperframes@0.7.109）
    (compose / "package.json").write_text(json.dumps({
        "name": "setup-explainer-01", "private": True, "type": "module",
        "scripts": {"render": "npx --yes hyperframes@0.7.109 render"}}), encoding="utf-8")
    (compose / "renders").mkdir(exist_ok=True)
    for old in (compose / "renders").glob("*.mp4"):
        old.unlink()
    r = run(["npm.cmd", "run", "render"], cwd=compose, env=env, timeout=5400)
    mps = sorted((compose / "renders").glob("*.mp4"))
    if r.returncode != 0 or not mps:
        print(json.dumps({"ok": False, "stage": "render", "error": "hyperframes 渲染失败",
                          "rc": r.returncode}, ensure_ascii=False))
        sys.exit(1)
    raw = mps[-1]

    # 3) 基础 QA
    qa_dir = proj / "artifacts" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    final_dur = ffprobe_dur(raw)
    qa = {"duration": final_dur, "ok_duration": bool(final_dur and TOTAL_MIN <= final_dur <= TOTAL_MAX)}
    sd = sh([FFMPEG, "-i", str(raw), "-af", "silencedetect=noise=-38dB:d=2.5", "-f", "null", "-"], timeout=900)
    qa["silence_holes_gt2.5s"] = [round(float(x), 1) for x in re.findall(r"silence_start: ([\d.]+)", sd.stdout or "")]
    # BGM 非静音
    vd = sh([FFMPEG, "-i", str(raw), "-af", "volumedetect", "-f", "null", "-"], timeout=300)
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", vd.stdout or "")
    qa["mean_volume_db"] = float(m.group(1)) if m else None
    qa["ok"] = qa["ok_duration"] and qa["silence_holes_gt2.5s"] == [] and (qa["mean_volume_db"] or -99) > -45
    (qa_dir / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    if not qa["ok"]:
        print(json.dumps({"ok": False, "stage": "qa", "qa": qa}, ensure_ascii=False))
        sys.exit(1)
    for k, ts in meta["qa_frames"].items():
        run([FFMPEG, "-y", "-ss", str(ts), "-i", str(raw), "-frames:v", "1",
             str(qa_dir / f"qa_{k}.jpg")], timeout=120)

    # 4) 定版 + 封面 + 成品包
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
    tags = pd.get("tags") or ["#AssettoCorsaRally", "#赛车调校", "#模拟赛车", "#赛车游戏"]
    (pkg / "publish.txt").write_text(
        f"{pd.get('title', '')}\n\n{pd.get('desc', '')}\n\n{' '.join(tags)}\n", encoding="utf-8")

    result = {"ok": True, "final": str(final), "package": str(pkg),
              "duration": final_dur, "qa": qa}
    print(json.dumps(result, ensure_ascii=False) if use_json else json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
