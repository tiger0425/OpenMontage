#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-Dub 系统的命令行入口
"""

import argparse
import json
import sys
import logging
from pathlib import Path

# 添加 OpenMontage 根目录和 apps/auto-dub 到 Python 路径
OMO_ROOT = Path(__file__).resolve().parent.parent  # bin/ -> OpenMontage/
APP_ROOT = OMO_ROOT / 'apps' / 'auto-dub'
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.batch_runner import BatchRunner

BANNER = r"""
==========================================================
    ___         __             ____        __    
   /   | __  __/ /_____       / __ \__  __/ /_   
  / /| |/ / / / __/ __ \_____/ / / / / / / __ \  
 / ___ / /_/ / /_/ /_/ /____/ /_/ / /_/ / /_/ /  
/_/  |_\__,_/\__/\____/    /_____/\__,_/_.___/   

             OpenMontage Auto-Dub CLI            
==========================================================
"""

def print_banner():
    """打印 ASCII Banner"""
    print(BANNER)

def _emit_json(obj: dict):
    """输出单行 JSON 摘要（Log Barrier：子 Agent 只回报这一行）。

    注意：--quiet 只抑制心跳/进度，绝不抑制 JSON 摘要 ——
    `--json --quiet` 组合必须仍输出 JSON（Worker 静默跑任务但上报摘要）。
    """
    print(json.dumps(obj, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(
        description="Auto-Dub 系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # 全局参数
    parser.add_argument(
        '--config', 
        type=str, 
        default=str(APP_ROOT / 'config.yaml'),
        help="指定配置文件路径 (默认: apps/auto-dub/config.yaml)"
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help="输出结构化单行 JSON 摘要（供 Compute Worker 子 Agent 回报给主 Agent）"
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help="抑制心跳/进度输出（只保留 JSON 摘要或静默退出）"
    )
    
    subparsers = parser.add_subparsers(
        dest='command', 
        title='可用子命令',
        help='请选择要执行的操作'
    )
    
    # 子命令: scan
    parser_scan = subparsers.add_parser('scan', help='扫描新视频，更新候选池')
    
    # 子命令: filter
    parser_filter = subparsers.add_parser('filter', help='筛选候选视频')
    
    # 子命令: process
    parser_process = subparsers.add_parser(
        'process', help='轻任务批量处理：仅 script+scene_plan（重算力请派发 Worker 用 run-heavy）')
    
    # 子命令: run
    parser_run = subparsers.add_parser(
        'run', help='scan + filter + process 一键执行（process 为轻任务模式）')
    
    # 子命令: status
    parser_status = subparsers.add_parser('status', help='查看处理状态统计')
    
    # 子命令: mark-done
    parser_mark_done = subparsers.add_parser('mark-done', help='标记视频为已发布')
    parser_mark_done.add_argument('video_id', type=str, help='需要标记为已发布的视频 ID')
    
    # ---- 重算力子命令（Compute Worker 执行，带 --json 回报） ----
    parser_render_assets = subparsers.add_parser(
        'render-assets', help='仅 TTS 合成 + 混音 + SRT（重算力 GPU，建议派发子 Agent）')
    parser_render_assets.add_argument('--video-id', required=True, help='目标视频 ID')
    
    parser_render_video = subparsers.add_parser(
        'render-video', help='仅 FFmpeg 压制 + 片尾 + 归档（重算力，建议派发子 Agent）')
    parser_render_video.add_argument('--video-id', required=True, help='目标视频 ID')
    
    parser_run_heavy = subparsers.add_parser(
        'run-heavy', help='assets + edit + compose 打包一条龙（重算力，建议派发子 Agent）')
    parser_run_heavy.add_argument('--video-id', required=True, help='目标视频 ID')

    # 让 --json / --quiet 在子命令前后都能使用。
    # default=argparse.SUPPRESS 是关键：子 parser 不覆盖全局已解析的值，
    # 否则 `python bin/auto_dub.py --json status` 会被子 parser 默认 False 覆盖。
    for _sub in subparsers._name_parser_map.values():
        _sub.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                          help=argparse.SUPPRESS)
        _sub.add_argument('--quiet', action='store_true', default=argparse.SUPPRESS,
                          help=argparse.SUPPRESS)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    if not args.quiet:
        print_banner()
    
    # 检查配置文件是否存在
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"错误: 找不到配置文件 {config_path}")
        sys.exit(1)
        
    try:
        # 初始化 BatchRunner（quiet 时抑制心跳）
        runner = BatchRunner(config_path, quiet=args.quiet)
        
        # 根据子命令调用对应的方法
        if args.command == 'scan':
            result = runner.scan()
        elif args.command == 'filter':
            result = runner.filter_videos()
        elif args.command == 'process':
            result = runner.process()
        elif args.command == 'run':
            result = runner.run()
        elif args.command == 'status':
            result = runner.status()
        elif args.command == 'mark-done':
            runner.mark_published(args.video_id)
            print(f"成功: 视频 {args.video_id} 已被标记为已发布状态。")
            result = {"command": "mark-done", "video_id": args.video_id, "success": True}
        elif args.command == 'render-assets':
            result = runner.render_assets(args.video_id)
        elif args.command == 'render-video':
            result = runner.render_video(args.video_id)
        elif args.command == 'run-heavy':
            result = runner.run_heavy(args.video_id)
        else:
            result = {"command": args.command, "success": False, "error": "未知子命令"}

        if args.json:
            _emit_json(result)
            
    except Exception as e:
        print(f"\n执行命令 '{args.command}' 时发生错误: {e}")
        logging.exception(e)
        if args.json:
            _emit_json({"command": args.command, "success": False, "error": str(e)})
        sys.exit(1)

if __name__ == '__main__':
    main()
