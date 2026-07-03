"""VoxCPM local GPU text-to-speech provider tool.

Supports plain TTS, voice cloning (reference_wav_path), and voice design
(voice_description).  Requires a CUDA GPU and the ``voxcpm`` Python package.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

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
    version = "0.1.0"
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
    agent_skills: list[str] = []

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
                "description": "Path to a reference WAV for voice cloning.",
            },
            "voice_description": {
                "type": "string",
                "description": "Natural-language voice description for voice design (e.g. 'A warm middle-aged male narrator').",
            },
            "cfg_value": {
                "type": "number",
                "default": 3.0,
                "description": "Classifier-free guidance scale.",
            },
            "inference_timesteps": {
                "type": "number",
                "default": 50,
                "description": "Number of inference diffusion steps.",
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
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        # --- lazy imports (no weight loading at module level) ---
        from voxcpm import VoxCPM

        model_id = os.environ.get("VOXCPM_MODEL", "openbmb/VoxCPM2")
        model = VoxCPM.from_pretrained(model_id, load_denoiser=False)

        text: str = inputs["text"]
        output_path = Path(inputs.get("output_path", "voxcpm_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        reference_wav_path = inputs.get("reference_wav_path")
        voice_description = inputs.get("voice_description")
        cfg_value = inputs.get("cfg_value", 3.0)
        inference_timesteps = inputs.get("inference_timesteps", 50)

        # --- voice design: prefix text with parenthesised description ---
        if voice_description and not reference_wav_path:
            text = f"({voice_description}). {text}"

        # --- generate ---
        generate_kwargs: dict[str, Any] = {
            "text": text,
            "cfg_value": cfg_value,
            "inference_timesteps": inference_timesteps,
        }
        if reference_wav_path:
            generate_kwargs["reference_wav_path"] = reference_wav_path

        audio_array = model.generate(**generate_kwargs)

        # --- write 48 kHz WAV via scipy ---
        import scipy.io.wavfile as wavfile
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
                "voice_design": bool(voice_description and not reference_wav_path),
                "cfg_value": cfg_value,
                "inference_timesteps": inference_timesteps,
            },
            artifacts=[str(output_path)],
            model=model_id,
        )
