# Asset Director — Fabric Showcase Pipeline

## When To Use

This stage generates all visual and audio assets for the fabric showcase video: fabric images via ComfyUI (Klein workflow), fabric motion clips via ComfyUI (LTX23 workflow), TTS narration, and BGM. Produces the `asset_manifest` artifact that records provenance for every asset.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["brief"]["fabric_brief"]` | Fabric facts, scene structure, voiceover script |
| Tools | `comfyui_image`, `comfyui_video`, `tts_selector`, `music_gen`, `audio_mixer` | Asset generation and mixing |
| Playbook | custom_only | No fixed playbook |

## Process

### 0. Truth-Gate Setup (MANDATORY first step)

Before generating any asset, read `fabric_brief.fabric_facts` and distill it into a **truth lock sheet** that every generation tool call will reference. This is the contract:

```
TRUTH LOCK:
  composition: "55% linen, 45% cotton"
  texture: "亚麻筋骨，棉柔软，亲肤透气"
  color: "复古红格（砖红+深棕），哑光"
  weight: "中厚"
  sheerness: "不透明"
  drape: "中等垂坠"
  must_not_change: [颜色, 格纹比例, 光泽度, 透明度, 成分表现]
```

Every generated image must be checked against this sheet before being accepted.

### 1. Sample Preview First (Prevents Wasted Spend)

Before batch-generating all assets, produce one sample of each expensive type and review:

1. **ComfyUI image sample**: Generate one fabric close-up image. Verify color, texture, and grain match the truth lock before generating additional scenes.
2. **ComfyUI video sample**: Generate one fabric motion clip. Verify fabric behavior (drape, weight, movement) matches fabric_facts.
3. **TTS sample**: Generate one section of narration. Confirm voice and tone fits the brand.

If rejected, adjust prompts or parameters and retry (max 2 iterations). Do not batch until approved.

### 2. Generate Fabric Images

Use `comfyui_image` with the Klein workflow for fabric still images.

**Prompt structure for fabric imagery:**

```
1. Production intent: fabric close-up / flat lay / hand touch / model
2. Truth lock: exact color, grain, texture from fabric_brief.fabric_facts
3. Light/camera: soft diffused light, macro (for close-up), shallow DoF
4. Brand mood: reference style_direction from fabric_brief.ad_intent
5. Negative constraints: no invented texture, no gloss/shine if fabric is matte, no text, no logos
6. Aspect ratio: from fabric_brief.ad_intent.aspect_ratio
```

**Key parameters:**

| Parameter | Typical Value | Notes |
|-----------|---------------|-------|
| `workflow_path` | `tools/_comfyui/workflows/klein_fabric.json` | Bundled fabric image workflow |
| `output_node` | ComfyUI output node ID | Must match the Klein workflow's save node |
| `seed` | Random or fixed | Fixed for reproducibility |

### 3. Generate Fabric Video Clips

Use `comfyui_video` with the LTX23 workflow for fabric motion scenes.

**Prompt structure for fabric video:**

```
1. Production intent: fabric swaying / hand stroking / model walking
2. Truth lock: same as image — exact color, grain, drape
3. Camera: slow dolly / handheld / locked-off
4. Fabric behavior: light swinging, natural drape, no impossible physics
5. Negative: no invented details, no garment distortion
```

**Key parameters:**

| Parameter | Typical Value | Notes |
|-----------|---------------|-------|
| `workflow_path` | `tools/_comfyui/workflows/ltx23_fabric.json` | Bundled fabric video workflow |
| `output_node` | ComfyUI output node ID | Must match the LTX workflow's save node |
| `reference_image_path` | Generated image from prior step | First frame for I2V |
| `num_frames` | 97 (for ~5s at ~20fps) | Adjust per scene duration |

### 4. Generate TTS Narration

Use `tts_selector` to generate voiceover from `fabric_brief.voiceover_script`.

**Rules:**

- **Do not modify the script text.** The script has been approved at the brief stage and any change could introduce unsubstantiated claims.
- Select a voice that matches the brand tone (e.g., warm female for "复古文艺", neutral male for "现代简约").
- Generate sample first, confirm with user, then batch the full script.

### 5. Generate or Select BGM

Use `music_gen` to generate a BGM track.

- Choose BGM that matches `fabric_brief.ad_intent.style_direction`:
  - 复古/文艺 → gentle piano, acoustic guitar, light strings
  - 现代/简约 → ambient pad, subtle electronic
  - 活力 → light percussion, upbeat acoustic
- Target duration = `fabric_brief.ad_intent.duration` + 3s padding for fade out
- Generate a short sample (5-10s) first, confirm style with user.

### 6. Build Asset Manifest

After all assets are generated, build and validate the `asset_manifest`:

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "fabric_closeup_01",
      "type": "image",
      "path": "projects/<id>/assets/images/fabric_closeup.png",
      "source_tool": "comfyui_image",
      "scene_id": "scene_01",
      "prompt": "...",
      "seed": 12345,
      "model": "klein-workflow"
    },
    {
      "id": "fabric_motion_01",
      "type": "video",
      "path": "projects/<id>/assets/video/fabric_motion.mp4",
      "source_tool": "comfyui_video",
      "scene_id": "scene_02",
      "prompt": "...",
      "seed": 67890,
      "model": "ltx23-workflow"
    }
  ],
  "total_cost_usd": 0.0
}
```

Every asset must include:
- **source_tool** — the exact tool name used
- **scene_id** — which scene this asset belongs to
- **provenance** — seed, prompt, model/workflow name

### 7. Audio Mixing

Use `audio_mixer` to mix TTS narration with BGM:

- Narration volume: 1.0 (full)
- BGM volume: 0.15-0.20 (background)
- Fade out: last 2s of video
- Output: `audio/mixed.mp3`, duration matching target

## Quality Gate

- All generated images checked against the truth lock sheet
- TTS narration matches voiceover_script verbatim
- All file paths in asset_manifest resolve to existing files
- provenance block complete for every asset
- Total cost within fabric_brief budget ($0.50)

## Common Pitfalls

- **Truth-Gate drift**: ComfyUI generates fabric that looks different from the reference. Always check against the truth lock before accepting.
- **Skipping sample preview**: Generating all 4 scene images before verifying one. Always sample first.
- **Missing provenance**: Seeds and model names should be recorded. We need them for reproducibility and QA.
- **Script modification in TTS**: The voiceover script was approved for claim accuracy. Do not let TTS deviate from it.

## When You Do Not Know How

If you encounter a generation technique, provider behavior, or prompting pattern you are unsure about:

1. **Search the web** for current best practices — ComfyUI workflows and model versions change frequently.
2. **Check `.agents/skills/`** for existing Layer 3 knowledge.
3. **If neither helps**, write a project-scoped skill documenting what you learned.
4. **Log it** in the decision log: `category: "capability_extension"`, `subject: "learned technique: <name>"`

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
