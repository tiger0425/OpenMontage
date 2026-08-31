#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文硬字幕 CLI 入口：给视频加中文字幕（不配音、不替换音轨）。

用法：
  python bin/auto_subtitle.py run --input <YouTube_URL|本地视频路径> [选项]

示例：
  python bin/auto_subtitle.py run --input "https://www.youtube.com/watch?v=xxxx"
  python bin/auto_subtitle.py run --input "E:/videos/demo.mp4" --lang en --model-size base
"""

import argparse
import json
import sys
from pathlib import Path

# 添加 OpenMontage 根目录到 Python 路径
OMO_ROOT = Path(__file__).resolve().parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(OMO_ROOT / "apps" / "auto-subtitle") not in sys.path:
    sys.path.insert(0, str(OMO_ROOT / "apps" / "auto-subtitle"))


def _emit_json(obj: dict):
    print(json.dumps(obj, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="中文硬字幕：给视频加中文字幕（保留原音轨，不生成配音）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", title="子命令", help="选择操作")

    p_run = subparsers.add_parser("run", help="给视频加中文字幕（主流程）")
    p_run.add_argument("--input", required=True, help="YouTube URL 或本地视频文件路径")
    p_run.add_argument("--lang", default=None, help="源语言 ISO 639-1 代码（如 en；默认自动检测）")
    p_run.add_argument("--model-size", default="large-v3",
                       choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                       help="Whisper 转录模型（默认 large-v3）")
    p_run.add_argument("--font", default="Microsoft YaHei", help="烧录中文字体（默认 Microsoft YaHei）")
    p_run.add_argument("--font-size", type=int, default=20, help="字幕字号（默认 20）")
    p_run.add_argument("--no-burn", action="store_true", help="只生成 SRT，不烧录到视频")

    # 让 --json 在子命令前后都能使用
    for _sub in subparsers._name_parser_map.values():
        _sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                          help=argparse.SUPPRESS)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        from subtitle_runner import SubtitleRunner
    except ImportError:
        from apps.auto_subtitle.subtitle_runner import SubtitleRunner

    config = {
        "pipeline": {
            "source_language": args.lang,
            "whisper_model": args.model_size,
        },
        "burn": {
            "enabled": not getattr(args, "no_burn", False),
            "font": args.font,
            "font_size": args.font_size,
        },
    }

    runner = SubtitleRunner(config)
    try:
        result = runner.run(args.input)
        if getattr(args, "json", False):
            _emit_json({"command": "run", "success": True, **result})
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        if getattr(args, "json", False):
            _emit_json({"command": "run", "success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
