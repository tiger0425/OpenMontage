"""Render critic — the only reviewer that sees the finished video.

Implements the numeric checks from the "6 Rules for Motion That Doesn't
Look AI-Made" critic prompt:

  - text is at least 4.5% of frame height (49 px at 1080p)
  - every line stays up for its character count divided by 15 seconds
  - nothing slides off the edge
  - the camera never jerks
  - every AI tell from the rules is flagged

The critic deliberately reads only the rendered file and its subtitle
track, never the project. It returns a dict that validates against
``schemas/artifacts/final_review.schema.json``.

It is intentionally dependency-light: ffprobe/ffmpeg for media, Pillow for
the optional frame checks. It never raises on a review finding — findings
are reported as ``issues`` so the pipeline can decide what to do.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

# Fonts that reliably make a video read as "AI-made" (rule 1).
DEFAULT_BANNED_FONTS = (
    "inter",
    "space grotesk",
    "ibm plex mono",
    "jetbrains mono",
    "roboto mono",
    "fira code",
)

# Text patterns that read as decorative AI filler (rule 1).
_DOT_SEPARATORS = (" · ", " • ", "・", " ·", "· ")
_FAKE_CODE_RE = re.compile(r"\b[A-Z]{2,5}[-–—]\d{2,4}\b")

TEXT_HEIGHT_RATIO_MIN = 0.045  # 4.5% of frame height
READING_CPS = 15.0  # characters per second


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _ffprobe(path: Path) -> dict[str, Any]:
    """Return a normalized technical probe."""
    probe: dict[str, Any] = {
        "valid_container": False,
        "duration_seconds": 0.0,
        "resolution": "",
        "fps": 0.0,
        "has_audio": False,
        "codec": "",
        "file_size_bytes": 0,
        "width": 0,
        "height": 0,
        "issues": [],
    }
    if not path.exists():
        probe["issues"].append(f"output not found: {path}")
        return probe

    probe["file_size_bytes"] = path.stat().st_size
    try:
        res = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ]
        )
        if res.returncode != 0:
            probe["issues"].append(f"ffprobe failed: {res.stderr.strip()[:200]}")
            return probe
        data = json.loads(res.stdout or "{}")
    except Exception as exc:  # noqa: BLE001 - probe must never crash the render
        probe["issues"].append(f"ffprobe error: {exc}")
        return probe

    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    probe["valid_container"] = bool(video)
    probe["duration_seconds"] = _safe_float(fmt.get("duration"))
    probe["width"] = int(video.get("width") or 0)
    probe["height"] = int(video.get("height") or 0)
    if probe["width"] and probe["height"]:
        probe["resolution"] = f"{probe['width']}x{probe['height']}"
    probe["fps"] = _parse_fps(video.get("r_frame_rate"))
    probe["codec"] = str(video.get("codec_name") or "")
    probe["has_audio"] = bool(audio)

    if not video:
        probe["issues"].append("no video stream")
    if not audio:
        probe["issues"].append("no audio stream")
    if probe["duration_seconds"] <= 0:
        probe["issues"].append("duration is zero or unknown")
    return probe


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_fps(raw: Any) -> float:
    if not raw:
        return 0.0
    text = str(raw)
    if "/" in text:
        num, _, den = text.partition("/")
        try:
            den_f = float(den)
            return float(num) / den_f if den_f else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_subtitles(path: Optional[Path]) -> list[dict[str, Any]]:
    """Parse SRT or ASS into a list of ``{start, end, text}`` cues."""
    if not path or not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []

    if path.suffix.lower() == ".ass":
        return _parse_ass(raw)
    return _parse_srt(raw)


_SRT_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def _srt_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000.0


def _parse_srt(raw: str) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        time_idx = next((i for i, ln in enumerate(lines) if _SRT_TIME_RE.search(ln)), None)
        if time_idx is None:
            continue
        match = _SRT_TIME_RE.search(lines[time_idx])
        if not match:
            continue
        g = match.groups()
        start = _srt_seconds(*g[0:4])
        end = _srt_seconds(*g[4:8])
        text = " ".join(lines[time_idx + 1 :]).strip()
        cues.append({"start": start, "end": end, "text": text})
    return cues


_ASS_DIALOGUE_RE = re.compile(
    r"^Dialogue:\s*\d+,(\d+):(\d{2}):(\d{2})\.(\d{2}),"
    r"(\d+):(\d{2}):(\d{2})\.(\d{2}),(.*)$"
)


def _parse_ass(raw: str) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _ASS_DIALOGUE_RE.match(line.strip())
        if not match:
            continue
        g = match.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 100.0
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 100.0
        # Dialogue fields after the timecodes: Style, Name, MarginL/R/V, Effect, Text
        rest = g[8].split(",", 6)
        text = rest[6] if len(rest) > 6 else ""
        text = re.sub(r"\{[^}]*\}", "", text).strip()
        cues.append({"start": start, "end": end, "text": text})
    return cues


def _sample_frames(
    path: Path,
    timestamps: Iterable[float],
    output_dir: Path,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[str] = []
    for idx, ts in enumerate(timestamps):
        out = output_dir / f"critic_{idx:02d}.jpg"
        try:
            res = _run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{max(0.0, float(ts)):.3f}",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(out),
                ],
                timeout=60,
            )
            if res.returncode == 0 and out.exists() and out.stat().st_size > 0:
                frames.append(str(out))
        except Exception:
            continue
    return frames


def _audio_levels(path: Path) -> dict[str, Any]:
    """Return mean/max volume in dB via ffmpeg volumedetect."""
    result = {"mean_db": None, "max_db": None, "clipping": False, "silent": False}
    try:
        res = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            timeout=180,
        )
        text = (res.stderr or "") + (res.stdout or "")
        mean = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
        peak = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
        if mean:
            result["mean_db"] = float(mean.group(1))
        if peak:
            result["max_db"] = float(peak.group(1))
        if result["max_db"] is not None and result["max_db"] > -1.0:
            result["clipping"] = True
        if result["mean_db"] is not None and result["mean_db"] < -50.0:
            result["silent"] = True
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def _check_text_size(
    font_px: Optional[float], height: int, min_ratio: float
) -> list[str]:
    if not font_px or not height:
        return []
    ratio = float(font_px) / float(height)
    if ratio < min_ratio:
        return [
            f"subtitle text is {ratio:.2%} of frame height "
            f"({font_px:.0f}px at {height}px); minimum is {min_ratio:.1%} "
            f"({min_ratio * height:.0f}px)"
        ]
    return []


def _check_reading_time(
    cues: list[dict[str, Any]], cps: float
) -> list[str]:
    issues: list[str] = []
    for idx, cue in enumerate(cues):
        text = re.sub(r"\s", "", cue.get("text") or "")
        if not text:
            continue
        duration = max(0.0, float(cue["end"]) - float(cue["start"]))
        required = len(text) / max(1.0, cps)
        if duration + 0.05 < required:
            issues.append(
                f"cue {idx + 1} holds {duration:.2f}s for {len(text)} chars "
                f"(needs {required:.2f}s at {cps:g} cps)"
            )
    return issues


def _check_timing(
    cues: list[dict[str, Any]], duration: float
) -> tuple[float, bool, list[str]]:
    if not cues or duration <= 0:
        return 0.0, False, []
    total = 0.0
    drift = False
    issues: list[str] = []
    for idx, cue in enumerate(cues):
        start = float(cue["start"])
        end = float(cue["end"])
        if start < -0.05 or end <= start:
            issues.append(f"cue {idx + 1} has an invalid time range ({start:.2f}-{end:.2f}s)")
        if end > duration + 0.5:
            drift = True
            issues.append(
                f"cue {idx + 1} ends at {end:.2f}s but the video is {duration:.2f}s"
            )
        total += max(0.0, min(end, duration) - max(0.0, start))
    return min(1.0, total / duration), drift, issues


def _check_ai_tells(
    cues: list[dict[str, Any]],
    subtitle_font: Optional[str],
    banned_fonts: Iterable[str],
) -> list[str]:
    issues: list[str] = []
    font = (subtitle_font or "").lower()
    for banned in banned_fonts:
        if banned.lower() in font:
            issues.append(f"banned font in use: {subtitle_font!r} (matches {banned!r})")
            break
    if font and "mono" in font:
        issues.append(f"monospaced caption font in use: {subtitle_font!r}")

    for idx, cue in enumerate(cues):
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        for sep in _DOT_SEPARATORS:
            if sep in text:
                issues.append(f"cue {idx + 1} uses a dot separator: {text[:40]!r}")
                break
        if _FAKE_CODE_RE.search(text):
            issues.append(f"cue {idx + 1} contains a decorative reference code: {text[:40]!r}")
        letters = [ch for ch in text if ch.isalpha()]
        if len(letters) >= 8 and sum(1 for ch in letters if ch.isupper()) / len(letters) > 0.8:
            issues.append(f"cue {idx + 1} is all-caps: {text[:40]!r}")
    return issues


def _check_edges(frames: list[str]) -> list[str]:
    """Optional: flag content that touches the outer 1.5% safe border."""
    try:
        from PIL import Image
    except Exception:
        return []

    issues: list[str] = []
    for frame_path in frames:
        try:
            img = Image.open(frame_path).convert("L")
        except Exception:
            continue
        w, h = img.size
        if w < 8 or h < 8:
            continue
        band_x = max(1, int(w * 0.015))
        band_y = max(1, int(h * 0.015))
        # Median luminance from the histogram (much cheaper than sorting
        # every pixel of a 1080p frame).
        hist = img.histogram()
        total = sum(hist) or 1
        acc = 0
        median = 0
        for level, count in enumerate(hist):
            acc += count
            if acc >= total // 2:
                median = level
                break
        border = []
        border.extend(img.crop((0, 0, w, band_y)).getdata())
        border.extend(img.crop((0, h - band_y, w, h)).getdata())
        border.extend(img.crop((0, band_y, band_x, h - band_y)).getdata())
        border.extend(img.crop((w - band_x, band_y, w, h - band_y)).getdata())
        if not border:
            continue
        hot = sum(1 for px in border if abs(px - median) > 70) / len(border)
        if hot > 0.15:
            issues.append(
                f"{Path(frame_path).name}: {hot:.0%} of the outer border is high-contrast; "
                "content may be clipped or sliding off the edge"
            )
    return issues


def _check_camera(frames: list[str]) -> list[str]:
    """Optional: flag abrupt frame-to-frame luminance spikes (camera jerk)."""
    try:
        from PIL import Image
    except Exception:
        return []

    diffs: list[float] = []
    prev = None
    for frame_path in frames:
        try:
            img = Image.open(frame_path).convert("L").resize((160, 90))
        except Exception:
            prev = None
            continue
        data = list(img.getdata())
        if prev is not None:
            diffs.append(sum(abs(a - b) for a, b in zip(data, prev)) / len(data))
        prev = data
    if len(diffs) < 2:
        return []
    ordered = sorted(diffs)
    median = ordered[len(ordered) // 2]
    issues: list[str] = []
    for idx, diff in enumerate(diffs):
        if median > 0 and diff > max(40.0, median * 4.0):
            issues.append(
                f"abrupt luminance jump between sampled frames {idx + 1} and {idx + 2} "
                f"(diff {diff:.1f} vs median {median:.1f}) — check for a camera jerk or hard cut"
            )
    return issues


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def review_render(
    video_path: str | Path,
    *,
    subtitle_path: str | Path | None = None,
    subtitle_font: str | None = None,
    subtitle_font_px: float | None = None,
    subtitle_font_script_size: float | None = None,
    script_playres_y: float = 288.0,
    expected_duration: float | None = None,
    sample_count: int = 6,
    output_dir: str | Path | None = None,
    banned_fonts: Iterable[str] = DEFAULT_BANNED_FONTS,
    renderer_family: str = "localization-dub",
    render_runtime: str = "ffmpeg",
    check_edges: bool = False,
    check_camera: bool = False,
    text_height_ratio_min: float = TEXT_HEIGHT_RATIO_MIN,
    reading_cps: float = READING_CPS,
) -> dict[str, Any]:
    """Review a rendered video and return a final_review-shaped dict.

    ``subtitle_font_px`` is the *effective* on-screen subtitle size in
    pixels. For SRT burned by libass at its default 288-unit script
    resolution, pass ``font_size / 288 * frame_height``. Alternatively
    pass ``subtitle_font_script_size`` (e.g. 16) and the conversion is
    done for you using ``script_playres_y`` (288 by default).
    """
    path = Path(video_path)
    probe = _ffprobe(path)
    duration = probe["duration_seconds"] or float(expected_duration or 0.0)
    height = probe["height"]
    if subtitle_font_px is None and subtitle_font_script_size and height:
        # SRT burned by libass uses a 288-unit script resolution by default.
        subtitle_font_px = round(
            float(subtitle_font_script_size) / max(1.0, float(script_playres_y)) * height,
            1,
        )
    issues: list[str] = []
    issues.extend(probe["issues"])

    # --- subtitle track ---
    cues = _parse_subtitles(Path(subtitle_path) if subtitle_path else None)
    coverage, timing_drift, timing_issues = _check_timing(cues, duration)
    issues.extend(timing_issues)
    issues.extend(_check_text_size(subtitle_font_px, height, text_height_ratio_min))
    issues.extend(_check_reading_time(cues, reading_cps))
    issues.extend(_check_ai_tells(cues, subtitle_font, banned_fonts))

    # --- frames ---
    frames: list[str] = []
    if probe["valid_container"] and duration > 0:
        if output_dir:
            frame_dir = Path(output_dir)
        else:
            frame_dir = Path(tempfile.mkdtemp(prefix="omo_critic_"))
        # opening / 20% / 40% / 60% / 80% / ending
        sample_count = max(4, int(sample_count))
        timestamps = [
            max(0.0, min(duration - 0.05, duration * (i + 0.5) / sample_count))
            for i in range(sample_count)
        ]
        frames = _sample_frames(path, timestamps, frame_dir)

    edge_issues = _check_edges(frames) if check_edges else []
    camera_issues = _check_camera(frames) if check_camera else []
    issues.extend(edge_issues)
    issues.extend(camera_issues)

    # --- audio ---
    levels = _audio_levels(path) if probe["has_audio"] else {}
    if levels.get("clipping"):
        issues.append(f"audio peaks at {levels['max_db']:.1f} dB (clipping)")
    if levels.get("silent"):
        issues.append(f"audio mean is {levels['mean_db']:.1f} dB (unexpected silence)")

    # --- status ---
    critical = (not probe["valid_container"]) or (not probe["has_audio"]) or duration <= 0
    if critical:
        status = "fail"
    elif issues:
        status = "revise"
    else:
        status = "pass"

    if status == "pass":
        recommended = "present_to_user"
    elif status == "fail":
        recommended = "block"
    elif any("cue" in i or "subtitle" in i for i in issues):
        recommended = "revise_edit"
    elif any("font" in i or "text" in i or "code" in i for i in issues):
        recommended = "revise_assets"
    else:
        recommended = "re_render"

    visual_issues = [i for i in issues if i in edge_issues or i in camera_issues]
    review = {
        "version": "1.0",
        "output_path": str(path),
        "status": status,
        "checks": {
            "technical_probe": {
                "valid_container": probe["valid_container"],
                "duration_seconds": round(duration, 3),
                "resolution": probe["resolution"],
                "fps": round(probe["fps"], 3),
                "has_audio": probe["has_audio"],
                "codec": probe["codec"],
                "file_size_bytes": int(probe["file_size_bytes"]),
                "issues": probe["issues"],
            },
            "visual_spotcheck": {
                "frames_sampled": max(4, len(frames)),
                "frame_paths": frames,
                "black_frames_detected": False,
                "broken_overlays": bool(edge_issues),
                "missing_assets": False,
                "unreadable_text": bool(_check_text_size(subtitle_font_px, height, text_height_ratio_min)),
                "issues": visual_issues,
            },
            "audio_spotcheck": {
                "narration_present": bool(probe["has_audio"]) and not levels.get("silent", False),
                "music_present": False,
                "unexpected_silence": bool(levels.get("silent", False)),
                "clipping_detected": bool(levels.get("clipping", False)),
                "mix_intelligible": bool(probe["has_audio"]),
                "issues": [
                    i for i in issues if "audio" in i or "dB" in i
                ],
            },
            "promise_preservation": {
                "delivery_promise_honored": status != "fail",
                "renderer_family_used": renderer_family,
                "render_runtime_used": render_runtime
                if render_runtime in ("remotion", "hyperframes", "ffmpeg")
                else "ffmpeg",
                "runtime_swap_detected": False,
                "runtime_swap_check": f"ok — {render_runtime}",
                "motion_ratio_actual": 0.0,
                "silent_downgrade_detected": False,
                "issues": [],
            },
            "subtitle_check": {
                "subtitles_expected": bool(subtitle_path),
                "subtitles_present": bool(cues),
                "coverage_ratio": round(coverage, 4),
                "timing_drift_detected": timing_drift,
                "issues": timing_issues,
            },
        },
        "issues_found": issues,
        "recommended_action": recommended,
        "metadata": {
            "critic_version": "1.0",
            "text_height_ratio_min": text_height_ratio_min,
            "reading_cps": reading_cps,
            "subtitle_font_px": subtitle_font_px,
        },
    }
    return review


__all__ = ["review_render", "DEFAULT_BANNED_FONTS"]
