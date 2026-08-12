"""MarkHasara 频道扫描器：拉取频道全部 Shorts 入库。

用 yt-dlp 拉取频道 playlist（931 条全部为 Shorts），写入独立 DedupDB。
二创模式不设时长过滤（全量 Shorts），仅按合规分类筛选进队列（见 compliance.py）。
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 频道 URL（可从 config 读，缺省用已知频道）
DEFAULT_CHANNEL_URL = "https://www.youtube.com/@MarkHasara"


def _fetch_playlist(channel_url: str, max_entries: Optional[int] = None) -> list[dict]:
    """用 yt-dlp 拉取频道 playlist 元数据（不下载视频）。

    返回 [{id, title, url, view_count, duration}]。Shorts 无 duration 字段时记为 None。
    """
    cmd = [
        "yt-dlp", "--flat-playlist", "--dump-json",
        "--no-download", "--no-warnings",
        "--playlist-end", str(max_entries) if max_entries else "2000",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.error("yt-dlp 拉取失败: %s", result.stderr[-500:])
        return []

    entries = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = e.get("id")
        if not vid:
            continue
        entries.append({
            "id": vid,
            "title": e.get("title", ""),
            "url": f"https://www.youtube.com/shorts/{vid}",
            "view_count": e.get("view_count"),
            "duration": e.get("duration"),
            "channel": "MarkHasara",
        })
    return entries


def scan_channel(config: dict, db) -> dict:
    """扫描 MarkHasara 频道并入库。返回新增/跳过统计。"""
    channel_cfg = config.get("channel", {})
    channel_url = channel_cfg.get("url", DEFAULT_CHANNEL_URL)
    playlist_id = channel_cfg.get("playlist_id", "")

    # 若配置了 playlist_id，用完整 playlist URL（更全）；否则用频道 URL
    target_url = f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id else channel_url

    logger.info("扫描 MarkHasara 频道: %s", target_url)
    entries = _fetch_playlist(target_url)
    if not entries:
        return {"command": "scan", "success": False, "error": "yt-dlp 未返回任何条目", "count": 0}

    added, skipped = 0, 0
    for e in entries:
        if db.exists(e["id"]):
            skipped += 1
            continue
        db.add_video(
            video_id=e["id"],
            url=e["url"],
            title=e["title"],
            channel="MarkHasara",
            channel_url=channel_url,
            duration_seconds=e.get("duration") or 0,
            published_at="",
            language="en",
            metadata={
                "view_count": e.get("view_count"),
                "is_short": True,
            },
        )
        added += 1

    stats = db.get_stats()
    total = sum(stats.values())
    return {
        "command": "scan",
        "success": True,
        "fetched": len(entries),
        "added": added,
        "skipped": skipped,
        "total_in_db": total,
    }
