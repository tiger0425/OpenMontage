"""MiniMax text-to-speech provider via native API (https://api.minimaxi.com).

Uses the non-streaming t2a_v2 endpoint with hex-encoded audio output.
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


class MiniMaxTTS(BaseTool):
    name = "minimax_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "minimax"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []  # checked dynamically via env var
    install_instructions = (
        "Set MINIMAX_API_KEY to your MiniMax API key.\n"
        "  Get one from https://platform.minimaxi.com/user-center/basic-information/interface-key\n"
        "  (Token Plan key; create in User Center → Interface Keys)"
    )
    agent_skills = ["text-to-speech"]
    fallback_tools = ["elevenlabs_tts", "openai_tts", "google_tts", "piper_tts"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "emotion_control",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "emotion": True,
    }
    best_for = [
        "Mandarin Chinese TTS with emotional control",
        "multilingual voice synthesis (Chinese, English, Japanese, Korean)",
        "cost-effective high-quality speech generation",
    ]
    not_good_for = [
        "voice cloning",
        "fully offline production",
        "streaming real-time TTS",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to convert to speech",
            },
            "model_id": {
                "type": "string",
                "default": "speech-2.8-hd",
                "description": "MiniMax TTS model (e.g. speech-2.8-hd, speech-02-hd, speech-02-turbo)",
            },
            "voice_id": {
                "type": "string",
                "default": "male-qn-qingse",
                "description": (
                    "MiniMax voice ID. Examples: male-qn-qingse (calm male), "
                    "female-shaonv (young female), male-qn-jingying (business male), "
                    "presenter_male, presenter_female, audiobook_male_1, audiobook_female_1"
                ),
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.5,
                "maximum": 2.0,
                "description": "Speech speed multiplier (0.5 = slow, 1.0 = normal, 2.0 = fast)",
            },
            "vol": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.1,
                "maximum": 10.0,
                "description": "Volume multiplier (1.0 = normal)",
            },
            "pitch": {
                "type": "integer",
                "default": 0,
                "minimum": -12,
                "maximum": 12,
                "description": "Pitch adjustment in semitones (-12 to 12)",
            },
            "emotion": {
                "type": "string",
                "description": (
                    "Emotional tone. Examples: happy, sad, angry, fearful, "
                    "disgusted, surprised, neutral, calm, empathetic, serious"
                ),
            },
            "output_format": {
                "type": "string",
                "default": "hex",
                "enum": ["hex", "url"],
                "description": "Audio output format. 'hex' returns hex-encoded audio, 'url' returns a download URL.",
            },
            "sample_rate": {
                "type": "integer",
                "default": 32000,
                "description": "Audio sample rate in Hz (default: 32000)",
            },
            "bitrate": {
                "type": "integer",
                "default": 128000,
                "description": "Audio bitrate in bps (default: 128000)",
            },
            "format": {
                "type": "string",
                "default": "mp3",
                "enum": ["mp3", "wav", "pcm", "flac"],
                "description": "Audio container format",
            },
            "subtitle_enable": {
                "type": "boolean",
                "default": False,
                "description": "Enable subtitle/timestamp generation in response",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["rate_limit", "timeout"]
    )
    idempotency_key_fields = ["text", "voice_id", "model_id", "speed", "pitch", "emotion"]
    side_effects = ["writes audio file to output_path", "calls MiniMax API"]
    user_visible_verification = [
        "Listen to generated audio for natural speech quality",
        "Verify emotional tone matches requested emotion",
    ]

    # ---- Key management ----

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    # ---- Cost estimation ----

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        text = inputs.get("text", "")
        # MiniMax speech-2.8-hd: ~$0.0003 per character (approximate)
        return round(len(text) * 0.0003, 4)

    # ---- Execution ----

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error=(
                    "MINIMAX_API_KEY environment variable not set. "
                    + self.install_instructions
                ),
            )

        start = time.time()
        try:
            result = self._generate(inputs, api_key)
        except Exception as exc:
            return ToolResult(success=False, error=f"MiniMax TTS failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any], api_key: str) -> ToolResult:
        import requests

        text = inputs["text"]
        model_id = inputs.get("model_id", "speech-2.8-hd")
        voice_id = inputs.get("voice_id", "male-qn-qingse")
        output_format = inputs.get("output_format", "hex")

        # Build voice_setting
        voice_setting: dict[str, Any] = {"voice_id": voice_id}
        if "speed" in inputs:
            voice_setting["speed"] = float(inputs["speed"])
        if "vol" in inputs:
            voice_setting["vol"] = float(inputs["vol"])
        if "pitch" in inputs:
            voice_setting["pitch"] = int(inputs["pitch"])
        if inputs.get("emotion"):
            voice_setting["emotion"] = inputs["emotion"]

        # Build audio_setting
        audio_setting: dict[str, Any] = {}
        if "sample_rate" in inputs:
            audio_setting["sample_rate"] = int(inputs["sample_rate"])
        if "bitrate" in inputs:
            audio_setting["bitrate"] = int(inputs["bitrate"])
        if "format" in inputs:
            audio_setting["format"] = inputs["format"]

        # Build payload
        payload: dict[str, Any] = {
            "model": model_id,
            "text": text,
            "stream": False,
            "voice_setting": voice_setting,
            "output_format": output_format,
        }
        if audio_setting:
            payload["audio_setting"] = audio_setting
        if inputs.get("subtitle_enable", False):
            payload["subtitle_enable"] = True

        response = requests.post(
            "https://api.minimaxi.com/v1/t2a_v2",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()

        # Check API-level error
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            return ToolResult(
                success=False,
                error=f"MiniMax API error: {base_resp.get('status_msg', 'unknown')}",
            )

        # Extract audio data
        audio_data = data.get("data", {})
        if output_format == "hex":
            hex_audio = audio_data.get("audio", "")
            if not hex_audio:
                return ToolResult(
                    success=False,
                    error="MiniMax returned empty hex audio",
                )
            audio_bytes = bytes.fromhex(hex_audio)
        else:
            # URL format — download the audio
            audio_url = audio_data.get("audio", "")
            if not audio_url:
                return ToolResult(
                    success=False,
                    error="MiniMax returned no audio URL",
                )
            audio_response = requests.get(audio_url, timeout=120)
            audio_response.raise_for_status()
            audio_bytes = audio_response.content

        # Write to output_path
        fmt = inputs.get("format", "mp3")
        output_path = Path(inputs.get("output_path", f"minimax_tts.{fmt}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        # Collect extra info
        extra_info = audio_data.get("extra_info", {})
        trace_id = data.get("trace_id", "")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model_id,
                "voice_id": voice_id,
                "text_length": len(text),
                "output": str(output_path),
                "format": fmt,
                "output_format": output_format,
                "audio_size_bytes": len(audio_bytes),
                "trace_id": trace_id,
                "word_count": extra_info.get("word_count"),
                "audio_length": extra_info.get("audio_length"),
                "audio_sample_rate": extra_info.get("audio_sample_rate"),
            },
            artifacts=[str(output_path)],
            model=model_id,
        )
