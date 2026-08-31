import sqlite3
conn=sqlite3.connect('projects/auto-dub/tracking.db')
c=conn.cursor()
c.execute("UPDATE videos SET status='queued' WHERE video_id='251hsWgoTPM'")
conn.commit()
print("reset to queued")
c.execute("SELECT video_id,status FROM videos WHERE video_id='251hsWgoTPM'")
print(c.fetchall())
