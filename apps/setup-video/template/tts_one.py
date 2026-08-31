#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单段口播重录（G1 指纹定向重录场景）。用法:
  python apps/setup-video/template/tts_one.py <episode.json> <assets_dir> <segment> [--json]
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
    ep_path, assets_dir, k = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    use_json = "--json" in sys.argv
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    from lib.gpu_lock import gpu_lock
    from tools.audio.indextts_tts import IndexTTS2TTS
    tool = IndexTTS2TTS()
    out = assets_dir / f"{k}.wav"
    with gpu_lock(label="setup-tts-explainer", timeout=1800, heartbeat=30):
        res = tool.execute({"text": ep["narration"][k], "output_path": str(out),
                            "spk_audio_prompt": TTS["spk_audio_prompt"],
                            "use_emo_text": TTS["use_emo_text"],
                            "emo_alpha": TTS["emo_alpha"],
                            "seed": TTS["seed"], "speed": TTS["speed"]})
    if not res.success:
        print(json.dumps({"ok": False, "k": k, "error": res.error}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"ok": True, "k": k, "out": str(out)}, ensure_ascii=False) if use_json
          else {"ok": True, "k": k, "out": str(out)})


if __name__ == "__main__":
    main()
