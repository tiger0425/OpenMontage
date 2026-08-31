#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ocr.json 的聚类代表帧拼成带时间戳标签的网格图，供对账。"""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

vid = sys.argv[1]
proj = Path(r"E:\YifuAIForge\OpenMontage\projects\setup-video\_incoming") / vid
ocr = json.loads((proj / "artifacts" / "ocr.json").read_text(encoding="utf-8"))
recs = ocr["frames"]

CELL_W, CELL_H, LABEL = 240, 135, 22
COLS = 8
rows = (len(recs) + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * CELL_W, rows * (CELL_H + LABEL)), (18, 18, 24))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 16)
except Exception:
    font = ImageFont.load_default()

for i, rec in enumerate(recs):
    cx, cy = (i % COLS) * CELL_W, (i // COLS) * (CELL_H + LABEL)
    img = Image.open(rec["frame"]).convert("RGB").resize((CELL_W, CELL_H))
    sheet.paste(img, (cx, cy + LABEL))
    mark = "*" if (rec.get("kind") == "config" and not rec.get("superseded")) else " "
    draw.text((cx + 4, cy + 3), f"#{i:02d} {rec['ts']}s{mark}", fill=(255, 214, 10), font=font)

out = proj / "artifacts" / "contact_sheet.jpg"
sheet.save(out, quality=88)
print(json.dumps({"ok": True, "cells": len(recs), "out": str(out)}, ensure_ascii=False))
