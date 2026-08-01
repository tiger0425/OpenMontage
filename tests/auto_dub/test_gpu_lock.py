"""GPU 物理互斥锁测试：跨进程排队，同一时间只有一人持有锁。"""

import sys
import tempfile
import threading
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from lib.gpu_lock import gpu_lock


class TestGpuLock:
    def test_serializes_across_threads(self):
        """两个线程竞争同一把锁，互斥执行，无并发进入。"""
        import time
        tmp = Path(tempfile.mkdtemp(prefix="gpu_lock_test_"))
        lock_path = tmp / ".gpu.lock"

        active = 0
        max_active = 0
        entered = []

        def worker(name):
            nonlocal active, max_active
            with gpu_lock(name, timeout=30, heartbeat=1, lock_path=lock_path):
                active += 1
                max_active = max(max_active, active)
                entered.append(name)
                time.sleep(0.3)  # 持锁 300ms
                active -= 1

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(entered) == 3
        assert max_active == 1  # 任何时刻最多一人持锁

    def test_timeout_raises(self):
        """锁被长时间占用时，等待方超时抛 TimeoutError。"""
        import time
        tmp = Path(tempfile.mkdtemp(prefix="gpu_lock_timeout_"))
        lock_path = tmp / ".gpu.lock"

        released = threading.Event()

        def holder():
            with gpu_lock("holder", timeout=30, heartbeat=1, lock_path=lock_path):
                released.wait(timeout=3)

        t = threading.Thread(target=holder)
        t.start()
        time.sleep(0.5)  # 确保 holder 已持锁

        raised = False
        try:
            with gpu_lock("waiter", timeout=1.0, heartbeat=0.2, lock_path=lock_path):
                pass
        except TimeoutError:
            raised = True

        released.set()
        t.join(timeout=5)
        assert raised

    def test_reentrant_same_thread_no_deadlock(self):
        """同线程嵌套获取（pipeline assets 层 → voxcpm 工具层）直接放行，不死锁。"""
        import time
        tmp = Path(tempfile.mkdtemp(prefix="gpu_lock_reentrant_"))
        lock_path = tmp / ".gpu.lock"

        # 外层持锁，内层再进入同一把锁 → 必须立即返回（重入）
        with gpu_lock("assets", timeout=10, heartbeat=1, lock_path=lock_path):
            start = time.time()
            with gpu_lock("voxcpm-tool", timeout=10, heartbeat=1, lock_path=lock_path):
                pass
            assert time.time() - start < 2.0  # 未等待锁 → 无死锁
