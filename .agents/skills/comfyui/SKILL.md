---
name: comfyui
description: Use when working with ComfyUI workflows in OpenMontage, including comfyui_image/comfyui_video, custom workflow_json/workflow_path inputs, output_node selection, missing model setup, LoRAs, low-VRAM workflow choices, and community workflow imports.
---

# ComfyUI Workflows in OpenMontage

Use this skill before calling `comfyui_image` or `comfyui_video`, and when converting a community ComfyUI workflow into an OpenMontage tool call.

## Server Contract

- ComfyUI must be running before the tool can generate. The default server is `http://localhost:8188`; override it with `COMFYUI_SERVER_URL`.
- Health and hardware status come from `GET /system_stats`.
- Jobs are submitted to `POST /prompt`, completed outputs are read from `GET /history/{prompt_id}`, and artifact bytes are downloaded with `GET /view`.
- Export workflows with ComfyUI's API-format JSON, not the UI layout format. If a downloaded workflow will not submit, re-export it from ComfyUI with API format enabled.

## Choosing a Workflow

- Use bundled workflows when the requested operation matches and the local machine has the required models and VRAM.
- Use a custom `workflow_json` or `workflow_path` when the user needs a community recipe, a lower-VRAM model, a different style family, or custom nodes.
- For 8GB-12GB GPUs, prefer lower-footprint workflows such as Wan 2.1 1.3B, LTXV FP8 or quantized workflows, or Wan 2.2 GGUF/quantized community workflows. The bundled Wan 2.2 14B FP8 video workflows are a 16GB-class path, not a provider-wide floor.
- Do not promise that arbitrary custom workflows will fit a machine. The workflow, quantization, resolution, frame count, and offload settings determine the real resource envelope.

## Output Node Contract

- Custom workflows must pass `output_node`.
- Pick the node that writes the artifact, usually `SaveImage`, `SaveVideo`, `VHS_VideoCombine`, or another terminal saver node.
- Pass the node ID as a string, for example `"108"`. Do not pass the class name.
- If a workflow has multiple savers, choose the final deliverable node, not previews or intermediates.

## Templated vs Fixed Nodes

- Identify templated nodes before execution: prompt text, seed, dimensions, frame count, source image, sampler settings, and output filename prefix.
- Fixed nodes are model loaders, VAEs, text encoders, LoRA loaders, schedulers, and graph wiring. Do not mutate those unless the workflow author intended that customization.
- For community workflows, inspect each loader node and note every required model or custom node before running. Missing models should be handled through the tool's structured `missing_models` payload when available.

## Model and LoRA Setup

- Use ComfyUI Manager or the workflow author's model links when available, and respect model licenses.
- Place models in the folders expected by the loader nodes: diffusion models under `ComfyUI/models/diffusion_models/`, text encoders under `ComfyUI/models/text_encoders/`, VAEs under `ComfyUI/models/vae/`, and LoRAs under `ComfyUI/models/loras/`.
- For LoRA stacks, use `LoraLoader` or `LoraLoaderModelOnly` chains in the workflow. Record each LoRA name plus `strength_model` and `strength_clip` when applicable.
- The current ComfyUI tools do not inject LoRAs into arbitrary graphs. To use LoRAs, provide a workflow that already contains the LoRA loader chain and pass model-stack provenance.

## Provenance

- For custom workflows, provide `workflow_name` and `workflow_model` when known.
- Provide `workflow_model_stack` for reproducibility when the workflow is not bundled. Include base checkpoint or diffusion model, quantization, text encoder, VAE, LoRAs and strengths, sampler or scheduler, steps, and guidance if the workflow exposes them.
- The tools record the final workflow hash. Treat that hash plus the model stack, seed, dimensions, and prompt as the reproducibility contract.

## Bundled Workflow: `Qwen21-txt2img.json` (standard Qwen-Image 2.1 T2I)

