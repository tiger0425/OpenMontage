"""
series-adapt 系列剧集追踪数据库模块

状态机: imported → fetched → briefed → rewritten → scene_planned
       → assets_ready → composed → rendered → reviewed → published
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

# 合法的状态流转
STATUS_FLOW = [
    "imported", "fetched", "briefed", "rewritten",
    "scene_planned", "assets_ready", "composed",
    "rendered", "reviewed", "published",
]

# 允许回退的目标状态（用于人工审查驳回）
REJECT_TARGETS = ["imported", "fetched", "briefed", "rewritten", "scene_planned", "assets_ready", "composed"]


class SeriesDB:
    """SQLite 剧集追踪数据库"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """初始化数据库，创建表结构"""
        query = """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_num INTEGER NOT NULL,
            source_video_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_title TEXT,
            status TEXT DEFAULT 'imported',
            title_zh TEXT,
            title_en TEXT,
            slug TEXT,
            work_dir TEXT,
            error_msg TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
        with self.conn:
            self.conn.execute(query)
            # 唯一约束：一集只能出现一次
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_episode_num ON episodes(episode_num)"
            )

    def add_episode(self, episode_num: int, source_video_id: str, source_url: str,
                    source_title: str = None) -> bool:
        """添加一集，如果已存在返回 False"""
        exists = self.get_episode(episode_num)
        if exists:
            return False
        now_iso = datetime.now().isoformat()
        query = """
        INSERT INTO episodes (episode_num, source_video_id, source_url, source_title,
                              status, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'imported', ?, ?)
        """
        try:
            with self.conn:
                self.conn.execute(query, (episode_num, source_video_id, source_url,
                                          source_title, now_iso, now_iso))
            return True
        except sqlite3.IntegrityError:
            return False

    def get_episode(self, episode_num: int) -> dict | None:
        """按集号获取记录"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM episodes WHERE episode_num = ?", (episode_num,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_by_status(self, status: str) -> list[dict]:
        """获取指定状态的所有集"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM episodes WHERE status = ? ORDER BY episode_num", (status,))
        return [dict(r) for r in cur.fetchall()]

    def get_all(self) -> list[dict]:
        """获取所有剧集"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM episodes ORDER BY episode_num")
        return [dict(r) for r in cur.fetchall()]

    def get_stats(self) -> dict:
        """获取统计信息: {status: count, ...}"""
        cur = self.conn.cursor()
        cur.execute("SELECT status, COUNT(*) as count FROM episodes GROUP BY status")
        return {r['status']: r['count'] for r in cur.fetchall()}

    def get_next_pending(self) -> dict | None:
        """获取下一个待处理的集（状态最早 + 集号最小）"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM episodes WHERE status = 'imported' "
            "ORDER BY episode_num LIMIT 1"
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def update_status(self, episode_num: int, status: str,
                      error_msg: str = None, work_dir: str = None,
                      title_en: str = None, slug: str = None) -> bool:
        """更新集状态（仅允许向前流转或显式回退）"""
        ep = self.get_episode(episode_num)
        if not ep:
            return False
        now_iso = datetime.now().isoformat()
        fields = ["status = ?", "updated_at = ?"]
        params: list = [status, now_iso]
        if error_msg is not None:
            fields.append("error_msg = ?")
            params.append(error_msg)
        if work_dir is not None:
            fields.append("work_dir = ?")
            params.append(work_dir)
        if title_en is not None:
            fields.append("title_en = ?")
            params.append(title_en)
        if slug is not None:
            fields.append("slug = ?")
            params.append(slug)
        params.append(episode_num)
        query = f"UPDATE episodes SET {', '.join(fields)} WHERE episode_num = ?"
        with self.conn:
            self.conn.execute(query, tuple(params))
        return True

    def reject(self, episode_num: int, target: str, reason: str) -> bool:
        """人工审查驳回：回退到指定阶段并记录原因"""
        if target not in REJECT_TARGETS:
            return False
        return self.update_status(episode_num, target, error_msg=reason)

    def mark_error(self, episode_num: int, error: str) -> None:
        """标记错误状态"""
        self.update_status(episode_num, "error", error_msg=error)

    def close(self):
        self.conn.close()
