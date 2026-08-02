#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
series-adapt 系统的命令行入口

用法:
  python bin/series_adapt.py import     # 导入播放列表到 tracking.db
  python bin/series_adapt.py status     # 查看各集处理状态
  python bin/series_adapt.py process    # 推进下一个待处理剧集
  python bin/series_adapt.py mark-done 01   # 标记第 01 集为已发布
"""

import argparse
import sys
from pathlib import Path

# 添加 OpenMontage 根目录和 apps/series-adapt 到 Python 路径
OMO_ROOT = Path(__file__).resolve().parent.parent  # bin/ -> OpenMontage/
APP_ROOT = OMO_ROOT / "apps" / "series-adapt"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from series_runner import SeriesRunner


def main():
    parser = argparse.ArgumentParser(
        description="series-adapt 系列内容适配管线 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(APP_ROOT / "config.yaml"),
        help="配置文件路径 (默认: apps/series-adapt/config.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command", title="可用子命令")

    subparsers.add_parser("import", help="导入源播放列表到 tracking.db")
    subparsers.add_parser("status", help="查看各集处理状态")
    subparsers.add_parser("process", help="推进下一个待处理剧集")

    parser_mark = subparsers.add_parser("mark-done", help="标记某集为已发布")
    parser_mark.add_argument("episode_num", type=int, help="剧集编号（如 01）")

    args = parser.parse_args()
    runner = SeriesRunner(Path(args.config))

    if args.command == "import":
        added = runner.import_playlist()
        print(f"新增 {added} 集")
        runner.print_status()
    elif args.command == "status":
        runner.print_status()
    elif args.command == "process":
        ok = runner.process_next()
        if not ok:
            sys.exit(1)
    elif args.command == "mark-done":
        ep = runner.db.get_episode(args.episode_num)
        if not ep:
            print(f"未找到第 {args.episode_num} 集")
            sys.exit(1)
        runner.db.update_status(args.episode_num, "published")
        print(f"第 {args.episode_num:02d} 集已标记为 published")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
