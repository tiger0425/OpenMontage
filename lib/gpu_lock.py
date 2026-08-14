"""GPU 物理互斥锁（跨智能体/跨进程文件级锁）。

背景：IndexTTS2 / VoxCPM 本地 GPU 推理占 8-16 GB VRAM。多个智能体
（OpenCode、OpenClaw、Cursor、Windsurf…）同时派发 Worker 合成时，
若并发加载模型必然 VRAM OOM。本模块提供进程间共享的文件锁：
任何 TTS 推理进入前必须获取；其他进程排队等待并打印友好心跳。

锁文件默认在用户级 %LOCALAPPDATA%/openmontage/.gpu.lock，
可用环境变量 OPENMONTAGE_GPU_LOCK_PATH 覆盖 —— 不同智能体/不同
工作目录只要同机即共享同一把锁。

陈旧锁自动接管：进程被强杀（Stop-Process -Force）时锁可能残留，
等待方每轮检测持有者 PID 是否存活（fallback 锁写入 pid=），或锁文件
mtime 超时无主（filelock 空锁文件），发现陈旧则删除并接管，避免永久卡死。

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
import sys
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


# ---------------------------------------------------------------------------
# 陈旧锁检测：进程被强杀（Stop-Process -Force）时锁文件/OS 锁残留，
# 新进程会永久等待。锁文件记录持有者 PID + 时间戳，等待方检测到
# 持有者进程已死（或锁文件超时无主）则自动接管，避免永久卡死。
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    """检测进程是否存活（跨平台）。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但无权限查看 → 视为存活
    except OSError:
        return False


def _lock_owner_pid(lock_path: Path) -> int | None:
    """读取锁文件记录的持有者 PID（fallback 分支写入 pid=<pid>）。"""
    try:
        content = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
    except (OSError, ValueError):
        return None
    if not content:
        return None
    for line in content.splitlines():
        if line.startswith("pid="):
            try:
                return int(line.split("=", 1)[1].strip())
            except (ValueError, IndexError):
                return None
    return None


def _lock_stale(lock_path: Path, timeout: float) -> bool:
    """判断锁是否陈旧（可安全接管）。

    - 有 PID：持有者进程已死 → 陈旧；持有者仍存活 → 非陈旧。
    - 无 PID（filelock 空锁文件 / 旧格式残留）：先尝试 OS 级探测是否真被持有
      （filelock is_locked / O_EXCL 探测），探测不到 → 视为陈旧。
    """
    try:
        st = lock_path.stat()
    except FileNotFoundError:
        return False
    pid = _lock_owner_pid(lock_path)
    if pid is not None:
        if pid == os.getpid():
            return False  # 自己持有
        if not _pid_alive(pid):
            return True
        return False
    # 无 PID：尝试探测锁是否真被持有（兼容 filelock 空锁文件 / 旧 O_EXCL 残留）
    if _HAVE_FILELOCK:
        try:
            _filelock_mod = filelock  # type: ignore[union-attr]
            probe = _filelock_mod.FileLock(str(lock_path))
            if not probe.is_locked:
                return True  # OS 锁未被持有 → 陈旧
            return False
        except Exception:
            pass
    # filelock 探测不可用：O_EXCL 探测
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        try:
            os.unlink(str(lock_path))
        except FileNotFoundError:
            pass
        return True  # 能创建 = 未被持有 → 陈旧
    except FileExistsError:
        return False
    except OSError:
        return False


def _remove_stale_lock(lock_path: Path, timeout: float) -> bool:
    """若锁陈旧则删除并返回 True（调用方随即重试获取）。"""
    if _lock_stale(lock_path, timeout):
        try:
            os.unlink(str(lock_path))
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True
    return False


def _filelock_release_with_cleanup(lock, lock_path: Path) -> Callable[[], None]:
    """filelock 释放：先释放 OS 锁，再删除锁文件（避免强杀场景残留）。"""
    def _release():
        try:
            lock.release()
        except Exception:
            pass
        try:
            os.unlink(str(lock_path))
        except FileNotFoundError:
            pass
        except OSError:
            pass

    return _release


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
    """真正获取文件锁（带等待心跳提示）。返回释放回调。

    防止永久卡死：等待期间周期性检测陈旧锁（持有者进程已死 / 超时无主），
    发现则删除并接管，而不是死等 timeout 全程。
    """
    if _HAVE_FILELOCK:
        _filelock_mod = filelock  # type: ignore[union-attr]
        lock = _filelock_mod.FileLock(str(lock_path))
        deadline = time.time() + timeout
        last_notice = 0.0
        while True:
            # 陈旧锁接管：持有者进程已死 / 锁文件超时无主 → 删除重试
            if _remove_stale_lock(lock_path, timeout):
                continue
            try:
                lock.acquire(timeout=0.05)
                return _filelock_release_with_cleanup(lock, lock_path)
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
        # 陈旧锁接管：持有者进程已死 → 删除重试
        if _remove_stale_lock(lock_path, timeout):
            continue
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                # 写入持有者 PID + 创建时间，供其他进程做陈旧锁检测
                os.write(fd, f"pid={os.getpid()}\ncreated={time.time():.6f}\n".encode("utf-8"))
            finally:
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
    path = Path(lock_path) if lock_path is not None else _default_lock_path()
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
        self.path = Path(lock_path) if lock_path is not None else _default_lock_path()
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
