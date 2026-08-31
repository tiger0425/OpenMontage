"""YouTube 频道监控器：拉取最新视频列表并获取完整元数据"""

import subprocess
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

class ChannelMonitor:
    """YouTube 频道监控器，拉取最新视频列表 (包含发布日期)"""
    
    def __init__(self, channels: list[dict]):
        # channels = [{"name": "AI For You", "url": "https://..."}]
        self.channels = channels
    
    def fetch_recent_videos(self, max_age_days: int = 30) -> list[dict]:
        all_videos = []
        for channel in self.channels:
            videos = self._fetch_channel_videos(channel, max_age_days)
            all_videos.extend(videos)
        return all_videos
    
    def _fetch_channel_videos(self, channel: dict, max_age_days: int) -> list[dict]:
        channel_url = channel.get("url", "")
        if not channel_url:
            return []
            
        # content_type: 频道标签页（默认 videos，可选 shorts / streams），
        # 支持 Shorts-only 频道（此类频道没有 videos 页，会报 "does not have a videos"）。
        content_type = channel.get("content_type", "videos")
        target_url = f"{channel_url.rstrip('/')}/{content_type}"
        # scan_mode: full=完整元数据（慢，含 upload_date/description，默认）；
        #            flat=列表模式（快，仅 title/view_count，适合 Shorts 全量拉取）。
        scan_mode = channel.get("scan_mode", "full")
        # 限制 --playlist-end（默认 15，频道可通过 max_videos 覆盖，拉取更多历史片）
        max_videos = int(channel.get("max_videos", 15))
        cmd = ["yt-dlp"]
        if scan_mode == "flat":
            cmd.append("--flat-playlist")
        cmd += [
            "--dump-json",
            "--playlist-end", str(max_videos),
            target_url,
        ]
        
        # 计算截止日期字符串（YYYYMMDD 格式）
        cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y%m%d")
        
        videos = []
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                logging.error(f"Failed to fetch channel videos for {channel_url}: {result.stderr[:300]}")
                
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    video_id = data.get("id")
                    if not video_id:
                        continue
                        
                    upload_date = data.get("upload_date")
                    if not upload_date and data.get("timestamp"):
                        try:
                            upload_date = datetime.fromtimestamp(data.get("timestamp")).strftime("%Y%m%d")
                        except Exception:
                            pass
                    
                    if not upload_date:
                        upload_date = ""
                        
                    # Python 端日期过滤
                    if upload_date and upload_date < cutoff:
                        continue
                        
                    video = {
                        "video_id": video_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "title": data.get("title", ""),
                        "channel": channel.get("name", data.get("uploader", "")),
                        "channel_url": channel_url,
                        "duration_seconds": data.get("duration") or 0,
                        "published_at": upload_date,
                        "description": data.get("description", ""),
                        # flat 模式保留 view_count，便于按播放量挑爆款
                        "metadata": {"view_count": data.get("view_count")},
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    logging.warning("Failed to decode JSON from yt-dlp output")
        except Exception as e:
            logging.error(f"Error executing yt-dlp for {channel_url}: {e}")
            
        return videos
