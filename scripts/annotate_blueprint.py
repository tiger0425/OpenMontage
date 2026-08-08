"""Annotate blueprint images with motion indicators (I2).

Reads a scene_plan beat and its blueprint PNG, draws element numbers (by
entrance_order), entrance-direction arrows (by family), and motion-name labels
(+stagger) on a COPY of the blueprint. Produces {beat_id}_annotated.png next
to the clean blueprint.

Usage:
    python scripts/annotate_blueprint.py --scene-plan <scene_plan.json> --beat b1.1 --blueprint assets/blueprints/b1.1.png [--out-dir assets/blueprints]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("PIL required: pip install pillow", file=sys.stderr)
    sys.exit(1)

# family -> arrow direction (entrance direction)
FAMILY_ARROW = {
    "slide": "from_left",
    "drop": "from_top",
    "slap": "from_top",
    "pop": "from_center",
    "unfold": "from_center",
    "wipe": "from_left",
    "mask_reveal": "from_center",
    "rotate": "from_top",
    "fade": "none",
}

# family -> label text
FAMILY_LABEL = {
    "slide": "SLIDE", "drop": "DROP", "slap": "SLAP", "pop": "POP",
    "unfold": "UNFOLD", "wipe": "WIPE", "mask_reveal": "REVEAL",
    "rotate": "ROTATE", "fade": "FADE",
}


def load_font(size: int):
    """Best-effort bold font: try素材库字体, fall back to PIL default."""
    candidates = [
        Path(__file__).resolve().parent.parent
        / "assets" / "shared_library" / "fonts" / "Oswald-Bold.ttf",
        Path(__file__).resolve().parent.parent
        / "assets" / "shared_library" / "fonts" / "Anton.ttf",
    ]
    for c in candidates:
        if c.exists():
            try:
                return ImageFont.truetype(str(c), size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def draw_arrow(d: ImageDraw.ImageDraw, cx: int, cy: int, direction: str, size: int = 60) -> None:
    """Draw an entrance-direction arrow centered at (cx, cy)."""
    if direction == "none":
        return
    red = (195, 59, 46, 255)
    lw = max(6, size // 10)
    if direction == "from_left":
        d.line([(cx - size, cy), (cx + size, cy)], fill=red, width=lw)
        d.polygon([(cx + size, cy - lw * 2), (cx + size + lw * 2, cy), (cx + size, cy + lw * 2)], fill=red)
    elif direction == "from_top":
        d.line([(cx, cy - size), (cx, cy + size)], fill=red, width=lw)
        d.polygon([(cx - lw * 2, cy + size), (cx, cy + size + lw * 2), (cx + lw * 2, cy + size)], fill=red)
    elif direction == "from_center":
        d.ellipse([cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2], outline=red, width=lw)


def annotate(
    blueprint_path: Path,
    scene_plan_path: Path,
    beat_id: str,
    out_dir: Path,
) -> Path:
    sp = json.loads(scene_plan_path.read_text(encoding="utf-8"))

    # locate beat
    beat = None
    for scene in sp["scenes"]:
        for b in scene.get("beats", []):
            if b["id"] == beat_id:
                beat = b
                break
        if beat:
            break
    if not beat:
        raise SystemExit(f"beat {beat_id!r} not found in scene_plan")

    img = Image.open(blueprint_path).convert("RGBA")
    W, H = img.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    font_num = load_font(44)
    font_label = load_font(30)

    # draw per-element annotations (img elements only; css elements marked CSS)
    order = 0
    for el in beat.get("elements", []):
        box = el.get("box")
        if not box:
            continue
        left, top, w, h = box
        cx = int(left / 100 * W)
        cy = int(top / 100 * H)
        cw = int(w / 100 * W)
        ch = int(h / 100 * H)

        if el.get("kind") == "css":
            # CSS decor: mark with small cyan tag
            d.rounded_rectangle([cx, cy, cx + 90, cy + 44], radius=8, fill=(0, 170, 170, 200))
            d.text((cx + 10, cy + 4), "CSS", font=font_label, fill=(255, 255, 255, 255))
            continue

        # number bubble (entrance order)
        order += 1
        num = str(order)
        bbox = d.textbbox((0, 0), num, font=font_num)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx, by = max(6, cx - 30), max(6, cy - 40)
        d.ellipse([bx, by, bx + bw + 30, by + bh + 20], fill=(195, 59, 46, 230))
        d.text((bx + 15 - bbox[0], by + 8 - bbox[1]), num, font=font_num, fill=(255, 255, 255, 255))

        # entrance arrow (center of element box)
        draw_arrow(d, cx + cw // 2, cy + ch // 2, FAMILY_ARROW.get(el.get("family", "fade"), "none"))

        # label: FAMILY + stagger
        family = FAMILY_LABEL.get(el.get("family", "fade"), el.get("family", "").upper())
        stagger = beat.get("stagger_ms", 400)
        label = f"{family} +{order * stagger // 1000:.1f}s"
        lbbox = d.textbbox((0, 0), label, font=font_label)
        lw2, lh2 = lbbox[2] - lbbox[0], lbbox[3] - lbbox[1]
        ly = min(H - lh2 - 10, cy + ch + 8)
        d.rounded_rectangle([cx, ly, cx + lw2 + 20, ly + lh2 + 12], radius=6, fill=(26, 26, 26, 200))
        d.text((cx + 10 - lbbox[0], ly + 5 - lbbox[1]), label, font=font_label, fill=(255, 255, 255, 255))

    # build-on / living-paper ratio bar at bottom
    ratio = beat.get("build_on_ratio", 0.7)
    bar_w = min(320, W - 20)
    d.rectangle([10, H - 26, 10 + bar_w, H - 10], fill=(60, 45, 20, 180))
    split_x = 10 + int(bar_w * ratio)
    d.rectangle([10, H - 26, split_x, H - 10], fill=(212, 168, 61, 220))
    d.text((16, H - 30), f"build-on {int(ratio*100)}% / living {int((1-ratio)*100)}%", font=font_label, fill=(255, 255, 255, 255))

    out = out_dir / f"{beat_id}_annotated.png"
    Image.alpha_composite(img, overlay).convert("RGB").save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Annotate blueprint with motion indicators")
    ap.add_argument("--scene-plan", required=True, type=Path, help="scene_plan JSON path")
    ap.add_argument("--beat", required=True, help="beat id, e.g. b1.1")
    ap.add_argument("--blueprint", required=True, type=Path, help="clean blueprint PNG path")
    ap.add_argument("--out-dir", type=Path, default=Path("assets/blueprints"))
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = annotate(args.blueprint, args.scene_plan, args.beat, args.out_dir)
    print(f"annotated blueprint: {out}")


if __name__ == "__main__":
    main()
