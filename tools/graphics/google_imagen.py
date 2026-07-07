"""Google Imagen image generation via Gemini API."""

from __future__ import annotations

import base64
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
from tools.google_credentials import (
    get_access_token,
    resolve_project_id,
    service_account_configured,
)

# Aspect ratio to approximate pixel dimensions (for cost/reporting only)
ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "3:4": (896, 1152),
    "4:3": (1152, 896),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}


def _dims_to_aspect_ratio(width: int, height: int) -> str:
    """Convert width/height to the nearest supported aspect ratio."""
    target = width / height
    best = "1:1"
    best_diff = float("inf")
    for ratio, (w, h) in ASPECT_RATIOS.items():
        diff = abs(target - w / h)
        if diff < best_diff:
            best_diff = diff
            best = ratio
    return best


class GoogleImagen(BaseTool):
    name = "google_imagen"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "google_imagen"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []  # checked dynamically via env var
    install_instructions = (
        "Auth option A — API key (AI Studio): set GOOGLE_API_KEY (or GEMINI_API_KEY).\n"
        "  Get one at https://aistudio.google.com/apikey\n"
        "Auth option B — service account (Vertex AI): set GOOGLE_APPLICATION_CREDENTIALS\n"
        "  to a service-account JSON key (needs the 'google-auth' package), plus\n"
        "  GOOGLE_CLOUD_PROJECT and optionally GOOGLE_CLOUD_LOCATION (default us-central1).\n"
        "  Requires the Vertex AI API enabled and billing on the project."
    )
    agent_skills = []

    capabilities = ["generate_image", "generate_illustration", "text_to_image", "image_to_image"]
    supports = {
        "negative_prompt": False,
        "seed": False,
        "custom_size": False,
        "aspect_ratio": True,
        "image_edit": True,
        "gemini_flash_image": True,
    }
    best_for = [
        "high-quality photorealistic images",
        "Google ecosystem integration",
        "fast generation with multiple aspect ratios",
    ]
    not_good_for = [
        "negative prompt control (not supported)",
        "exact pixel dimensions (uses aspect ratios)",
        "offline generation",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "description": "Image description (max 480 tokens)"},
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "3:4", "4:3", "9:16", "16:9"],
                "default": "1:1",
                "description": "Aspect ratio of generated image",
            },
            "width": {
                "type": "integer",
                "description": "Desired width in pixels — mapped to nearest aspect ratio",
            },
            "height": {
                "type": "integer",
                "description": "Desired height in pixels — mapped to nearest aspect ratio",
            },
            "model": {
                "type": "string",
                "enum": [
                    "imagen-4.0-generate-001",
                    "imagen-4.0-fast-generate-001",
                    "imagen-4.0-ultra-generate-001",
                    "gemini-3.1-flash-lite-image",
                ],
                "default": "imagen-4.0-generate-001",
                "description": "Imagen model variant or Gemini flash lite image model",
            },
            "number_of_images": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 4,
            },
            "output_path": {"type": "string"},
            "image_path": {
                "type": "string",
                "description": "Local path to a reference image for img2img (image-to-image) generation. The model will generate a new image based on both the prompt and the reference image.",
            },
            "image_strength": {
                "type": "number",
                "default": 0.7,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "How much the reference image influences the output (0.0=ignore, 1.0=exact). Only used when image_path is provided.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "aspect_ratio", "model"]
    side_effects = ["writes image file to output_path", "calls Google Generative AI API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def _get_api_key(self) -> str | None:
        return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    def get_status(self) -> ToolStatus:
        # API key -> AI Studio endpoint; service-account JSON -> Vertex AI.
        if self._get_api_key() or service_account_configured():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", "imagen-4.0-generate-001")
        n = inputs.get("number_of_images", 1)
        if "ultra" in model:
            return 0.06 * n
        if "fast" in model:
            return 0.02 * n
        if "gemini-3.1-flash-lite-image" in model:
            return 0.00 * n  # Free tier available
        return 0.04 * n

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import logging
        logger = logging.getLogger(__name__)
        start = time.time()

        model = inputs.get("model", "imagen-4.0-generate-001")
        prompt = inputs["prompt"]
        image_path = inputs.get("image_path")
        output_path = Path(inputs.get("output_path", "generated_image.png"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if this is a Gemini flash image model (uses google.genai client)
        is_gemini_model = "gemini" in model.lower() and "image" in model.lower()

        try:
            if is_gemini_model:
                # Use new google.genai client (v2+) for Gemini flash image models
                from google import genai
                from google.genai import types

                api_key = self._get_api_key()
                if not api_key:
                    return ToolResult(
                        success=False,
                        error="No Google API key found. Set GOOGLE_API_KEY in .env"
                    )

                client = genai.Client(api_key=api_key)

                # Build content: text + optional image
                parts = [types.Part(text=prompt)]
                if image_path:
                    image_file = Path(image_path)
                    if image_file.exists():
                        image_bytes = image_file.read_bytes()
                        ext = image_file.suffix.lower()
                        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
                        mime_type = mime_map.get(ext, "image/png")
                        parts.append(
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                        )
                        logger.info("google_imagen: img2img mode with reference image %s", image_path)

                contents = [types.Content(role="user", parts=parts)]

                # Use generate_content API (v2+)
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                )

                # Extract image from response
                image_bytes = None
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            image_bytes = part.inline_data.data
                            break
                    if image_bytes:
                        break

                if not image_bytes:
                    return ToolResult(success=False, error="No image in Gemini response")

                output_path.write_bytes(image_bytes)
                logger.info("google_imagen: Generated image via Gemini, saved to %s", output_path)

            else:
                # Standard Imagen API (predict endpoint) - existing code
                import requests

                api_key = self._get_api_key()
                if not api_key and not service_account_configured():
                    return ToolResult(
                        success=False,
                        error="No Google credentials found. " + self.install_instructions,
                    )

                # Resolve aspect ratio
                if "aspect_ratio" in inputs:
                    aspect_ratio = inputs["aspect_ratio"]
                elif "width" in inputs and "height" in inputs:
                    aspect_ratio = _dims_to_aspect_ratio(inputs["width"], inputs["height"])
                else:
                    aspect_ratio = "1:1"

                number_of_images = inputs.get("number_of_images", 1)

                parameters: dict[str, Any] = {
                    "sampleCount": number_of_images,
                    "aspectRatio": aspect_ratio,
                }

                # Build instance with optional image
                instance: dict[str, Any] = {"prompt": prompt}
                if image_path:
                    image_file = Path(image_path)
                    if image_file.exists():
                        image_bytes = image_file.read_bytes()
                        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                        ext = image_file.suffix.lower()
                        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
                        mime_type = mime_map.get(ext, "image/png")
                        instance["image"] = {"bytesBase64Encoded": image_b64, "mimeType": mime_type}
                        logger.info("google_imagen: img2img mode with reference image %s", image_path)

                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:predict"
                )
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                }

                response = requests.post(
                    url,
                    headers=headers,
                    json={
                        "instances": [instance],
                        "parameters": parameters,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

                predictions = data.get("predictions", [])
                if not predictions:
                    return ToolResult(success=False, error="No images returned from Imagen API")

                image_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                output_path.write_bytes(image_bytes)

        except Exception as e:
            return ToolResult(success=False, error=f"Imagen generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "google_imagen",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "images_generated": 1,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
