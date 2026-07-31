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
            
        target_url = f"{channel_url}/videos"
        # 移除 --flat-playlist 以便获取 upload_date
        # 限制 --playlist-end 为 15，只获取最近的 15 个视频
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--playlist-end", "15",
            target_url
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
                        "duration_seconds": data.get("duration", 0),
                        "published_at": upload_date,
                        "description": data.get("description", "")
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    logging.warning("Failed to decode JSON from yt-dlp output")
        except Exception as e:
            logging.error(f"Error executing yt-dlp for {channel_url}: {e}")
            
        return videos
