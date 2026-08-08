# Compose Director — repo-to-video Pipeline

## When to Use

You are the **Compose Director** for a repo-to-video episode. Your job is to take the
generated assets (narration, BGM, SFX, code/README material) and assemble them into
a metro-map style HyperFrames HTML/GSAP composition, then lint, validate, render to
`final.mp4`, and verify the output. This stage bundles edit + compose + render.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan.json` | Scene sequence with timing + motion |
| `asset_manifest.json` | File paths for narration, bgm, sfx |
| `script.json` | Narration text per scene |
| `apps/repo-to-video/config.yaml` | Composition config, color scheme |
| `fetch_report.json` | README / real code for code-window scenes |
| `hyperframes_compose` | Scaffold, lint, validate, render |
| `video_compose` (optional) | ffprobe validation |

## Process

### Step 0: HyperFrames capability refresh

```bash
npx hyperframes --version
npx hyperframes catalog --json
```

### Step 1: Scaffold workspace

Create the HyperFrames workspace:
```
projects/repo-to-video/{slug}/hyperframes/
├── index.html
├── hyperframes.json
├── compositions/
└── assets/  # symlinks or copies of narration/bgm/sfx/README
```

Call `hyperframes_compose operation=scaffold` with scene_plan + asset_manifest.
Stage all audio and the real code/README material.

### Step 2: Write the metro-map index.html

**Global style (CSS custom properties) — from scene-director palette:**
```css
:root {
  --color-bg: #0B0D0A;
  --color-panel: #171C14;
  --color-fg: #F3F0E8;
  --color-sub: #A9B0A0;
  --color-accent: #C7F04B;
  --color-risk: #FF6B4A;
  --color-line: #35402F;
  --font-cn: 'Noto Sans SC';
  --font-mono: 'JetBrains Mono';
}
```

**Audio wiring:**
```html
<audio id="narration-scene01" src="assets/audio/seg_001.wav" data-start="0.4"></audio>
<audio id="bgm" src="assets/audio/bgm.mp3" data-start="0" data-volume="0.13"></audio>
<audio id="sfx-node01" src="assets/sfx/soft-boop.wav" data-start="12.5" data-volume="0.28"></audio>
```
Mix levels: BGM ~0.13, narration 1.0, SFX ~0.28.

**Scene composition rules (per scene_plan):**
- Each scene is a timed `<section>` with `data-clip` attributes
- Scene transitions via GSAP (see ledger pattern: cut-the-curve / inverse zoom-through)
- **code_window**: real repo code from fetch stage in a mono-font window, path sweeps
- **graph_map**: SVG nodes + edges draw via `stroke-dashoffset`, nodes light up sequentially
- **stat_band**: numbers in JetBrains Mono, scale band with "基线为读取整个源码语料" footnote
- **terminal**: commands typed in sequence (install → build → install-mcp), graph forms on the right
- **text_card**: stamp-appear title/closing cards

**Motion rules (borrowed from series-adapt compose-director — see that file for
implementation details):**
- ≥2 moving elements per scene; adjacent scenes differ in camera_move + entrance
- No morph / warp / vortex / explode; no orbit / roll / whip / fast_zoom
- FINITE repeats only — `repeat: -1` FAILS lint. Compute `repeat = floor((scene_end - loop_start)/cycle) - 1` with yoyo, sine.inOut, `overwrite:"auto"`.
- Scenes >12s = 2+ sub-shots, each with distinct visual event
- Boundary rule: fades end ≥0.1s BEFORE clip boundary (`tl.set` hard kill at boundary)

### Step 3: SFX placement

Place each SFX `<audio data-start="<landing_time>" data-volume="0.28">` at the element
landing time per `asset_manifest.sfx.set` mapping. SFX under the voice.

### Step 4: Quality checks

```bash
npx hyperframes lint
npx hyperframes validate
```
Address all lint issues before render.

### Step 5: Render

```bash
npx hyperframes render --strict --fps 30
```
> Render at 30fps — `--fps 12` breaks audio extraction in the hyperframes CLI.
> The stepped "12fps Vox feel" comes from keyframes, not render frame rate.

**Sync rules (borrowed from series-adapt, verified):**
- After assemble, verify `scene-1.data-start + 0.4 ≈ vo.data-start` (±0.2s)
- Outro holds ≥2s after last narration line
- Final fade ≤0.5s (never swallow the last word)

### Step 6: Verify output

`ffprobe` on `final.mp4`:
- h264, 1920×1080, ≥24fps
- Duration within ±5% of scene_plan total
- Audio stream present, stereo, ≥44100 Hz

### Step 7: Produce composition_report

```json
{
  "slug": "code-review-graph",
  "render_runtime": "hyperframes",
  "output_path": "hyperframes/renders/final.mp4",
  "hyperframes_version": "0.x.x",
  "lint_passed": true,
  "validate_passed": true,
  "render_duration_seconds": 178,
  "render_target_seconds": 180,
  "resolution": "1920x1080",
  "fps": 30,
  "ffprobe_valid": true,
  "generated_at": "ISO timestamp"
}
```

## Quality Rules

- `hyperframes lint` exit 0 before render
- Every scene from scene_plan present in output
- Audio levels: narration 1.0 / BGM 0.13 / SFX 0.28
- No raw English README text dumped as-is on screen (labels ≤8 字中文)
- Self-contained workspace (no external URL dependencies for assets)
