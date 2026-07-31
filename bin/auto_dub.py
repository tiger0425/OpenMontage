#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-Dub 系统的命令行入口
"""

import argparse
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
    parser_process = subparsers.add_parser('process', help='批量处理待处理队列')
    
    # 子命令: run
    parser_run = subparsers.add_parser('run', help='scan + filter + process 一键执行')
    
    # 子命令: status
    parser_status = subparsers.add_parser('status', help='查看处理状态统计')
    
    # 子命令: mark-done
    parser_mark_done = subparsers.add_parser('mark-done', help='标记视频为已发布')
    parser_mark_done.add_argument('video_id', type=str, help='需要标记为已发布的视频 ID')

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    print_banner()
    
    # 检查配置文件是否存在
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"错误: 找不到配置文件 {config_path}")
        sys.exit(1)
        
    try:
        # 初始化 BatchRunner
        runner = BatchRunner(config_path)
        
        # 根据子命令调用对应的方法
        if args.command == 'scan':
            runner.scan()
        elif args.command == 'filter':
            runner.filter_videos()
        elif args.command == 'process':
            runner.process()
        elif args.command == 'run':
            runner.run()
        elif args.command == 'status':
            runner.status()
        elif args.command == 'mark-done':
            runner.mark_published(args.video_id)
            print(f"成功: 视频 {args.video_id} 已被标记为已发布状态。")
            
    except Exception as e:
        print(f"\n执行命令 '{args.command}' 时发生错误: {e}")
        logging.exception(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
