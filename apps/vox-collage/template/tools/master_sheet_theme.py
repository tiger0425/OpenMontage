# -*- coding: utf-8 -*-
"""主题化基准图母版生成器 (master_sheet_theme.py)

问题：`presets/<theme>/` 只有 `archival-red` 附带 `master_sheet_16_9.png`。
`new` 命令对其它主题会**静默回退**到 archival-red 的棕色母版，导致
「基准图前置锚定」铁律被破坏（风格锚与调色板 tokens 不一致）。

解法：以 archival-red 母版为版式底稿，按设计代币做「锚点色置换 + 亮度保持」重着色，
生成主题专属母版并落盘到 `presets/<theme>/master_sheet_16_9.png`，让锚点永远自洽。
"""

from pathlib import Path

import numpy as np
from PIL import Image

# archival-red 母版的 6 个语义锚点色（源自 design-system.md）
ANCHORS = [
    ((0xC9, 0xBB, 0x9C), "stage_tan", (0xC9, 0xBB, 0x9C)),
    ((0x1A, 0x1A, 0x1A), "ink_black", (0x1A, 0x1A, 0x1A)),
    ((0x8C, 0x8C, 0x8C), "halftone_gray", (0x8C, 0x8C, 0x8C)),
    ((0xB6, 0x2E, 0x1F), "accent_red", (0xB6, 0x2E, 0x1F)),
    ((0xD9, 0xA4, 0x41), "tag_mustard", (0xD9, 0xA4, 0x41)),
    ((0xF7, 0xF5, 0xEE), "paper_white", (0xF7, 0xF5, 0xEE)),
]


def _hex_to_rgb(hex_str: str, fallback):
    try:
        h = str(hex_str).lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return fallback


def _luminance(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def build_theme_master_sheet(src_png: Path, tokens: dict, dst_png: Path) -> Path:
    """把 archival-red 母版重着色为主题母版。

    对每个像素做「最近锚点 + 亮度比例保持」置换：既套上主题调色板，
    又保留纸张纤维、网点与暗角等原始质感。
    """
    src_png = Path(src_png)
    dst_png = Path(dst_png)
    if not src_png.exists():
        raise FileNotFoundError(f"base master sheet not found: {src_png}")

    palette = (tokens or {}).get("palette", {})

    src_anchors = np.array([a[0] for a in ANCHORS], dtype=np.float32)
    tgt_anchors = np.array(
        [_hex_to_rgb(palette.get(a[1]), a[2]) for a in ANCHORS], dtype=np.float32
    )

    img = Image.open(src_png).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)

    # 每个像素到 6 个锚点的欧氏距离，取最近锚点
    diff = arr[:, :, None, :] - src_anchors[None, None, :, :]
    dist = np.sum(diff * diff, axis=-1)
    idx = np.argmin(dist, axis=-1)

    # 亮度比例保持（避免整体压成纯色块，保留纸张质感）
    lum_src = _luminance(arr)
    lum_anchor = np.maximum(_luminance(src_anchors), 1.0)
    ratio = np.clip(lum_src / lum_anchor[idx], 0.45, 1.4)

    out = tgt_anchors[idx] * ratio[:, :, None]
    out = np.clip(out, 0, 255).astype(np.uint8)

    dst_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, mode="RGB").save(dst_png, "PNG")
    return dst_png
