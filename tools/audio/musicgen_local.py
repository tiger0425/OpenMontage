"""Local Meta MusicGen generation tool using RTX 3090 / CUDA.

Runs Meta MusicGen locally without any external API keys or cloud costs.
Automatically selects between 'large' (3.3B) and 'small' (300M) based on local cache availability.
"""

from __future__ import annotations

import os
import time
import subprocess
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class MusicgenLocal(BaseTool):
    name = "musicgen_local"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "music_generation"
    provider = "meta"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["torch", "transformers", "scipy"]
    install_instructions = (
        "Install PyTorch with CUDA and HuggingFace Transformers:\n"
        "  pip install torch transformers scipy\n"
        "Model weights are cached in ~/.cache/huggingface/hub/models--facebook--musicgen-*"
    )

    agent_skills = ["music"]

    capabilities = [
        "generate_background_music",
        "generate_instrumental",
        "generate_lofi",
    ]
    supports = {
        "instrumental": True,
        "offline": True,
        "zero_cost": True,
        "bpm_control": True,
        "model_scale": True,
    }
    best_for = [
        "lofi hip hop and chillhop background music",
        "offline zero-cost high-fidelity music generation",
        "warm rhodes piano and acoustic drum loops",
    ]
    not_good_for = [
        "vocal songs with explicit singing lyrics (use Suno or YuE)",
        "running without an NVIDIA GPU (requires >= 4GB VRAM)",
    ]

    fallback_tools = ["freesound_music", "pixabay_music", "minimax_music"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Music description (e.g. 'lofi hip hop, chillhop, 75 bpm, warm rhodes piano, vinyl crackle')",
            },
            "duration_seconds": {
                "type": "integer",
                "default": 30,
                "minimum": 5,
                "maximum": 120,
                "description": "Target duration in seconds (5 to 120).",
            },
            "model_size": {
                "type": "string",
                "enum": ["auto", "small", "large"],
                "default": "auto",
                "description": "Model scale. 'auto' prefers large if fully cached, else small.",
            },
            "guidance_scale": {
                "type": "number",
                "default": 3.0,
                "description": "Classifier-free guidance scale (higher = adheres closer to prompt).",
            },
            "output_path": {
                "type": "string",
                "description": "Path to save output audio file (.wav or .mp3).",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=4096, vram_mb=8192, disk_mb=8000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1)
    idempotency_key_fields = ["prompt", "duration_seconds", "model_size"]
    side_effects = ["writes audio file to output_path", "consumes local GPU VRAM"]
    user_visible_verification = [
        "Verify generated audio playback",
        "Check musical tempo and instrument quality",
    ]

    def get_status(self) -> ToolStatus:
        try:
            import torch
            if not torch.cuda.is_available():
                return ToolStatus.DEGRADED  # Can run on CPU but very slow
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # 100% local, zero API cost

    def _resolve_model_id(self, requested_size: str) -> str:
        repo_root = Path(__file__).resolve().parent.parent.parent
        project_models = repo_root / "models" / "musicgen"
        proj_large = project_models / "large"
        proj_small = project_models / "small"

        large_ready = False
        if proj_large.exists():
            bin_files = list(proj_large.glob("pytorch_model*.bin"))
            config_file = proj_large / "config.json"
            preproc_file = proj_large / "preprocessor_config.json"
            if len(bin_files) >= 2 and config_file.exists() and preproc_file.exists():
                large_ready = True

        small_ready = False
        if proj_small.exists() and (proj_small / "model.safetensors").exists():
            small_ready = True

        if requested_size == "large":
            if large_ready:
                return str(proj_large)
            raise RuntimeError("musicgen-large is still preparing in models/musicgen/large.")
        elif requested_size == "small":
            if small_ready:
                return str(proj_small)
            return "facebook/musicgen-small"
        else:  # auto
            if large_ready:
                return str(proj_large)
            elif small_ready:
                return str(proj_small)
            return "facebook/musicgen-small"

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import torch
        import scipy.io.wavfile
        from transformers import AutoProcessor, MusicgenProcessor, MusicgenForConditionalGeneration

        start = time.time()
        prompt = inputs["prompt"]
        duration = int(inputs.get("duration_seconds", 30))
        model_size_req = inputs.get("model_size", "auto")
        guidance_scale = float(inputs.get("guidance_scale", 3.0))

        try:
            model_id = self._resolve_model_id(model_size_req)
            device = "cuda" if torch.cuda.is_available() else "cpu"

            try:
                processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
            except Exception:
                processor = MusicgenProcessor.from_pretrained(model_id, local_files_only=True)

            model = MusicgenForConditionalGeneration.from_pretrained(model_id, torch_dtype=torch.float16, local_files_only=True).to(device)

            model_inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)

            # 50 tokens = 1 second of audio
            max_new_tokens = int(50 * duration)
            with torch.no_grad():
                audio_values = model.generate(
                    **model_inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    guidance_scale=guidance_scale,
                )

            sampling_rate = model.config.audio_encoder.sampling_rate
            audio_data = audio_values[0, 0].cpu().float().numpy()

            # Output path handling
            out_path_str = inputs.get("output_path")
            if not out_path_str:
                out_dir = Path("projects/lofi-tiger-pilot/assets/audio")
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"musicgen_{int(time.time())}.mp3"
            else:
                out_path = Path(out_path_str)
                out_path.parent.mkdir(parents=True, exist_ok=True)

            # Save temporary wav
            temp_wav = out_path.with_suffix(".wav")
            scipy.io.wavfile.write(temp_wav, rate=sampling_rate, data=audio_data)

            # Convert to final target format via FFmpeg if needed
            if out_path.suffix.lower() == ".mp3":
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(temp_wav), "-c:a", "libmp3lame", "-b:a", "320k", str(out_path)],
                    capture_output=True,
                    check=True
                )
                if temp_wav != out_path and temp_wav.exists():
                    temp_wav.unlink()
            elif out_path.suffix.lower() == ".m4a":
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(temp_wav), "-c:a", "aac", "-b:a", "320k", str(out_path)],
                    capture_output=True,
                    check=True
                )
                if temp_wav != out_path and temp_wav.exists():
                    temp_wav.unlink()
            else:
                if temp_wav != out_path:
                    temp_wav.rename(out_path)

            elapsed = round(time.time() - start, 2)
            return ToolResult(
                success=True,
                data={
                    "tool": self.name,
                    "provider": self.provider,
                    "model_used": model_id,
                    "prompt": prompt,
                    "duration_seconds": duration,
                    "output": str(out_path),
                    "device": device,
                    "elapsed_seconds": elapsed,
                    "sampling_rate": sampling_rate,
                },
                artifacts=[str(out_path)],
                cost_usd=0.0,
                duration_seconds=elapsed,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Local MusicGen generation failed: {e}",
                duration_seconds=round(time.time() - start, 2),
            )
