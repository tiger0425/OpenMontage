"""IndexTTS2 local GPU text-to-speech provider tool.

Bridges to the IndexTTS-2 repo's own Python venv via the resident server
script (<repo>/indextts_server.py): the model loads once in a subprocess
and each synthesize call is one JSON request line on stdin / response
line on stdout.  This keeps the GPU model inside its compatible Python
env (the repo venv) instead of forcing it into the OpenMontage process.

Supports zero-shot voice cloning (spk_audio_prompt -> voice_ref), 8-dim
emotion control (emo_vector), seed reproducibility, and automatic RMS
normalization (server-side).  GPU usage is protected by the shared GPU
lock (lib.gpu_lock) for the whole server lifetime.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    DependencyError,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

from lib.gpu_lock import GpuLockHandle

_DEFAULT_REPO_CANDIDATES = [Path("D:/index-tts"), Path("C:/Users/tiger/index-tts")]

CALM_EMO_VECTOR = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

_SERVER_START_TIMEOUT_SECONDS = 600.0
_SERVER_READY_MARKER = ">> model ready"


def resolve_emotion_mode(
    emo_vector: list[float] | None,
    use_emo_text: bool | None,
    emo_alpha: float,
) -> dict[str, Any]:
    """三态情感判定规则（与 D:/index-tts/indextts_server.py 的实现保持一致，改动需两边同步）。

    1) use_emo_text=True  -> auto：自动从文字判情感，覆盖 emo_vector
    2) use_emo_text=False -> fixed：固定 emo_vector，未传则 calm
    3) 未指定            -> 传了 emo_vector 则 fixed；未传则 auto
    返回 {"mode", "emo_vector", "emo_alpha"}；fixed 模式下 emo_alpha 恒为 1.0
    （服务端此时不传 emo_alpha，infer_v2 默认 1.0，避免缩放显式向量）。
    """
    if use_emo_text is True:
        return {"mode": "auto", "emo_vector": None, "emo_alpha": emo_alpha}
    if use_emo_text is False:
        vec = emo_vector if emo_vector is not None else CALM_EMO_VECTOR
        return {"mode": "fixed", "emo_vector": vec, "emo_alpha": 1.0}
    if emo_vector is not None:
        return {"mode": "fixed", "emo_vector": emo_vector, "emo_alpha": 1.0}
    return {"mode": "auto", "emo_vector": None, "emo_alpha": emo_alpha}

_SERVER_PROC: subprocess.Popen | None = None
_SERVER_LOCK = threading.Lock()
_GPU_HANDLE: GpuLockHandle | None = None
_SERVER_LAST_ERROR: str | None = None


def _repo_root() -> Path:
    root = os.environ.get("INDEXTTS_REPO")
    if root:
        return Path(root)
    for candidate in _DEFAULT_REPO_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent.parent / "vendor" / "IndexTTS-2"


def _venv_python(repo: Path) -> Path | None:
    windows = repo / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return windows
    posix = repo / ".venv" / "bin" / "python"
    if posix.is_file():
        return posix
    return None


def _server_script(repo: Path) -> Path:
    """优先用收编进 OpenMontage 的桥（apps/indextts-bridge/），回退 repo 根。"""
    omo_server = Path(__file__).resolve().parents[1] / "apps" / "indextts-bridge" / "indextts_server.py"
    if omo_server.is_file():
        return omo_server
    return repo / "indextts_server.py"


def _start_server() -> subprocess.Popen:
    global _SERVER_PROC, _GPU_HANDLE, _SERVER_LAST_ERROR
    repo = _repo_root()
    venv_py = _venv_python(repo)
    server = _server_script(repo)
    if venv_py is None:
        raise RuntimeError(
            f"IndexTTS-2 venv python not found under {repo}/.venv. "
            "Run 'uv sync --all-extras' inside the repo first."
        )
    if not server.is_file():
        raise RuntimeError(
            f"IndexTTS-2 bridge script not found: {server}. "
            "The resident server script (indextts_server.py) must live in the repo root."
        )

    handle = GpuLockHandle("indextts", timeout=1800, heartbeat=15)
    handle.acquire()
    try:
        # 模型版本：2.5（默认）/ 2（回退），env INDEXTTS_MODEL_VERSION 可覆盖
        version = os.environ.get("INDEXTTS_MODEL_VERSION", "2.5")
        cmd = [str(venv_py), str(server), "--version", version]
        # 权重目录：env / config / D:/index-tts 默认（桥在 apps/indextts-bridge/ 下，不能靠脚本同级推断）
        ckpts = os.environ.get("INDEXTTS_CHECKPOINTS", r"D:/index-tts/checkpoints")
        if version == "2":
            ckpts = os.environ.get("INDEXTTS_CHECKPOINTS_2", r"D:/index-tts/checkpoints_2")
        cmd += ["--checkpoints", ckpts]
        if os.environ.get("INDEXTTS_USE_QWEN_EMO") == "1":
            cmd.append("--use-qwen-emo")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        handle.release()
        raise

    ready = threading.Event()
    errors: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                print(f"[IndexTTS2] {line}", flush=True)
            if _SERVER_READY_MARKER in line:
                ready.set()
            if ">> ERROR" in line:
                errors.append(line)

    threading.Thread(target=_drain_stderr, daemon=True).start()

    if not ready.wait(timeout=_SERVER_START_TIMEOUT_SECONDS):
        if proc.poll() is not None:
            handle.release()
            raise RuntimeError(
                "IndexTTS2 server exited during startup. "
                f"Last stderr: {errors[-1] if errors else 'no output'}"
            )
        proc.terminate()
        handle.release()
        raise TimeoutError(
            f"IndexTTS2 server did not become ready within {_SERVER_START_TIMEOUT_SECONDS:.0f}s"
        )

    _SERVER_PROC = proc
    _GPU_HANDLE = handle
    _SERVER_LAST_ERROR = None
    return proc


def _stop_server() -> None:
    global _SERVER_PROC, _GPU_HANDLE
    proc = _SERVER_PROC
    handle = _GPU_HANDLE
    _SERVER_PROC = None
    _GPU_HANDLE = None
    if proc is not None and proc.poll() is None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps({"cmd": "exit"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=30)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    if handle is not None:
        handle.release()


atexit.register(_stop_server)


def _synthesize_via_server(
    text: str,
    output_path: str,
    voice_ref: str | None,
    seed: int,
    emo_vector: list[float] | None,
    use_emo_text: bool | None,
    emo_alpha: float,
    duration_factor: float | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    global _SERVER_PROC, _SERVER_LAST_ERROR
    with _SERVER_LOCK:
        if _SERVER_PROC is None or _SERVER_PROC.poll() is not None:
            _SERVER_PROC = _start_server()
        proc = _SERVER_PROC

    assert proc is not None and proc.stdin is not None and proc.stdout is not None

    rid = uuid.uuid4().hex[:8]
    req = {
        "id": rid,
        "text": text,
        "output_path": output_path,
        "voice_ref": voice_ref,
        "seed": seed,
        "emo_vector": emo_vector,
        "use_emo_text": use_emo_text,
        "emo_alpha": emo_alpha,
    }
    # 2.5 版本透传 lang / duration_factor（桥端 2 版本忽略未知字段）
    if os.environ.get("INDEXTTS_MODEL_VERSION", "2.5") == "2.5":
        req["lang"] = lang or os.environ.get("INDEXTTS_LANG", "ZH")
        if duration_factor:
            req["duration_factor"] = float(duration_factor)
    try:
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("IndexTTS2 server closed stdout unexpectedly (crashed?)")
        resp = json.loads(line)
    except Exception as exc:
        with _SERVER_LOCK:
            if _SERVER_PROC is not None and _SERVER_PROC.poll() is not None:
                _SERVER_PROC = _start_server()
                proc = _SERVER_PROC
                assert proc is not None and proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError(
                        "IndexTTS2 server closed stdout after restart"
                    ) from exc
                resp = json.loads(line)
            else:
                raise
    if not resp.get("ok"):
        _SERVER_LAST_ERROR = str(resp.get("error", "unknown error"))
        raise RuntimeError(f"IndexTTS2 synthesis failed: {_SERVER_LAST_ERROR}")
    return resp


class IndexTTS2TTS(BaseTool):
    name = "indextts_tts"
    version = "0.2.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "indextts"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = [
        "cmd:espeak-ng",
    ]
    install_instructions = (
        "IndexTTS2 local GPU TTS via the repo's resident server bridge:\n"
        "  1. Clone https://github.com/IndexTeam/IndexTTS-2 and run 'uv sync --all-extras'\n"
        "  2. Place checkpoints/ (config.yaml + weights) inside the repo\n"
        "  3. The bridge runs <repo>/indextts_server.py with the repo venv python "
        "(model loads once, JSON protocol on stdin/stdout)\n"
        "  4. Set INDEXTTS_REPO to the clone path "
        "(default candidates: D:/index-tts, C:/Users/tiger/index-tts)\n"
        "  5. espeak-ng must be on PATH (winget install espeak-ng)\n"
        "Requires a CUDA GPU (~8-12 GB VRAM in FP16)."
    )
    agent_skills: list[str] = ["indextts-tts"]

    capabilities = [
        "text_to_speech",
        "voice_cloning",
        "emotion_control",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": True,
        "voice_design": False,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline high-quality GPU TTS",
        "zero-shot voice cloning from a single reference clip",
        "emotion-controlled delivery (8-dim emo_vector)",
        "multilingual narration with cloned voice",
        "privacy-sensitive local-only voice generation",
        "English / Chinese audio production at zero marginal cost",
    ]
    not_good_for = [
        "environments without a CUDA GPU",
        "CPU-only inference (not practical)",
        "sub-second latency real-time streaming",
        "voice design from text description (IndexTTS2 has no voice-description API)",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to synthesize into speech.",
            },
            "output_path": {
                "type": "string",
                "description": "Path to write the generated WAV file.",
            },
            "spk_audio_prompt": {
                "type": "string",
                "description": (
                    "Path to a reference WAV for zero-shot voice cloning (required for "
                    "synthesis; IndexTTS2 has no default voice). A clean 5-30 second "
                    "clip of the target speaker is sufficient. Use the same file across "
                    "all segments for consistent timbre. Falls back to INDEXTTS_VOICE_REF "
                    "env var, then <repo>/voice_reference.wav."
                ),
            },
            "emo_vector": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 8,
                "maxItems": 8,
                "description": (
                    "8-dim emotion vector: "
                    "[happy, angry, sad, fearful, disgusted, surprised, neutral, calm]. "
                    "Values are typically in [0, 1] range. "
                    "THREE-STATE SEMANTICS: (1) OMIT (default) -> the server auto-detects "
                    "emotion from the text via use_emo_text (see use_emo_text field); "
                    "(2) PASS a vector -> fixed emotion, auto-detection OFF (e.g. calm "
                    "[0,0,0,0,0,0,0,1] for a documentary read); (3) PASS a vector AND "
                    "use_emo_text=True -> auto-detection wins and OVERRIDES the vector "
                    "(IndexTTS2 infer_v2 behavior)."
                ),
            },
            "use_emo_text": {
                "type": ["boolean", "null"],
                "default": None,
                "description": (
                    "Auto-detect emotion from the text with IndexTTS2's built-in Qwen "
                    "emotion classifier. Three-state: (1) null (default) -> auto-detect "
                    "IF AND ONLY IF emo_vector is omitted; (2) true -> always auto-detect, "
                    "overrides any emo_vector passed; (3) false -> never auto-detect, "
                    "falls back to emo_vector (or calm if none passed)."
                ),
            },
            "emo_alpha": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.6,
                "description": (
                    "Emotion strength applied when use_emo_text auto-detection is active. "
                    "0.0 = neutral read, 1.0 = fully match detected emotion, "
                    "0.6 is a good default for natural narration. Ignored when "
                    "auto-detection is off."
                ),
            },
            "use_fp16": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Server runs FP16 fixed; this flag is accepted for schema compatibility "
                    "and reported back."
                ),
            },
            "speed": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 2.0,
                "default": 1.0,
                "description": (
                    "Speaking speed multiplier applied after synthesis via resampling. "
                    "Keep at 1.0 for dubbing workflows (zero speed modification rule)."
                ),
            },
            "seed": {
                "type": "integer",
                "default": 42,
                "description": (
                    "Random seed for reproducibility. "
                    "Segments sharing the same seed and voice reference keep consistent timbre. "
                    "Set to -1 to skip seeding."
                ),
            },
            "max_text_tokens_per_segment": {
                "type": "integer",
                "default": 200,
                "description": (
                    "Accepted for schema compatibility; long text is handled server-side."
                ),
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=8192, vram_mb=12288, disk_mb=8000, network_required=False
    )
    idempotency_key_fields = [
        "text",
        "spk_audio_prompt",
        "emo_vector",
        "use_emo_text",
        "emo_alpha",
        "speed",
        "seed",
    ]
    side_effects = ["writes audio file to output_path"]
    fallback_tools = ["voxcpm_tts", "piper_tts", "google_tts"]
    user_visible_verification = [
        "Listen to generated audio for naturalness, clarity, and emotion accuracy",
        "Verify voice cloning fidelity against the reference speaker",
    ]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def check_dependencies(self) -> None:
        if shutil.which("espeak-ng") is None:
            raise DependencyError(
                "Command 'espeak-ng' not found. " + self.install_instructions
            )
        repo = _repo_root()
        if not repo.is_dir():
            raise DependencyError(
                f"IndexTTS-2 repo not found (INDEXTTS_REPO unset, tried {_DEFAULT_REPO_CANDIDATES}). "
                + self.install_instructions
            )
        if _venv_python(repo) is None:
            raise DependencyError(
                f"No venv python under {repo}/.venv. "
                "Run 'uv sync --all-extras' inside the IndexTTS-2 repo first."
            )
        if not _server_script(repo).is_file():
            raise DependencyError(
                f"Bridge script {_server_script(repo)} missing. "
                "The resident server script (indextts_server.py) must live in the repo root."
            )

    def get_status(self) -> ToolStatus:
        try:
            self.check_dependencies()
        except Exception:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    # ------------------------------------------------------------------
    # Cost

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # ------------------------------------------------------------------
    # Execute

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        status = self.get_status()
        if status != ToolStatus.AVAILABLE:
            if status == ToolStatus.UNAVAILABLE:
                return ToolResult(
                    success=False,
                    error="IndexTTS2 TTS not available. " + self.install_instructions,
                )
            return ToolResult(
                success=False,
                error=f"IndexTTS2 TTS status is {status.value}. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"IndexTTS2 TTS generation failed: {exc}",
            )

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # Generation

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        import numpy as np
        import scipy.io.wavfile as wavfile

        text: str = inputs["text"]
        output_path = Path(inputs.get("output_path", "indextts_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        spk_audio_prompt: str | None = inputs.get("spk_audio_prompt")
        emo_vector_raw = inputs.get("emo_vector")
        emo_vector: list[float] | None = (
            list(emo_vector_raw) if emo_vector_raw is not None else None
        )
        use_emo_text: bool | None = inputs.get("use_emo_text")
        if use_emo_text is not None:
            use_emo_text = bool(use_emo_text)
        emo_alpha: float = float(inputs.get("emo_alpha", 0.6))
        use_fp16: bool = bool(inputs.get("use_fp16", True))
        speed: float = float(inputs.get("speed", 1.0))
        seed: int = int(inputs.get("seed", 42))

        if emo_vector is not None and len(emo_vector) != 8:
            emo_vector = None

        emotion_mode = resolve_emotion_mode(emo_vector, use_emo_text, emo_alpha)

        voice_ref = spk_audio_prompt
        if not voice_ref:
            env_ref = os.environ.get("INDEXTTS_VOICE_REF")
            if env_ref and Path(env_ref).is_file():
                voice_ref = env_ref
            else:
                repo_ref = _repo_root() / "voice_reference.wav"
                if repo_ref.is_file():
                    voice_ref = str(repo_ref)
        if not voice_ref:
            raise RuntimeError(
                "IndexTTS2 requires a reference voice file to synthesize. "
                "Pass spk_audio_prompt (a clean 5-30s speech WAV), or set "
                "INDEXTTS_VOICE_REF, or drop a voice_reference.wav into the "
                "IndexTTS-2 repo root."
            )

        try:
            resp = _synthesize_via_server(
                text=text,
                output_path=str(output_path),
                voice_ref=voice_ref,
                seed=seed,
                emo_vector=emo_vector,
                use_emo_text=use_emo_text,
                emo_alpha=emo_alpha,
                duration_factor=inputs.get("duration_factor"),
                lang=inputs.get("lang"),
            )
        except Exception as exc:
            raise RuntimeError(
                f"IndexTTS2 synthesis failed (server restart handled internally): {exc}"
            ) from exc

        sample_rate = 24000
        if speed != 1.0:
            try:
                sr, data = wavfile.read(str(output_path))
                audio = np.asarray(data, dtype=np.float32)
                import scipy.signal
                new_length = int(len(audio) / speed)
                audio = np.asarray(
                    scipy.signal.resample(audio, new_length), dtype=np.float32
                )
                audio = np.clip(audio, -1.0, 1.0)
                out_i16 = (audio * 32767.0).astype(np.int16)
                wavfile.write(str(output_path), sr, out_i16)
                sample_rate = sr
            except Exception:
                pass

        version = os.environ.get("INDEXTTS_MODEL_VERSION", "2.5")
        model_label = f"indextts-{version}"
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model_label,
                "text_length": len(text),
                "output": str(output_path),
                "format": "wav",
                "sample_rate": sample_rate,
                "voice_cloning": bool(voice_ref),
                "voice_anchor_used": False,
                "emo_vector": emo_vector,
                "use_emo_text": use_emo_text,
                "emo_alpha": emo_alpha,
                "emotion_mode": emotion_mode["mode"],
                "effective_emo_vector": emotion_mode["emo_vector"],
                "effective_emo_alpha": emotion_mode["emo_alpha"],
                "use_fp16": use_fp16,
                "speed": speed,
                "seed": seed,
                "effective_spk_prompt": voice_ref,
                "bridge": "indextts_server.py",
                "model_version": version,
                "rms_normalized": True,
            },
            artifacts=[str(output_path)],
            model=model_label,
        )
