#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑素材制备：从 10 条批量项目复制选定的背景/驾驶/证据素材到特辑 compose/assets/。

用法:
  python apps/setup-video/template/prepare_explainer_assets.py <episode.json> <project_dir>

按 episode.scenes 的引用组装：
  bg_<slug>.mp4     ← projects/setup-video/assetto-corsa-rally/<slug>/assets/bg_loop.mp4
  drive_<slug>.mp4  ← .../s1_drive.mp4（仅 s1 drive_clips_mix 用）
  ev_<slug>_<shot>.png ← .../shot_<shot>.png
  bgm.mp3           ← 任一源 bgm.mp3（无则 FALLBACK_BGM）
"""
import json
import re
import shutil
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC_ROOT = OMO_ROOT / "projects" / "setup-video" / "assetto-corsa-rally"
FALLBACK_BGM = OMO_ROOT / "projects" / "setup-video-template" / "assets" / "bgm.mp3"


def main():
    ep_path, proj_dir = Path(sys.argv[1]), Path(sys.argv[2])
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assets = proj_dir / "compose" / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    scenes = ep["scenes"]
    done = {"bg": [], "drive": [], "ev": [], "bgm": []}

    def copy(src: Path, dst: Path, kind: str, key: str):
        if not src.exists():
            print(f"[warn] 缺源: {src}", file=sys.stderr)
            return
        shutil.copy2(src, dst)
        done[kind].append(key)

    # 背景 / 驾驶
    for k, sc in scenes.items():
        for slug in sc.get("bg", []):
            src_bg = SRC_ROOT / slug / "assets" / "bg_loop.mp4"
            copy(src_bg, assets / f"bg_{slug}.mp4", "bg", f"{slug}")
            if sc.get("bg_mode") == "drive_clips_mix":
                src_dr = SRC_ROOT / slug / "assets" / "s1_drive.mp4"
                copy(src_dr, assets / f"drive_{slug}.mp4", "drive", slug)
    # 证据截图
    for k, sc in scenes.items():
        for key, ref in (sc.get("evidence") or {}).items():
            m = re.fullmatch(r"([\w-]+)/(shot_s\d(?:_\d)?)", ref)
            if not m:
                continue
            slug, shot = m.group(1), m.group(2)
            src = SRC_ROOT / slug / "assets" / f"{shot}.png"
            copy(src, assets / f"ev_{slug}_{shot}.png", "ev", f"{slug}_{shot}")
    # BGM
    bgm_src = next((SRC_ROOT / s / "assets" / "bgm.mp3" for s in ["208-rally4-wales", "delta-hf-integrale-wales"]
                    if (SRC_ROOT / s / "assets" / "bgm.mp3").exists()), None)
    if bgm_src:
        copy(bgm_src, assets / "bgm.mp3", "bgm", "bgm")
    elif FALLBACK_BGM.exists():
        copy(FALLBACK_BGM, assets / "bgm.mp3", "bgm", "bgm(fallback)")

    print(json.dumps({
        "ok": True,
        "bg": done["bg"], "drive": done["drive"], "ev": done["ev"],
        "bgm": done["bgm"], "target": str(assets),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
