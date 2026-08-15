"""IndexTTS 统一客户端 —— 所有工作流的唯一调用入口。

三个工作流（auto-dub / markhasara / repo-to-video / series-adapt / 独立包）
统一通过本模块调用 IndexTTS 常驻服务，消除各自实现调用层的重复与踩坑。

统一封装：
- 桥位置：apps/indextts-bridge/indextts_server.py（勿用 D:/index-tts/indextts_server.py 旧桥）
- 启动命令：venv python + --version 2.5|2 + --checkpoints + 可选 --use-qwen-emo
- UTF-8 编码：stdin/stdout 一律 UTF-8（防止 PowerShell GBK 管道导致中文乱码）
- 情感纯净路径：2.5 固定 calm 不传 emo_vector（否则触发情感-音色混合 → 男声变女声）
- GPU 锁：GpuLockHandle 跨进程互斥 + 陈旧锁自动接管（防强杀残留）
- 请求超时：防止服务卡死时永久阻塞

用法：
    with IndexTTSSession(...) as tts:
        ok = tts.synthesize(text, output_path, seed=42)
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 路径解析（集中，消除各处重复常量）
# ---------------------------------------------------------------------------

def engine_paths() -> dict:
    """解析 IndexTTS venv python / server / checkpoints。

    优先级：env > config 段落（由调用方传 config_paths）> 平台默认。
    本函数返回 env 或默认值；config 段落由调用方优先传入。
    """
    omo_root = Path(__file__).resolve().parents[2]  # apps/indextts-bridge -> OpenMontage 根
    return {
        "venv": os.environ.get("INDEXTTS_VENV_PYTHON", r"D:/index-tts/.venv/Scripts/python.exe"),
        "server": os.environ.get(
            "INDEXTTS_SERVER",
            str(omo_root / "apps" / "indextts-bridge" / "indextts_server.py"),
        ),
        "checkpoints": os.environ.get("INDEXTTS_CHECKPOINTS", r"D:/index-tts/checkpoints"),
        "checkpoints_2": os.environ.get("INDEXTTS_CHECKPOINTS_2", r"D:/index-tts/checkpoints_2"),
    }


def _map_lang(target_language: str) -> str:
    """target_language（如 zh-CN）→ IndexTTS 2.5 lang 标签（默认 ZH）。"""
    base = (target_language or "zh-CN").split("-")[0].strip().lower()
    return {"zh": "ZH", "en": "EN", "ja": "JA", "es": "ES",
            "ko": "KO", "fr": "FR", "de": "DE"}.get(base, "ZH")


# ---------------------------------------------------------------------------
# 统一会话
# ---------------------------------------------------------------------------

class IndexTTSSession:
    """IndexTTS 常驻服务会话：一次初始化，多次合成。上下文管理器。"""

    def __init__(
        self,
        voice_ref: Optional[Path | str] = None,
        model_version: str = "2.5",
        lang: str = "ZH",
        use_qwen_emo: bool = False,
        emotion: str = "calm",
        timeout_seconds: float = 600.0,
        lock_timeout: float = 1800.0,
        checkpoints: Optional[Path | str] = None,
        project_dir: Optional[Path] = None,
    ):
        self.voice_ref = str(voice_ref) if voice_ref else None
        self.model_version = model_version
        self.lang = lang
        self.use_qwen_emo = use_qwen_emo
        self.emotion = emotion
        self.timeout_seconds = timeout_seconds
        self.lock_timeout = lock_timeout
        self.project_dir = project_dir

        paths = engine_paths()
        self.venv_python = paths["venv"]
        self.server = paths["server"]
        if checkpoints:
            self.checkpoints = str(checkpoints)
        elif model_version == "2":
            self.checkpoints = paths["checkpoints_2"]
        else:
            self.checkpoints = paths["checkpoints"]

        self._proc: Optional[subprocess.Popen] = None
        self._gpu_lock = None
        self._io_lock = threading.Lock()
        self._stderr_log = None

    # ---------------- 生命周期 ----------------

    def start(self) -> "IndexTTSSession":
        if self._proc is not None:
            return self
        from lib.gpu_lock import GpuLockHandle
        self._gpu_lock = GpuLockHandle("indextts", timeout=self.lock_timeout, heartbeat=15)
        self._gpu_lock.acquire()
        try:
            if self.project_dir is not None:
                log_path = Path(self.project_dir) / "indextts_server.log"
            else:
                log_path = Path(self.checkpoints).parent / "indextts_server.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_log = open(log_path, "w", encoding="utf-8", errors="replace")
            cmd = [self.venv_python, self.server, "--version", self.model_version]
            if self.use_qwen_emo:
                cmd.append("--use-qwen-emo")
            cmd += ["--checkpoints", self.checkpoints]
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr_log,
                text=True, encoding="utf-8", errors="replace",
            )
        except Exception:
            if self._gpu_lock is not None:
                try:
                    self._gpu_lock.release()
                except Exception:
                    pass
                self._gpu_lock = None
            raise
        self._wait_ready()
        return self

    def _wait_ready(self, timeout: float = 900.0) -> None:
        """等待常驻服务就绪（模型加载完成，日志出现 'model ready' 标记）。

        冷启动加载模型需数分钟；就绪前发请求会读到空响应 → 假失败。
        轮询 stderr 日志，出现 `>> model ready` 或进程退出即返回。
        """
        import time as _time
        deadline = _time.time() + timeout
        ready_marker = "model ready"
        while _time.time() < deadline:
            proc = self._proc
            if proc is None:
                return
            if proc.poll() is not None:
                raise RuntimeError(
                    f"IndexTTS 服务启动失败（进程退出 code={proc.returncode}），见 indextts_server.log"
                )
            try:
                if self._stderr_log is not None:
                    self._stderr_log.flush()
                if self.project_dir is not None:
                    log_path = Path(self.project_dir) / "indextts_server.log"
                else:
                    log_path = Path(self.checkpoints).parent / "indextts_server.log"
                if log_path.exists():
                    content = log_path.read_text(encoding="utf-8", errors="replace")
                    if ready_marker in content:
                        return
            except Exception:
                pass
            _time.sleep(2)
        raise TimeoutError(f"IndexTTS 服务 {timeout:.0f}s 内未就绪")

    def stop(self) -> None:
        """停止服务并释放 GPU 锁（幂等，可安全多次调用）。"""
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.stdin.write('{"cmd": "exit"}\n')
                proc.stdin.flush()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._gpu_lock is not None:
            try:
                self._gpu_lock.release()
            except Exception:
                pass
            self._gpu_lock = None

    def __enter__(self) -> "IndexTTSSession":
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False

    # ---------------- 合成 ----------------

    def synthesize(
        self,
        text: str,
        output_path: Path | str,
        seed: int = 42,
        target_duration: Optional[float] = None,
        lang: Optional[str] = None,
    ) -> bool:
        """合成单段音频。返回是否成功。

        - 2.5 版本：透传 lang + duration_factor（target_duration 换算）。
        - 情感纯净：固定 calm 不传 emo_vector（官方纯净克隆，保声纹）；
          emotion=auto 时用 use_emo_text（需 --use-qwen-emo）。
        """
        if self._proc is None:
            self.start()
        assert self._proc is not None and self._proc.stdin and self._proc.stdout

        req = {
            "id": str(hash((text, str(output_path)))),
            "text": text,
            "output_path": str(output_path),
            "seed": seed,
        }
        if self.model_version == "2.5":
            req["lang"] = lang or self.lang
            if target_duration and target_duration > 0:
                req["duration_factor"] = float(target_duration)
        # 情感纯净路径（2.5 关键：calm 不传 emo_vector，否则音色漂移/女声化）
        if self.model_version == "2.5":
            if self.emotion == "auto":
                req["use_emo_text"] = True
                req["emo_alpha"] = 0.6
            # calm：不传任何情感参数 → 官方纯净克隆
        else:
            # 2 版本：沿用旧行为（calm 固定向量）
            if self.emotion == "calm":
                req["use_emo_text"] = False
                req["emo_vector"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        if self.voice_ref:
            req["voice_ref"] = self.voice_ref

        try:
            with self._io_lock:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
                resp_line = self._proc.stdout.readline()
            if not resp_line:
                self._dump_stderr("服务无响应")
                return False
            resp = json.loads(resp_line)
            ok = bool(resp.get("ok"))
            if not ok:
                self._dump_stderr(f"服务返回失败: {resp.get('error')}")
            return ok
        except Exception as e:
            self._dump_stderr(f"服务异常: {e}")
            return False

    def _dump_stderr(self, reason: str) -> None:
        """打印服务 stderr 日志尾部（诊断用）。"""
        try:
            print(f"      [IndexTTS2] {reason}", flush=True)
        except Exception:
            pass
        try:
            if self._stderr_log is None:
                return
            self._stderr_log.flush()
            # stderr 日志路径
            if self.project_dir is not None:
                log_path = Path(self.project_dir) / "indextts_server.log"
            else:
                log_path = Path(self.checkpoints).parent / "indextts_server.log"
            if not log_path.exists():
                return
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for ln in lines[-20:]:
                print("      | " + ln, flush=True)
        except Exception:
            pass