`tools/_comfyui/workflows/Qwen21-txt2img.json` is the verified standard text-to-image
workflow for Qwen-Image 2.1. Use it for clean single-subject images on a flat background
(character sprites, product cutouts, title-card art).

Verified node pairing — **do not substitute these**:

| Role | File |
| --- | --- |
| Diffusion | `qwen_image_2.1_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_8b_int8_convrot.safetensors` with `type: qwen_image` |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` |
| Scheduler node | `ModelSamplingAuraFlow` (`shift: 3.0`) → into `KSampler` |
| Sampler | `euler` / `simple`, 25 steps, `cfg 4.0`, `denoise 1.0` |
| Output node id | `10` (`SaveImage`) |

Prompt/seed are templated via `workflow_overrides` on nodes `5` (positive),
`6` (negative), and `8` (`seed` / `steps` / `cfg`).

### Text-encoder pairing is dimension-locked

Qwen-Image 2.1 expects a **4096-wide** text embedding. `Qwen3-VL-8B` produces 4096;
`Qwen2.5-VL-7B` produces **3584** and fails at the sampler with
`Given normalized_shape=[4096], expected input with shape [*4096], but got input of size[1, N, 3584]`.
If you see that error, the CLIP is mismatched — not the resolution, not the sampler.

### Two traps that cost real time

1. **Do not reuse Flux2 graph structure for Qwen.** `Flux2Scheduler` and
   `SamplerCustomAdvanced` are Flux-specific; a Qwen graph needs `KSampler` +
   `ModelSamplingAuraFlow`. Verify node signatures against `GET /object_info/<NodeClass>`
   before authoring — do not copy a sibling workflow's wiring by analogy.
2. **`Qwen-Layered-*` is not a text-to-image model.** The Layered family emits N RGBA
   *contributions* to a layered illustration (background plate, outline layer, colour
   layer, shadow layer, and an occasional text layer). Compositing them back does not
   yield a foreground cutout, and `negative` prompts cannot suppress the baked-in
   background plate or its texture. Reach for `Qwen21-txt2img.json` instead when the
   goal is a clean subject; use Layered only when you actually want editable layers.

### Resolution

Generate at a native 16:9 size (`1664x928`). Off-native sizes such as `1280x720`
produce texture/pattern artefacts in the background.

### Post-processing: crop to content before compositing

These models pad the frame with background. A `1664x928` output may contain a subject
occupying under 40% of the width, so setting CSS `width: 420px` yields a visually tiny
element. Crop to the non-background bounding box before handing the asset to a
composition.

## Bundled Workflow: `Qwen21-edit.json` (Qwen-Image-Edit 2.1, single reference)

`tools/_comfyui/workflows/Qwen21-edit.json` is the single-reference edit/restyle workflow
(real photo or chart → collage restyle), derived from the vox-collage app template with the
second-reference slot removed. Verified pairing: output node `461` (`SaveImageAdvanced`);
prompt and `negative_prompt` at `459:474`; reference image at node `470` via
`<UPLOADED_IMAGE>`; seed at `459:458`; latent size at `459:456` (default `1664x928`).
Do not hand a two-image template into a single-image job: a leftover second reference slot
contaminates the edit. State the text plan explicitly in the prompt — specified CJK text
renders correctly (content-driven, no per-image cap), supporting scraps get explicit
Chinese labels, short English words, or icons, and anything left unspecified is filled
with corrupted pseudo-text.

## Failure Handling

- If the server is unavailable, surface the structured setup offer. Starting ComfyUI or setting `COMFYUI_SERVER_URL` is the first fix.
- If models are missing, read `data.missing_models[]`; each item should include the file name, role, destination hint, and download URL when OpenMontage knows it.
- If custom nodes are missing, ask the user to install them through ComfyUI Manager or the workflow author's documented install path, then restart ComfyUI.
- If a long render times out locally, check ComfyUI history before retrying from scratch; the server may still have completed the prompt.
