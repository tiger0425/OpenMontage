"""Extract frames at many timestamps to see the full picture."""
import subprocess, os

video = "projects/ai-news-daily/renders/final.mp4"
out_dir = "projects/ai-news-daily/renders"

for t in [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 30, 60, 90, 120, 150, 175]:
    out = os.path.join(out_dir, f"scan_{t:03d}s.png")
    cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", video, "-vframes", "1", "-q:v", "2", out]
    subprocess.run(cmd, capture_output=True)
    sz = os.path.getsize(out) if os.path.exists(out) else 0
    tag = "BLACK" if sz < 10000 else "HAS CONTENT"
    print(f"t={t:3d}s  {sz:7d} bytes  {tag}")
