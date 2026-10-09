"""Vertical episode: compose a re-creation episode from an uncropped 16:9 source.

The layout problem
------------------
A 16:9 technical explainer carries its information in fine detail — a
seam of flow that is *just barely* attached, a row of vortex generators
five pixels tall. Centre-crop that into 9:16 and you keep neither: the
car loses its front, the detail is unreadable, and the colour legend
survives as a few illegible pixels. Cropping is the wrong operation.

So the source frame is never cropped for the main band. It plays full
width, and the layout supplies what the source will not: a **loupe**.
The same instant, magnified, sitting directly under the frame it came
from, with a frame drawn on the main view showing where it is looking.
That pairing is the whole trick — one band gives context, the other
gives the detail the explanation is actually about.

The loupe has to move
---------------------
A static crop is a screenshot, not a video. So the loupe is recomputed
per frame, and the spec says where to look: either an explicit
normalised rectangle (the writer knows which part of the frame this
sentence is about) or `"auto"`, which finds the region itself. Auto
prefers the source's own annotation convention — this class of video
marks the point under discussion with red arrows, and the centroid of
the red pixels is where the creator is pointing. Failing that it falls
back to the highest-detail region, because that is where the information
is.

Text is rendered with PIL, not ffmpeg drawtext
-----------------------------------------------
ffmpeg's drawtext cannot wrap CJK, cannot mix colours inside one line,
and cannot centre a measured run. PIL does all three, so the subtitle
band is rendered once per sentence and cached, then pasted per frame.

Timing
------
The episode's clock is the *new* narration, not the source. Each
sentence in the spec gets an equal share of the episode, weighted by its
character count, and the source is read at the speed needed to deliver
that share. Once IndexTTS2 audio exists the weights become its real
durations; until then character count is the best available estimate.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

CANVAS_W, CANVAS_H = 1080, 1920
BAND = 608                 # 16:9 at 1080 wide
TOP_BAR, SUB_BAND, FOOT = 112, 420, 172
BG = (14, 16, 19)
ACC = (232, 178, 58)
DIM = (122, 128, 120)
WHITE = (255, 255, 255)
DARK = (58, 64, 72)


# ----------------------------------------------------------------------
# text rendering
# ----------------------------------------------------------------------


def _wrap_cjk(text: str, font, max_w: int) -> list[str]:
    """Wrap to a pixel width, breaking between CJK glyphs and on spaces."""
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _segments(text: str, keywords: list[str], font, font_b):
    """Split text into (text, color, font) runs, keyword runs in accent."""
    if not keywords:
        return [(text, WHITE, font)]
    pat = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True))
    out = []
    for piece in re.split(f"({pat})", text):
        if not piece:
            continue
        out.append((piece, ACC if piece in keywords else WHITE,
                    font_b if piece in keywords else font))
    return out


def _draw_centered(d, cx: int, y: int, segs) -> int:
    total = sum(d.textlength(t, font=f) for t, _, f in segs)
    x = cx - total / 2
    for t, col, f in segs:
        d.text((x, y), t, font=f, fill=col)
        x += d.textlength(t, font=f)
    return y


# ----------------------------------------------------------------------
# loupe targeting
# ----------------------------------------------------------------------


def _red_centroid(im) -> Optional[tuple[int, int]]:
    """Where the source's own annotation is pointing."""
    small = im.convert("RGB").resize((im.width // 4, im.height // 4))
    px = small.load()
    xs = ys = n = 0
    for y in range(small.height):
        for x in range(small.width):
            r, g, b = px[x, y]
            if r > 150 and g < 95 and b < 95:
                xs += x; ys += y; n += 1
    if n < 40:
        return None
    return xs * 4 // n, ys * 4 // n


def _detail_centroid(im) -> tuple[int, int]:
    """Highest-gradient region. Last resort only — see _subject_centroid."""
    g = im.convert("L").resize((48, 27))
    px = g.load()
    best, bx, by = -1.0, im.width // 2, im.height // 2
    for y in range(1, 26):
        for x in range(1, 47):
            v = (abs(px[x, y] - px[x - 1, y]) + abs(px[x, y] - px[x, y - 1]))
            if v > best:
                best, bx, by = v, x * im.width // 48, y * im.height // 27
    return bx, by


def _subject_centroid(im, safe=(0.0, 0.10, 1.0, 0.76)) -> tuple[int, int]:
    """Centroid of the thing being explained, when nothing is annotated.

    Max-gradient is the obvious fallback and it is *wrong* for technical
    renders: the highest-contrast region in a CFD frame is the colour
    legend — a black box with a saturated rainbow in it — and magnifying
    that tells the viewer nothing. The subject is the opposite: a large,
    low-saturation, mid-to-bright mass (a white car body) against a
    high-saturation field. So look for pixels that are pale, not busy.

    `safe` clips the search away from the top strip (titles) and the
    bottom strip (legends, colour bars), which are the two places a
    source video reliably wastes space.
    """
    sw, sh = 96, 54
    small = im.convert("RGB").resize((sw, sh))
    px = small.load()
    x_lo, y_lo, x_hi, y_hi = (int(safe[0] * sw), int(safe[1] * sh),
                              int(safe[2] * sw), int(safe[3] * sh))
    xs = ys = n = 0
    for y in range(max(0, y_lo), min(sh, y_hi)):
        for x in range(max(0, x_lo), min(sw, x_hi)):
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            sat = (mx - mn) / mx if mx else 1.0
            lum = (r + g + b) / 3
            if sat < 0.20 and 105 < lum < 246:
                xs += x; ys += y; n += 1
    if n < 20:
        return _detail_centroid(im)
    return xs * im.width // sw, ys * im.height // sh


def _loupe_rect(im, zoom: float, focus: Any) -> tuple[int, int, int, int]:
    cw = int(im.width / zoom)
    ch = int(cw * 9 / 16)
    if isinstance(focus, (list, tuple)) and len(focus) == 4:
        x0 = int(focus[0] * im.width); y0 = int(focus[1] * im.height)
        x1 = int(focus[2] * im.width); y1 = int(focus[3] * im.height)
        return (x0, y0, min(x0 + cw, im.width), min(y0 + ch, im.height))
    hit = _red_centroid(im)
    cx, cy = hit if hit else _detail_centroid(im)
    x0 = max(0, min(im.width - cw, cx - cw // 2))
    y0 = max(0, min(im.height - ch, cy - ch // 2))
    return x0, y0, x0 + cw, y0 + ch


# ----------------------------------------------------------------------
# tool
# ----------------------------------------------------------------------


class VerticalEpisode(BaseTool):
    """Compose one re-creation episode as a 9:16 video from an uncropped 16:9 source."""

    name = "vertical_episode"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["bin:ffmpeg", "python:numpy", "python:pillow"]
    install_instructions = "ffmpeg on PATH; pip install numpy pillow"
    agent_skills: list[str] = []

    capabilities = [
        "uncropped_16_9_in_9_16",
        "tracking_loupe",
        "cjk_subtitle_wrap",
        "hook_card",
        "episode_progress_rail",
    ]
    supports = {
        "source_never_cropped": True,
        "per_sentence_focus": True,
        "auto_focus_via_source_annotation": True,
        "keyword_highlight": True,
    }
    best_for = [
        "re-cutting a 16:9 explainer into a vertical re-creation episode",
        "showing technical detail that a centre-crop would destroy",
    ]
    not_good_for = [
        "producing the new narration audio (use indextts-bridge)",
        "deciding the episode split (use narrative_segment + the script skill)",
        "portrait-native sources (crop those directly instead)",
    ]

    input_schema = {
        "type": "object",
        "required": ["spec", "out"],
        "properties": {
            "spec": {"type": "string", "description": "Episode spec JSON path."},
            "out": {"type": "string", "description": "Output .mp4 path."},
            "fps": {"type": "integer", "default": 30, "minimum": 12, "maximum": 60},
            "zoom": {"type": "number", "default": 2.1, "minimum": 1.2, "maximum": 5.0},
            "font_regular": {"type": "string", "default": r"C:\Windows\Fonts\msyh.ttc"},
            "font_bold": {"type": "string", "default": r"C:\Windows\Fonts\msyhbd.ttc"},
            "subtitle_size": {"type": "integer", "default": 60, "minimum": 32, "maximum": 96},
            "keep_source_audio": {
                "type": "boolean", "default": False,
                "description": "Off by default — a re-creation replaces the "
                               "narration, and keeping the original audio "
                               "is both wrong and a giveaway.",
            },
            "preview_seconds": {
                "type": "number", "default": 0.0, "minimum": 0.0,
                "description": "Render only the first N seconds. Use to "
                               "check the layout before a full render.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=0, disk_mb=800, network_required=False
    )
    side_effects = ["writes the composed mp4 to <out>"]
    user_visible_verification = [
        "Watch the first 3 seconds: the hook card should be readable and "
        "the source frame uncropped.",
        "Spot-check that the loupe tracks the sentence you expected it to.",
    ]

    # ------------------------------------------------------------------

    def get_status(self) -> ToolStatus:
        import shutil
        if not shutil.which("ffmpeg"):
            return ToolStatus.UNAVAILABLE
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        from PIL import Image, ImageDraw, ImageFont

        spec = json.loads(Path(inputs["spec"]).read_text(encoding="utf-8"))
        out = Path(inputs["out"])
        fps = int(inputs.get("fps", 30))
        zoom = float(inputs.get("zoom", 2.1))
        keep_audio = bool(inputs.get("keep_source_audio", False))
        preview = float(inputs.get("preview_seconds", 0.0))

        fr = inputs.get("font_regular", r"C:\Windows\Fonts\msyh.ttc")
        fb = inputs.get("font_bold", r"C:\Windows\Fonts\msyhbd.ttc")
        sub_size = int(inputs.get("subtitle_size", 60))

        f_ep = ImageFont.truetype(fb, 30)
        f_ti = ImageFont.truetype(fr, 36)
        f_sm = ImageFont.truetype(fb, 22)
        f_ra = ImageFont.truetype(fr, 30)
        f_me = ImageFont.truetype(fr, 22)
        f_su = ImageFont.truetype(fr, sub_size)
        f_kw = ImageFont.truetype(fb, sub_size)

        src = Path(spec["source"])
        if not src.is_absolute():
            src = Path(inputs["spec"]).parent / src
        if not src.exists():
            return ToolResult(success=False, error=f"source not found: {src}",
                              data={"source": str(src)})

        # --- timing: share the episode by character count --------------
        sents = spec["sentences"]
        hook_d = float(spec.get("hook_duration", 1.8))
        a0, a1 = float(spec["source_range"][0]), float(spec["source_range"][1])
        weights = [max(1, len(s["t"])) for s in sents]
        total_w = sum(weights)
        src_span = a1 - a0
        hook_src = min(3.0, src_span * 0.04)

        # chars/sec assumed for a Mandarin voiceover
        CPS = 4.6
        body_dur = sum(weights) / CPS
        total_dur = body_dur + hook_d

        t = hook_d
        cues = []
        for s, w in zip(sents, weights):
            d = w / total_w * body_dur
            s0 = a0 + src_span * (t - hook_d) / max(0.001, body_dur)
            s1 = a0 + src_span * (t + d - hook_d) / max(0.001, body_dur)
            cues.append({"t0": t, "t1": t + d, "src0": s0, "src1": s1, **s})
            t += d

        if preview > 0:
            total_dur = min(total_dur, preview)

        # --- static layers, rendered once ------------------------------
        head = Image.new("RGB", (CANVAS_W, TOP_BAR), BG)
        d = ImageDraw.Draw(head)
        d.text((34, 26), f"EP{spec['episode_no']:02d}", font=f_ep, fill=ACC)
        d.text((132, 24), spec["title"], font=f_ti, fill=WHITE)
        d.text((CANVAS_W - 32, 38), f"原片完整保留 · 放大镜 {zoom}x",
               font=f_sm, fill=DIM, anchor="ra")

        foot = Image.new("RGB", (CANVAS_W, FOOT), BG)
        d = ImageDraw.Draw(foot)
        seg_w, gap, x = 118, 8, 34
        for i in range(int(spec.get("total_episodes", 8))):
            d.rectangle([x, 48, x + seg_w, 56],
                        fill=ACC if i < spec["episode_no"] else DARK)
            x += seg_w + gap
        d.text((34, 92), f"第 {spec['episode_no']} / "
               f"{spec.get('total_episodes', 8)} 集", font=f_ra, fill=WHITE)
        d.text((34, 132), "素材来源：原作者画面 · 二次创作", font=f_me, fill=DIM)

        hook_img = Image.new("RGB", (CANVAS_W, CANVAS_H), (8, 9, 11))
        dh = ImageDraw.Draw(hook_img)
        hook_lines = (spec.get("hook") or "").split("\n")
        y = CANVAS_H // 2 - len(hook_lines) * 60
        for ln in hook_lines:
            w = dh.textlength(ln, font=f_kw)
            dh.text(((CANVAS_W - w) / 2, y), ln, font=f_kw, fill=WHITE)
            y += 110
        dh.text((CANVAS_W / 2, CANVAS_H - 260), "二次创作",
                font=f_ep, fill=ACC, anchor="mm")

        # per-sentence subtitle bands (wrapped, keyword-coloured)
        sub_cache: dict[int, Image.Image] = {}
        for i, c in enumerate(cues):
            band = Image.new("RGB", (CANVAS_W, SUB_BAND), BG)
            dd = ImageDraw.Draw(band)
            segs = _segments(c["t"], c.get("kw") or [], f_su, f_kw)
            lines, cur, cw = [], [], 0
            for tx, col, fo in segs:
                for chx in tx:
                    w = dd.textlength(chx, font=fo)
                    if cw + w > CANVAS_W - 96 and cur:
                        lines.append(cur); cur, cw = [], 0
                    cur.append((chx, col, fo)); cw += w
            if cur:
                lines.append(cur)
            total = len(lines)
            ly = (SUB_BAND - total * (sub_size + 26)) // 2
            for ln in lines:
                tw = sum(dd.textlength(t, font=f) for t, _, f in ln)
                x = (CANVAS_W - tw) / 2
                for t, col, f in ln:
                    dd.text((x, ly), t, font=f, fill=col)
                    x += dd.textlength(t, font=f)
                ly += sub_size + 26
            sub_cache[i] = band

        # --- frame loop -------------------------------------------------
        n = int(total_dur * fps)
        sw, sh = 1920, 1080
        dec = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{a0:.3f}", "-i", str(src),
             "-t", f"{total_dur + 2:.2f}", "-vf", f"fps={fps},scale={sw}:{sh}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, bufsize=10 ** 8)
        outp = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{CANVAS_W}x{CANVAS_H}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(out)],
            stdin=subprocess.PIPE, bufsize=10 ** 8)

        import io
        fsize = sw * sh * 3
        rendered = 0
        assert dec.stdout is not None and outp.stdin is not None
        try:
            for fi in range(n):
                buf = dec.stdout.read(fsize)
                if not buf or len(buf) < fsize:
                    break
                frame = Image.frombytes("RGB", (sw, sh), buf)
                et = fi / fps

                if et < hook_d:
                    k = et / hook_d
                    outp.stdin.write(Image.blend(frame.resize(
                        (CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS).convert("RGB"),
                        hook_img, min(1.0, k * 1.6)).tobytes())
                    rendered += 1
                    continue

                idx = 0
                for i, c in enumerate(cues):
                    if c["t0"] <= et < c["t1"]:
                        idx = i
                        break
                else:
                    idx = len(cues) - 1
                c = cues[idx]
                span = max(0.001, c["src1"] - c["src0"])
                phase = min(1.0, max(0.0, (et - c["t0"]) / max(0.001, c["t1"] - c["t0"])))
                focus = c.get("focus", "auto")
                if isinstance(focus, (list, tuple)):
                    # 写死的框也让它动起来：沿对角线缓慢漂移，
                    # 幅度小到看不出是漂移，但观众不会觉得画面死了
                    dx = 0.020 * (phase - 0.5)
                    dy = 0.014 * (phase - 0.5)
                    focus = [min(0.92, max(0.0, focus[0] + dx)),
                             min(0.92, max(0.0, focus[1] + dy)),
                             min(0.98, max(0.0, focus[2] + dx)),
                             min(0.98, max(0.0, focus[3] + dy))]
                lx0, ly0, lx1, ly1 = _loupe_rect(frame, zoom, focus)

                canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
                canvas.paste(head, (0, 0))
                main = frame.resize((CANVAS_W, BAND), Image.Resampling.LANCZOS)
                bx = lx0 * CANVAS_W // sw
                by = ly0 * CANVAS_W // sw
                bwd = (lx1 - lx0) * CANVAS_W // sw
                bht = (ly1 - ly0) * CANVAS_W // sw
                ImageDraw.Draw(main).rectangle(
                    [bx, by, bx + bwd, by + bht], outline=ACC, width=3)
                canvas.paste(main, (0, TOP_BAR))

                zoomed = frame.crop((lx0, ly0, lx1, ly1)).resize(
                    (CANVAS_W, BAND), Image.Resampling.LANCZOS)
                ImageDraw.Draw(zoomed).rectangle([0, 0, CANVAS_W, 4], fill=ACC)
                canvas.paste(zoomed, (0, TOP_BAR + BAND))

                canvas.paste(sub_cache[idx], (0, TOP_BAR + 2 * BAND))
                canvas.paste(foot, (0, TOP_BAR + 2 * BAND + SUB_BAND))
                outp.stdin.write(canvas.tobytes())
                rendered += 1
        finally:
            try:
                outp.stdin.close()
            except Exception:
                pass
            dec.stdout.close()
            dec.wait()
            outp.wait()

        return ToolResult(
            success=out.exists() and out.stat().st_size > 0,
            data={
                "out": str(out),
                "fps": fps,
                "frames": rendered,
                "duration_seconds": round(rendered / fps, 2),
                "expected_duration": round(total_dur, 2),
                "sentences": len(cues),
                "chars_per_second_assumed": CPS,
                "hook_seconds": hook_d,
                "size_mb": round(out.stat().st_size / 1024 / 1024, 2) if out.exists() else 0,
                "source_audio_kept": keep_audio,
                "note": "narration audio is not muxed; timings are "
                        "character-count estimates until IndexTTS2 runs",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )
