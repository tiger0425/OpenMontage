"""MiniMax Image generation via native API (https://api.minimaxi.com)."""

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


class MiniMaxImage(BaseTool):
    name = "minimax_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "minimax"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.API

    dependencies = []  # checked dynamically via env var
    install_instructions = (
        "Set MINIMAX_API_KEY to your MiniMax API key.\n"
        "  Get one from https://platform.minimaxi.com/user-center/basic-information/interface-key\n"
        "  (Token Plan key; create in User Center → Interface Keys)"
    )
    agent_skills = ["flux-best-practices"]

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "seed": True,
        "aspect_ratio": True,
        "prompt_optimizer": True,
        "custom_size": True,
        "batch_generation": True,
    }
    best_for = [
        "cost-effective image generation",
        "large batch image generation",
        "prompt-optimized results",
    ]
    not_good_for = ["complex text rendering in images", "offline generation"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of image to generate (max 1500 chars)",
            },
            "model": {
                "type": "string",
                "enum": ["image-01", "image-01-live"],
                "default": "image-01",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"],
                "default": "1:1",
            },
            "width": {
                "type": "integer",
                "description": "Image width (512-2048, divisible by 8). Overrides aspect_ratio resolution.",
                "minimum": 512,
                "maximum": 2048,
            },
            "height": {
                "type": "integer",
                "description": "Image height (512-2048, divisible by 8). Overrides aspect_ratio resolution.",
                "minimum": 512,
                "maximum": 2048,
            },
            "n": {
                "type": "integer",
                "description": "Number of images to generate (1-9)",
                "default": 1,
                "minimum": 1,
                "maximum": 9,
            },
            "seed": {
                "type": "integer",
                "description": "Seed for reproducibility",
            },
            "response_format": {
                "type": "string",
                "enum": ["url", "base64"],
                "default": "url",
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "Enable prompt optimization",
                "default": True,
            },
            "style": {
                "type": "string",
                "description": "Style hint for image generation",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "model", "aspect_ratio", "seed"]
    side_effects = ["writes image file to output_path", "calls MiniMax API"]
    fallback_tools = ["flux_image", "openai_image", "google_imagen"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    # ---- Key management ----

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    # ---- Cost estimation ----

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # MiniMax image-01 pricing: ~$0.005 per image (approximate)
        n = int(inputs.get("n", 1))
        model = inputs.get("model", "image-01")
        per_image = 0.005 if model == "image-01" else 0.005
        return round(per_image * n, 4)

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

        import requests

        start = time.time()
        model = inputs.get("model", "image-01")
        prompt = inputs["prompt"]
        n = int(inputs.get("n", 1))
        response_format = inputs.get("response_format", "url")

        # Build payload
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "response_format": response_format,
        }

        # Optional parameters
        if inputs.get("prompt_optimizer", True):
            payload["prompt_optimizer"] = True

        if inputs.get("aspect_ratio"):
            payload["aspect_ratio"] = inputs["aspect_ratio"]

        if inputs.get("width") and inputs.get("height"):
            payload["width"] = int(inputs["width"])
            payload["height"] = int(inputs["height"])

        if inputs.get("seed") is not None:
            payload["seed"] = int(inputs["seed"])

        if inputs.get("style"):
            payload["style"] = inputs["style"]

        try:
            response = requests.post(
                "https://api.minimaxi.com/v1/image_generation",
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

            # Extract image URLs
            image_urls: list[str] = data.get("data", {}).get("image_urls", [])
            if not image_urls:
                return ToolResult(
                    success=False,
                    error="MiniMax returned no images",
                )

            # Download first image to output_path
            output_path_str = inputs.get("output_path", "generated_image.png")
            output_path = Path(output_path_str)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            image_url = image_urls[0]
            image_response = requests.get(image_url, timeout=120)
            image_response.raise_for_status()
            output_path.write_bytes(image_response.content)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"MiniMax image generation failed: {e}",
            )

        return ToolResult(
            success=True,
            data={
                "provider": "minimax",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "seed": inputs.get("seed"),
                "image_url": image_url,
                "image_count": n,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            seed=inputs.get("seed"),
            model=model,
        )
