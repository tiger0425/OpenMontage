#!/usr/bin/env python3
"""Render critic CLI (rule 6).

Inspect a finished render and report numeric defects: subtitle text size,
reading time, timing drift, AI-tell fonts/patterns, optional edge/camera
checks, plus technical and audio probes.

Examples:
    python bin/critic.py --video renders/final.mp4
    python bin/critic.py --video renders/final.mp4 --subtitle assets/subtitles.srt --font "Noto Sans CJK SC" --font-script-size 16
    python bin/critic.py --video renders/final.mp4 --check-edges --check-camera --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.critic import DEFAULT_BANNED_FONTS, review_render


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review a rendered video against the rule 6 critic checks."
    )
    parser.add_argument("--video", required=True, help="Rendered video path.")
    parser.add_argument("--subtitle", help="SRT or ASS subtitle track to check.")
    parser.add_argument("--font", help="Subtitle font family (for AI-tell checks).")
    parser.add_argument(
        "--font-size",
        type=float,
        help="Effective on-screen subtitle size in pixels.",
    )
    parser.add_argument(
        "--font-script-size",
        type=float,
        help="libass script font size (e.g. 16 for SRT); converted using video height.",
    )
    parser.add_argument(
        "--script-playres-y",
        type=float,
        default=288.0,
        help="libass script PlayResY (default 288).",
    )
    parser.add_argument(
        "--expected-duration",
        type=float,
        help="Expected duration in seconds (used when ffprobe cannot read it).",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for sampled frames (default: a temp dir).",
    )
    parser.add_argument(
        "--check-edges",
        action="store_true",
        help="Flag content touching the outer 1.5%% safe border.",
    )
    parser.add_argument(
        "--check-camera",
        action="store_true",
        help="Flag abrupt luminance jumps between sampled frames.",
    )
    parser.add_argument(
        "--banned-font",
        action="append",
        default=[],
        help="Additional banned font substring (repeatable).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when status is revise or fail.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw final_review JSON instead of a text report.",
    )
    return parser.parse_args()


def _format(report: dict) -> str:
    lines = [f"status: {report.get('status')}"]
    issues = report.get("issues_found") or []
    if issues:
        lines.append(f"issues ({len(issues)}):")
        lines.extend(f"  - {issue}" for issue in issues)
    else:
        lines.append("issues: none")
    checks = report.get("checks") or {}
    subtitle = checks.get("subtitle_check") or {}
    if subtitle:
        lines.append(
            f"subtitles: expected={subtitle.get('subtitles_expected')} "
            f"present={subtitle.get('subtitles_present')} "
            f"coverage={subtitle.get('coverage_ratio')} "
            f"drift={subtitle.get('timing_drift_detected')}"
        )
    technical = checks.get("technical_probe") or {}
    if technical:
        lines.append(
            f"technical: {technical.get('resolution')} "
            f"{technical.get('duration_seconds')}s "
            f"audio={technical.get('has_audio')} "
            f"codec={technical.get('codec')}"
        )
    lines.append(f"recommended_action: {report.get('recommended_action')}")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    banned = list(DEFAULT_BANNED_FONTS) + [f for f in args.banned_font if f]
    report = review_render(
        args.video,
        subtitle_path=args.subtitle,
        subtitle_font=args.font,
        subtitle_font_px=args.font_size,
        subtitle_font_script_size=args.font_script_size,
        script_playres_y=args.script_playres_y,
        expected_duration=args.expected_duration,
        output_dir=args.output_dir,
        banned_fonts=banned,
        check_edges=args.check_edges,
        check_camera=args.check_camera,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format(report))
    if args.strict and report.get("status") != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
