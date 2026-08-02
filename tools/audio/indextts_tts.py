"""IndexTTS2 local GPU text-to-speech provider tool.

Supports zero-shot voice cloning (spk_audio_prompt), 8-dim emotion
control (emo_vector), and FP16 inference.  Requires a CUDA GPU and
IndexTTS-2 cloned from GitHub with ``uv sync --all-extras`` completed.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

_MODEL_CACHE: dict[str, Any] = {}

_VOICE_ANCHOR_CACHE: dict[tuple[str, int], Path] = {}

_ANCHOR_TEXT = "This is a voice identity anchor."

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


class IndexTTS2TTS(BaseTool):
    name = "indextts_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "indextts"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = [
        "python:indextts",
        "cmd:espeak-ng",
    ]
    install_instructions = (
        "Install IndexTTS-2 for local GPU TTS with voice cloning:\n"
        "  git clone https://github.com/IndexTeam/IndexTTS-2.git\n"
        "  cd IndexTTS-2\n"
        "  uv sync --all-extras\n"
        "  # Install espeak-ng for phonemization:\n"
        "  #   Windows: winget install espeak-ng\n"
        "  #   Ubuntu:  sudo apt install espeak-ng\n"
        "  #   macOS:   brew install espeak-ng\n"
        "Download pretrained weights and place in IndexTTS-2/checkpoints/.\n"
        "Set INDEXTTS_REPO env var to the IndexTTS-2 clone path.\n"
        "Set INDEXTTS_CFG env var to override the config YAML path.\n"
        "Set INDEXTTS_MODEL_DIR env var to override the model directory.\n"
        "Requires a CUDA GPU (FP16: ~8-12 GB VRAM; FP32: ~16-22 GB VRAM)."
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
        "English / multilingual audio production at zero marginal cost",
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
                    "Path to a reference WAV for zero-shot voice cloning. "
                    "A clean 5-30 second clip of the target speaker is sufficient. "
                    "Use the same file across all segments for consistent timbre."
                ),
            },
            "emo_vector": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 8,
                "maxItems": 8,
                "default": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                "description": (
                    "8-dim emotion vector: "
                    "[happy, angry, sad, fearful, disgusted, surprised, neutral, other]. "
                    "Default is neutral [0,0,0,0,0,0,1,0]. "
                    "Values are typically in [0, 1] range."
                ),
            },
            "use_fp16": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Use FP16 inference to reduce VRAM (~8-12 GB vs ~16-22 GB). "
                    "Quality loss is negligible for voice cloning."
                ),
            },
            "speed": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 2.0,
                "default": 1.0,
                "description": "Speaking speed multiplier.",
            },
            "seed": {
                "type": "integer",
                "default": 42,
                "description": (
                    "Random seed for reproducibility. "
                    "All segments sharing the same seed (and no explicit spk_audio_prompt) "
                    "will be cloned from the same auto-generated anchor, ensuring consistent timbre. "
                    "Set to -1 to skip anchoring."
                ),
            },
            "max_text_tokens_per_segment": {
                "type": "integer",
                "default": 200,
                "description": (
                    "Max tokens per generation call. Longer text is split and "
                    "reassembled automatically."
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
        "use_fp16",
        "speed",
        "seed",
    ]
    side_effects = ["writes audio file to output_path"]
    fallback_tools = ["piper_tts", "elevenlabs_tts"]
    user_visible_verification = [
        "Listen to generated audio for naturalness, clarity, and emotion accuracy",
        "Verify voice cloning fidelity against the reference speaker",
    ]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> ToolStatus:
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
                    error="IndexTTS2 TTS not available. Requires CUDA GPU and the "
                    "indextts Python package. " + self.install_instructions,
                )
            return ToolResult(
                success=False,
                error=f"IndexTTS2 TTS status is {status.value}. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"IndexTTS2 TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _repo_root(self) -> Path:
        root = os.environ.get("INDEXTTS_REPO")
        if root:
            return Path(root)
        defaults = [Path("D:/index-tts"), Path("C:/Users/tiger/index-tts")]
        for d in defaults:
            if d.is_dir():
                return d
        return Path(__file__).resolve().parent.parent.parent / "vendor" / "IndexTTS-2"

    def _cfg_path(self) -> Path:
        env = os.environ.get("INDEXTTS_CFG")
        if env:
            return Path(env)
        return self._repo_root() / "checkpoints" / "config.yaml"

    def _model_dir(self) -> Path:
        env = os.environ.get("INDEXTTS_MODEL_DIR")
        if env:
            return Path(env)
        return self._repo_root() / "checkpoints"

    def _load_model(self, use_fp16: bool) -> Any:
        cache_key = f"fp16={use_fp16}"
        if cache_key not in _MODEL_CACHE:
            from indextts.infer_v2 import IndexTTS2

            model = IndexTTS2(
                cfg_path=str(self._cfg_path()),
                model_dir=str(self._model_dir()),
                use_fp16=use_fp16,
                device="cuda",
            )
            _MODEL_CACHE[cache_key] = model
        return _MODEL_CACHE[cache_key]

    def _get_or_create_anchor(
        self,
        model: Any,
        use_fp16: bool,
        seed: int,
        emo_vector: list[float],
    ) -> tuple[Path, str]:
        import hashlib

        anchor_transcript = _ANCHOR_TEXT
        emo_key = "_".join(f"{v:.2f}" for v in emo_vector)
        cache_key = (f"fp16={use_fp16}", seed, emo_key)
        if cache_key in _VOICE_ANCHOR_CACHE:
            return _VOICE_ANCHOR_CACHE[cache_key], anchor_transcript

        import tempfile
        import numpy as np

        anchor_dir = Path(tempfile.gettempdir()) / "indextts_anchors"
        anchor_dir.mkdir(parents=True, exist_ok=True)

        fp_tag = "fp16" if use_fp16 else "fp32"
        seed_hash = hashlib.md5(f"{seed}{emo_key}".encode()).hexdigest()[:8]
        anchor_path = anchor_dir / f"anchor_{fp_tag}_seed{seed}_{seed_hash}.wav"

        if not anchor_path.exists():
            print(f"[IndexTTS2] Generating voice anchor (seed={seed})...")
            try:
                import torch
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
            except ImportError:
                pass

            anchor_audio = model.infer(
                spk_audio_prompt=None,
                text=anchor_transcript,
                emo_vector=emo_vector,
                verbose=False,
            )

            if isinstance(anchor_audio, np.ndarray):
                import scipy.io.wavfile as wavfile
                sample_rate = getattr(model, "sample_rate", 24000)
                wavfile.write(str(anchor_path), sample_rate, anchor_audio)
            else:
                raise RuntimeError(
                    f"IndexTTS2 model.infer() returned unexpected type: {type(anchor_audio)}"
                )

            print(f"[IndexTTS2] Voice anchor saved: {anchor_path}")

        _VOICE_ANCHOR_CACHE[cache_key] = anchor_path
        return anchor_path, anchor_transcript

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        import numpy as np
        import scipy.io.wavfile as wavfile

        text: str = inputs["text"]
        output_path = Path(inputs.get("output_path", "indextts_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        spk_audio_prompt: str | None = inputs.get("spk_audio_prompt")
        emo_vector: list[float] = list(inputs.get("emo_vector", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]))
        use_fp16: bool = bool(inputs.get("use_fp16", True))
        speed: float = float(inputs.get("speed", 1.0))
        seed: int = int(inputs.get("seed", 42))

        if len(emo_vector) != 8:
            emo_vector = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]

        model = self._load_model(use_fp16)

        # ------------------------------------------------------------------
        # Resolve spk_audio_prompt (voice-anchor priority)
        # 1. User explicitly provides spk_audio_prompt → use directly
        # 2. seed != -1                            → auto-generate / reuse anchor
        # 3. seed == -1                            → no cloning (IndexTTS2 default voice)
        # ------------------------------------------------------------------
        effective_spk: str | None = spk_audio_prompt
        anchor_used = False

        if not effective_spk and seed != -1:
            anchor_path, _ = self._get_or_create_anchor(
                model, use_fp16, seed, emo_vector,
            )
            effective_spk = str(anchor_path)
            anchor_used = True

        # --- seed for reproducibility ---
        if seed != -1:
            try:
                import torch
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
            except ImportError:
                pass

        # --- generate ---
        infer_kwargs: dict[str, Any] = {
            "text": text,
            "emo_vector": emo_vector,
            "verbose": False,
        }
        if effective_spk:
            infer_kwargs["spk_audio_prompt"] = effective_spk

        audio_array = model.infer(**infer_kwargs)

        sample_rate = getattr(model, "sample_rate", 24000)

        if speed != 1.0:
            try:
                import scipy.signal
                new_length = int(len(audio_array) / speed)
                audio_array = scipy.signal.resample(audio_array, new_length)
            except ImportError:
                pass

        if not isinstance(audio_array, np.ndarray):
            audio_array = np.array(audio_array, dtype=np.float32)

        wavfile.write(str(output_path), sample_rate, audio_array)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": "indextts-2",
                "text_length": len(text),
                "output": str(output_path),
                "format": "wav",
                "sample_rate": sample_rate,
                "voice_cloning": bool(effective_spk),
                "voice_anchor_used": anchor_used,
                "emo_vector": emo_vector,
                "use_fp16": use_fp16,
                "speed": speed,
                "seed": seed,
                "effective_spk_prompt": effective_spk,
            },
            artifacts=[str(output_path)],
            model="indextts-2",
        )
