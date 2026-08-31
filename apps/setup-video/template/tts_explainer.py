#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑 TTS：IndexTTS fixed calm 合成 6 段口播 → compose/assets/s1..s6.wav。

用法:
  python apps/setup-video/template/tts_explainer.py <episode.json> <assets_dir> [--json]

重命令：GPU 锁贯穿（OPENMONTAGE_GPU_LOCK_PATH 可指 workspace 内）；Worker 以 danger-full-access 跑。
"""
import json
import os
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(OMO_ROOT))

TTS = dict(use_emo_text=False, emo_alpha=1.0, seed=42, speed=1.0,
           spk_audio_prompt="D:/index-tts/my_voice.wav")


def main():
    ep_path, assets_dir = Path(sys.argv[1]), Path(sys.argv[2])
    use_json = "--json" in sys.argv
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assets_dir.mkdir(parents=True, exist_ok=True)

    from lib.gpu_lock import gpu_lock
    from tools.audio.indextts_tts import IndexTTS2TTS

    tool = IndexTTS2TTS()
    made, skipped = [], []
    with gpu_lock(label="setup-tts-explainer", timeout=1800, heartbeat=30):
        for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
            out = assets_dir / f"{k}.wav"
            text = ep["narration"][k]
            res = tool.execute({"text": text, "output_path": str(out),
                                "spk_audio_prompt": TTS["spk_audio_prompt"],
                                "use_emo_text": TTS["use_emo_text"],
                                "emo_alpha": TTS["emo_alpha"],
                                "seed": TTS["seed"], "speed": TTS["speed"]})
            if not res.success:
                print(json.dumps({"ok": False, "k": k, "error": res.error}, ensure_ascii=False))
                sys.exit(1)
            made.append(k)
            print(f"[tts] {k} done -> {out}", flush=True)

    result = {"ok": True, "made": made, "dir": str(assets_dir)}
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result)


if __name__ == "__main__":
    main()
