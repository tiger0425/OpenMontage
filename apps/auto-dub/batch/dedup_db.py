"""
视频去重追踪数据库模块
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

class DedupDB:
    """SQLite 视频去重追踪数据库"""
    
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        # 自动创建父目录
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 连接到数据库，设置线程安全标志
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False
        )
        # 设置结果返回字典形式以便操作
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """初始化数据库，创建表结构"""
        query = """
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            channel TEXT,
            channel_url TEXT,
            duration_seconds INTEGER,
            published_at TEXT,
            language TEXT,
            status TEXT DEFAULT 'discovered',
            discovered_at TEXT,
            processed_at TEXT,
            output_path TEXT,
            error_msg TEXT,
            metadata TEXT
        )
        """
        with self.conn:
            self.conn.execute(query)
    
    def exists(self, video_id: str) -> bool:
        """检查视频是否已在数据库中"""
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,))
        return cur.fetchone() is not None

    def get_video_status(self, video_id: str) -> str | None:
        """获取视频的当前状态，不存在则返回 None"""
        cur = self.conn.cursor()
        cur.execute("SELECT status FROM videos WHERE video_id = ?", (video_id,))
        row = cur.fetchone()
        return row['status'] if row else None

    def get_by_id(self, video_id: str) -> dict | None:
        """按 video_id 获取视频记录，不存在则返回 None"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    
    def add_video(self, video_id: str, url: str, title: str, channel: str, channel_url: str, 
                  duration_seconds: int, published_at: str, language: str = None, metadata: dict = None) -> bool:
        """添加视频，如果已存在返回 False"""
        if self.exists(video_id):
            return False
            
        now_iso = datetime.now().isoformat()
        metadata_str = json.dumps(metadata) if metadata else None
        
        query = """
        INSERT INTO videos (
            video_id, url, title, channel, channel_url, 
            duration_seconds, published_at, language, discovered_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.conn:
                self.conn.execute(query, (
                    video_id, url, title, channel, channel_url,
                    duration_seconds, published_at, language, now_iso, metadata_str
                ))
            return True
        except sqlite3.IntegrityError:
            return False
    
    def update_status(self, video_id: str, status: str, error_msg: str = None, output_path: str = None):
        """更新视频状态"""
        now_iso = datetime.now().isoformat()
        query = """
        UPDATE videos 
        SET status = ?, error_msg = ?, output_path = ?, processed_at = ?
        WHERE video_id = ?
        """
        with self.conn:
            self.conn.execute(query, (status, error_msg, output_path, now_iso, video_id))
    
    def get_by_status(self, status: str) -> list[dict]:
        """获取指定状态的所有视频"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM videos WHERE status = ?", (status,))
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    
    def get_stats(self) -> dict:
        """获取统计信息: {status: count, ...}"""
        cur = self.conn.cursor()
        cur.execute("SELECT status, COUNT(*) as count FROM videos GROUP BY status")
        rows = cur.fetchall()
        return {row['status']: row['count'] for row in rows}
    
    def get_all(self) -> list[dict]:
        """获取所有视频记录"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM videos")
        rows = cur.fetchall()
        return [dict(row) for row in rows]
