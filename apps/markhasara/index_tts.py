"""IndexTTS2 常驻服务桥接（与 auto-dub 完全一致）。

复用 auto-dub 的 IndexTTS2 调用模式：
- 常驻服务进程（模型只加载一次，GPU 加速）
- JSON 行协议（stdin 发请求，stdout 收响应）
- GpuLockHandle 跨进程持 GPU 锁（杜绝并发 OOM）
- voice_ref 传入用户声音 WAV → 克隆用户音色
- use_emo_text + emo_vector 控制情感

配置（config.yaml voice 段）：
- user_voice_ref: 用户声音样本 WAV（克隆用）
- tts_emotion: calm / auto / excited
"""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# IndexTTS venv python（机器相关，可用 env 覆盖）
INDEXTTS_VENV_PYTHON = os.environ.get(
    "INDEXTTS_VENV_PYTHON", r"D:/index-tts/.venv/Scripts/python.exe"
)
# 桥收编进 OpenMontage apps/indextts-bridge/
_OMO_ROOT = Path(__file__).resolve().parents[2]
INDEXTTS_SERVER = os.environ.get(
    "INDEXTTS_SERVER",
    str(_OMO_ROOT / "apps" / "indextts-bridge" / "indextts_server.py"),
)

# 情感向量：与 auto-dub 一致（8 维 emo_vector）
# 平静=[0,0,0,0,0,0,0,1]；激昂/兴奋=[1,0,0,0,0,0,0,0]（用文字自动判断更稳）
EMO_EXCITED = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
EMO_CALM = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]


class IndexTTS2Bridge:
    """IndexTTS2 常驻服务桥。一次初始化，多次合成。"""

    def __init__(self, project_dir: Path, voice_ref: Optional[Path] = None,
                 emotion: str = "calm", model_version: str = "2.5",
                 lang: str = "ZH", use_qwen_emo: bool = False):
        self.project_dir = project_dir
        self.voice_ref = voice_ref
        self.model_version = model_version
        self.lang = lang
        self.use_qwen_emo = use_qwen_emo
        self.emotion = emotion
        self._proc = None
        self._gpu_lock = None
        self._lock = threading.Lock()
        self._stderr_log = None

    # ------------------------------------------------------------------
    # 服务生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动常驻服务（获取 GPU 锁 + 拉起进程）。"""
        from lib.gpu_lock import GpuLockHandle
        self._gpu_lock = GpuLockHandle("indextts", timeout=1800, heartbeat=15)
        self._gpu_lock.acquire()
        try:
            self._stderr_log = open(
                self.project_dir / "indextts_server.log", "w",
                encoding="utf-8", errors="replace",
            )
            cmd = [INDEXTTS_VENV_PYTHON, INDEXTTS_SERVER, "--version", self.model_version]
            if self.use_qwen_emo:
                cmd.append("--use-qwen-emo")
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr_log,
                text=True, encoding="utf-8", errors="replace",
            )
        except Exception:
            self._gpu_lock.release()
            self._gpu_lock = None
            raise

    def stop(self):
        """停止服务并释放 GPU 锁（幂等）。"""
        if self._proc is not None:
            try:
                self._proc.stdin.write('{"cmd": "exit"}\n')
                self._proc.stdin.flush()
                self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        if self._gpu_lock is not None:
            try:
                self._gpu_lock.release()
            except Exception:
                pass
            self._gpu_lock = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # ------------------------------------------------------------------
    # 合成
    # ------------------------------------------------------------------

    def synthesize(self, text: str, output_path: Path, seed: int = 42,
                   target_duration: Optional[float] = None) -> bool:
        """合成单段音频。voice_ref 存在则克隆用户音色。"""
        if self._proc is None:
            self.start()
        req = {
            "id": str(hash((text, str(output_path)))),
            "text": text,
            "output_path": str(output_path),
            "seed": seed,
        }
        # 2.5 版本：透传 lang 与 duration_factor；2 版本桥忽略未知字段
        if self.model_version == "2.5":
            req["lang"] = self.lang
            if target_duration:
                req["duration_factor"] = float(target_duration)
        # 情感控制（与 auto-dub 一致）
        if self.emotion == "calm":
            req["use_emo_text"] = False
            req["emo_vector"] = EMO_CALM
        elif self.emotion == "excited":
            req["use_emo_text"] = False
            req["emo_vector"] = EMO_EXCITED
        # 音色克隆（用户声音）
        if self.voice_ref is not None:
            req["voice_ref"] = str(self.voice_ref)
        try:
            with self._lock:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
                resp_line = self._proc.stdout.readline()
            if not resp_line:
                logger.error("IndexTTS2 服务无响应")
                return False
            resp = json.loads(resp_line)
            ok = bool(resp.get("ok"))
            if not ok:
                logger.error("IndexTTS2 合成失败: %s", resp.get("error"))
            return ok
        except Exception as e:
            logger.error("IndexTTS2 服务异常: %s", e)
            return False
