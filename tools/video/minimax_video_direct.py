"""MiniMax (Hailuo AI) video generation via direct REST API.

Calls `POST https://api.minimaxi.com/v1/video_generation` to create an async task,
polls `GET /v1/query/video_generation` for status, then downloads the result via
`GET /v1/files/retrieve` and writes it to `output_path`.

This is the direct-channel tool for MiniMax. It coexists with `minimax_video.py`
(fal.ai channel) — both have provider="minimax" but use different API gateways.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import requests

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
from tools.video._shared import probe_output


# ── constants ──────────────────────────────────────────────────────────────

_BASE_URL = "https://api.minimaxi.com"
_CREATE_URL = f"{_BASE_URL}/v1/video_generation"
_QUERY_URL = f"{_BASE_URL}/v1/query/video_generation"
_FILE_RETRIEVE_URL = f"{_BASE_URL}/v1/files/retrieve"
_FILE_UPLOAD_URL = f"{_BASE_URL}/v1/files/upload"

_DEFAULT_MODEL = "MiniMax-Hailuo-2.3"
_DEFAULT_DURATION = 6
_DEFAULT_RESOLUTION = "768P"

# Terminal states from the MiniMax API (VideoProcessStatus enum)
_POLL_INTERVAL = 10  # seconds — MiniMax recommends 10s
_MAX_POLL_SECONDS = 900  # 15 minutes
_TERMINAL_OK = "Success"
_TERMINAL_FAIL = "Fail"
_NONTERMINAL = {"Preparing", "Queueing", "Processing"}


# ── helpers ────────────────────────────────────────────────────────────────

def _upload_image_minimax(image_path: str, api_key: str) -> str | None:
    """Upload an image to MiniMax and return its public file URL.

    Returns None on failure (caller should fall back or error).
    """
    path = Path(image_path)
    if not path.exists():
        return None

    # Try multiple purpose values — MiniMax has not documented a dedicated
    # "video_generation_input" purpose, but "video_understanding" accepts
    # image/video files and produces a retrievable file_id.
    for purpose in ("video_understanding",):
        try:
            with open(path, "rb") as fh:
                resp = requests.post(
                    _FILE_UPLOAD_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (path.name, fh, "application/octet-stream")},
                    data={"purpose": purpose},
                    timeout=60,
                )
            if resp.status_code == 200:
                data = resp.json()
                file_obj = data.get("file", data)
                file_id = file_obj.get("file_id") or data.get("file_id")
                if file_id:
                    # Retrieve the download URL for this file
                    retrieve_resp = requests.get(
                        _FILE_RETRIEVE_URL,
                        headers={"Authorization": f"Bearer {api_key}"},
                        params={"file_id": file_id},
                        timeout=30,
                    )
                    if retrieve_resp.status_code == 200:
                        rd = retrieve_resp.json()
                        file_info = rd.get("file", rd)
                        download_url = file_info.get("download_url")
                        if download_url:
                            return download_url
        except Exception:
            continue

    return None


def _upload_via_fal(image_path: str) -> str | None:
    """Fallback: upload a local image to fal.ai storage and return its public URL."""
    from tools.video._shared import upload_image_fal

    try:
        return upload_image_fal(image_path)
    except Exception:
        return None


def _resolve_image_ref(inputs: dict[str, Any], api_key: str) -> str | None:
    """Resolve reference_image_path / reference_image_url to a public URL."""
    url = inputs.get("reference_image_url")
    if url:
        return url

    path = inputs.get("reference_image_path")
    if not path:
        return None

    # 1. Try MiniMax file upload
    url = _upload_image_minimax(path, api_key)
    if url:
        return url

    # 2. Fallback: fal.ai storage
    url = _upload_via_fal(path)
    if url:
        return url

    return None


# ── tool ───────────────────────────────────────────────────────────────────

class MiniMaxVideoDirect(BaseTool):
    name = "minimax_video_direct"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "minimax"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.ASYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set MINIMAX_API_KEY to your MiniMax API key.\n"
        "  Get one at https://platform.minimax.io — Account Management → API Keys"
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "camera_direction": True,
        "native_audio": False,
        "reference_image": True,
    }
    best_for = [
        "cost-effective video generation with direct MiniMax API",
        "prompt-following with camera directions (framing, motion, composition)",
        "high-texture footage without intermediate gateway proxies",
    ]
    not_good_for = ["offline generation", "very long clips"]
    fallback_tools = ["minimax_video", "kling_video", "veo_video", "wan_video"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model_variant": {
                "type": "string",
                "enum": [
                    "MiniMax-Hailuo-2.3",
                    "MiniMax-Hailuo-2.3-Fast",
                    "MiniMax-Hailuo-02",
                    "I2V-01-Director",
                    "I2V-01-live",
                    "I2V-01",
                ],
                "default": _DEFAULT_MODEL,
            },
            "duration": {
                "type": "integer",
                "minimum": 2,
                "maximum": 10,
                "default": _DEFAULT_DURATION,
                "description": "Duration in seconds (2-10)",
            },
            "resolution": {
                "type": "string",
                "enum": ["768P", "1080P"],
                "default": _DEFAULT_RESOLUTION,
            },
            "reference_image_url": {
                "type": "string",
                "description": "Public URL of the first-frame image for image_to_video",
            },
            "reference_image_path": {
                "type": "string",
                "description": "Local path of the first-frame image for image_to_video (auto-uploaded)",
            },
            "output_path": {"type": "string"},
            "poll_interval_seconds": {
                "type": "integer",
                "minimum": 5,
                "default": _POLL_INTERVAL,
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 30,
                "default": _MAX_POLL_SECONDS,
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=5.0,
        retryable_errors=["rate_limit", "timeout", "server_error"],
    )
    idempotency_key_fields = [
        "prompt", "model_variant", "operation", "duration", "resolution",
    ]
    side_effects = ["writes video file to output_path", "calls MiniMax REST API"]
    user_visible_verification = [
        "Watch generated clip for motion coherence, prompt adherence, and visual quality",
    ]

    # ── lifecycle ──────────────────────────────────────────────────────

    def _get_api_key(self) -> str | None:
        return os.environ.get("MINIMAX_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model_variant", _DEFAULT_MODEL)
        duration = int(inputs.get("duration", _DEFAULT_DURATION))
        # Approximate costs based on MiniMax pricing (varies by model/region)
        if "Fast" in model:
            base = 0.04  # $0.04/s for fast tier
        elif "Director" in model or "live" in model:
            base = 0.05
        else:
            base = 0.06  # $0.06/s for standard quality
        return round(base * duration, 2)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model_variant", _DEFAULT_MODEL)
        duration = int(inputs.get("duration", _DEFAULT_DURATION))
        if "Fast" in model:
            return 20.0 + duration * 3.0
        return 40.0 + duration * 5.0

    # ── execution ──────────────────────────────────────────────────────

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="MINIMAX_API_KEY not set. " + self.install_instructions,
            )

        start = time.time()
        model = inputs.get("model_variant", _DEFAULT_MODEL)
        operation = inputs.get("operation", "text_to_video")
        duration = int(inputs.get("duration", _DEFAULT_DURATION))
        resolution = inputs.get("resolution", _DEFAULT_RESOLUTION)
        poll_interval = int(inputs.get("poll_interval_seconds", _POLL_INTERVAL))
        timeout_seconds = int(inputs.get("timeout_seconds", _MAX_POLL_SECONDS))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # --- Step 1: Create generation task ---
        payload: dict[str, Any] = {
            "model": model,
            "prompt": inputs["prompt"],
            "duration": duration,
            "resolution": resolution,
        }

        if operation == "image_to_video":
            image_url = _resolve_image_ref(inputs, api_key)
            if not image_url:
                return ToolResult(
                    success=False,
                    error=(
                        "image_to_video requires reference_image_url or reference_image_path. "
                        "Provide a public URL of your first-frame image. "
                        "If using reference_image_path, ensure either MINIMAX_API_KEY "
                        "image upload succeeds or FAL_KEY is set for fallback upload."
                    ),
                )
            payload["first_frame_image"] = image_url

        try:
            create_resp = requests.post(
                _CREATE_URL, headers=headers, json=payload, timeout=60,
            )
            create_resp.raise_for_status()
            create_data = create_resp.json()

            # Check base_resp status code for API-level errors
            base_resp = create_data.get("base_resp", {})
            status_code = base_resp.get("status_code", 0)
            if status_code != 0:
                return ToolResult(
                    success=False,
                    error=(
                        f"MiniMax API error (code={status_code}): "
                        f"{base_resp.get('status_msg', 'unknown')}"
                    ),
                )

            task_id = create_data.get("task_id")
            if not task_id:
                return ToolResult(
                    success=False,
                    error=f"No task_id in response: {create_data}",
                )

        except requests.RequestException as exc:
            return ToolResult(
                success=False,
                error=f"MiniMax task creation failed: {exc}",
            )

        # --- Step 2: Poll until terminal ---
        deadline = time.time() + timeout_seconds
        file_id: str | None = None
        video_width: int | None = None
        video_height: int | None = None

        while time.time() < deadline:
            time.sleep(poll_interval)
            try:
                query_resp = requests.get(
                    _QUERY_URL,
                    headers=headers,
                    params={"task_id": task_id},
                    timeout=30,
                )
                query_resp.raise_for_status()
                query_data = query_resp.json()
            except requests.RequestException as exc:
                return ToolResult(
                    success=False,
                    error=f"MiniMax status query failed (task={task_id}): {exc}",
                )

            status = query_data.get("status", "")

            if status == _TERMINAL_OK:
                file_id = query_data.get("file_id")
                video_width = query_data.get("video_width")
                video_height = query_data.get("video_height")
                break

            if status == _TERMINAL_FAIL:
                q_base = query_data.get("base_resp", {})
                return ToolResult(
                    success=False,
                    error=(
                        f"MiniMax video generation failed (task={task_id}). "
                        f"code={q_base.get('status_code', '?')}, "
                        f"msg={q_base.get('status_msg', status)}"
                    ),
                )

            if status not in _NONTERMINAL:
                # Unknown status — treat as transient, keep polling
                pass

        else:
            return ToolResult(
                success=False,
                error=f"MiniMax video generation timed out after {timeout_seconds}s (task={task_id})",
            )

        if not file_id:
            return ToolResult(
                success=False,
                error=f"MiniMax task {task_id} completed but no file_id returned",
            )

        # --- Step 3: Retrieve download URL and download ---
        try:
            file_resp = requests.get(
                _FILE_RETRIEVE_URL,
                headers=headers,
                params={"file_id": file_id},
                timeout=30,
            )
            file_resp.raise_for_status()
            file_data = file_resp.json()
        except requests.RequestException as exc:
            return ToolResult(
                success=False,
                error=f"MiniMax file retrieval failed (file_id={file_id}): {exc}",
            )

        file_info = file_data.get("file", file_data)
        download_url = file_info.get("download_url")
        if not download_url:
            return ToolResult(
                success=False,
                error=f"No download_url in file response (file_id={file_id}): {file_data}",
            )

        output_path = Path(inputs.get("output_path", "minimax_video_direct_output.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            video_resp = requests.get(download_url, timeout=300)
            video_resp.raise_for_status()
            output_path.write_bytes(video_resp.content)
        except requests.RequestException as exc:
            return ToolResult(
                success=False,
                error=f"MiniMax video download failed: {exc}",
            )

        # --- Probe output for metadata ---
        probed = probe_output(output_path)

        return ToolResult(
            success=True,
            data={
                "provider": "minimax",
                "model": model,
                "prompt": inputs["prompt"],
                "operation": operation,
                "task_id": task_id,
                "file_id": file_id,
                "duration": duration,
                "resolution": resolution,
                "video_width": video_width or probed.get("video_width"),
                "video_height": video_height or probed.get("video_height"),
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                "channel": "direct",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
