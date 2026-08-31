import subprocess, time, os, sys
from pathlib import Path

target = Path("projects/auto-dub/auto-dub-251hsWgoTPM/source.mp4")
part = Path("projects/auto-dub/auto-dub-251hsWgoTPM/source.mp4.part")
# also check source.mp4.part naming from yt-dlp may be exactly source.mp4.part
# show existing
start_size = part.stat().st_size if part.exists() else (target.stat().st_size if target.exists() else 0)
print(f"[init] part={part.exists()} size={start_size/1024/1024:.2f} MB, target={target.exists()}")

# yt-dlp path
cmd = [
    "yt-dlp",
    "--no-playlist",
    "--extractor-args", "youtube:player_client=android,web",
    "-f", "18",
    "-o", "projects/auto-dub/auto-dub-251hsWgoTPM/source.mp4",
    "https://www.youtube.com/watch?v=251hsWgoTPM",
    "--progress",
    "--no-mtime",
]
print("CMD:", " ".join(cmd))

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8", errors="replace")

start = time.time()
last_size = start_size
last_time = start
# 30 min timeout = 1800s
timeout = 1800
poll_interval = 30
next_poll = start + poll_interval
# read output in non-blocking via thread? Simple poll file size while proc alive
import threading, queue
q = queue.Queue()
def reader():
    for line in proc.stdout:
        q.put(line)
        # also print yt-dlp line if contains % or Downloading
        if "%" in line or "Downloading" in line or "ERROR" in line:
            print(f"[yt-dlp] {line.rstrip()}")
    q.put(None)
t = threading.Thread(target=reader, daemon=True)
t.start()

elapsed = 0
done = False
while True:
    now = time.time()
    elapsed = now - start
    if now >= next_poll:
        # check file size
        sz = 0
        if target.exists() and not part.exists():
            sz = target.stat().st_size
        elif part.exists():
            sz = part.stat().st_size
        elif target.exists():
            sz = target.stat().st_size
        dt = now - last_time
        ds = sz - last_size
        speed = ds/dt if dt>0 else 0
        # speed in KB/s or MB/s
        if speed > 1024*1024:
            sp = f"{speed/1024/1024:.2f} MB/s"
        else:
            sp = f"{speed/1024:.1f} KB/s"
        print(f"[{int(elapsed)//60:02d}:{int(elapsed)%60:02d}] 已下载 {sz/1024/1024:.2f} MB / 182MB 速度 {sp}")
        last_size = sz
        last_time = now
        next_poll = now + poll_interval
        # drain queue print
        while not q.empty():
            try:
                line = q.get_nowait()
                if line is None:
                    done = True
                    break
                # already printed filtered
            except:
                break
        if done:
            pass

    # check if process done
    if proc.poll() is not None:
        # process finished
        # drain remaining
        time.sleep(0.5)
        while not q.empty():
            line = q.get()
            if line is None:
                break
            if line.strip():
                print(f"[yt-dlp] {line.rstrip()}")
        ret = proc.returncode
        print(f"[exit] yt-dlp returncode={ret} elapsed={elapsed:.0f}s")
        break
    if elapsed > timeout:
        print(f"[timeout] 30分钟超时，终止")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except:
            proc.kill()
        break
    time.sleep(1)
    # also check if source.mp4 exists and no .part means complete even if proc still running? but proc will exit
    if target.exists() and not part.exists():
        # file completed
        sz = target.stat().st_size
        print(f"[complete] source.mp4 已存在 {sz/1024/1024:.2f} MB, 无 .part")
        # wait for proc to exit quickly
        for _ in range(10):
            if proc.poll() is not None:
                break
            time.sleep(1)
        if proc.poll() is None:
            print("[complete] proc仍在运行，等待退出")
        else:
            print(f"[complete] proc已退出 code={proc.returncode}")
        break

# final status
if target.exists() and not part.exists():
    print("RESULT: DONE")
    sz = target.stat().st_size
    print(f"final size {sz}")
else:
    if part.exists():
        print(f"RESULT: PARTIAL part={part.stat().st_size/1024/1024:.2f} MB")
    else:
        print("RESULT: NO FILE")
    if target.exists():
        print(f"target exists {target.stat().st_size/1024/1024:.2f} MB")

sys.exit(0)
