#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console-remake 封面排版层（apps/console-remake/template/make_cover.py）

封面两步法（见 .agents/skills/console-remake/SKILL.md）：
  1) 生图工具产「无字底稿」：image_selector（prompt 强调 no text/letters/numbers，
     构图预留左侧暗部给排版），建议 16:9 与 4:3 各出 2 张候选择优；
  2) 本脚本叠字：左侧渐变遮罩 + 红色强调条 + 标题/副题/中文版标签。

用法：
  python apps/console-remake/template/make_cover.py \
      --bg projects/<slug>/assets/covers/bg_169.png --size 1920x1080 \
      --title "Agent Harness 是什么？" --sub "8 分钟看懂「比模型更重要的那层壳」" \
      --tag "中文版 · 控制台译制" --out projects/<slug>/package/cover_16x9.png \
      [--bias 0.5] [--title-base 96] [--block-y 0.62]
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

F_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
F_REG = "C:/Windows/Fonts/msyh.ttc"
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # 老版本 Pillow
    RESAMPLE = 1


def fit_font(draw, text, path, size, max_w):
    f = ImageFont.truetype(path, size)
    while draw.textbbox((0, 0), text, font=f)[2] > max_w and size > 20:
        size -= 2
        f = ImageFont.truetype(path, size)
    return f, size


def make_cover(bg, canvas, out, title, sub, tag, crop_bias=0.5,
               title_base=96, block_y=0.62):
    W, H = canvas
    im = Image.open(bg).convert("RGBA")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s + 0.5), int(im.height * s + 0.5)), RESAMPLE)
    left = int((im.width - W) * crop_bias)
    top = int((im.height - H) * 0.5)
    im = im.crop((left, top, left + W, top + H))

    # 左侧 + 底部渐变遮罩（保证字可读）
    s1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d1 = ImageDraw.Draw(s1)
    for x in range(W):
        a = int(208 * max(0.0, 1 - x / (W * 0.68)) ** 1.15)
        if a:
            d1.line([(x, 0), (x, H)], fill=(5, 7, 9, a))
    im = Image.alpha_composite(im, s1)
    s2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(s2)
    y0 = int(H * 0.52)
    for y in range(y0, H):
        a = int(150 * ((y - y0) / (H - y0)) ** 1.25)
        if a:
            d2.line([(0, y), (W, y)], fill=(5, 7, 9, a))
    im = Image.alpha_composite(im, s2)

    d = ImageDraw.Draw(im)
    mx = W - 140
    ft, ts = fit_font(d, title, F_BOLD, title_base, mx - 150)
    fs, ss = fit_font(d, sub, F_REG, int(title_base * 0.42), mx - 150)
    fg = ImageFont.truetype(F_REG, int(title_base * 0.30))

    bx = 96 if W > 1600 else 72
    by = int(H * block_y)
    th = ts + int(ts * 0.72)
    d.rectangle([bx, by - 6, bx + 8, by + th + int(ss * 1.6)], fill=(229, 72, 77))
    d.text((bx + 40, by), title, font=ft, fill=(243, 246, 248),
           stroke_width=2, stroke_fill=(5, 7, 9))
    d.text((bx + 42, by + th), sub, font=fs, fill=(201, 209, 217))
    d.text((bx + 44, by + th + int(ss * 1.7)), tag, font=fg, fill=(139, 148, 158))

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, "PNG")
    return out


def main():
    ap = argparse.ArgumentParser(description="封面排版层（无字底稿 → 叠字）")
    ap.add_argument("--bg", required=True)
    ap.add_argument("--size", default="1920x1080", help="如 1920x1080 / 1440x1080")
    ap.add_argument("--title", required=True)
    ap.add_argument("--sub", default="")
    ap.add_argument("--tag", default="中文版 · 控制台译制")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bias", type=float, default=0.5, help="裁剪横向偏置 0~1")
    ap.add_argument("--title-base", type=int, default=96)
    ap.add_argument("--block-y", type=float, default=0.62)
    args = ap.parse_args()
    w, h = (int(x) for x in args.size.lower().split("x"))
    out = make_cover(args.bg, (w, h), args.out, args.title, args.sub, args.tag,
                     crop_bias=args.bias, title_base=args.title_base, block_y=args.block_y)
    print(f"cover saved: {out} ({w}x{h})")


if __name__ == "__main__":
    main()
