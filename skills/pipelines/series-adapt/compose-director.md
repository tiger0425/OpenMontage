# Compose Director — series-adapt Pipeline

## When to Use

You are the **Compose Director** for a series-adapt episode. Your job is to take the generated assets (images, narration, music) and assemble them into a Vox-style documentary composition via HyperFrames HTML/GSAP. You scaffold the workspace, write `index.html`, run lint/validate, render to `final.mp4`, and verify the output.

This stage bundles three sub-steps that in other pipelines are separate stages (edit + compose + render), because HyperFrames handles all three natively.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan.json` | Scene sequence with timing and animation types |
| `asset_manifest.json` | File paths for all images and audio |
| `apps/series-adapt/config.yaml` | Composition settings, color scheme |
| **`projects/<series>/DESIGN_SYSTEM.md`** | Series design system — palette, typography, subtitles, SFX, transitions |
| `styles/vox-collage.yaml` | Generic style-library playbook |
| `hyperframes_compose` | Scaffold, lint, validate, render |
| `video_compose` (optional) | ffprobe validation |

## Process

### Step 0: HyperFrames capability refresh

Before composing, run the per-session capability check:

```bash
npx hyperframes --version
npx hyperframes --help
npx hyperframes catalog --json
```

Note any new features, blocks, or deprecated flags. Use the latest available capabilities.

### Step 1: Scaffold workspace

Create the episode's HyperFrames workspace:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/hyperframes/
├── index.html
├── hyperframes.json
├── DESIGN.md
├── compositions/
└── assets/  # (symlinks or copies of generated assets)
```

Call `hyperframes_compose` operation=`scaffold` with the episode's scene_plan and asset_manifest. Stage all image and audio assets into the workspace.

### Step 2: Write Vox-style index.html

Write the HyperFrames composition with the following Vox design system:

**Global style (CSS custom properties):**
```css
:root {
  --color-bg: #1a1a2e;
  --color-fg: #e0e0e0;
  --color-accent: #c1440e;
  --color-military-green: #4a6741;
  --color-sand: #c4a35a;
  --color-chart-blue: #3a7ca5;
  --font-heading: 'Georgia', serif;
  --font-body: 'system-ui', sans-serif;
}
```

