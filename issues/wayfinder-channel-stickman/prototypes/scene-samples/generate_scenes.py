"""Ticket 12 verification: 3 scene backgrounds x 2 providers (minimax vs imagen).

Routes through image_selector (AGENTS.md: selectors only). Outputs 9:16 images.
"""
import json
import os
import sys
from pathlib import Path

OPENMONTAGE = r"E:\YifuAIForge\OpenMontage"
sys.path.insert(0, OPENMONTAGE)
os.chdir(OPENMONTAGE)

# Load .env into process env (keys: MINIMAX_API_KEY / GOOGLE_API_KEY)
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

STYLE = ("flat vector illustration, soft pastel palette, no text, no words, no letters, no signage, "
         "no people, simple clean composition, subject placed on the right side, "
         "empty space on the left-center, 9:16 vertical")

SCENES = {
    "supermarket": "a supermarket aisle with shelves of groceries, anchor pricing signs (blank), warm lighting",
    "organs": "a friendly simplified human body anatomy diagram, organs as cute flat shapes, soft colors",
    "bedroom": "a cozy dark bedroom at night, moonlight through window, soft pastel, calm atmosphere",
}

SEL = ImageSelector()
results = []
for scene, subject in SCENES.items():
    prompt = STYLE + ", " + subject
    for provider in ["minimax", "google_imagen"]:
        out_path = OUT / f"{scene}__{provider}.png"
        try:
            res = SEL.execute({
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "seed": 42,
                "preferred_provider": provider,
                "output_path": str(out_path),
            })
            results.append({
                "scene": scene, "provider": provider,
                "ok": bool(res.success if hasattr(res, "success") else res.get("success")),
                "path": str(out_path),
                "error": getattr(res, "error", None),
            })
        except Exception as e:
            results.append({"scene": scene, "provider": provider, "ok": False, "error": str(e)})

print(json.dumps({"success": True, "images": results}, ensure_ascii=False))