#!/usr/bin/env python3
"""QA Test 10: VoxCPM TTS — plain TTS, voice cloning, and voice design.

Verifies that VoxCPMTTS generates valid 48 kHz WAV output for all three scenarios.
When VoxCPM is unavailable (no CUDA GPU or voxcpm package not installed), the
script prints a skip message and exits 0 cleanly.
"""

import json
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.env_loader import load_env

load_env()

from tools.audio.voxcpm_tts import VoxCPMTTS
from tools.base_tool import ToolStatus

OUT = os.path.join(os.path.dirname(__file__), "output")

# ---------------------------------------------------------------------------
# Status gate — skip cleanly when VoxCPM is not available
# ---------------------------------------------------------------------------

tool = VoxCPMTTS()
status = tool.get_status()
print(f"VoxCPMTTS status: {status.value}")

if status != ToolStatus.AVAILABLE:
    # Diagnose the specific reason for the skip message
    reasons: list[str] = []
    try:
        import voxcpm  # noqa: F401
    except ImportError:
        reasons.append("voxcpm package not installed")
    try:
        import torch  # noqa: F401
        if not torch.cuda.is_available():
            reasons.append("CUDA GPU not available")
    except ImportError:
        reasons.append("torch not installed (required for CUDA support)")
    if not reasons:
        reasons.append("unknown — check tool dependencies")
    print(f"SKIP: VoxCPM TTS not available -- {', '.join(reasons)}.")
    sys.exit(0)

print("VoxCPM TTS is available — running integration tests.\n")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper: generate a short 48 kHz mono reference WAV for voice cloning
# ---------------------------------------------------------------------------

REFERENCE_WAV = os.path.join(OUT, "voxcpm_reference.wav")


def _generate_sine_wav(
    path: str,
    frequency: float = 440.0,
    duration_seconds: float = 3.0,
    sample_rate: int = 48000,
) -> None:
    """Write a short 16-bit mono sine-wave WAV file using the stdlib wave module."""
    num_samples = int(sample_rate * duration_seconds)
    max_amplitude = 32767 * 0.5  # half-scale to avoid clipping

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            sample = int(max_amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            wf.writeframes(struct.pack("<h", sample))


_generate_sine_wav(REFERENCE_WAV, duration_seconds=3.0)
print(f"Generated reference WAV for voice cloning: {REFERENCE_WAV}\n")

# ---------------------------------------------------------------------------
# Helper: ffprobe a WAV file and return parsed stream info
# ---------------------------------------------------------------------------


def probe_wav(path: str) -> dict[str, str]:
    """Run ffprobe on a WAV file and return the first audio stream dict."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True,
        text=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    if not streams:
        raise RuntimeError(f"No streams found in {path}")
    return streams[0]


def print_probe_info(label: str, path: str) -> None:
    """Print probe details for a WAV file."""
    s = probe_wav(path)
    print(
        f"[{label}]  duration={s.get('duration', '?')}s  "
        f"sample_rate={s.get('sample_rate', '?')}Hz  "
        f"channels={s.get('channels', '?')}  "
        f"codec={s.get('codec_name', '?')}  "
        f"size={os.path.getsize(path)} bytes"
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Plain TTS
# ---------------------------------------------------------------------------

print("--- Scenario 1: Plain TTS ---")
r1 = tool.execute({
    "text": "Hello, this is VoxCPM speaking.",
    "output_path": os.path.join(OUT, "voxcpm_plain.wav"),
    "cfg_value": 3.0,
    "inference_timesteps": 50,
})
assert r1.success, f"Scenario 1 failed: {r1.error}"
assert os.path.exists(os.path.join(OUT, "voxcpm_plain.wav")), "Output WAV not created for Scenario 1"

s1 = probe_wav(os.path.join(OUT, "voxcpm_plain.wav"))
assert s1.get("sample_rate") == "48000", (
    f"Expected 48000 Hz, got {s1.get('sample_rate')} for Scenario 1"
)
assert s1.get("codec_name") in ("pcm_s16le",), (
    f"Unexpected codec {s1.get('codec_name')} for Scenario 1"
)
print_probe_info("plain", os.path.join(OUT, "voxcpm_plain.wav"))
print("Scenario 1 PASSED\n")

# ---------------------------------------------------------------------------
# Scenario 2 — Voice Cloning (requires reference WAV)
# ---------------------------------------------------------------------------

print("--- Scenario 2: Voice Cloning ---")
r2 = tool.execute({
    "text": "This voice should sound like the reference.",
    "reference_wav_path": REFERENCE_WAV,
    "output_path": os.path.join(OUT, "voxcpm_clone.wav"),
})
assert r2.success, f"Scenario 2 failed: {r2.error}"
assert os.path.exists(os.path.join(OUT, "voxcpm_clone.wav")), "Output WAV not created for Scenario 2"

s2 = probe_wav(os.path.join(OUT, "voxcpm_clone.wav"))
assert s2.get("sample_rate") == "48000", (
    f"Expected 48000 Hz, got {s2.get('sample_rate')} for Scenario 2"
)
assert s2.get("codec_name") in ("pcm_s16le",), (
    f"Unexpected codec {s2.get('codec_name')} for Scenario 2"
)
print_probe_info("clone", os.path.join(OUT, "voxcpm_clone.wav"))
print("Scenario 2 PASSED\n")

# ---------------------------------------------------------------------------
# Scenario 3 — Voice Design (voice_description)
# ---------------------------------------------------------------------------

print("--- Scenario 3: Voice Design ---")
r3 = tool.execute({
    "text": "This is a designed narrator voice.",
    "voice_description": "A warm middle-aged male narrator",
    "output_path": os.path.join(OUT, "voxcpm_design.wav"),
})
assert r3.success, f"Scenario 3 failed: {r3.error}"
assert os.path.exists(os.path.join(OUT, "voxcpm_design.wav")), "Output WAV not created for Scenario 3"

s3 = probe_wav(os.path.join(OUT, "voxcpm_design.wav"))
assert s3.get("sample_rate") == "48000", (
    f"Expected 48000 Hz, got {s3.get('sample_rate')} for Scenario 3"
)
assert s3.get("codec_name") in ("pcm_s16le",), (
    f"Unexpected codec {s3.get('codec_name')} for Scenario 3"
)
print_probe_info("design", os.path.join(OUT, "voxcpm_design.wav"))
print("Scenario 3 PASSED\n")

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

print("=== VOXCPM TTS INTEGRATION TEST COMPLETE (3/3 passed) ===")
