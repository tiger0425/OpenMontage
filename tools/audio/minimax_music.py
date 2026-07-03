"""MiniMax music generation via REST API.

Generates instrumental background music and songs with lyrics.
Sync HTTP call internally, but marked ASYNC per project convention
for generation tools that take multiple seconds.
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
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

# MiniMax fixed duration slots (in seconds)
_DURATION_SLOTS = (30, 60, 120)


def _snap_duration(seconds: float) -> int:
    """Map user-requested duration to nearest MiniMax fixed slot."""
    return min(_DURATION_SLOTS, key=lambda s: abs(s - seconds))


class MiniMaxMusic(BaseTool):
    name = "minimax_music"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "music_generation"
    provider = "minimax"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.ASYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []  # checked dynamically via env var
    install_instructions = (
        "Set the MINIMAX_API_KEY environment variable:\n"
        "  export MINIMAX_API_KEY=your_key_here\n"
        "Get a key at https://platform.minimaxi.com"
    )

    agent_skills = ["music"]

    capabilities = [
        "generate_background_music",
        "generate_song",
        "generate_instrumental",
    ]
    supports = {
        "instrumental": True,
        "vocals": True,
        "custom_lyrics": True,
        "style_control": True,
    }
    best_for = [
        "fast instrumental background music generation",
        "cost-effective music generation",
        "short to medium duration tracks (30s-120s)",
    ]
    not_good_for = [
        "sound effects (use ElevenLabs SFX instead)",
        "long-form tracks beyond 120 seconds",
        "music covers (not supported)",
        "offline generation",
    ]

    fallback_tools = ["suno_music", "music_gen", "freesound_music", "pixabay_music"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Music description (mood, genre, instruments, tempo). For songs with lyrics, include the lyrics in the prompt.",
            },
            "is_instrumental": {
                "type": "boolean",
                "default": True,
                "description": "True for instrumental music only (no vocals), False to include vocals/lyrics.",
            },
            "duration_seconds": {
                "type": "integer",
                "enum": [30, 60, 120],
                "default": 60,
                "description": "Target duration in seconds. MiniMax supports 30, 60, or 120 seconds.",
            },
            "model": {
                "type": "string",
                "default": "music-2.6",
                "description": "MiniMax music model version.",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "is_instrumental", "duration_seconds", "model"]
    side_effects = ["writes audio file to output_path", "calls MiniMax API"]
    user_visible_verification = [
        "Listen to generated music for mood, genre accuracy, and quality",
    ]

    _API_URL = "https://api.minimaxi.com/v1/music_generation"

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # MiniMax music pricing: roughly $0.01 per generation
        return 0.01

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="No MiniMax API key. " + self.install_instructions,
            )

        if "prompt" not in inputs:
            return ToolResult(
                success=False,
                error=(
                    "minimax_music: 'prompt' is required. "
                    "Provide a music description (e.g., 'ambient piano, calm background music') "
                    "or song lyrics if is_instrumental=False."
                ),
            )

        start = time.time()

        try:
            result = self._generate(inputs, api_key)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"MiniMax music generation failed: {e}",
            )

        duration = round(time.time() - start, 2)

        return ToolResult(
            success=True,
            data={
                "provider": "minimax",
                "model": inputs.get("model", "music-2.6"),
                "prompt": inputs["prompt"],
                "is_instrumental": inputs.get("is_instrumental", True),
                "duration_seconds": result["snapped_duration"],
                "requested_duration": inputs.get("duration_seconds"),
                "output": result["output_path"],
                "format": "mp3",
            },
            artifacts=[result["output_path"]],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=duration,
            model=f"minimax/{inputs.get('model', 'music-2.6')}",
        )

    def _generate(self, inputs: dict[str, Any], api_key: str) -> dict[str, Any]:
        """Call MiniMax API and write decoded audio to output_path.

        Returns dict with output_path and snapped_duration.
        """
        import requests

        prompt: str = inputs["prompt"]
        is_instrumental: bool = inputs.get("is_instrumental", True)
        model: str = inputs.get("model", "music-2.6")

        # Snap duration to nearest fixed slot
        requested_duration: int = inputs.get("duration_seconds", 60)
        snapped_duration = _snap_duration(requested_duration)

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "is_instrumental": is_instrumental,
            "duration_seconds": snapped_duration,
        }

        response = requests.post(
            self._API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        # MiniMax returns audio as hex-encoded string
        hex_audio = data.get("data", {}).get("audio") or data.get("audio")
        if not hex_audio:
            raise RuntimeError(
                f"MiniMax returned no audio data. Response: {data}"
            )

        # Decode hex to binary
        audio_bytes = bytes.fromhex(hex_audio)

        output_path = Path(inputs.get("output_path", "minimax_output.mp3"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        return {
            "output_path": str(output_path),
            "snapped_duration": snapped_duration,
        }
