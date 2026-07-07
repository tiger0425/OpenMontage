"""VoxCPM local GPU text-to-speech provider tool.

Supports plain TTS, voice cloning (reference_wav_path), and voice design
(voice_description).  Requires a CUDA GPU and the ``voxcpm`` Python package.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# 模型单例缓存：避免每次调用重新加载 8GB 权重
# key: model_id (str) -> VoxCPM instance
_MODEL_CACHE: dict[str, Any] = {}

# 锚点音频缓存：key = (model_id, seed) -> Path
# VoxCPM2 是自回归扩散模型，不同文本长度消耗随机状态数不同，
# 仅靠 torch.manual_seed 无法保证多段一致。
# 解决方案：用固定短文本+固定seed生成一段"声音身份锚点"，
# 后续所有分段通过 reference_wav_path 声音克隆模式生成，
# 从而将说话人身份锁定到同一个参考音频上。
_VOICE_ANCHOR_CACHE: dict[tuple[str, int], Path] = {}

# 生成锚点时使用的固定短文本（足够短以加速，足够清晰以捕获音色）
_ANCHOR_TEXT = "你好，这是声音身份锚点。"

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class VoxCPMTTS(BaseTool):
    name = "voxcpm_tts"
    version = "0.2.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "voxcpm"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["python:voxcpm"]
    install_instructions = (
        "Install VoxCPM for local GPU TTS:\n"
        "  pip install voxcpm\n"
        "Requires a CUDA GPU and PyTorch with CUDA support.\n"
        "First-run will download the model from Hugging Face (~8 GB).\n"
        "Set VOXCPM_MODEL env var to override the default model (openbmb/VoxCPM2)."
    )
    agent_skills: list[str] = ["voxcpm-tts"]

    capabilities = [
        "text_to_speech",
        "voice_cloning",
        "voice_design",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": True,
        "voice_design": True,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline high-quality GPU TTS",
        "voice cloning from reference audio",
        "voice design via natural-language description",
        "privacy-sensitive local-only voice generation",
    ]
    not_good_for = [
        "environments without a CUDA GPU",
        "CPU-only inference (too slow, not designed for it)",
        "sub-second latency real-time streaming",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to synthesize into speech."},
            "output_path": {
                "type": "string",
                "description": "Path to write the generated WAV file (48 kHz).",
            },
            "reference_wav_path": {
                "type": "string",
                "description": (
                    "Path to a reference WAV for voice cloning. "
                    "When provided, voice identity is anchored to this audio — "
                    "use the same file across all segments to guarantee consistent timbre."
                ),
            },
            "voice_description": {
                "type": "string",
                "description": (
                    "Natural-language voice description for voice design "
                    "(e.g. '温暖成熟的男性配音员，语调沉稳'). "
                    "Ignored when reference_wav_path is supplied."
                ),
            },
            "cfg_value": {
                "type": "number",
                "default": 3.0,
                "description": "Classifier-free guidance scale.",
            },
            "inference_timesteps": {
                "type": "number",
                "default": 10,
                "description": (
                    "Number of inference diffusion steps. "
                    "Official default is 10; higher values improve quality at the cost of "
                    "speed (50 steps ≈ 5× slower)."
                ),
            },
            "seed": {
                "type": "integer",
                "default": 42,
                "description": (
                    "Random seed used when auto-generating the voice anchor. "
                    "All segments sharing the same seed (and no explicit reference_wav_path) "
                    "will be cloned from the same auto-generated anchor, ensuring consistent timbre. "
                    "Set to -1 to skip anchoring and use random voice each time."
                ),
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=4096, vram_mb=10240, disk_mb=2000, network_required=True
    )
    idempotency_key_fields = [
        "text",
        "reference_wav_path",
        "voice_description",
        "cfg_value",
        "inference_timesteps",
        "seed",
    ]
    side_effects = ["writes audio file to output_path"]
    fallback_tools = ["piper_tts"]
    user_visible_verification = ["Listen to generated audio for naturalness and clarity"]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> ToolStatus:
        """Available only when voxcpm is installed AND a CUDA GPU is present."""
        try:
            self.check_dependencies()
        except Exception:
            return ToolStatus.UNAVAILABLE
        try:
            import torch
            if not torch.cuda.is_available():
                return ToolStatus.UNAVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    # ------------------------------------------------------------------
    # Cost
    # ------------------------------------------------------------------

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        status = self.get_status()
        if status != ToolStatus.AVAILABLE:
            if status == ToolStatus.UNAVAILABLE:
                return ToolResult(
                    success=False,
                    error="VoxCPM TTS not available. Requires CUDA GPU and the voxcpm Python package. "
                    + self.install_instructions,
                )
            return ToolResult(
                success=False,
                error=f"VoxCPM TTS status is {status.value}. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"VoxCPM TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self, model_id: str) -> Any:
        """返回缓存的 VoxCPM 实例，首次调用时加载权重。"""
        if model_id not in _MODEL_CACHE:
            from voxcpm import VoxCPM
            _MODEL_CACHE[model_id] = VoxCPM.from_pretrained(model_id, load_denoiser=False)
        return _MODEL_CACHE[model_id]

    def _get_or_create_anchor(
        self, model: Any, model_id: str, seed: int,
        voice_description: str | None,
        cfg_value: float, inference_timesteps: int,
    ) -> tuple[Path, str]:
        """
        获取或生成"声音身份锁点"WAV。

        VoxCPM2 是自回归扩散模型，不同文本长度消耗随机状态不同，
        torch.manual_seed 无法跨段保证音色一致。
        解决方案：用固定短文本+固定seed生成一段锁点音频，
        并通过 Ultimate Cloning（prompt_wav_path + prompt_text + reference_wav_path）
        将说话人身份锁定到同一参考上。

        返回 (anchor_path, anchor_transcript)。
        """
        import hashlib
        import tempfile
        import torch
        import scipy.io.wavfile as wavfile

        # 锁点文本：包含 voice_description 前缀（初始化音色风格）
        anchor_transcript = _ANCHOR_TEXT
        if voice_description:
            anchor_text_gen = f"({voice_description}). {_ANCHOR_TEXT}"
        else:
            anchor_text_gen = _ANCHOR_TEXT

        desc_hash = hashlib.md5((voice_description or "").encode()).hexdigest()[:6]
        cache_key = (model_id, seed, desc_hash)
        if cache_key in _VOICE_ANCHOR_CACHE:
            return _VOICE_ANCHOR_CACHE[cache_key], anchor_transcript

        safe_model = hashlib.md5(model_id.encode()).hexdigest()[:8]
        anchor_dir = Path(tempfile.gettempdir()) / "voxcpm_anchors"
        anchor_dir.mkdir(parents=True, exist_ok=True)
        anchor_path = anchor_dir / f"anchor_{safe_model}_seed{seed}_desc{desc_hash}.wav"

        if not anchor_path.exists():
            print(f"[VoxCPM] Generating voice anchor (seed={seed})...")
            torch.manual_seed(seed)
            torch.cuda.manual_seed(seed)
            anchor_audio = model.generate(
                text=anchor_text_gen,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
            )
            wavfile.write(str(anchor_path), 48000, anchor_audio)
            print(f"[VoxCPM] Voice anchor saved: {anchor_path}")

        _VOICE_ANCHOR_CACHE[cache_key] = anchor_path
        return anchor_path, anchor_transcript

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        import scipy.io.wavfile as wavfile

        model_id = os.environ.get("VOXCPM_MODEL", "openbmb/VoxCPM2")
        model = self._load_model(model_id)

        text: str = inputs["text"]
        output_path = Path(inputs.get("output_path", "voxcpm_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        reference_wav_path: str | None = inputs.get("reference_wav_path")
        voice_description: str | None = inputs.get("voice_description")
        cfg_value: float = float(inputs.get("cfg_value", 3.0))
        inference_timesteps: int = int(inputs.get("inference_timesteps", 10))
        seed: int = int(inputs.get("seed", 42))

        # ------------------------------------------------------------------
        # 确定最终使用的 reference_wav_path（音色锚定优先级）
        # 1. 用户显式传入 reference_wav_path  → 直接使用（完全由用户控制）
        # 2. seed != -1                        → 自动生成/复用锚点音频，保证多段一致
        # 3. seed == -1                        → 纯随机（每段音色不同）
        # ------------------------------------------------------------------
        effective_reference: str | None = reference_wav_path
        anchor_used = False

        if not effective_reference and seed != -1:
            anchor_path, _ = self._get_or_create_anchor(
                model, model_id, seed, voice_description, cfg_value, inference_timesteps
            )
            effective_reference = str(anchor_path)
            anchor_used = True

        # voice_description 前缀：仅在无 reference 时才追加到 text
        if voice_description and not effective_reference:
            text = f"({voice_description}). {text}"

        # --- generate ---
        generate_kwargs: dict[str, Any] = {
            "text": text,
            "cfg_value": cfg_value,
            "inference_timesteps": inference_timesteps,
        }
        if effective_reference:
            generate_kwargs["reference_wav_path"] = effective_reference

        audio_array = model.generate(**generate_kwargs)

        # --- write 48 kHz WAV ---
        wavfile.write(str(output_path), 48000, audio_array)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model_id,
                "text_length": len(text),
                "output": str(output_path),
                "format": "wav",
                "sample_rate": 48000,
                "voice_cloning": bool(reference_wav_path),
                "voice_anchor_used": anchor_used,
                "voice_design": bool(voice_description and not effective_reference),
                "cfg_value": cfg_value,
                "inference_timesteps": inference_timesteps,
                "seed": seed,
                "effective_reference": effective_reference,
            },
            artifacts=[str(output_path)],
            model=model_id,
        )
