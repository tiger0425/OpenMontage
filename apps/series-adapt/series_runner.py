"""
series-adapt 系列管理器

职责：
1. import_playlist  — 从 YouTube 播放列表导入剧集元数据到 tracking.db
2. process_next     — 取下一个待处理剧集，推进管线（调用 OMO harness）
3. get_status_report — 汇总各状态计数
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from db import SeriesDB, STATUS_FLOW

OMO_ROOT = Path(__file__).resolve().parent.parent.parent  # apps/series-adapt/ -> OpenMontage/


class SeriesRunner:
    """系列管理器"""

    STATUS_FLOW = STATUS_FLOW

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.db_path = self._resolve_path(self.config.get("database", {}).get("path", "projects/series-adapt-99/tracking.db"))
        self.base_dir = self._resolve_path(self.config.get("output", {}).get("base_dir", "projects/series-adapt-99"))
        self.db = SeriesDB(self.db_path)

    def _load_config(self) -> dict:
        import yaml
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _resolve_path(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (OMO_ROOT / path)

    # ── 导入播放列表 ────────────────────────────────────────────

    def import_playlist(self) -> int:
        """用 yt-dlp 获取播放列表元数据，导入 tracking.db。返回新增集数。"""
        playlist_url = self.config["series"]["source_playlist"]
        print(f"Fetching playlist: {playlist_url}")
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist", "--playlist-items", "1-100", playlist_url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        if result.returncode != 0:
            print(f"yt-dlp failed: {result.stderr[-500:]}")
            return 0

        added = 0
        for line in result.stdout.strip().splitlines():
            try:
                info = json.loads(line)
            except json.JSONDecodeError:
                continue
            video_id = info.get("id")
            title = info.get("title")
            if not video_id:
                continue
            url = f"https://www.youtube.com/watch?v={video_id}"
            # 从标题提取集号：如 【99追憶】/【99追忆】NN...
            episode_num = self._extract_episode_num(title, video_id)
            if self.db.add_episode(episode_num, video_id, url, source_title=title):
                added += 1
        print(f"Imported {added} episodes. Total in DB: {len(self.db.get_all())}")
        return added

    @staticmethod
    def _extract_episode_num(title: str, video_id: str) -> int:
        """从中文标题提取集号。格式如 【99追憶】01.xxx 或 【99追憶】...一/二/三。"""
        import re
        if not title:
            return 1
        # 匹配阿拉伯数字：【99追憶NN】 或 【99追忆NN】
        m = re.search(r"[【\[]99追[忆憶](\d{1,3})[】\]]", title)
        if m:
            return int(m.group(1))
        # 匹配中文数字后缀：【99追憶】...一/二/三/四/五/六
        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                  "七": 7, "八": 8, "九": 9, "十": 10}
        m = re.search(r"[。．]?\s*([一二三四五六七八九十])$", title)
        if m and m.group(1) in cn_map:
            return cn_map[m.group(1)]
        # 兜底：用 video_id 的哈希生成一个稳定编号
        return int(hash(video_id) % 1000) or 1

    # ── 推进管线 ────────────────────────────────────────────────

    def process_next(self) -> bool:
        """取下一个 imported 状态的剧集，调用 OMO harness 启动 fetch 阶段。"""
        ep = self.db.get_next_pending()
        if not ep:
            print("No pending episodes. Use `import` first.")
            return False
        ep_num = ep["episode_num"]
        print(f"Processing episode {ep_num}: {ep.get('source_title')}")

        # 创建工作目录
        slug = f"ep-{ep_num:02d}"
        work_dir = self.base_dir / slug
        work_dir.mkdir(parents=True, exist_ok=True)
        self.db.update_status(ep_num, "in_progress", work_dir=str(work_dir))

        # 调用 OMO harness 启动 fetch 阶段
        # （实际执行由 Agent 读取 start-stage 指令后完成）
        omo = OMO_ROOT / "bin" / "omo.py"
        cmd = [sys.executable, str(omo), "start-stage",
               "--project", f"series-adapt-99-{slug}",
               "--pipeline", "series-adapt"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
            if result.returncode == 0:
                print(result.stdout[-800:])
            else:
                print(f"OMO start-stage warning: {result.stderr[-300:]}")
        except subprocess.TimeoutExpired:
            print("OMO start-stage timed out (may be first-run init).")

        self.db.update_status(ep_num, "imported")  # 待 Agent 真正执行 fetch 后由管线更新
        print(f"Episode {ep_num} queued for pipeline. Start fetch via OMO.")
        return True

    # ── 状态报告 ────────────────────────────────────────────────

    def get_status_report(self) -> dict:
        stats = self.db.get_stats()
        next_ep = self.db.get_next_pending()
        report = {
            "stats": stats,
            "total": len(self.db.get_all()),
            "next_pending": next_ep["episode_num"] if next_ep else None,
        }
        return report

    def print_status(self):
        report = self.get_status_report()
        print("=" * 40)
        print("series-adapt 状态报告")
        print("=" * 40)
        print(f"总集数: {report['total']}")
        print(f"下一个待处理: 第 {report['next_pending']} 集" if report["next_pending"] else "无待处理集")
        print("-" * 40)
        for status in self.STATUS_FLOW:
            count = report["stats"].get(status, 0)
            if count:
                print(f"  {status:<16s} {count}")
        error_count = report["stats"].get("error", 0)
        if error_count:
            print(f"  {'error':<16s} {error_count}")
        print("-" * 40)
