"""Relocate MusicGen models into OpenMontage project models/musicgen directory."""

import os
import shutil
import subprocess
from pathlib import Path

repo_root = Path(r"E:\YifuAIForge\OpenMontage")
target_dir = repo_root / "models" / "musicgen"
target_large = target_dir / "large"
target_small = target_dir / "small"

c_cache_root = Path(os.path.expanduser(r"~/.cache/huggingface/hub"))
src_large_snap = c_cache_root / "models--facebook--musicgen-large" / "snapshots" / "15ccdc92099879e47b6da12c350cdb71d4eab3ca"
src_small_snap = c_cache_root / "models--facebook--musicgen-small" / "snapshots" / "4c8334b02c6ec4e8664a91979669a501ec497792"

target_large.mkdir(parents=True, exist_ok=True)
target_small.mkdir(parents=True, exist_ok=True)

print(f"Relocating MusicGen models to project directory: {target_dir}")

def copy_or_move(src_dir: Path, dst_dir: Path, name: str):
    print(f"Moving {name} from {src_dir} to {dst_dir}...")
    for item in src_dir.iterdir():
        dst_item = dst_dir / item.name
        if dst_item.exists() and dst_item.stat().st_size == item.stat().st_size:
            print(f"  Already exists at dest: {item.name}")
            continue
        print(f"  Moving {item.name} ({item.stat().st_size / 1024 / 1024:.2f} MB)...")
        shutil.move(str(item), str(dst_item))
    print(f"Finished moving {name}!")

copy_or_move(src_small_snap, target_small, "MusicGen-Small")
copy_or_move(src_large_snap, target_large, "MusicGen-Large")

# Remove leftover incomplete files on C: drive to reclaim space
incompletes = list(c_cache_root.glob("models--facebook--musicgen*/**/*.incomplete"))
for inc in incompletes:
    try:
        inc_size_mb = inc.stat().st_size / 1024 / 1024
        inc.unlink()
        print(f"Cleaned up C: incomplete file: {inc.name} ({inc_size_mb:.2f} MB)")
    except Exception as e:
        print(f"Failed to clean up {inc}: {e}")

# Clean up blobs if empty or redundant
for model_name in ["models--facebook--musicgen-large", "models--facebook--musicgen-small"]:
    blobs = c_cache_root / model_name / "blobs"
    if blobs.exists():
        for b in blobs.iterdir():
            try:
                b.unlink()
            except Exception:
                pass

print("Models successfully relocated into OpenMontage/models/musicgen/ !")
