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

### HARD RULES (ABSOLUTE — must read before doing anything else)

1. **WORKFLOW FILES ARE LOCKED.** You MUST use exactly these two files:
   - Image generation → `tools/_comfyui/workflows/klein_fabric.json` ONLY
   - Video generation → `tools/_comfyui/workflows/ltx23_fabric.json` ONLY
   - Do NOT use any other workflow in `tools/_comfyui/workflows/` (e.g. `ltx23_i2v_vertical.json`, `wan22-*.json`, `flux2-*.json` are WRONG)

2. **SCENE ITERATION IS COMPULSORY.** Read `fabric_brief.scene_structure` and generate assets for **EVERY SCENE** in the list. Do NOT skip any scene. If the scene structure has 5 entries, you must produce 5 sets of assets. If only 3 scenes have assets after you finish, that is WRONG.

3. **ORDER IS LOCKED.** Images MUST be generated BEFORE video. Video generation takes `reference_image_path` from the prior image step. Generating video without a reference image is WRONG.

4. **IMAGE COUNT IS LOCKED.** Each video scene needs its OWN dedicated reference image. For a 5-scene fabric video with scenes [特写(no video), 飘动(video), 触感(video), 模特(video), CTA(no video)], you need exactly 3 images and 3 videos — one per video scene. Do NOT generate one image and use it for all videos.

5. **IMAGE UPLOAD IS AUTOMATIC.** The `comfyui_image` and `comfyui_video` tools handle image upload to ComfyUI's server internally via `ComfyUIClient.upload_image()`. You MUST call these tools (they are in the registry as `comfyui_image` and `comfyui_video`). Do NOT write custom code to call the ComfyUI API directly — let the tool handle the upload cycle.

6. **TRUTH-GATE IS LOCKED.** Every generated asset MUST be checked against `fabric_brief.fabric_facts` before acceptance. If the fabric color/texture/drape in the output doesn't match the truth sheet, reject it immediately.

### 0. Truth-Gate Setup

Read `fabric_brief.fabric_facts` and distill it into a truth lock sheet:

```
TRUTH LOCK:
  composition: "<from fabric_brief>"
  texture: "<from fabric_brief>"
  color: "<from fabric_brief>"
  weight: "<from fabric_brief>"
  sheerness: "<from fabric_brief>"
  drape: "<from fabric_brief>"
  must_not_change: [颜色, 格纹比例, 光泽度, 透明度, 成分表现]
```

Every generated asset MUST pass this check before being accepted.

### 1. Sample Preview (Prevents Wasted Spend)

Before batch-generating all assets, produce ONE sample of each type and review:

1. **ComfyUI image sample** — one fabric close-up. Verify texture, color, grain match truth lock before generating more.
2. **ComfyUI video sample** — one fabric motion clip. Verify fabric behavior matches fabric_facts.
3. **TTS sample** — one section of narration. Confirm voice fits brand.

Max 2 iterations per sample if rejected. Do NOT batch until ALL samples approved.

### 2. Generate Fabric Images (MUST run before video step)

**Generate ONE image per video scene.** Read `fabric_brief.scene_structure` and create a separate image for every scene that needs a video clip. For the standard 5-scene structure, that means 3 images: one for 面料飘动, one for 手部触碰, one for 模特上身 (the close-up scene uses the original reference image).

Use `comfyui_image` with workflow `tools/_comfyui/workflows/klein_fabric.json`:

⚠️ **CRITICAL: Klein is I2I (image-to-image). DO NOT write lighting descriptions.**
The reference image provides all lighting and texture cues. Adding lighting prompts
(e.g. "soft light from left", "diffused side light") causes the model to try to
re-light the fabric, producing color drift and quality loss. Keep prompts to
composition, truth lock, and negative constraints only.

```
Prompt structure (I2I mode — NO lighting):
1. Production intent: fabric close-up / flat lay / hand touch / model
2. Truth lock: exact color, grain, texture from fabric_brief.fabric_facts
3. Framing/composition: macro, shallow DoF, angle
4. Brand mood: reference style_direction from fabric_brief.ad_intent
5. Negative constraints: no invented texture, no gloss/shine if fabric is matte, no text, no logos
6. Aspect ratio: from fabric_brief.ad_intent.aspect_ratio
```

Parameters:

| Parameter | Value (LOCKED) |
|-----------|----------------|
| `workflow_path` | `tools/_comfyui/workflows/klein_fabric.json` |
| `output_node` | Must match Klein workflow's save node |
| `seed` | Random or fixed |

### 3. Generate Fabric Video Clips (MUST run after ALL images exist)

For each scene that requires video, run `comfyui_video` once. Each video uses the image generated for that specific scene as its `reference_image_path`. Do NOT reuse the same image for multiple video clips.

Use `comfyui_video` with workflow `tools/_comfyui/workflows/ltx23_fabric.json`:

⚠️ **I2I image rule — NO static lighting descriptions.** Static lighting ("soft light from left 45°") in the prompt conflicts with the reference image's actual lighting, causing color drift. This does NOT apply to DYNAMIC lighting changes in video — those are valid motion cues.

