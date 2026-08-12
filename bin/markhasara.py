#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MarkHasara 二创解说流水线 CLI 入口。

二创解说模式：拉取频道 Shorts -> 转录 -> 中文二创解说文案（夸张军事风）
-> 用户声音克隆 TTS -> 头像框替换数字人 -> 字幕 + 压制 -> 抖音/小红书成品包。

复用 auto-dub 内核：DedupDB（队列状态机）、Transcriber、LLMClient、GPU 锁、
轻/重任务拆分 + Log Barrier（--json 单行回报）。

用法:
  python bin/markhasara.py scan                # 扫描频道 Shorts 入库
  python bin/markhasara.py classify            # 重建合规分类清单 (BLOCK/REMAKE/SAFE)
  python bin/markhasara.py process             # 轻任务：下载->转录->二创文案 (LLM)
  python bin/markhasara.py render-assets --video-id X   # 重算力：TTS 合成用户声音
  python bin/markhasara.py render-video --video-id X    # 重算力：头像框替换+字幕+压制
  python bin/markhasara.py status              # 队列状态
"""

import argparse
import json
import logging
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent  # bin/ -> OpenMontage/
APP_ROOT = OMO_ROOT / "apps" / "markhasara"
AUTODUB_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(AUTODUB_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTODUB_ROOT))


def _emit_json(obj: dict):
    print(json.dumps(obj, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="MarkHasara 二创解说流水线 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=str, default=str(APP_ROOT / "config.yaml"),
        help="配置文件路径 (默认: apps/markhasara/config.yaml)",
    )
    parser.add_argument("--json", action="store_true", help="输出单行 JSON 摘要")
    parser.add_argument("--quiet", action="store_true", help="抑制心跳/进度")

    subparsers = parser.add_subparsers(dest="command", title="可用子命令")

    subparsers.add_parser("scan", help="扫描 MarkHasara 频道 Shorts 入库")
    subparsers.add_parser("classify", help="重建合规分类清单 (BLOCK/REMAKE/SAFE)")
    subparsers.add_parser("process", help="轻任务：下载->转录->二创文案 (LLM)")
    subparsers.add_parser("status", help="查看队列状态")

    p_assets = subparsers.add_parser("render-assets", help="重算力：TTS 合成（用户声音）")
    p_assets.add_argument("--video-id", required=True, help="目标视频 ID")

    p_video = subparsers.add_parser("render-video", help="重算力：头像框替换+字幕+压制")
    p_video.add_argument("--video-id", required=True, help="目标视频 ID")

    for _sub in subparsers._name_parser_map.values():
        _sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        _sub.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    from batch.dedup_db import DedupDB
    import yaml

    config_path = Path(args.config)
    if not config_path.exists():
        _emit_json({"command": args.command, "success": False, "error": f"配置文件不存在: {config_path}"})
        sys.exit(1)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    db_path = OMO_ROOT / config["database"]["path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = DedupDB(db_path)

    try:
        if args.command == "scan":
            from apps.markhasara.scanner import scan_channel
            result = scan_channel(config, db)
        elif args.command == "classify":
            from apps.markhasara.compliance import rebuild_compliance
            result = rebuild_compliance(config, db)
        elif args.command == "process":
            from apps.markhasara.pipeline import process_light
            result = process_light(config, db)
        elif args.command == "render-assets":
            from apps.markhasara.pipeline import render_assets
            result = render_assets(config, db, args.video_id)
        elif args.command == "render-video":
            from apps.markhasara.pipeline import render_video
            result = render_video(config, db, args.video_id)
        elif args.command == "status":
            result = db.get_stats()
            result["command"] = "status"
        else:
            result = {"command": args.command, "success": False, "error": "未知子命令"}

        if args.json:
            _emit_json(result)
        elif not args.quiet and isinstance(result, dict):
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        logging.exception(e)
        print(f"\n执行命令 '{args.command}' 时发生错误: {e}", file=sys.stderr)
        if args.json:
            _emit_json({"command": args.command, "success": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