**Scene composition rules:**
- Each scene is a timed `<section>` with `data-clip` attributes
- Scene transitions via GSAP timelines (fade, slide, zoom)
- Background: dark (#1a1a2e) with military-green accents
- Image treatment: tank illustrations animate via GSAP `scale` + `x/y` for pan-zoom effect
- Charts: SVG with staggered reveal animation (bars grow from zero, lines draw from left)
- Map timelines: CSS-positioned markers appear sequentially with labels
- Text cards: Full-screen with typewriter effect for quotes/statistics
- Overlay text: lower-third style labels with accent color left border

**Audio:**
```html
<audio id="narration" src="assets/audio/seg_001.wav" data-start="0">
```

**Animation palette (per scene_type):**

| scene_type | GSAP approach |
|---|---|
| tank_illustration | `gsap.fromTo(img, {scale:1.1, x:-20}, {scale:1, x:0, duration:scene_dur, ease:'power2.out'})` |
| stat_chart | Staggered `gsap.from('.bar', {scaleY:0, duration:0.8, stagger:0.1, transformOrigin:'bottom'})` |
| map_timeline | Sequential `gsap.to('.marker', {opacity:1, scale:1, stagger:0.5})` with connecting line draw |
| text_card | Typewriter via GSAP TextPlugin or CSS animation |
| comparison_grid | Two panels slide in from opposite sides, `gsap.from('.left', {x:-100})` + `gsap.from('.right', {x:100})` simultaneously |

### Step 2b: Scene transitions = cross dissolve (not hard cuts, not wipes)

The proven transition pattern (ep-01 S01):

1. **Scene windows overlap 0.5s** on alternating `data-track-index` (odd scenes track 1, even scenes track 2 — same-track overlap fails lint).
2. **Each scene's board layer** (`<div class="board">` with an id, CSS `opacity:0`) gets two tweens:
   - fade in: `tl.fromTo("#bd-b1", {opacity:0}, {opacity:1, duration:0.5, ease:"power1.out"}, scene_start + 0.05)`
   - fade out: `tl.to("#bd-b1", {opacity:0, duration:0.45, ease:"power1.in"}, scene_end - 0.45)`
   - The 0.5s overlap is exactly the dissolve: old scene fades out while the new fades in — "一进一出".
3. **Element entrances live inside the board** and start after the board begins fading in (scene_start + 0.3).
4. Do NOT use a full-screen paper wipe between scenes (reads as a flash); keep a single shared `#w1` wipe element only for the opening.
5. Scale+opacity must be animated in ONE `fromTo` (two overlapping tweens on the same property trigger lint errors).

### Step 2c: Word-synced bilingual subtitles (karaoke highlight)

1. **Transcribe the final narration WAV** (transcriber tool, word timestamps enabled).
2. Build subtitle HTML at the ROOT level (not inside scene sections — inside a clip they get clipped by the scene window):
   - `.sub` container: `position:absolute; left:0; right:0; bottom:76px; z-index:90; opacity:0; text-align:center`
   - `.sub-en`: English, one `<span class="wk">` per word, 34px, Courier-style
   - `.sub-zh`: Chinese translation, 34px, PingFang/YaHei
3. Timing:
   - Show window = `[voice_start + 0.1, voice_end + 0.35]`, fade in 0.2s, fade out 0.25s — short sentences must still be readable (never let a 0.8s sentence flash for 0.4s).
   - **Karaoke cumulative highlight**: each word turns `color:#C0392B; fontWeight:800` at its word timestamp and STAYS (never reverts) — spoken words accumulate red+bold, unspoken stay paper-white 500.
   - After the fade-out, add a `tl.set(sub, {opacity:0})` hard kill (prevents stale visibility on seek).
4. Chinese line = the English narration translated (follows the dub, not the source video's original words).

### Step 2d: Paper-craft SFX (VOX paper ASMR)

Voice-only documentaries benefit from subtle paper sounds on element landings (per the Vox spec: paper slide, cardstock tap, tape press, stamp thud, string zip, pin click — all subtle).

1. Generate the 6 SFX with ffmpeg synthesized tones/noise (no SFX provider configured):
   - `paper_slide` (filtered pink noise, 0.9s), `paper_tap` (180Hz 0.09s), `tape_press` (90Hz 0.28s), `stamp_thud` (75Hz 0.22s), `string_zip` (600Hz 0.18s), `pin_click` (2200Hz 0.06s)
2. Add one `<audio src="assets/sfx/<name>.wav" data-start="<landing_time>" data-volume="0.28">` instance PER element landing (HyperFrames plays each `data-start` instance independently; give each an `id` and a `<track>` to pass lint).
3. Map by element: photo/board → paper_slide, strip/label → tape_press, stamp → stamp_thud, string → string_zip, pin → pin_click.
4. Mix levels: BGM ~0.13, narration 1.0, SFX ~0.28 — SFX must stay under the voice.

### Step 3: Run quality checks

```bash
# In the hyperframes workspace:
npx hyperframes lint    # Must exit 0 — structural checks
npx hyperframes validate # Browser-based visual check
```

Address any lint issues before proceeding to render.

### Step 4: Render

```bash
npx hyperframes render --strict
```

Output: `hyperframes/renders/final.mp4`

### Step 5: Verify output

Run `ffprobe` on `final.mp4`:
- Video codec: h264
- Resolution: 1920×1080
- Frame rate: ≥24 fps
- Duration: within ±5% of `scene_plan.total_duration_seconds`
- Audio stream present, stereo, ≥44100 Hz

### Step 6: Produce composition_report

Output `composition_report.json`:

```json
{
  "episode_num": 1,
  "render_runtime": "hyperframes",
  "output_path": "hyperframes/renders/final.mp4",
  "hyperframes_version": "0.x.x",
  "lint_passed": true,
  "validate_passed": true,
  "render_duration_seconds": 598,
  "render_target_seconds": 600,
  "resolution": "1920x1080",
  "fps": 30,
  "file_size_mb": 245,
  "ffprobe_valid": true,
  "generated_at": "ISO timestamp"
}
```

Update tracking.db status to `rendered`.

## Quality Rules

- `hyperframes lint` must exit 0 before render
- `hyperframes validate` must pass before render
- Rendered video must be playable and have audio
- Duration must be within ±5% of target
- Every scene from scene_plan must be present in the output
- No raw Chinese text visible on screen (all labels/overlays in English)
- The HyperFrames workspace is self-contained (no external URL dependencies for assets)
