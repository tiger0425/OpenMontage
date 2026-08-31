import sqlite3
con=sqlite3.connect('projects/auto-dub/tracking.db')
cur=con.cursor()
cur.execute('UPDATE videos SET status=? WHERE video_id=?', ('queued', 'kC4hErBshbc'))
con.commit()
print("reset to queued")
cur.execute('SELECT video_id, status FROM videos WHERE video_id=?', ('kC4hErBshbc',))
print(cur.fetchall())
# also clean up failed checkpoint maybe not needed - keep idea checkpoint
