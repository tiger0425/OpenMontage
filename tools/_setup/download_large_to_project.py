"""Download missing files for musicgen-large directly into OpenMontage/models/musicgen/large."""

import os
import sys
import time
import requests
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

target_dir = Path("models/musicgen/large")
target_dir.mkdir(parents=True, exist_ok=True)

# List of smaller files
SMALL_FILES = [
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "pytorch_model.bin.index.json",
    "compression_state_dict.bin",
]

LARGE_FILE = "pytorch_model-00002-of-00002.bin"
LARGE_FILE_EXPECTED_SIZE = 3731557007  # ~3.56 GB

def download_file(filename: str, expected_size: int = None):
    out_file = target_dir / filename
    if out_file.exists() and not out_file.name.endswith(".incomplete"):
        if expected_size is None or out_file.stat().st_size == expected_size:
            print(f"Already exists: {filename} ({out_file.stat().st_size / 1024 / 1024:.2f} MB)")
            return

    url = f"https://hf-mirror.com/facebook/musicgen-large/resolve/main/{filename}"
    inc_file = target_dir / f"{filename}.incomplete"
    current_size = inc_file.stat().st_size if inc_file.exists() else 0

    headers = {"User-Agent": "Mozilla/5.0"}
    if current_size > 0:
        headers["Range"] = f"bytes={current_size}-"

    print(f"Downloading {filename} (starting from {current_size / 1024 / 1024:.2f} MB)...")

    retries = 0
    while retries < 20:
        try:
            with requests.get(url, headers=headers, stream=True, timeout=20, allow_redirects=True) as resp:
                if resp.status_code not in (200, 206):
                    print(f"Error status {resp.status_code}, retrying...")
                    time.sleep(3)
                    retries += 1
                    continue

                total_len = int(resp.headers.get("content-length", 0)) + current_size
                with open(inc_file, "ab") as f:
                    last_log = time.time()
                    bytes_since_log = 0
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            current_size += len(chunk)
                            bytes_since_log += len(chunk)
                            now = time.time()
                            if now - last_log >= 5.0:
                                speed = (bytes_since_log / (now - last_log)) / 1024 / 1024
                                if total_len > 0:
                                    pct = (current_size / total_len) * 100
                                    print(f"[{filename}] {current_size / 1024 / 1024:.1f} MB ({pct:.1f}%) | Speed: {speed:.2f} MB/s")
                                else:
                                    print(f"[{filename}] {current_size / 1024 / 1024:.1f} MB | Speed: {speed:.2f} MB/s")
                                last_log = now
                                bytes_since_log = 0

            # Finished
            inc_file.rename(out_file)
            print(f"Successfully finished {filename} ({out_file.stat().st_size / 1024 / 1024:.2f} MB)!")
            return

        except Exception as e:
            print(f"Connection dropped ({e}), retrying in 3s...")
            time.sleep(3)
            current_size = inc_file.stat().st_size if inc_file.exists() else 0
            headers["Range"] = f"bytes={current_size}-"
            retries += 1

if __name__ == "__main__":
    print("=== Downloading configs and smaller weights ===")
    for sf in SMALL_FILES:
        download_file(sf)

    print("=== Downloading pytorch_model-00002-of-00002.bin ===")
    download_file(LARGE_FILE, LARGE_FILE_EXPECTED_SIZE)
    print("=== ALL FILES FOR MUSICGEN-LARGE COMPLETE IN PROJECT! ===")
