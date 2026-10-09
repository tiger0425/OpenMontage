# -*- coding: utf-8 -*-
"""VOX Collage 资料图排版生成引擎 (dataliao_builder.py)

支持 16:9 横屏 (1920x1080) 与 9:16 竖屏 (1080x1920) 两种画幅自适应。
严格按照 design-system.md 规范，将真实照片排版为半调剪贴报刊底板。
产物作为 Qwen-Image-Edit 2.1 风格化流的输入资料图。
"""

import math
import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

# 六大微场景构图范式 (design-system.md §5) —— 与 collage_episode.schema.json 的 mode 枚举严格一致
VALID_MODES = (
    "stat_hero",            # 模式 A 数据流向叙事
    "map_pin",              # 模式 B 地图时空标定
    "archival_mat",         # 模式 C 档案相纸散落
    "exploded_blueprint",   # 模式 D 技术爆炸拆解
    "versus_clash",         # 模式 E 双阵营天平对抗
    "macro_halftone",       # 模式 F 局部网点特写
)

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None

FONTS_WINDOWS = {
    "cjk_bold": r"C:\Windows\Fonts\msyhbd.ttc",
    "cjk_heavy": r"C:\Windows\Fonts\simhei.ttf",
    "impact": r"C:\Windows\Fonts\impact.ttf",
    "typewriter": r"C:\Windows\Fonts\simsun.ttc",
    "serif": r"C:\Windows\Fonts\georgia.ttf",
}


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb) -> float:
    """感知亮度 (0~255)，用于自动挑选与撕纸白底对比的标题墨色。"""
    r, g, b = rgb[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def annot_label(annot: str) -> str:
    """规范化图注前缀，避免出现 'Fig. - Fig. 1 - ...' 的双前缀。"""
    a = (annot or "").strip()
    if not a:
        return ""
    if a[:3].lower() == "fig":
        return a
    return f"Fig. - {a}"


def load_font(font_key: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS_WINDOWS.get(font_key, r"C:\Windows\Fonts\msyhbd.ttc")
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(r"C:\Windows\Fonts\simhei.ttf", size)
        except Exception:
            return ImageFont.load_default()


def validate_mode_rotation(scenes: list) -> tuple:
    """校验 design-system.md §5「严禁连续两幕采用同一种构图」。

    这条铁律在 schema 层无法表达 (JSON Schema draft-07 没有 "不等于上一项" 约束)，
    因此必须在运行期强制。本函数是全片唯一执行点。

    返回 (errors, warnings)：
      errors   —— 必须修复：非法/缺失 mode、相邻两幕同 mode
      warnings —— 建议修复：跨章节同 mode、全片范式过度集中
    """
    errors, warnings = [], []
    seq = [s for s in scenes if isinstance(s, dict)]

    for s in seq:
        mode = s.get("mode")
        sid = s.get("id", "?")
        if not mode:
            # build_scene() 缺省会静默回落 stat_hero，相邻两幕都缺省就会构图雷同
            errors.append(f"幕 {sid}: 缺少 mode 字段（六大范式之一：{'/'.join(VALID_MODES)}）")
        elif mode not in VALID_MODES:
            errors.append(f"幕 {sid}: 非法 mode '{mode}'，必须是 {'/'.join(VALID_MODES)} 之一")

    for a, b in zip(seq, seq[1:]):
        ma, mb = a.get("mode"), b.get("mode")
        if ma and ma == mb:
            same_chapter = a.get("chapter") and a.get("chapter") == b.get("chapter")
            msg = f"幕 {a.get('id','?')} 与 幕 {b.get('id','?')} 构图雷同（均为 {ma}）"
            (errors if same_chapter or not a.get("chapter") else warnings).append(msg)

    used = {s.get("mode") for s in seq if s.get("mode")}
    if len(seq) >= 4 and len(used) == 1:
        warnings.append(
            f"全片 {len(seq)} 幕仅使用一种构图范式（{used.pop()}），"
            "「范式轮转」形同虚设，建议至少覆盖 3 种"
        )
    return errors, warnings


class DataliaoEngine:
    def __init__(self, ratio: str = "16:9", tokens: dict = None, cache_dir: Path = None):
        self.ratio = ratio
        if ratio == "16:9":
            self.width, self.height = 1920, 1080
        else:
            self.width, self.height = 1080, 1920

        palette = (tokens or {}).get("palette", {})
        self.c_stage = hex_to_rgb(palette.get("stage_tan", "#C9BB9C"))
        self.c_ink = hex_to_rgb(palette.get("ink_black", "#1A1A1A"))
        self.c_gray = hex_to_rgb(palette.get("halftone_gray", "#8C8C8C"))
        self.c_accent = hex_to_rgb(palette.get("accent_red", "#B62E1F"))
        self.c_tag = hex_to_rgb(palette.get("tag_mustard", "#D9A441"))
        self.c_white = hex_to_rgb(palette.get("paper_white", "#F7F5EE"))

        # 撕纸底衬永远是浅色相纸，标题墨色必须与白纸形成对比。
        # 深色主题（tech-cyan 等）的 ink_black 是近白色，直接用它写字会白字白底不可读，
        # 因此这里自动挑选：优先 ink，其次 stage（深底主题的深色），最后兜底近黑。
        strip_lum = luminance(self.c_white)
        if luminance(self.c_ink) <= strip_lum - 70:
            self.c_strip_ink = self.c_ink
        elif luminance(self.c_stage) <= strip_lum - 70:
            self.c_strip_ink = self.c_stage
        else:
            self.c_strip_ink = (26, 26, 26)

        self.cache_dir = cache_dir or Path(".media/refs/_cutouts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rng = random.Random(42)

    def create_paper_background(self) -> Image.Image:
        """生成具备哑光纤维颗粒与暗角的档案纸底 (The Stage)"""
        w, h = self.width, self.height
        base = Image.new("RGB", (w, h), self.c_stage)
        # 纸张纤维噪点
        noise = Image.effect_noise((w, h), 16).convert("L").point(lambda v: 210 + v // 6)
        base = Image.composite(base, base.point(lambda v: int(v * 0.94)), noise)

        # 档案局部轻微斑点与深浅交错
        spots = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(spots)
        for _ in range(12):
            cx, cy = self.rng.randint(0, w), self.rng.randint(0, h)
            rx, ry = self.rng.randint(120, 360), self.rng.randint(90, 280)
            d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=self.rng.randint(10, 35))
        spots = spots.filter(ImageFilter.GaussianBlur(70))
        deeper_color = tuple(max(0, int(c * 0.86)) for c in self.c_stage)
        base = Image.composite(Image.new("RGB", (w, h), deeper_color), base, spots)

        # 四周暗角 (Vignette)
        vg = Image.new("L", (w, h), 0)
        ImageDraw.Draw(vg).ellipse([-w // 4, -h // 4, w + w // 4, h + h // 4], fill=255)
        vg = vg.filter(ImageFilter.GaussianBlur(160))
        base = Image.composite(base, base.point(lambda v: int(v * 0.88)), vg)
        return base

    def get_cutout(self, img_path: Path) -> Image.Image:
        """带缓存的 rembg 真实照片主体抠图"""
        if not img_path.exists():
            return None
        cache_file = self.cache_dir / f"{img_path.stem}_cutout.png"
        if cache_file.exists():
            return Image.open(cache_file).convert("RGBA")

        raw = Image.open(img_path).convert("RGBA")
        if rembg_remove:
            cut = rembg_remove(raw)
        else:
            cut = raw  # 回退

        cut.save(cache_file)
        return cut

    def apply_offset_strokes(self, cutout: Image.Image, keyline_px: int = 5, offset_px: int = 6) -> Image.Image:
        """应用统一工艺：粗糙相纸白边 + 错位红色描边 + 阴影"""
        if cutout.mode != "RGBA":
            cutout = cutout.convert("RGBA")
        w, h = cutout.size
        pad = keyline_px + offset_px + 20
        canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))

        alpha = cutout.split()[-1]
        # layer 与 mask 必须同尺寸（都取抠图尺寸），再整体偏移贴入大画布
        # 1. 错位强调色描边 (向右下偏移 offset_px)
        offset_mask = alpha.filter(ImageFilter.MaxFilter(keyline_px * 2 + 1))
        offset_layer = Image.new("RGBA", cutout.size, (*self.c_accent, 255))
        canvas.paste(offset_layer, (pad + offset_px, pad + offset_px), mask=offset_mask)

        # 2. 内层贴合白边 (Keyline)
        white_mask = alpha.filter(ImageFilter.MaxFilter(keyline_px * 2 + 1))
        white_layer = Image.new("RGBA", cutout.size, (*self.c_white, 255))
        canvas.paste(white_layer, (pad, pad), mask=white_mask)

        # 3. 原始抠图主体贴入
        canvas.paste(cutout, (pad, pad), mask=alpha)
        return canvas

    def make_torn_strip(self, width: int, height: int, fill=None) -> Image.Image:
        """生成带纤维毛刺边缘的撕纸垫条"""
        c = fill or self.c_white
        strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(strip)
        pts = []
        steps = 30
        for i in range(steps + 1):
            pts.append((int(width * i / steps), self.rng.randint(0, 8)))
        for i in range(steps + 1):
            pts.append((width - self.rng.randint(0, 6), int(height * i / steps)))
        for i in range(steps + 1):
            pts.append((int(width - width * i / steps), height - self.rng.randint(0, 8)))
        for i in range(steps + 1):
            pts.append((self.rng.randint(0, 6), int(height - height * i / steps)))
        d.polygon(pts, fill=(*c, 255))
        return strip.filter(ImageFilter.GaussianBlur(1.0))

    def make_archival_mat(self, photo_path: Path, max_w: int = 500, rotate_deg: float = 2.5) -> Image.Image:
        """生成带白边相纸框与微旋转的档案老相纸 (含阴影)"""
        if not photo_path.exists():
            return None
        img = Image.open(photo_path).convert("RGBA")
        ratio = min(max_w / img.width, max_w / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

        border = 18
        mat_w, mat_h = img.width + border * 2, img.height + border * 2 + 16
        mat = Image.new("RGBA", (mat_w, mat_h), (*self.c_white, 255))
        mat.paste(img, (border, border))

        if rotate_deg != 0:
            mat = mat.rotate(rotate_deg, resample=Image.Resampling.BICUBIC, expand=True)

        # 叠加微翘纸阴影
        pad = 25
        res = Image.new("RGBA", (mat.width + pad * 2, mat.height + pad * 2), (0, 0, 0, 0))
        a = mat.split()[-1]
        # 阴影 source 与 mask 必须同尺寸（都取相纸尺寸），再整体偏移贴入画布
        sh = Image.new("RGBA", mat.size, (0, 0, 0, 95))
        res.paste(sh, (pad + 6, pad + 10), mask=a)
        res = res.filter(ImageFilter.GaussianBlur(14))
        res.paste(mat, (pad, pad), mask=a)
        return res

    def cutout_coverage(self, cutout: Image.Image) -> float:
        """抠图实体像素占比。大量留白的图（如折线图）被 rembg 去底后会只剩一条线，
        需要据此回退到相纸框排版，避免画面近乎空白。"""
        a = cutout.convert("RGBA").split()[-1]
        hist = a.histogram()
        total = sum(hist)
        if total == 0:
            return 0.0
        return sum(hist[41:]) / total

    # ---------- 模式 D / F 专用：局部裁切与网点特写 ----------

    def _crop_zoom(self, img: Image.Image, box_w: int, box_h: int,
                   focus_x: float = 0.5, focus_y: float = 0.5, zoom: float = 2.2) -> Image.Image:
        """按目标框宽高比做偏置放大裁切（focus 0~1，0.5 为正中）。"""
        ratio = box_w / box_h
        src = img.convert("RGB")
        if src.width / src.height > ratio:
            base_w, base_h = int(src.height * ratio), src.height
        else:
            base_w, base_h = src.width, int(src.width / ratio)
        scale = zoom * max(box_w / base_w, box_h / base_h)
        tw, th = max(box_w, int(base_w * scale)), max(box_h, int(base_h * scale))
        src = src.resize((tw, th), Image.Resampling.LANCZOS)
        left = int((tw - box_w) * focus_x)
        top = int((th - box_h) * focus_y)
        return src.crop((left, top, left + box_w, top + box_h))

    def make_detail_card(self, photo_path, box_w: int, box_h: int,
                         focus_x: float = 0.5, focus_y: float = 0.5) -> Image.Image:
        """模式 D 局部细节卡：裁出真实照片的不同部位 → 高对比灰度 → 白边相纸 + 红色定位框。"""
        if photo_path is None or not Path(photo_path).exists():
            return None
        gray = ImageOps.grayscale(Image.open(photo_path).convert("RGB"))
        gray = self._crop_zoom(gray, box_w, box_h, focus_x, focus_y, zoom=2.6)
        gray = ImageOps.autocontrast(gray, cutoff=2)
        gray = ImageEnhance.Contrast(gray).enhance(1.35)

        border = 10
        card = Image.new("RGB", (box_w + border * 2, box_h + border * 2), self.c_white)
        card.paste(gray, (border, border))
        ImageDraw.Draw(card).rectangle(
            [border - 3, border - 3, border + box_w + 2, border + box_h + 2],
            outline=self.c_accent, width=3,
        )
        return card

    def make_halftone_closeup(self, photo_path, box_w: int, box_h: int,
                              focus_x: float = 0.5, focus_y: float = 0.5) -> Image.Image:
        """模式 F 局部网点特写：灰度 → 偏置放大 → 粗网点化 → 高对比，落白边相纸内。"""
        if photo_path is None or not Path(photo_path).exists():
            return None
        gray = ImageOps.grayscale(Image.open(photo_path).convert("RGB"))
        gray = self._crop_zoom(gray, box_w, box_h, focus_x, focus_y, zoom=3.0)
        # 粗网点：缩小再放大成块，与原灰度混合出印刷网点质感
        cell = 5
        small = gray.resize((max(2, box_w // cell), max(2, box_h // cell)), Image.Resampling.BOX)
        dots = small.resize((box_w, box_h), Image.Resampling.NEAREST)
        gray = Image.blend(ImageOps.autocontrast(gray, cutoff=1), ImageOps.autocontrast(dots), 0.45)
        gray = ImageEnhance.Contrast(gray).enhance(1.5)

        border = 14
        card = Image.new("RGB", (box_w + border * 2, box_h + border * 2), self.c_white)
        card.paste(gray, (border, border))
        ImageDraw.Draw(card).rectangle(
            [border - 3, border - 3, border + box_w + 2, border + box_h + 2],
            outline=self.c_ink, width=3,
        )
        return card

    @staticmethod
    def _project_to_rect(rect, toward: tuple) -> tuple:
        """把目标点投影到矩形边界，用作引线终止点（避免引线压在卡片上）。"""
        x0, y0, x1, y1 = rect
        return (min(max(toward[0], x0), x1), min(max(toward[1], y0), y1))

    def render_exploded_blueprint(self, canvas, draw, ref_img,
                                  subj: tuple, cards: list, anchor: tuple, labels=None):
        """模式 D · 技术爆炸拆解：主体 + 3 张局部细节卡 + 红色放射引线（带端点）。

        subj  = (x, y, max_w, box_h)   主体抠图框
        cards = [(x, y, w, h) x3]       细节卡位（竖排或横排由调用方给）
        anchor= (x, y)                  引线起点（通常为画面中心）
        """
        if not ref_img:
            return
        labels = list(labels or ["", "", ""])
        focuses = [(0.30, 0.32), (0.68, 0.44), (0.50, 0.70)]

        # 1) 引线先画，随后被主体与卡片自然遮住一部分 → 技术图纸「线从件后穿出」的观感
        for (cx, cy, cw, ch) in cards:
            ex, ey = self._project_to_rect((cx, cy, cx + cw, cy + ch), anchor)
            draw.line([anchor[0], anchor[1], ex, ey], fill=self.c_accent, width=3)
            r = 6
            draw.ellipse([ex - r, ey - r, ex + r, ey + r], fill=self.c_accent)

        # 2) 主体
        sx, sy, sw, sh = subj
        self.paste_cutout_or_mat(canvas, ref_img, sw, sh, sx, sy, sw)

        # 3) 细节卡 + 打字机标签
        for (cx, cy, cw, ch), (fx, fy), label in zip(cards, focuses, labels):
            card = self.make_detail_card(ref_img, cw, ch, fx, fy)
            if card is None:
                continue
            canvas.paste(card, (cx, cy))
            if label:
                f = load_font("typewriter", 22)
                draw.text((cx, cy + card.height + 6), label, font=f, fill=self.c_ink)

    def render_macro_halftone(self, canvas, draw, ref_img, box: tuple, text_xy: tuple,
                              stat: str, annot: str, stat_size: int = 140, annot_size: int = 28):
        """模式 F · 局部网点特写：黑白半调极致放大 + 留白处一行断言（Stat + 打字机图注）。"""
        if not ref_img:
            return
        bx, by, bw, bh = box
        card = self.make_halftone_closeup(ref_img, bw, bh)
        if card is not None:
            canvas.paste(card, (bx, by))
            draw.rectangle([bx - 4, by - 4, bx + card.width + 3, by + card.height + 3],
                           outline=self.c_accent, width=4)
        tx, ty = text_xy
        if stat:
            self.draw_stat(draw, stat, tx, ty, stat_size)
        if annot:
            ay = ty + stat_size + 30
            f = load_font("typewriter", annot_size)
            draw.text((tx, ay), annot_label(annot), font=f, fill=self.c_ink)
            draw.line([tx, ay + annot_size + 10, tx + len(annot) * annot_size, ay + annot_size + 10],
                      fill=self.c_accent, width=3)

    def draw_stat(self, draw, stat: str, x: int, y: int, size: int):
        if not stat:
            return
        font_stat = load_font("impact", size)
        draw.text((x, y), stat, font=font_stat, fill=self.c_accent)

    def paste_photo_mat(self, canvas, ref_img, max_w: int, rotate_deg: float, x: int, y: int):
        mat = self.make_archival_mat(ref_img, max_w=max_w, rotate_deg=rotate_deg)
        if mat:
            canvas.paste(mat, (x, y), mask=mat)

    def paste_cutout_or_mat(self, canvas, ref_img, max_w_cut: int, box_h: int,
                            x: int, y: int, fallback_max_w: int):
        """优先用 rembg 抠图 + 错位描边；若抠图过空则回退为相纸框照片。"""
        cut = self.get_cutout(ref_img)
        if cut is not None and self.cutout_coverage(cut) > 0.06:
            cut_styled = self.apply_offset_strokes(cut)
            ratio = min(max_w_cut / cut_styled.width, box_h / cut_styled.height)
            cut_styled = cut_styled.resize(
                (int(cut_styled.width * ratio), int(cut_styled.height * ratio)),
                Image.Resampling.LANCZOS,
            )
            canvas.paste(cut_styled, (x, y), mask=cut_styled)
        else:
            self.paste_photo_mat(canvas, ref_img, fallback_max_w, 1.5, x, y)

    def build_scene(self, scene_spec: dict, refs_dir: Path) -> Image.Image:
        """主入口：根据 scene_spec 的 mode 分发排版"""
        mode = scene_spec.get("mode", "stat_hero")
        headline = scene_spec.get("visual", {}).get("headline", "")
        stat = scene_spec.get("visual", {}).get("stat_number", "")
        annot = scene_spec.get("visual", {}).get("annotation", "")
        ref_keys = scene_spec.get("visual", {}).get("real_asset_refs", [])

        # 获取首张真实参考素材
        ref_img = None
        for rk in ref_keys:
            candidate = refs_dir / rk
            if candidate.is_dir():
                pics = list(candidate.glob("*.jpg")) + list(candidate.glob("*.png"))
                if pics:
                    ref_img = pics[0]
                    break
            elif candidate.is_file():
                ref_img = candidate
                break

        canvas = self.create_paper_background()
        draw = ImageDraw.Draw(canvas)

        if self.ratio == "16:9":
            self._render_16_9(canvas, draw, mode, headline, stat, annot, ref_img)
        else:
            self._render_9_16(canvas, draw, mode, headline, stat, annot, ref_img)

        return canvas

    def _render_16_9(self, canvas, draw, mode, headline, stat, annot, ref_img):
        """16:9 横屏构图排版逻辑"""
        w, h = self.width, self.height
        # 1. 顶部大标题
        if headline:
            font_head = load_font("cjk_bold", 72)
            # 撕纸底条垫底
            strip = self.make_torn_strip(min(len(headline) * 80 + 60, 1600), 100)
            canvas.paste(strip, (120, 90), mask=strip)
            draw.text((150, 100), headline, font=font_head, fill=self.c_strip_ink)
            # 手绘红色下划线
            draw.line([(150, 195), (150 + len(headline) * 65, 195)], fill=self.c_accent, width=8)

        # 2. 主体与模式分发
        if mode == "stat_hero":
            self.draw_stat(draw, stat, 150, 380, 170)
            if ref_img:
                self.paste_photo_mat(canvas, ref_img, 750, 2.5, w - 850, 240)
        elif mode == "archival_mat":
            if ref_img:
                mat = self.make_archival_mat(ref_img, max_w=900, rotate_deg=-2.0)
                if mat:
                    canvas.paste(mat, (w // 2 - mat.width // 2, 280), mask=mat)
        elif mode in ("versus_clash", "map_pin"):
            # 对抗/地图类：真实照片用相纸框呈现（大留白的图不会被 rembg 抠空）
            self.draw_stat(draw, stat, 150, 380, 170)
            if ref_img:
                self.paste_photo_mat(canvas, ref_img, 820, -1.5, w - 960, h // 2 - 300)
        elif mode == "exploded_blueprint":
            # 模式 D · 技术爆炸拆解：主体居右 + 左侧 3 张局部细节卡 + 红色放射引线
            if stat:
                self.draw_stat(draw, stat, 1060, 845, 96)
            self.render_exploded_blueprint(
                canvas, draw, ref_img,
                subj=(1050, 280, 680, 520),
                cards=[(150, 300, 300, 175), (150, 520, 300, 175), (150, 740, 300, 175)],
                anchor=(1390, 540),
                labels=["细节 01", "细节 02", "细节 03"],
            )
        elif mode == "macro_halftone":
            # 模式 F · 局部网点特写：黑白半调极致放大 + 右侧留白断言
            self.render_macro_halftone(
                canvas, draw, ref_img,
                box=(140, 300, 1040, 620),
                text_xy=(1290, 380),
                stat=stat, annot=annot,
                stat_size=140, annot_size=28,
            )
        else:
            # 显式失败优于静默兜底：D/F 曾长期共用 else 分支而失去各自版式。
            raise ValueError(f"unknown mode: {mode!r} (合法值 {'/'.join(VALID_MODES)})")

        # 3. 图注便签 (Annotation)：贴在大标题下方，避开底部字幕带（字幕居中占底部约 160px）
        if annot:
            font_annot = load_font("typewriter", 28)
            draw.text((150, 230), annot_label(annot), font=font_annot, fill=self.c_ink)
            draw.line([(150, 268), (150 + len(annot) * 32, 268)], fill=self.c_accent, width=3)

    def _render_9_16(self, canvas, draw, mode, headline, stat, annot, ref_img):
        """9:16 竖屏构图排版逻辑"""
        w, h = self.width, self.height
        # 1. 顶部大标题
        if headline:
            font_head = load_font("cjk_bold", 64)
            strip = self.make_torn_strip(min(len(headline) * 70 + 50, 960), 90)
            canvas.paste(strip, (60, 200), mask=strip)
            draw.text((85, 210), headline, font=font_head, fill=self.c_strip_ink)
            draw.line([(85, 295), (85 + len(headline) * 58, 295)], fill=self.c_accent, width=6)

        # 2. 竖屏中间核心区
        if mode == "stat_hero":
            self.draw_stat(draw, stat, 85, 420, 150)
            if ref_img:
                mat = self.make_archival_mat(ref_img, max_w=720, rotate_deg=2.5)
                if mat:
                    canvas.paste(mat, (w // 2 - mat.width // 2, 750), mask=mat)
        elif mode == "archival_mat":
            if ref_img:
                mat = self.make_archival_mat(ref_img, max_w=820, rotate_deg=-2.5)
                if mat:
                    canvas.paste(mat, (w // 2 - mat.width // 2, 500), mask=mat)
        elif mode in ("versus_clash", "map_pin"):
            self.draw_stat(draw, stat, 85, 420, 150)
            if ref_img:
                mat = self.make_archival_mat(ref_img, max_w=820, rotate_deg=-1.5)
                if mat:
                    canvas.paste(mat, (w // 2 - mat.width // 2, 700), mask=mat)
        elif mode == "exploded_blueprint":
            # 模式 D · 技术爆炸拆解：主体居上 + 下方 3 张横向细节卡 + 向下放射引线
            if stat:
                self.draw_stat(draw, stat, 90, 1240, 120)
            self.render_exploded_blueprint(
                canvas, draw, ref_img,
                subj=(150, 420, 780, 460),
                cards=[(40, 960, 300, 175), (390, 960, 300, 175), (740, 960, 300, 175)],
                anchor=(540, 880),
                labels=["细节 01", "细节 02", "细节 03"],
            )
        elif mode == "macro_halftone":
            # 模式 F · 局部网点特写：黑白半调极致放大 + 下方留白断言
            self.render_macro_halftone(
                canvas, draw, ref_img,
                box=(100, 430, 880, 560),
                text_xy=(100, 1070),
                stat=stat, annot=annot,
                stat_size=120, annot_size=26,
            )
        else:
            raise ValueError(f"unknown mode: {mode!r} (合法值 {'/'.join(VALID_MODES)})")

        # 3. 图注：贴在大标题下方，避开底部字幕带
        if annot:
            font_annot = load_font("typewriter", 26)
            draw.text((85, 330), annot_label(annot), font=font_annot, fill=self.c_ink)
            draw.line([(85, 366), (85 + len(annot) * 28, 366)], fill=self.c_accent, width=3)
