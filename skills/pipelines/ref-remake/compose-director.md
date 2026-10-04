# Compose Director — ref-remake Pipeline

## When to Use

You are the **Compose Director** for a ref-remake episode. Your job is to build
the HyperFrames composition from the measured narration timeline + textless AI
images, render the final 9:16 vertical MP4, and produce a `composition_report`.
This is a **HEAVY STAGE** — dispatch rendering to a Compute Worker with `--json`
single-line report.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan` | Scene order + narration mapping |
| `asset_manifest` | Measured TTS durations + image paths |
| `styles/ref-remake.yaml` | V2 点缀式 + typography + motion rules |
| HyperFrames skills | `hyperframes`, `hyperframes-core`, `hyperframes-animation` — read before authoring |

## Process

### Step 1: Build the timeline

- Use **measured TTS durations** from asset_manifest (word-ratio fallback if a
  duration is missing). Do NOT use fixed 10s segments.
- Scene order follows scene_plan; each scene window = its narration segment.

### Step 2: Author index.html

- Textless AI images as scene backgrounds/hero; **all text (titles, numbers,
  captions, subtitles) via HTML overlay** — never baked into images.
- Scene divs: `data-layout-allow-overflow` (push transition overflow is
  expected); after transition, old scene `opacity: 0`.
- `pushWithRank` only for scenes with rank badges; ending scene uses plain push.
- Chinese fonts: declare `@font-face { src: local(...) }` for Noto Sans SC /
  PingFang SC / Microsoft YaHei — required or lint fails.
- Delete `index.sample.html` before lint (multiple_root_compositions).
- Default **NO BGM**; only if the user requested it, mix via `audio_mixer`
  below -18dB under narration.

### Step 3: Lint, validate, render

1. `hyperframes check` (lint) — must pass with exit 0.
2. `hyperframes validate` (browser-based) — must pass.
3. Render: `--resolution portrait --fps 30` (9:16, 1080x1920).
4. `composition_report.json`:
```json
{
  "output": "renders/final.mp4",
  "duration_s": 200.4,
  "render_runtime": "hyperframes",
  "lint_exit": 0,
  "validate_exit": 0,
  "ffprobe": {"width": 1080, "height": 1920, "fps": 30.0}
}
```

## Review Notes

- build_index-style scripts: the index.html path is relative to the OpenMontage
  ROOT — run from the repo root, never from inside the project dir (handoff
  pitfall: nested path renders the 10s template).
- Runtime choice: `render_runtime=hyperframes` is the pipeline default; if both
  Remotion and HyperFrames are available, per AGENT_GUIDE the proposal must have
  presented both — record `options_considered` in the decision log.
- HEAVY: render via Compute Worker; never block the lead session.
