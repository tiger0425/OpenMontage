"""GPU 物理互斥锁（跨智能体/跨进程文件级锁）。

背景：IndexTTS2 / VoxCPM 本地 GPU 推理占 8-16 GB VRAM。多个智能体
（OpenCode、OpenClaw、Cursor、Windsurf…）同时派发 Worker 合成时，
若并发加载模型必然 VRAM OOM。本模块提供进程间共享的文件锁：
任何 TTS 推理进入前必须获取；其他进程排队等待并打印友好心跳。

锁文件默认在用户级 %LOCALAPPDATA%/openmontage/.gpu.lock，
可用环境变量 OPENMONTAGE_GPU_LOCK_PATH 覆盖 —— 不同智能体/不同
工作目录只要同机即共享同一把锁。

两种使用方式::

    # 1. 上下文管理器（一段代码内持锁）
    from lib.gpu_lock import gpu_lock
    with gpu_lock("indextts-assets", timeout=1800, heartbeat=15):
        ... 模型加载 + 推理 ...

    # 2. 手动句柄（跨方法持锁，如 IndexTTS2 常驻服务生命周期）
    from lib.gpu_lock import GpuLockHandle
    handle = GpuLockHandle("indextts", timeout=1800, heartbeat=15)
    handle.acquire()
    ...
    handle.release()
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

try:
    import filelock  # type: ignore
    _HAVE_FILELOCK = True
except ImportError:
    _HAVE_FILELOCK = False

# 线程本地锁路径栈：同线程嵌套获取同一路径锁时直接放行（防 pipeline→工具层死锁）；
# 不同路径的锁不互相豁免（路径感知重入）。
_tls = threading.local()


def _held_paths() -> list[str]:
    paths = getattr(_tls, "paths", None)
    if paths is None:
        paths = []
        _tls.paths = paths
    return paths


# 锁文件默认位置：用户级，跨智能体共享
def _default_lock_path() -> Path:
    override = os.environ.get("OPENMONTAGE_GPU_LOCK_PATH")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "openmontage" / ".gpu.lock"


def _acquire_file(lock_path: Path, label: str, timeout: float, heartbeat: float) -> Callable[[], None]:
    """真正获取文件锁（带等待心跳提示）。返回释放回调。"""
    if _HAVE_FILELOCK:
        _filelock_mod = filelock  # type: ignore[union-attr]
        lock = _filelock_mod.FileLock(str(lock_path))
        deadline = time.time() + timeout
        last_notice = 0.0
        while True:
            try:
                lock.acquire(timeout=0.05)
                return lock.release
            except _filelock_mod.Timeout:
                now = time.time()
                if now - last_notice >= heartbeat:
                    print(
                        f"[AutoDub] 等待 GPU 锁（被其他任务占用，label={label}）...",
                        flush=True,
                    )
                    last_notice = now
                if now >= deadline:
                    raise TimeoutError(
                        f"[GPU Lock] 等待 {label} 超过 {timeout:.0f}s 仍无法获取锁 {lock_path}"
                    )
                time.sleep(0.5)

    # Fallback: O_EXCL create-file lock（filelock 不可用时）
    deadline = time.time() + timeout
    last_notice = 0.0
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)

            def _release():
                try:
                    os.unlink(str(lock_path))
                except FileNotFoundError:
                    pass

            return _release
        except FileExistsError:
            now = time.time()
            if now - last_notice >= heartbeat:
                print(
                    f"[AutoDub] 等待 GPU 锁（被其他任务占用，label={label}）...",
                    flush=True,
                )
                last_notice = now
            if now >= deadline:
                raise TimeoutError(
                    f"[GPU Lock] 等待 {label} 超过 {timeout:.0f}s 仍无法获取锁 {lock_path}"
                )
            time.sleep(1.0)


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
    path_str = str(path)

    held = _held_paths()
    if path_str in held:
        # 同线程、同路径重入（pipeline 层已持锁，工具层再进入）→ 直接放行
        yield
        return

    held.append(path_str)
    release: Optional[Callable[[], None]] = None
    try:
        release = _acquire_file(path, label, timeout, heartbeat)
        yield
    finally:
        if release is not None:
            release()
        if path_str in held:
            held.remove(path_str)


class GpuLockHandle:
    """可手动 acquire/release 的 GPU 锁句柄。

    用于跨方法持锁的场景（如 IndexTTS2 常驻服务：启动时 acquire、
    停止时 release），保证整个服务生命周期内其他进程排队等待。
    同线程、同路径嵌套 acquire 直接放行（幂等），需要对称调用 release。
    """

    def __init__(
        self,
        label: str,
        timeout: float = 1800.0,
        heartbeat: float = 15.0,
        lock_path: Path | None = None,
    ):
        self.label = label
        self.timeout = timeout
        self.heartbeat = heartbeat
        self.path = lock_path or _default_lock_path()
        self._release_fn: Optional[Callable[[], None]] = None
        self._nested: bool = False

    def acquire(self) -> "GpuLockHandle":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        path_str = str(self.path)
        held = _held_paths()
        if path_str in held:
            self._nested = True  # 同线程同路径已持有 → 幂等放行
            return self
        held.append(path_str)
        try:
            self._release_fn = _acquire_file(self.path, self.label, self.timeout, self.heartbeat)
        except Exception:
            if path_str in held:
                held.remove(path_str)
            raise
        return self

    def release(self) -> None:
        if self._nested:
            self._nested = False
            return
        if self._release_fn is not None:
            self._release_fn()
            self._release_fn = None
        path_str = str(self.path)
        held = _held_paths()
        if path_str in held:
            held.remove(path_str)

    def __enter__(self) -> "GpuLockHandle":
        return self.acquire()

    def __exit__(self, *exc) -> bool:
        self.release()
        return False
