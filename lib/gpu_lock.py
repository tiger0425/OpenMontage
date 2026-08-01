"""GPU 物理互斥锁（跨智能体/跨进程文件级锁）。

背景：IndexTTS2 / VoxCPM 本地 GPU 推理占 8-16 GB VRAM。多个智能体
（OpenCode、OpenClaw、Cursor、Windsurf…）同时派发 Worker 合成时，
若并发加载模型必然 VRAM OOM。本模块提供一个进程间共享的文件锁，
任何 TTS 推理进入前必须获取；其他进程排队等待并打印友好心跳。

锁文件默认在用户级 %LOCALAPPDATA%/openmontage/.gpu.lock，
可用环境变量 OPENMONTAGE_GPU_LOCK_PATH 覆盖 —— 不同智能体/不同
工作目录只要同机即共享同一把锁。

用法::

    from lib.gpu_lock import gpu_lock
    with gpu_lock("indextts-assets", timeout=1800, heartbeat=15):
        # ... 模型加载 + 推理 ...
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import filelock  # type: ignore
    _HAVE_FILELOCK = True
except ImportError:
    _HAVE_FILELOCK = False

# 锁文件默认位置：用户级，跨智能体共享
def _default_lock_path() -> Path:
    override = os.environ.get("OPENMONTAGE_GPU_LOCK_PATH")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "openmontage" / ".gpu.lock"


@contextmanager
def gpu_lock(
    label: str,
    timeout: float = 1800.0,
    heartbeat: float = 15.0,
    lock_path: Path | None = None,
) -> Iterator[None]:
    """获取 GPU 互斥锁。排队等待时周期性打印友好提示。

    Args:
        label: 占用者标识（如 "indextts-assets"），用于诊断。
        timeout: 最长等待秒数，超时抛 TimeoutError。
        heartbeat: 等待提示间隔秒数。
        lock_path: 覆盖锁文件路径（默认用户级共享锁）。
    """
    path = lock_path or _default_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if _HAVE_FILELOCK:
        _lock = filelock.FileLock(str(path), timeout=timeout)  # type: ignore[union-attr]
        try:
            with _lock:
                yield
        except filelock.Timeout:  # type: ignore[union-attr]
            raise TimeoutError(
                f"[GPU Lock] 等待 {label} 超过 {timeout:.0f}s 仍无法获取锁 {path}"
            )
        return

    # Fallback: O_EXCL create-file lock（filelock 不可用时）
    deadline = time.time() + timeout
    last_notice = 0.0
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            try:
                yield
            finally:
                try:
                    os.unlink(str(path))
                except FileNotFoundError:
                    pass
            return
        except FileExistsError:
            now = time.time()
            if now - last_notice >= heartbeat:
                print(
                    f"[AutoDub] 等待 GPU 锁（被其他任务占用），"
                    f"最长 {int(timeout - (now - (deadline - timeout)))}s ...",
                    flush=True,
                )
                last_notice = now
            if now >= deadline:
                raise TimeoutError(
                    f"[GPU Lock] 等待 {label} 超过 {timeout:.0f}s 仍无法获取锁 {path}"
                )
            time.sleep(1.0)
