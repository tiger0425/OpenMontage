# -*- coding: utf-8 -*-
"""ref-remake 配音模板：IndexTTS 克隆音色分段配音。

用法（workdir 必须在 OpenMontage 根目录）：
    python apps/ref-remake/scripts/gen_tts.py --config projects/<slug>/artifacts/tts_config.json

tts_config.json 格式：
{
  "project": "projects/<slug>",
  "voice_ref": "D:/index-tts/voice_ref_futian3.wav",
  "seed": 20260825,
  "speed": 1.0,
  "segments": [
    {"name": "00_open", "text": "中文旁白..."}
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
    ap.add_argument("--config", required=True, help="tts_config.json 路径")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    project = cfg["project"]
    voice_ref = cfg.get("voice_ref", r"D:\index-tts\voice_ref_futian3.wav")
    seed = cfg.get("seed", 20260825)
    speed = cfg.get("speed", 1.0)

    os.environ["INDEXTTS_VOICE_REF"] = voice_ref

    from tools.audio.indextts_tts import IndexTTS2TTS

    tool = IndexTTS2TTS()
    base = os.path.join(project, "assets", "audio")
    os.makedirs(base, exist_ok=True)

    results = []
    for item in cfg["segments"]:
        name = item["name"]
        text = item["text"]
        out = os.path.join(base, f"seg_{name}.wav")
        print(f"[{name}] generating ({len(text)} chars)...", flush=True)
        r = tool.execute({
            "text": text,
            "output_path": out,
            "seed": seed,
            "speed": speed,
        })
        ok = r.success
        err = (r.error or "")[:150]
        print(f"[{name}] success={ok} err={err}", flush=True)
        results.append({"name": name, "success": ok, "error": err, "path": out})
        time.sleep(1)

    print(json.dumps({"summary": {"total": len(results), "ok": sum(1 for x in results if x["success"])}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
