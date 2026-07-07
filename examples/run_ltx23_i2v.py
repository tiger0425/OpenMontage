#!/usr/bin/env python3
"""Example: run LTX-2.3 image-to-video through the local ComfyUI server.

Prerequisites:
1. ComfyUI is installed and running (default http://localhost:8188).
2. ComfyUI-LTXVideo custom nodes are installed.
3. ltx-2.3-22b-dev-fp8.safetensors is in ComfyUI/models/diffusion_models/.
4. You have exported an API-format workflow from ComfyUI and saved it as
   tools/_comfyui/workflows/ltx23-i2v.json.

Usage:
    conda activate comfy
    python examples/run_ltx23_i2v.py \
        --image assets/fashion_design.png \
        --prompt "A model walks down a runway wearing this design, elegant, cinematic lighting"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root so we can import tools
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.video.comfyui_video import ComfyUIVideo


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LTX-2.3 I2V via ComfyUI")
    parser.add_argument("--image", required=True, help="Path to reference image")
    parser.add_argument("--prompt", required=True, help="Text prompt for video generation")
    parser.add_argument("--workflow", default="tools/_comfyui/workflows/ltx23-i2v.json", help="Path to API-format workflow JSON")
    parser.add_argument("--output", default="outputs/ltx23_i2v.mp4", help="Output video path")
    parser.add_argument("--width", type=int, default=768, help="Video width")
    parser.add_argument("--height", type=int, default=512, help="Video height")
    parser.add_argument("--frames", type=int, default=49, help="Number of frames")
    parser.add_argument("--steps", type=int, default=30, help="Inference steps")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--output-node", default=None, help="ComfyUI output node ID (auto-detect if omitted)")
    args = parser.parse_args()

    tool = ComfyUIVideo()
    status = tool.get_status()
    print(f"ComfyUI status: {status.name}")
    if status.name != "AVAILABLE":
        print("ERROR: ComfyUI server is not running or missing required models.")
        print("Please start ComfyUI and verify LTX-2.3 models are installed.")
        print("See docs/COMFYUI_LTX_SETUP.md")
        return 1

    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print(f"ERROR: Workflow file not found: {workflow_path}")
        print("Build an LTX-2.3 I2V workflow in ComfyUI, export it as API JSON,")
        print("and save it to the path above.")
        return 1

    # If the user did not specify an output node, try to find a SaveVideo/SaveImage node
    output_node = args.output_node
    if output_node is None:
        import json
        with open(workflow_path) as f:
            wf = json.load(f)
        for node_id, node in wf.items():
            cls = node.get("class_type", "")
            if cls in ("SaveVideo", "SaveImage", "VideoCombine", "VHS_VideoCombine"):
                output_node = node_id
                print(f"Auto-detected output node: {output_node} ({cls})")
                break
        if output_node is None:
            print("ERROR: Could not auto-detect output node. Please pass --output-node.")
            return 1

    inputs = {
        "operation": "image_to_video",
        "prompt": args.prompt,
        "reference_image_path": str(Path(args.image).resolve()),
        "workflow_path": str(workflow_path.resolve()),
        "output_node": output_node,
        "output_path": str(Path(args.output).resolve()),
        "width": args.width,
        "height": args.height,
        "num_frames": args.frames,
        "num_inference_steps": args.steps,
        "seed": args.seed,
        "workflow_name": "ltx23-i2v",
        "workflow_model": "ltx-2.3-22b-dev-fp8",
    }

    print(f"Submitting workflow...")
    print(f"  image: {inputs['reference_image_path']}")
    print(f"  prompt: {inputs['prompt']}")
    print(f"  size: {inputs['width']}x{inputs['height']}, frames: {inputs['num_frames']}")
    result = tool.execute(inputs)

    if not result.success:
        print(f"ERROR: {result.error}")
        return 1

    print(f"Success!")
    print(f"  output: {result.data['output']}")
    print(f"  duration: {result.data['duration_seconds']}s")
    print(f"  fps: {result.data['fps']}")
    print(f"  frames: {result.data['num_frames']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
