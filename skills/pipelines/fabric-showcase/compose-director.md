# Compose Director — Fabric Showcase Pipeline

## When To Use

Render the fabric showcase video using HyperFrames. This stage assembles generated assets (images, videos, audio) into the final HTML/GSAP composition, applies motion design, mixes audio, and verifies the output.

## Runtime Lock (MANDATORY — no selection needed)

`render_runtime` is **locked to 'hyperframes'** for this pipeline. Fabric showcase videos use HTML/GSAP for kinetic title cards, light-reveal effects, SVG product line art, and scene transitions — all native to HyperFrames. There is no runtime selection step.

- **Silent runtime swap is a CRITICAL governance violation.** If HyperFrames is unavailable (Node < 22, missing ffmpeg/npx), surface a structured blocker per AGENT_GUIDE.md procedures — do not fall back to FFmpeg or Remotion without user approval and a logged `render_runtime_selection` decision.
- **Pass `fabric_brief` to `video_compose.execute()`** so the tool's in-tool swap-detection check runs against the brief directly.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json`, `schemas/artifacts/final_review.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]`, `state.artifacts["brief"]["fabric_brief"]` | Assets and direction |
| Tools | `video_compose` (HyperFrames route), `audio_mixer` | Final assembly |
| Playbook | custom_only | No fixed playbook |

## Process

### 1. Verify HyperFrames Readiness

```bash
npx hyperframes doctor
```

Must pass before render attempt. Common failures:
- Node version < 22 → upgrade Node
- ffmpeg not found → install ffmpeg
- npx not found → install npm/node

### 2. Set Working Directory (CRITICAL — must be project dir)

Before running any hyperframes command, change to the project directory:
```bash
cd projects/<project-id>/
```
All hyperframes commands (`init`, `lint`, `validate`, `render`) MUST be run from `projects/<project-id>/`. Running them from the repo root creates files in the wrong place.

### 3. Build the Composition

Use the scene structure from `fabric_brief.scene_structure` to build the HyperFrames `index.html`.

**Composition template:**

```html
<div data-duration="{total_duration}" data-width="1080" data-height="1920" data-fps="30">
  <!-- Scene 1: Fabric close-up + title reveal -->
  <div class="scene" data-start="0" data-duration="{scene_1_duration}">
    <video class="clip" data-src="assets/video/scene1.mp4" ...>
    <h1 class="title">复古红格</h1>
    ...
  </div>

  <!-- Scene 2: Fabric motion -->
  <div class="scene" data-start="{s1_end}" data-duration="{scene_2_duration}">
    <video class="clip" data-src="assets/video/scene2.mp4" ...>
    ...
  </div>

  <!-- Scene 3: Hand interaction -->
  ...

  <!-- Scene 4: Model -->
  <div class="scene" data-start="{s3_end}" data-duration="{scene_4_duration}">
    <video class="clip" data-src="assets/video/scene4.mp4" ...>
    ...
  </div>

  <!-- Scene 5: CTA/收尾 -->
  <div class="scene" data-start="{s4_end}" data-duration="{scene_5_duration}">
    <div class="cta-card">
      <h2 class="cta-title">品牌名</h2>
      <p class="cta-subtitle">标语/成分</p>
    </div>
    ...
  </div>
</div>
```

**Key design patterns from verified production runs:**

- **Light reveal**: Use transform-based dark panels (`.scene-dark-left`, `.scene-dark-right`) that slide apart — NOT CSS mask (causes stutter).
- **Audio**: Single `<audio>` element for mixed BGM+voiceover, no separate voiceover track.
- **Product line SVG icons**: Optional — only if `fabric_brief.product_line_drawings.enabled` is true. Use stroke-dasharray/draw SVG animation for product outlines.
- **Title typography**: Use Google Fonts or downloaded calligraphy fonts for Chinese titles. Font path must be relative to project root.
- **Ken Burns effect**: For static model images, apply CSS `scale` + `translateX` transforms for subtle camera motion.
- **CTA/收尾**: 黑底或半透明底文字卡，品牌名大标题居中，BGM 渐弱淡出，无旁白。不依赖视频素材。

### 4. Audio Mixing

Use `audio_mixer` if the BGM and narration were not already mixed in the assets stage:

- BGM volume: ≤ 0.20
- Voiceover volume: 1.0
- Fade out last 2s
- Output duration matches target

### 5. Render

```bash
npm run render
```

With quality setting: `-q high` for hero renders.

Output path: `renders/{project_name}_{timestamp}.mp4`

### 6. QA (ffprobe Verification)

Run these checks on every render:

```bash
# Resolution
ffprobe -v error -select_streams v:0 -show_entries stream=width,height

# Duration
ffprobe -v error -show_entries format=duration

# Audio presence
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name

# File size
ls -lh renders/video.mp4
```

### 7. Post-Render Self-Review

Extract keyframes at scene boundaries and visually inspect:

- Scene 1 (t=0.5s, t=2.5s): Close-up texture visible? Title animation smooth?
- Scene 2 (t=5.5s, t=7.0s): Fabric movement natural? Color preserved?
- Scene 3 (t=9.5s, t=11.0s): Hand interaction realistic? Fabric folds natural?
- Scene 4 (t=13.5s, t=15.0s): Model crop appropriate? Fabric visible?
- Scene 5 (t=17.5s, t=19.0s): CTA text clear? Audio fade-out smooth?

Log findings in `final_review` artifact and append `self_review_completed: true`.

### 8. Build Render Report

```json
{
  "version": "1.0",
  "outputs": [
    {
      "path": "renders/video.mp4",
      "format": "mp4",
      "resolution": "1080x1920",
      "duration_seconds": 20.0,
      "fps": 30,
      "codec": "h264",
      "audio_codec": "aac",
      "platform_target": "xiaohongshu"
    }
  ],
  "render_time_seconds": 120.0,
  "warnings": [],
  "render_grammar": "product-reveal",
  "self_review_completed": true
}
```

## Quality Gate

- `hyperframes doctor` passes before render
- `hyperframes lint` and `validate` pass
- ffprobe confirms duration within ±10% of target
- Audio track present with narration clear
- render_runtime='hyperframes' verified in render_report
- Self-review completed with per-scene quality notes

## Common Pitfalls

- **Mask-based reveal**: Fabric promotional videos often use dark-to-light reveal effects. Use transform-based panels, not CSS mask (mask caused visible stutter in production).
- **Font issues on Windows**: ffmpeg drawtext fails with Chinese characters on Windows. Use Python Pillow for cover text or embed fonts via `@font-face` in HTML for HyperFrames.
- **Duration mismatch**: Scene timings in `data-start`/`data-duration` must sum exactly to `fabric_brief.ad_intent.duration`. A single second off breaks platform uploads.
- **Audio sync**: After mixing, verify that voiceover end aligns with final scene — narration that cuts off before video ends looks unprofessional.

---

## Gate Reminder (Binding)

This stage does NOT gate on human approval (`human_approval_default: false`). Proceed to publish after successful render and ffprobe validation. Write checkpoint as `completed` and continue — do not wait.
