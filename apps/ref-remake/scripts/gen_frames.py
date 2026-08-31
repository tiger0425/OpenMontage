# -*- coding: utf-8 -*-
"""ref-remake 生图模板：V2 点缀式 + 参考图锚点（MiniMax image-01）。

用法（workdir 必须在 OpenMontage 根目录）：
    python apps/ref-remake/scripts/gen_frames.py --config projects/<slug>/artifacts/frames_config.json

frames_config.json 格式：
{
  "project": "projects/<slug>",
  "anchor": "background_library/ref-remake/anchor/ahhuang_anchor.png",
  "style_block": "STYLE_BLOCK 文本（省略则用 styles/ref-remake.yaml 的 image_prompt_prefix）",
  "frames": [
    {"name": "s0_0", "seed": 6001, "scene": "The yellow blob character sitting on a pile of books, a glowing light bulb icon above head..."}
  ]
}
"""
import os
import sys
import json
import argparse
import time

sys.path.insert(0, os.getcwd())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="frames_config.json 路径")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    project = cfg["project"]
    anchor = cfg.get("anchor", r"background_library\ref-remake\anchor\ahhuang_anchor.png")
    style_block = cfg.get("style_block") or _style_block_from_playbook()
    out_dir = os.path.join(project, "assets", "images")
    os.makedirs(out_dir, exist_ok=True)

    from tools.graphics.minimax_image import MiniMaxImage

    tool = MiniMaxImage()
    results = []
    for item in cfg["frames"]:
        name = item["name"]
        seed = item["seed"]
        scene = item["scene"]
        out = os.path.join(out_dir, f"{name}.png")
        print(f"[{name}] generating...", flush=True)
        r = tool.execute({
            "prompt": f"{style_block} {scene}",
            "aspect_ratio": "9:16",
            "seed": seed,
            "reference_image": anchor,
            "output_path": out,
        })
        ok = r.success
        err = (r.error or "")[:150]
        print(f"[{name}] success={ok} err={err}", flush=True)
        results.append({"name": name, "success": ok, "error": err, "path": out})
        time.sleep(0.8)

    summary = {
        "summary": {"total": len(results), "ok": sum(1 for x in results if x["success"])}
    }
    print(json.dumps(summary, ensure_ascii=False))


def _style_block_from_playbook() -> str:
    """从 styles/ref-remake.yaml 读取 image_prompt_prefix（verbatim 风格块）。"""
    import yaml
    with open("styles/ref-remake.yaml", encoding="utf-8") as f:
        playbook = yaml.safe_load(f)
    return playbook["asset_generation"]["image_prompt_prefix"].strip()


if __name__ == "__main__":
    main()
