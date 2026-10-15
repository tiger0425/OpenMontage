---
name: comfyui
description: Use when working with ComfyUI workflows in OpenMontage, including comfyui_image/comfyui_video/comfyui_music, custom workflow_json/workflow_path inputs, output_node selection, missing model setup, LoRAs, low-VRAM workflow choices, and community workflow imports.
---

# ComfyUI Workflows in OpenMontage

Use this skill before calling `comfyui_image`, `comfyui_video`, or `comfyui_music`, and when converting a community ComfyUI workflow into an OpenMontage tool call.

## Server Contract

- ComfyUI must be running before the tool can generate. The default server is `http://localhost:8188`; override it with `COMFYUI_SERVER_URL`.
- Running separate ComfyUI instances per capability (different GPU, different model set)? `COMFYUI_IMAGE_SERVER_URL` / `COMFYUI_VIDEO_SERVER_URL` / `COMFYUI_MUSIC_SERVER_URL` each override `COMFYUI_SERVER_URL` for that one tool only. Optional -- a single-server setup needs none of these.
- Health and hardware status come from `GET /system_stats`.
- Jobs are submitted to `POST /prompt`, completed outputs are read from `GET /history/{prompt_id}`, and artifact bytes are downloaded with `GET /view`.
- Long waits (video, music) prefer ComfyUI's websocket feed for immediate completion/error detection and transparently fall back to REST polling if `websocket-client` isn't installed. Either way, a timeout is recoverable: pass the error's `prompt_id` back in as `resume_prompt_id` to resume waiting on the same job instead of resubmitting it.
- Export workflows with ComfyUI's API-format JSON, not the UI layout format. If a downloaded workflow will not submit, re-export it from ComfyUI with API format enabled.

### Partner Nodes are hosted

- `gemini_omni_flash`, `seedance_2.5`, and `minimax_h3_api` in
  `comfyui_video` are official ComfyUI Partner Nodes. They call hosted APIs and
  require network access, a logged-in Comfy account, and prepaid credits.
- Do not describe Partner Nodes as local, offline, or free merely because the
  graph runs in a local ComfyUI process.
- `minimax_h3_local` is a separate open-weight path. It requires the official
  MiniMax H3 workflow exported in API format, its `output_node`, and the model
  stack reported by the tool.

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

### Video workflows need a temporal latent

- A video workflow's empty-latent node must be a **video** latent -- `EmptyHunyuanLatentVideo` for Wan 2.2 t2v, `Wan22ImageToVideoLatent` or `WanImageToVideo` for the image-conditioned variants. The frame count goes in `length`; `batch_size` is how many separate clips to generate and stays at `1`.
- `EmptyLatentImage` with `batch_size` set to the frame count is a trap: it asks for N unrelated images, and the resulting MP4 has the right frame count, duration and codec and passes `ffprobe` cleanly -- it just strobes. Check the latent node before running any unfamiliar video workflow.

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
- If a long render times out locally, check ComfyUI history before retrying from scratch; the server may still have completed the prompt -- or just call again with `resume_prompt_id` set to the `prompt_id` from the timeout error.

## Music (`comfyui_music`)

- Bundled default is ACE-Step v1 (3.5B) text-to-audio, built from ComfyUI's *native* `TextEncodeAceStepAudio`/`EmptyAceStepLatentAudio` nodes (core, not a third-party pack) -- unlike ACE-Step 1.5 or other custom node packs, v1's interface is standardized enough to bundle safely.
- `prompt` maps to the bundled workflow's `tags` field (style/genre/mood, e.g. `"upbeat electronic pop, female vocals"`), matching the same "prompt = music description" convention `suno_music` uses. `lyrics` is a separate optional field -- leave empty for instrumental, or use `[verse]`/`[chorus]`/`[bridge]` structure tags and `[zh]`/`[ja]`/`[ko]`-style language-code prefixes for non-English lines.
- `duration_seconds`, `steps`, `cfg`, `lyrics_strength`, and `seed` are patchable on the bundled workflow. Missing `ace_step_v1_3.5b.safetensors` surfaces through the same `data.missing_models[]` contract as image/video.
- Need ACE-Step 1.5, a different node pack, or a non-ACE-Step audio model? Fall back to `workflow_json`/`workflow_path` + `output_node`, exactly like a custom image/video workflow -- in that mode `prompt` becomes provenance/logging only again and must already be baked into the graph.
- `output_node` (bundled or custom) should be the node that writes the final audio -- the bundled workflow's is `SaveAudioMP3`. The client reads artifacts from that node's `"audio"` output key (parallel to `"images"` for image/video savers).
- For custom workflows, provide `workflow_name`/`workflow_model`/`workflow_model_stack` for provenance exactly as you would for a custom image/video workflow.
