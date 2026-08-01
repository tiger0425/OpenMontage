import json
import sys
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

# 在 Windows 下强制 stdout 使用 UTF-8 编码，避免 emoji 打印崩溃
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 添加 OpenMontage 根目录和 auto-dub 根目录到 Python 路径
OMO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(__file__).resolve().parents[1]

if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from discovery.channel_monitor import ChannelMonitor
from discovery.keyword_searcher import KeywordSearcher
from discovery.video_filter import VideoFilter
from batch.dedup_db import DedupDB
from batch.glossary import Glossary
from batch.auto_reviewer import AutoReviewer
from batch.pipeline_automator import PipelineAutomator
from batch.llm_client import LLMClient


class BatchRunner:
    """批量调度器：扫描 -> 筛选 -> 逐个处理
    
    整合视频发现、筛选、去重、localization-dub 管线调用。
    """
    
    def __init__(self, config_path: Path = None, quiet: bool = False):
        # 加载配置
        if config_path is None:
            config_path = APP_ROOT / 'config.yaml'
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.quiet = quiet
        
        # 初始化各模块
        self.projects_dir = OMO_ROOT / self.config['output']['base_dir']
        self.review_dir = OMO_ROOT / self.config['output']['review_dir']
        self.published_dir = OMO_ROOT / self.config['output']['published_dir']
        
        db_path = OMO_ROOT / self.config['database']['path']
        self.db = DedupDB(db_path)
        
        self.glossary = Glossary.from_config(self.config.get('glossary', {}))
        self.channel_monitor = ChannelMonitor(self.config.get('channels', []))
        self.keyword_searcher = KeywordSearcher(self.config.get('keywords', []))
        self.video_filter = VideoFilter(self.config.get('filters', {}), self.db)
        self.auto_reviewer = AutoReviewer(
            self.config.get('auto_review', {}),
            self.projects_dir
        )
        self.auto_reviewer.set_glossary(self.glossary)
        self.auto_reviewer.set_llm(LLMClient())
        
        # 确保目录存在
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.published_dir.mkdir(parents=True, exist_ok=True)
    
    def scan(self) -> list[dict]:
        """扫描新视频：频道拉新 + 关键词搜索"""
        print("\n" + "="*60)
        print("🔍 开始扫描新视频...")
        print("="*60)
        
        max_age = self.config['filters']['max_age_days']
        
        # 1. 频道拉新
        print(f"\n📺 扫描 {len(self.config['channels'])} 个频道...")
        channel_videos = self.channel_monitor.fetch_recent_videos(max_age_days=max_age)
        print(f"   发现 {len(channel_videos)} 个视频")
        
        # 2. 关键词搜索
        max_results = self.config.get('batch', {}).get('search_max_results', 10)
        print(f"\n🔍 搜索 {len(self.config['keywords'])} 个关键词...")
        search_videos = self.keyword_searcher.search(
            max_results_per_keyword=max_results,
            max_age_days=max_age
        )
        print(f"   发现 {len(search_videos)} 个视频")
        
        # 3. 合并去重
        all_videos = self._merge_videos(channel_videos, search_videos)
        print(f"\n📊 合并后共 {len(all_videos)} 个唯一视频")
        
        # 4. 写入数据库
        new_count = 0
        for v in all_videos:
            added = self.db.add_video(
                video_id=v['video_id'],
                url=v['url'],
                title=v.get('title', ''),
                channel=v.get('channel', ''),
                channel_url=v.get('channel_url', ''),
                duration_seconds=v.get('duration_seconds', 0),
                published_at=v.get('published_at', ''),
                language=v.get('language'),
                metadata=json.dumps(v.get('metadata', {}), ensure_ascii=False)
            )
            if added:
                new_count += 1
        
        print(f"✅ 新增 {new_count} 个视频到数据库")
        return all_videos
    
    def filter_videos(self) -> list[dict]:
        """筛选候选视频"""
        print("\n" + "="*60)
        print("📋 开始筛选视频...")
        print("="*60)
        
        # 获取所有 discovered 状态的视频
        candidates = self.db.get_by_status('discovered')
        if not candidates:
            print("没有待筛选的视频")
            return []
        
        print(f"候选视频: {len(candidates)}")
        
        # 更新状态为 filtering
        for v in candidates:
            self.db.update_status(v['video_id'], 'filtering')
        
        # 运行筛选器
        passed = self.video_filter.filter_batch(candidates)
        
        # 更新状态
        passed_ids = {v['video_id'] for v in passed}
        for v in candidates:
            if v['video_id'] in passed_ids:
                self.db.update_status(v['video_id'], 'queued')
            else:
                self.db.update_status(v['video_id'], 'skipped')
        
        print(f"\n✅ 筛选通过: {len(passed)}/{len(candidates)}")
        return passed
    
    def process(self) -> dict:
        """批量处理待处理队列"""
        print("\n" + "="*60)
        print("⚡ 开始批量处理...")
        print("="*60)
        
        max_per_run = self.config.get('batch', {}).get('max_per_run', 5)
        queue = self.db.get_by_status('queued')
        
        if not queue:
            print("没有待处理的视频")
            return {'processed': 0, 'success': 0, 'failed': 0}
        
        # 取前 N 个
        batch = queue[:max_per_run]
        print(f"本次处理: {len(batch)}/{len(queue)} 个视频")
        
        stats = {'processed': 0, 'success': 0, 'failed': 0}
        
        for i, video in enumerate(batch, 1):
            print(f"\n{'='*40}")
            print(f"[{i}/{len(batch)}] 处理: {video['title']}")
            print(f"   URL: {video['url']}")
            print(f"{'='*40}")
            
            self.db.update_status(video['video_id'], 'processing')
            stats['processed'] += 1
            
            try:
                success = self._process_single_video(video)
                if success:
                    self.db.update_status(
                        video['video_id'], 'done',
                        output_path=str(self.review_dir / video['video_id'])
                    )
                    stats['success'] += 1
                    print(f"✅ 处理成功")
                else:
                    self.db.update_status(video['video_id'], 'failed', error_msg="管线执行失败")
                    stats['failed'] += 1
                    print(f"❌ 处理失败")
            except Exception as e:
                self.db.update_status(video['video_id'], 'failed', error_msg=str(e))
                stats['failed'] += 1
                print(f"❌ 异常: {e}")
        
        print(f"\n📊 批量处理结果: 处理 {stats['processed']}, 成功 {stats['success']}, 失败 {stats['failed']}")
        return stats
    
    def run(self) -> dict:
        """一键执行: scan + filter + process"""
        self.scan()
        self.filter_videos()
        return self.process()

    # ==========================================
    # 重算力子命令（Compute Worker 执行）
    # ==========================================
    def _get_video(self, video_id: str) -> dict:
        """按 video_id 取视频，不存在则抛错。"""
        video = self.db.get_by_id(video_id)
        if not video:
            raise ValueError(f"视频 {video_id} 不存在于数据库")
        return video

    def _build_automator(self, video: dict):
        """为单个视频构建 PipelineAutomator（复用 _process_single_video 的构造逻辑）。"""
        from batch.pipeline_automator import PipelineAutomator
        video_id = video['video_id']
        project_id = f"auto-dub-{video_id}"
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return PipelineAutomator(
            project_id=project_id,
            project_dir=project_dir,
            video=video,
            config=self.config,
            db=self.db,
            glossary=self.glossary,
            auto_reviewer=self.auto_reviewer
        )

    def render_assets(self, video_id: str) -> dict:
        """仅 TTS 合成 + 混音 + SRT（重算力 GPU）。前置依赖 script/scene_plan checkpoint。"""
        video = self._get_video(video_id)
        print(f"\n  🔊 [render-assets] {video_id}: {video.get('title', '')}")
        automator = self._build_automator(video)
        report = automator.render_assets_only()
        summary = {
            "project_id": f"auto-dub-{video_id}",
            "stage": "assets",
            "success": report is not None,
            "output_path": report.get("output_path") if isinstance(report, dict) else None,
            "drift_seconds": report.get("drift_seconds") if isinstance(report, dict) else None,
            "verification_notes": (report or {}).get("verification_notes", []),
            "warnings": (report or {}).get("warnings", []),
            "error": (report or {}).get("error"),
        }
        if summary["success"]:
            self.db.update_status(video_id, 'processing')
            print("  ✅ render-assets 完成")
        else:
            self.db.update_status(video_id, 'failed', error_msg=str(summary["error"]))
            print(f"  ❌ render-assets 失败: {summary['error']}")
        return summary

    def render_video(self, video_id: str) -> dict:
        """仅 FFmpeg 压制 + 片尾 + 归档（重算力）。前置依赖 assets checkpoint。"""
        video = self._get_video(video_id)
        print(f"\n  🎬 [render-video] {video_id}: {video.get('title', '')}")
        automator = self._build_automator(video)
        report = automator.render_video_only()
        summary = {
            "project_id": f"auto-dub-{video_id}",
            "stage": "video",
            "success": report is not None,
            "output_path": report.get("output_path") if isinstance(report, dict) else None,
            "drift_seconds": report.get("drift_seconds") if isinstance(report, dict) else None,
            "verification_notes": (report or {}).get("verification_notes", []),
            "warnings": (report or {}).get("warnings", []),
            "error": (report or {}).get("error"),
        }
        if summary["success"]:
            self.db.update_status(video_id, 'done')
            print("  ✅ render-video 完成")
        else:
            self.db.update_status(video_id, 'failed', error_msg=str(summary["error"]))
            print(f"  ❌ render-video 失败: {summary['error']}")
        return summary

    def run_heavy(self, video_id: str) -> dict:
        """assets + edit + compose 打包一条龙（重算力，漂移超标自动缩短重翻）。"""
        video = self._get_video(video_id)
        print(f"\n  🏗️ [run-heavy] {video_id}: {video.get('title', '')}")
        automator = self._build_automator(video)
        success = automator.run_heavy()
        summary = {
            "project_id": f"auto-dub-{video_id}",
            "stage": "heavy",
            "success": success,
            "output_path": str(self.review_dir / video_id) if success else None,
            "drift_seconds": automator.get_last_drift(),
            "verification_notes": automator.get_last_verification_notes(),
            "warnings": automator.get_last_warnings(),
            "error": None if success else "run-heavy 管线执行失败",
        }
        self.db.update_status(video_id, 'done' if success else 'failed',
                              error_msg=None if success else summary["error"])
        if success:
            print("  ✅ run-heavy 完成")
        else:
            print(f"  ❌ run-heavy 失败: {summary['error']}")
        return summary

    
    def status(self) -> dict:
        """查看处理状态统计"""
        stats = self.db.get_stats()
        print("\n" + "="*60)
        print("  视频处理状态统计")
        print("="*60)
        total = sum(stats.values())
        print(f"总计: {total}")
        labels = {
            'discovered': '[新]', 'filtering': '[筛]', 'queued': '[待]',
            'processing': '[中]', 'done': '[完]', 'published': '[发]',
            'failed': '[败]', 'skipped': '[跳]'
        }
        for status, count in sorted(stats.items()):
            label = labels.get(status, '[*]')
            print(f"  {label} {status}: {count}")
        return stats
    
    def mark_published(self, video_id: str):
        """标记视频为已发布"""
        self.db.update_status(video_id, 'published')
        print(f"✅ 已标记 {video_id} 为已发布")
    
    def _merge_videos(self, *video_lists) -> list[dict]:
        """合并多个视频列表，按 video_id 去重"""
        seen = set()
        merged = []
        for videos in video_lists:
            for v in videos:
                vid = v.get('video_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    merged.append(v)
        return merged
    
    def _process_single_video(self, video: dict) -> bool:
        """处理单个视频：下载 -> localization-dub 管线
        
        这是核心处理函数，调用 OpenMontage 的 localization-dub 管线。
        流程：
        1. 创建项目目录
        2. 下载视频 (yt-dlp)
        3. 构建 brief artifact
        4. 通过自动审核器运行各阶段
        """
        import subprocess
        
        video_id = video['video_id']
        project_id = f"auto-dub-{video_id}"
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # === Step 1: 下载视频 ===
        print(f"  📥 下载视频...")
        source_video = project_dir / "source.mp4"
        if not source_video.exists():
            try:
                cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "-o", str(source_video),
                    "--no-playlist",
                    video['url']
                ]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"  ❌ 下载失败: {e.stderr[:200]}")
                return False
        print(f"  ✅ 视频已下载: {source_video}")
        
        # === Step 2: 构建 brief ===
        print(f"  📝 构建 brief...")
        brief_data = {
            "version": "1.0",
            "title": video.get('title', 'Untitled'),
            "hook": f"翻译配音: {video.get('title', '')}",
            "key_points": [
                "Translate English tutorial to Chinese dubbing",
                "Generate natural Chinese TTS audio",
                "Burn Chinese subtitles with English technical terms preserved"
            ],
            "tone": "professional",
            "style": "clean-professional",
            "target_platform": "bilibili",
            "target_duration_seconds": float(video.get('duration_seconds', 600)),
            "design_system": {
                "background_color": "#08050a",
                "lighting_style": "clean studio lighting",
                "global_mood": "Professional Technology Tutorial"
            },
            "beat_plan": [
                {
                    "scene_name": "full_video",
                    "composition_rule": "Maintain original video with dubbed audio and burned subtitles"
                }
            ],
            "metadata": {
                "source_language": self.config['pipeline'].get('source_language', 'en-US'),
                "target_languages": [self.config['pipeline'].get('target_language', 'zh-CN')],
                "deliverable_mode_map": {
                    self.config['pipeline'].get('target_language', 'zh-CN'): "dub_audio_only"
                },
                "glossary_terms": {t: t for t in self.glossary.get_protected_terms()},
                "protected_terms": self.glossary.get_protected_terms(),
                "source_mode": "single_speaker",
                "render_runtime": self.config['pipeline'].get('render_runtime', 'ffmpeg'),
                "source_video_path": str(source_video),
                "tts_engine": self.config['pipeline'].get('tts_engine', 'voxcpm')
            }
        }
        
        # === Step 3: 用自动审核器通过 idea 阶段 ===
        decision_log = {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [
                {
                    "decision_id": "d-outro-001",
                    "stage": "idea",
                    "category": "render_runtime_selection",
                    "subject": "Auto-dub end-card composition engine",
                    "options_considered": [
                        {
                            "option_id": "hyperframes",
                            "label": "HyperFrames HTML/GSAP motion end-card",
                            "score": 1.0,
                            "reason": "Lightweight, no Remotion dep, fits B站 一键三连"
                        },
                        {
                            "option_id": "remotion",
                            "label": "Remotion React composition",
                            "score": 0.4,
                            "reason": "Could render similar motion graphics",
                            "rejected_because": "Avoid installing remotion-composer for single short end-card"
                        },
                        {
                            "option_id": "ffmpeg",
                            "label": "FFmpeg static end-card",
                            "score": 0.2,
                            "reason": "Can append static frame, no animation",
                            "rejected_because": "Cannot author animated icons without pre-rendered assets"
                        }
                    ],
                    "selected": "hyperframes",
                    "reason": "HyperFrames renders B站 一键三连 animated end-card without pulling Remotion deps.",
                    "user_visible": True,
                    "user_approved": True,
                    "confidence": 0.95
                }
            ]
        }
        success, issues = self.auto_reviewer.review_and_approve(
            project_id=project_id,
            stage="idea",
            artifacts={"brief": brief_data, "decision_log": decision_log}
        )
        if not success:
            print(f"  ❌ idea 阶段审核失败: {issues}")
            return False
        
        # === Step 4: 调用管线自动执行器执行后续所有阶段 ===
        automator = PipelineAutomator(
            project_id=project_id,
            project_dir=project_dir,
            video=video,
            config=self.config,
            db=self.db,
            glossary=self.glossary,
            auto_reviewer=self.auto_reviewer
        )
        
        success = automator.run_pipeline()
        return success
