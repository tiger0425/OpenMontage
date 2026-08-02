"""导入 97Xwo6BJOhw 到 tracking.db 并标记 queued。"""
import json
import subprocess
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))
sys.path.insert(0, str(OMO_ROOT / "apps" / "auto-dub"))

from batch.dedup_db import DedupDB

VIDEO_ID = "97Xwo6BJOhw"
URL = "https://www.youtube.com/watch?v=97Xwo6BJOhw"

cmd = [
    "yt-dlp", "--skip-download", "--no-playlist",
    "--print", "%(id)s\t%(title)s\t%(channel)s\t%(channel_url)s\t%(duration)s\t%(upload_date)s",
    URL,
]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
if res.returncode != 0:
    print(f"yt-dlp 失败: {res.stderr[:300]}")
    sys.exit(1)
line = res.stdout.strip().splitlines()[-1]
vid, title, channel, channel_url, duration, upload_date = line.split("\t")
print(f"元数据: {vid} | {title} | {channel} | {duration}s | {upload_date}")

db_path = OMO_ROOT / "projects" / "auto-dub" / "tracking.db"
db = DedupDB(db_path)
added = db.add_video(
    video_id=vid, url=URL, title=title, channel=channel, channel_url=channel_url,
    duration_seconds=int(duration), published_at=upload_date, language="en",
    metadata=json.dumps({"source": "user_test"}),
)
print("add_video ->", "新增" if added else "已存在")
db.update_status(vid, "queued")
print("status -> queued")
