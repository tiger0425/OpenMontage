# -*- coding: utf-8 -*-
"""package 阶段：图文卡片合成（原图 3:4 + 文字卡片排版层）。

原则：AI 图内无文字（无字底稿）；要点文字由 PIL 排版层渲染后合成到卡片图。
每张卡片 = 原图 9:16 裁中部 75% 高度 → 3:4 (1080x1440) + 底部半透明文字卡片。
用法（闸门 B 放行后执行）：
    python apps/ref-remake/scripts/build_note_cards.py --config <note_card_config.json>
"""
import json
import argparse
import os
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",      # Microsoft YaHei Bold
    "C:/Windows/Fonts/msyh.ttc",        # Microsoft YaHei
    "C:/Windows/Fonts/simhei.ttf",      # SimHei
    "C:/Windows/Fonts/NotoSansSC-Bold.otf",
]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) > max_width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
    return lines


def make_card(src: str, dst: str, point: str, title: str = "") -> None:
    img = Image.open(src).convert("RGB")
    w, h = img.size  # 720x1280
    # 裁中部 75% 高度 -> 3:4
    crop_h = int(h * 0.75)
    top = (h - crop_h) // 2
    img = img.crop((0, top, w, top + crop_h))
    # 放大到 1080x1440
    img = img.resize((1080, 1440), Image.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")

    # 底部半透明文字卡片
    card_top = 1080
    overlay = Image.new("RGBA", (1080, 1440 - card_top), (252, 251, 247, 235))
    img.paste(overlay, (0, card_top), overlay)
    draw = ImageDraw.Draw(img)

    y = card_top + 40
    if title:
        f_title = load_font(72)
        draw.text((60, y), title, fill=(26, 26, 26), font=f_title)
        y += 110
    f_body = load_font(56)
    for line in wrap_text(draw, point, f_body, 960):
        draw.text((60, y), line, fill=(26, 26, 26), font=f_body)
        y += 80

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    img.save(dst, "PNG")
    print("card:", dst)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    out_dir = os.path.join(cfg["project"], "assets", "notes")
    for i, card in enumerate(cfg["cards"], 1):
        src = os.path.join(cfg["project"], "assets", "images", f"{card['image']}.png")
        dst = os.path.join(out_dir, f"card_{i:02d}.png")
        make_card(src, dst, card["point"], card.get("title", ""))


if __name__ == "__main__":
    main()
