import sqlite3
from pathlib import Path
db=Path('projects/auto-dub/tracking.db')
con=sqlite3.connect(db)
cur=con.cursor()
video_id='kC4hErBshbc'
url='https://www.youtube.com/watch?v=kC4hErBshbc'
title="Ancient Technologies We Still Can't Explain"
channel='Professor Historian'
channel_url='https://www.youtube.com/@ProfessorHistorian'
duration=996
published_at='2026-05-03'
language='en'
cur.execute('SELECT 1 FROM videos WHERE video_id=?', (video_id,))
row=cur.fetchone()
if row:
    print('exists, updating to queued')
    cur.execute('UPDATE videos SET status=?, title=?, channel=?, channel_url=?, duration_seconds=?, published_at=?, language=? WHERE video_id=?', ('queued', title, channel, channel_url, duration, published_at, language, video_id))
else:
    print('inserting')
    cur.execute('INSERT INTO videos (video_id, url, title, channel, channel_url, duration_seconds, published_at, language, status, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime("now"))', (video_id, url, title, channel, channel_url, duration, published_at, language, 'queued'))
con.commit()
cur.execute('SELECT video_id, status, title FROM videos WHERE video_id=?', (video_id,))
print(cur.fetchall())
