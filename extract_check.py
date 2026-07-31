"""Extract frames from the video to check if text is visible."""
import subprocess
import os

video = "projects/ai-news-daily/renders/final.mp4"
out_dir = "projects/ai-news-daily/renders"

# Extract frames at 0s, 2s, 5s, 10s
for t in [0, 2, 5, 10]:
    out = os.path.join(out_dir, f"check_{t}s.png")
    cmd = [
        "ffmpeg", "-y", "-ss", str(t), "-i", video,
        "-vframes", "1", "-q:v", "2", out
    ]
    subprocess.run(cmd, capture_output=True)
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print(f"Frame at {t}s: {size} bytes -> {out}")
