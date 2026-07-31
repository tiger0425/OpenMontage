"""YouTube 关键词搜索器：补充获取包含发布日期的视频"""

import subprocess
import json
import logging
from datetime import datetime, timedelta

class KeywordSearcher:
    """YouTube 关键词搜索器，补充发现优质视频"""
    
    def __init__(self, keywords: list[str]):
        # keywords = ["free AI models tutorial", ...]
        self.keywords = keywords
    
    def search(self, max_results_per_keyword: int = 10, max_age_days: int = 30) -> list[dict]:
        all_videos = []
        seen_ids = set()
        
        for keyword in self.keywords:
            videos = self._search_keyword(keyword, max_results_per_keyword, max_age_days)
            for video in videos:
                if video["video_id"] not in seen_ids:
                    seen_ids.add(video["video_id"])
                    all_videos.append(video)
                    
        return all_videos
    
    def _search_keyword(self, keyword: str, max_results: int, max_age_days: int) -> list[dict]:
        # 移除 --flat-playlist 以便获取 upload_date
        cmd = [
            "yt-dlp",
            "--dump-json",
            f"ytsearch{max_results}:{keyword}"
        ]
        
        videos = []
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                logging.error(f"Failed to search for keyword '{keyword}': {result.stderr[:300]}")
                
            cutoff_date_str = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y%m%d")
            
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
                        
                    # 时间过滤
                    if upload_date and upload_date < cutoff_date_str:
                        continue
                        
                    video = {
                        "video_id": video_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "title": data.get("title", ""),
                        "channel": data.get("uploader", ""),
                        "channel_url": data.get("uploader_url", ""),
                        "duration_seconds": data.get("duration", 0),
                        "published_at": upload_date,
                        "description": data.get("description", "")
                    }
                    videos.append(video)
                except json.JSONDecodeError:
                    logging.warning("Failed to decode JSON from yt-dlp output")
        except Exception as e:
            logging.error(f"Error executing yt-dlp for search '{keyword}': {e}")
            
        return videos
