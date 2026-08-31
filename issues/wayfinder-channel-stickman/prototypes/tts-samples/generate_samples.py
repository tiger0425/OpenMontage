"""Generate TTS voice samples for ticket 09 (channel-stickman voice selection).

Uses IndexTTSSession (apps/indextts-bridge/client.py) per CALLING.md:
- use_emo_text=False, no emo_vector (pure cloning, no voice drift)
- UTF-8 via Python subprocess (handled by client)
- Same narration text for every candidate voice ref
"""
import importlib.util
import os
import sys
import json
from pathlib import Path

OPENMONTAGE = r"E:\YifuAIForge\OpenMontage"
OUT_DIR = Path(OPENMONTAGE) / "issues" / "wayfinder-channel-stickman" / "prototypes" / "tts-samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_spec = importlib.util.spec_from_file_location(
    "indextts_client", os.path.join(OPENMONTAGE, "apps", "indextts-bridge", "client.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

TEXT = ("大家好，我是柴米。今天告诉你一个生活冷知识："
        "你的身体里，其实藏着三个你可能一辈子都用不上的零件。"
        "每天两分钟，看完就能用。")

VOICES = {
    "voice_05": r"D:\index-tts\examples\voice_05.wav",
    "voice_09": r"D:\index-tts\examples\voice_09.wav",
    "voice_11": r"D:\index-tts\examples\voice_11.wav",
    "my_voice": r"D:\index-tts\my_voice.wav",
}

results = []
for name, ref in VOICES.items():
    out = OUT_DIR / f"sample_{name}.wav"
    try:
        with _mod.IndexTTSSession(voice_ref=ref, model_version="2.5", lang="ZH", emotion="calm") as tts:
            ok = tts.synthesize(TEXT, str(out))
        results.append({"voice": name, "ref": ref, "ok": ok, "path": str(out)})
    except Exception as e:
        results.append({"voice": name, "ref": ref, "ok": False, "error": str(e)})

print(json.dumps({"success": True, "samples": results}, ensure_ascii=False))
