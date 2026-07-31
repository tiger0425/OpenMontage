"""Verify rendered MP4 metadata and extract test frames."""
import subprocess, json
from pathlib import Path

mp4 = Path("projects/ai-news-daily/renders/final.mp4")
out_dir = Path("projects/ai-news-daily/renders")
out_dir.mkdir(parents=True, exist_ok=True)

# Probe
probe = subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json",
     "-show_format", "-show_streams", str(mp4)],
    capture_output=True, text=True
)
info = json.loads(probe.stdout)
print("=== File Info ===")
print(f"  Format: {info['format']['format_name']}")
print(f"  Duration: {info['format']['duration']}s")
print(f"  Size: {float(info['format']['size'])/(1024*1024):.1f} MB")
for s in info["streams"]:
    codec = s["codec_type"]
    print(f"  Stream: {codec} / {s.get('codec_name','?')}", end="")
    if codec == "video":
        print(f" / {s.get('width','?')}x{s.get('height','?')} / {s.get('r_frame_rate','?')}")
    else:
        print()

# Extract test frames at key timestamps
timestamps = [0, 1, 3, 10, 20, 30, 60, 90, 135, 170]
for t in timestamps:
    out = out_dir / f"verify_{t:03d}s.png"
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", str(mp4),
         "-vframes", "1", "-q:v", "2", str(out)],
        capture_output=True, text=True
    )
    if out.exists():
        size_kb = out.stat().st_size / 1024
        status = "HAS_CONTENT" if size_kb > 15 else "BLACK_OR_EMPTY"
        print(f"  t={t}s: {size_kb:.1f} KB [{status}]")
