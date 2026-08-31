"""Ticket 12 iteration v2: interaction-aware backgrounds (bed for lying, organs bigger/higher)."""
import json
import os
import sys
from pathlib import Path

OPENMONTAGE = r"E:\YifuAIForge\OpenMontage"
sys.path.insert(0, OPENMONTAGE)
os.chdir(OPENMONTAGE)

_env_path = Path(OPENMONTAGE) / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from tools.graphics.image_selector import ImageSelector  # noqa: E402

OUT = Path(OPENMONTAGE) / "issues" / "wayfinder-channel-stickman" / "prototypes" / "scene-samples"
OUT.mkdir(parents=True, exist_ok=True)

BASE = ("flat vector illustration, soft pastel palette, no text, no words, no letters, no signage, "
        "no people, simple clean composition, 9:16 vertical")

SCENES_V2 = {
    "bedroom_v2": BASE + ", a cozy bedroom at night, "
        "a bed with a visible flat mattress surface occupying the lower-middle area, "
        "moonlight through window in the upper area, soft pastel, calm, "
        "bed surface clear and unobstructed so a small character could lie on it",
    "organs_v2": BASE + ", a human body anatomy diagram, "
        "detailed cute flat organ shapes drawn in the upper-middle-right area, "
        "each organ clearly outlined and softly colored, "
        "a soft gradient wall with a subtle floor line in the background, "
        "simple decorative plant in the bottom-right corner",
}

SEL = ImageSelector()
results = []
for scene, prompt in SCENES_V2.items():
    out_path = OUT / f"{scene}__minimax.png"
    try:
        res = SEL.execute({
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "seed": 42,
            "preferred_provider": "minimax",
            "output_path": str(out_path),
        })
        results.append({"scene": scene, "ok": bool(res.success), "path": str(out_path), "error": res.error})
    except Exception as e:
        results.append({"scene": scene, "ok": False, "error": str(e)})

print(json.dumps({"success": True, "images": results}, ensure_ascii=False))