⚠️ **Video prompt MUST be short and motion-specific.** LTX23 is a small video model. Long prompts or abstract descriptions (e.g. "展示垂坠和重量") produce chaotic, meaningless motion. Describe only ONE specific motion clearly.

```
Prompt structure for LTX23 video (keep under 20 words):
1. Subject (from scene): fabric / hand on fabric / person
2. ONE motion: "fabric gently swaying left to right" / "hand slowly stroking from top to bottom"
   OR dynamic light change: "sunlight slowly sweeping across fabric"
3. Speed: slowly / gently / calmly
4. What stays still: "background static"
5. Negative: no invented texture, no color shift
```

**Video prompts can include DYNAMIC lighting changes as motion cues** — these are not static lighting setups and do not conflict with I2I:

| Valid dynamic light prompt | What it does |
|---------------------------|--------------|
| "Sunlight slowly sweeping across fabric from left to right" | 光线缓缓扫过，展示纹理变化 |
| "Warm light gradually brightening on fabric surface" | 灯光渐渐亮起，凸显质感 |
| "Soft shadow moving across fabric as light source shifts" | 阴影缓缓移动，展示立体感 |

**Scene-specific example prompts:**

| Scene | Effective prompt | What it describes |
|-------|-----------------|-------------------|
| 面料飘动 | "Fabric gently swaying left to right, sunlight slowly sweeping across" | 飘动+光线变化=纹理层次感 |
| 手部触碰 | "Hand slowly pressing fabric, fingers gently rubbing surface" | 静止光线，专注触感 |
| 模特上身 | "Person walking forward slowly, fabric flowing naturally" | 静态光线，聚焦穿着效果 |

**Common failure patterns to avoid:**

| Bad prompt (too vague or conflicting) | Result | Good alternative |
|------------------------|--------|-----------------|
| "面料展示垂坠和重量" | 画面乱动/无意义扭曲 | "Fabric gently swaying left to right" |
| "手抚过面料，展示柔软度" | 手部变形/动作不自然 | "Hand slowly pressing fabric surface" |
| "柔和侧光从上往下" (静态光线 in I2I) | 颜色漂移 | (I2I禁止静态光线，但视频可写 "sunlight slowly sweeping") |
| "模特穿着连衣裙" | 模特抽搐/衣服飘动异常 | "Person walking forward slowly" |
| "展示竹节纹理细节" | 镜头乱晃/画面闪烁 | (纹理细节由参考图提供，视频prompt只写运动) |
```

Parameters:

| Parameter | Value (LOCKED) |
|-----------|----------------|
| `workflow_path` | `tools/_comfyui/workflows/ltx23_fabric.json` |
| `output_node` | Must match LTX workflow's save node |
| `reference_image_path` | MUST be the image generated in step 2 |
| `num_frames` | 97 (for ~5s at ~20fps)

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

### 6. Build Asset Manifest (must cover ALL scenes)

After ALL assets from ALL scenes are generated, build the `asset_manifest`. It must have one entry per generated asset per scene — if `fabric_brief.scene_structure` has 5 scenes and 3 of them need images+video, the manifest should have 6 entries (3 images + 3 videos). Count them. If the count is wrong, you skipped a scene.

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "fabric_motion_image",
      "type": "image",
      "path": "projects/<id>/assets/images/scene2_fabric_flat.jpg",
      "source_tool": "comfyui_image",
      "scene_id": "scene_02",
      "prompt": "...",
      "seed": 12345,
      "model": "klein_fabric"
    },
    {
      "id": "fabric_motion_video",
      "type": "video",
      "path": "projects/<id>/assets/video/scene2_fabric_flow.mp4",
      "source_tool": "comfyui_video",
      "scene_id": "scene_02",
      "prompt": "...",
      "seed": 67890,
      "model": "ltx23_fabric"
    },
    {
      "id": "hand_touch_image",
      "type": "image",
      "path": "projects/<id>/assets/images/scene3_hand_touch.jpg",
      "source_tool": "comfyui_image",
      "scene_id": "scene_03",
      "prompt": "...",
      "seed": 12346,
      "model": "klein_fabric"
    },
    {
      "id": "hand_touch_video",
      "type": "video",
      "path": "projects/<id>/assets/video/scene3_hand_touch.mp4",
      "source_tool": "comfyui_video",
      "scene_id": "scene_03",
      "prompt": "...",
      "seed": 67891,
      "model": "ltx23_fabric"
    }
  ],
  "total_cost_usd": 0.0
}
```

Every asset must include:
- **source_tool** — the exact tool name used
- **scene_id** — which scene this asset belongs to
- **provenance** — seed, prompt, model/workflow name

**VALIDATION: Count `asset_manifest.assets` and compare to expected.**
  - Example: 5 scenes [特写=no gen, 飘动=img+vid, 触感=img+vid, 模特=img+vid, CTA=no gen] → expected count = 6
  - If your manifest has fewer entries than expected, you skipped a scene. Go back.

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
