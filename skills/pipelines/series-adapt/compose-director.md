# Compose Director — series-adapt Pipeline

## When to Use

> **遇到问题先查 [known-issues.md](known-issues.md)（症状索引 K-01~K-13）**

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
| `references/vox-motion-library.md` | camera_move implementations + element_motion engine + GSAP paper-feel moves |
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

**Generator pipeline (L-018 — verified s04, one-pass no rework):** for episodes 2+, do NOT hand-write per-scene index.html. Use the parameterized generators (keep them in `skills/pipelines/series-adapt/tools/`):
1. write `{sid}_windows.json` (L-009 continuous windows) + `{sid}_design.json` (per-scene layout/label/camera) + `{sid}_zh.json` (per-segment Chinese subtitles)
2. `python build_episode_parts.py {sid} {num_scenes} {total_dur}` → parts json
3. `python assemble_episode.py {sid} {total_dur} {num_scenes}` → workspace + index.html
4. lint + render. The generators already encode: cross-dissolve boards, finite-repeat continuous micro-motion, multi-element entrances, word-synced karaoke subtitles, per-landing SFX.

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

### Step 2a: camera_move + element_motion (per-scene motion, from scene_plan)

Each scene carries `camera_move` and `element_motion` from the scene plan — implement per `references/vox-motion-library.md`:

**camera_move (one per scene, on the whole image layer):**
- `static`: no transform on the image; only element micro-float
- `push_in`: `gsap.to(img, {scale:1.07, duration:scene_dur, ease:'power1.out'})`
- `pull_out`: `gsap.from(img, {scale:1.1, duration:scene_dur, ease:'power1.out'})`
- `pan`: `gsap.to(img, {xPercent:-8, duration:scene_dur, ease:'power1.inOut'})` (over-wide images only)
- `tilt`: `gsap.to(img, {yPercent:-8, duration:scene_dur, ease:'power1.inOut'})`
- `parallax`: fg/mid/bg layers at different speeds (image as bg + 2-3 cutout layers)
- `element`: image static; one element slides/hinges in (use an entry move from Step 2a2)
- Banned (breaks flat paper language): orbit, dolly_zoom, roll, whip, handheld, fast_zoom — do NOT implement even though GSAP could

**element_motion (the energy engine — ≥2 elements moving per scene):**
- Give each scene ≥2 moving paper elements with safe rigid-paper verbs: drift / sway / ripple / flutter / slide / pivot / bob / pulse / shimmer / settle / layer parallax. **No morph / warp / vortex / explode.**
- WIDE scenes: several elements move; CLOSE/DETAIL scenes: the single hero element animates strongly, others micro-move.
- Elements **settle then hold static** (stop-motion cadence) — after landing, only micro-life (paper corner lift, halftone shimmer).
- **Text-protection**: the label strip moves as one rigid piece (translate/scale only), never letter-by-letter or warped.

**Visual beat rhythm:** every 4–7s a visual event (element entrance / chart update / sub-shot switch) — `visual_beat_seconds` from the scene plan. Scenes >12s are 2+ sub-shots; each sub-shot has its own camera_move/entrance, narration continues across the cut.

### Step 2a2: Paper-feel entrances (GSAP implementation from vox-motion-library)

Entry moves, mapped by scene `animation_type` — the paper-feel comes from these easing choices:

| Entrance | GSAP snippet | Used for |
|---|---|---|
| `fly_in` | `gsap.from(el, {x:-600, rotation:-12, ease:'back.out(1.7)', duration:0.9})` | photos, boards |
| `slap` | `gsap.from(el, {scale:1.3, ease:'power3.in', duration:0.25})` | stamps, labels |
| `drop` | `gsap.from(el, {y:-260, ease:'bounce.out', duration:1.1})` | objects falling |
| `pop_settle` | `gsap.from(el, {scale:1.35, autoAlpha:0, ease:'power3.out', duration:0.7})` | focus reveal, no off-screen travel — no ghost |
| `stamp-appear` | `gsap.from(el, {scale:1.25, autoAlpha:0, duration:0.35, ease:'power2.out'})` + `stagger:0.08` | title/closing cards |

**Anti-ghost rule** (from vox-director's local engine): when an element flies in to a spot on a photo, blur that region on the image with a placeholder block (`filter: blur(6px)`) until the element lands, then hide the blur block — luminance/color preserved, no dark patch. For scale-settles over a full backdrop use `power3.out` (a `back` overshoot dips below 1.0 and reveals a copy).

**Hero flying element (highlight scenes only):** the episode's ≤2 `highlight: true` scenes (from scene_plan) get one hero element flying across the frame (paper bird / shell / badge / arrow): `gsap.fromTo(el, {x:-300, rotate:-15}, {x:600, rotate:10, duration:2.5, ease:'power1.inOut'})` with a slight arc (sinusoidal y), settling with a small `back.out` overshoot. Never on non-highlight scenes.

**Anti-monotony:** adjacent scenes MUST NOT reuse the same camera_move nor the same entrance family — rotate scale-family (slap/pop_settle/scale-in) ↔ translate-family (fly_in/drop/poster-rise) ↔ opacity-family (stamp-appear/vignette-in). `static` + `pop_settle` combos are reserved for highlight/closing beats.

### Step 2a3: CONTINUOUS micro-motion layer (L-010 — verified on s02)

Entrances alone are not enough. After the entrance animations settle (~scene_start + 3.2s), the scene must keep **2-4 elements looping until scene end** — otherwise 60-70% of the scene is dead static:

| Element | Loop | Cycle |
|---|---|---|
| main photo | gentle sway / bob (`y: 5-8, rotation: 0.25-0.5deg`) | 3.6-4.5s |
| label strip | paper-corner lift (`rotation: 0.7, y: 3`) | 2.9s |
| caption | drift (`x: 5`) | 3.4s |
| pin | pulse (`scale: 1.12`) | 1.8s |
| stamp | breathe (`scale: 1.04, rotation: -6.2`) | 2.4s |

**FINITE repeats only (L-011):** `repeat: -1` FAILS lint — the deterministic capture engine seeks to exact frame times and cannot resolve infinite loops. Compute per loop: `repeat = Math.floor((scene_end - loop_start) / cycle_duration) - 1` with `yoyo: true, ease: "sine.inOut"`. Add `overwrite: "auto"` to loops sharing a property with the camera tween (photo scale) to avoid overlapping-tween lint errors.

### Step 2a4: Multi-element scenes (L-012 — verified on s02)

Never render a bare photo. Every scene carries **3-4 composed elements minimum**, entering staggered:
- hero image (entrance per Step 2a2)
- typewriter label strip (start + 1.2s, `x:70` slide-in)
- caption / sub-label (start + 1.9s, `x:-60`)
- pin (start + 2.6s, scale pop) and/or stamp (start + 2.2s, scale slam)

Layout families rotate per scene: left-tall / center / wide / letterbox / center-card / right-tall — never two adjacent scenes with the same layout family.

### Step 2a5: DISTINCT COMPOSITIONS, not just photo positions (L-027 — verified s05 handmade)

A centered photo + label/caption/pin is the SAME composition no matter how the photo is positioned. Every scene needs a composition FAMILY that changes the structure, and each scene gets its own element_motion (not the same yoyo loops):

| Composition family | Structure | element_motion signature |
|---|---|---|
| `full-bleed` | image fills frame + dark vignette overlay + headline slam | vignette fade-in, headline scale-slam |
| `left-right-split` | left panel + right card, red string connects | string draws between panels |
| `top-title-cascade` | title top + N strips pop in sequence below | strips stamp-appear staggered 0.5s |
| `quadrant-grid` | 2x2 grid of small panels + red frame | grid reveals staggered |
| `blueprint-draw` | full blueprint + coordinate lines draw themselves | SVG line stroke-dashoffset draw |
| `editorial-split` | tall left photo + right text block + stamp | photo x-slide, stamp slam |
| `letterbox` | wide band image + top/bottom foreground strips | band rises, strips press |

Rules:
- Two adjacent scenes MUST NOT use the same composition family (nor the same camera_move).
- **SUB-SHOT LEVEL variety (L-036 — verified EP.02):** composition families are assigned PER SUB-SHOT, not per scene. A 6-shot scene using ONE family across all shots reads as the same layout repeated 6 times — this is a visual failure even when images differ. Rotate the family list across sub-shots (shot 1 full-bleed, shot 2 editorial-split, shot 3 letterbox, ...) so adjacent shots always differ in structure. The generator `build_episode_parts.py` accepts a family list; pass one family per sub-shot, never a single value for the whole scene.
- A 'center' composition is only allowed if it adds a distinguishing element (arch, vignette, split card, drawn line).
- Write element_motion per scene content (red-string draw for maps, strip cascade for lists, grid reveal for grids, line draw for blueprints) — never a generic yoyo on every element.

### Step 2a6: Vox motion methodology (L-028..L-031 — from Vox-style tutorial analysis)

Four rules that make motion feel like Vox, not generic CG:

1. **Low frame-rate signature (L-028):** Vox runs 12fps among high-fps content — the stepped cadence IS the style. In HyperFrames either render at `--fps 12-15`, or animate with stepped keyframes (hold 2-3 frames between steps). Never leave everything at 30fps smooth power1.
2. **Whip easing (L-029):** motion shape = slow ease-out → whip into speed → slow ease-in (`power2/power3.inOut`, `cubic-bezier(0.25,0.9,0.25,1)`). Identical curves across multi-property tweens (x+y+scale). Plain sine yoyo only for the faintest ambient micro-life.
3. **Story-motivated transitions (L-030):** most Vox cuts are HARD CUTS. Dissolve only where emotion/timeline continuity needs it (memories, tears, time jumps); hard-cut narrative pushes (charges, explosions, quotes). ≥ half of boundaries should be hard cuts.
4. **Cut on motion peak (L-031):** land the cut just AFTER the scene's signature element completes (string fully drawn, strip slapped, pin pressed, grid closed). Voice boundaries set the window; the motion peak sets the exact cut inside it.

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
6. **Boundary rule applies to ALL fades (L-023 — verified on s07):** board fade-outs (and any exit tween) whose end time lands EXACTLY on a clip boundary fail lint (`gsap_exit_missing_hard_kill`). With continuous windows (L-009), a 0.45s board fade-out starting at `scene_end - 0.45` ends exactly at the next scene's start. Budget it to end ≥0.1s BEFORE the boundary: `tl.to(board, {opacity:0, duration:0.45}, scene_end - 0.55)`, or land a `tl.set` hard kill exactly at the boundary.

### Step 2c: Word-synced bilingual subtitles (karaoke highlight)

0. **NO burned-in subtitles (L-032 — verified on EP.01):** never render subtitles into the video pixels. Render the composition CLEAN (no `.sub` elements, no subtitle JS). Captions ship as SRT sidecar files (`ep01.en.srt` + `ep01.zh.srt`) produced by the publish stage — YouTube renders them, viewers can toggle/translate them. If a render already has `.sub` layers, strip them before re-render (regex-remove `.sub` divs + subtitle JS block).

1. **Transcribe the final narration WAV** (transcriber tool, word timestamps enabled).
2. **Subtitle EN words come from the SCRIPT, not the transcript (L-014 — verified on s03).** Whisper mis-hears proper nouns (Zhu→"Jew", Chongqing→"chunking", Yan'an→"Yane"). Use the transcript ONLY for word timestamps; the display text is the approved `adaptation_script.json` narration, word-aligned to those timestamps (map each script sentence to the transcript segment covering its time window).
3. Build subtitle HTML at the ROOT level (not inside scene sections — inside a clip they get clipped by the scene window):
   - `.sub` container: `position:absolute; left:0; right:0; bottom:76px; z-index:90; opacity:0; text-align:center`
   - `.sub-en`: English, one `<span class="wk">` per word, 34px, Courier-style
   - `.sub-zh`: Chinese translation, 34px, PingFang/YaHei
4. Timing:
   - Show window = `[voice_start + 0.1, voice_end + 0.35]`, fade in 0.2s, fade out 0.25s — short sentences must still be readable (never let a 0.8s sentence flash for 0.4s).
   - **Karaoke cumulative highlight**: each word turns `color:#C0392B; fontWeight:800` at its word timestamp and STAYS (never reverts) — spoken words accumulate red+bold, unspoken stay paper-white 500.
   - After the fade-out, add a `tl.set(sub, {opacity:0})` hard kill (prevents stale visibility on seek).
5. Chinese line = the English narration translated (follows the dub, not the source video's original words).
6. **ZH map strictness (L-019 — verified on s05):** the Chinese subtitle array MUST have exactly `len(segs)` entries with a hard assert — hand-counting lines caused a full-shift misalignment (every zh line off by one, last line lost). Build zh from the SCRIPT narration (one zh sentence per script sentence), then map script sentences to transcript segments by time window.
7. **Script semantics over transcript wording (L-020):** whisper segments often split/merge differently than the script sentences ("a strange thought surfaced" → "a strange, hot surface"; "turtle-shell bunkers apart" split in two). The EN words come from the script (L-014) and the ZH line translates the script sentence — time windows come from whisper, meaning comes from the script.
8. **Hard-kill boundary alignment (L-021 — verified on s06):** a subtitle fade-out that ends across a scene boundary fails lint (`gsap_exit_missing_hard_kill`). The `tl.set(sub, {opacity:0})` hard kill must land EXACTLY on the boundary timestamp (19.30 passed; 19.35/19.40 failed). Options: move the fade-out earlier so it ends before the boundary, or set the hard kill at the boundary time exactly.
9. **Idempotent patches (L-022):** patch scripts (including the generator's hard-kill pass) must check for an existing line before inserting — running a fix twice injected duplicate `tl.set` lines and confused lint. Dedupe before write.

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

- **Render at 30fps (L-045 — verified EP.02):** `--fps 12` breaks audio extraction in the hyperframes CLI (missing audio.aac). Always render 30fps; the Vox 12fps signature (L-028) comes from stepped keyframes / hold-2-3-frames animation, not the render frame rate.
- **Merge: verify head-trim before applying (L-040 — verified EP.02):** EP.01 segments had a 2.6s leading blank (vo data-start=3 silent lead) so the merge trimmed 2.6s per segment. A new episode's segments may have NO leading blank — blind-copying the trim cut 2.6s of real content per segment (23s total). Before merging: run `ffprobe`/`volumedetect` on the first 3s of each segment; trim ONLY if actually blank.
- **Outro needs an end-card hold (L-041 — verified EP.02):** the final scene's duration must exceed narration end by ≥2s (empty screen hold after the last line, mirroring EP.01's s10 = 27.7s video vs 13.1s narration). Formula: outro duration = audio_lead + narration_seconds + ≥2s. Verify narration end time < video end time by ≥2s, and keep the final fade ≤0.5s so it never swallows the last word.
- **Episode title card (L-042 — verified EP.02):** every episode's FIRST scene (track 0, 2.6s) is `scene-open`: series title (IRON DRAGON) + `EP.NN` stamp + episode subtitle strip. BGM `data-start="0"` so music starts WITH the card. When offsetting all other scene times by +2.6s, keep scene-open at 0, keep BGM at 0.
- **SCENE TIMELINE ↔ VO OFFSET MUST MATCH (L-048 — verified EP.02, the sync root cause):** the `vo` audio `data-start` and the scene timeline's origin MUST be designed together. EP.01 pattern (canonical): scene-1 starts at **2.6s**, `vo data-start="3"` (0.4s picture-lead), merge trims 2.6s head. If the scene timeline starts at 0 (no offset) but `vo data-start="3"` is kept, narration lags 3s behind visuals in EVERY segment — first line arrives late, last line gets cut. Rule: after assemble, ALWAYS verify `scene-1.data-start + 0.4 ≈ vo.data-start` (±0.2s) and that merge trim equals scene-1.data-start. Either both-offset (EP.01 pattern) or both-zero (vo data-start=0.4 with scene-1 at 0) — never mixed.

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
- **Motion rules (per `references/vox-motion-library.md`):** every scene has ≥2 moving elements (rigid-paper verbs only); adjacent scenes differ in camera_move AND entrance family; no morph/warp/vortex/explode anywhere; no orbit/roll/whip camera moves
- **Highlight quota:** hero flying elements appear only on `highlight: true` scenes (≤2 per episode), never on ordinary scenes
- **Anti-ghost:** any element flying in over a photo has a blurred placeholder at its landing spot until it lands; scale-settles over a full backdrop use `power3.out` (no `back` undershoot)
- **Visual rhythm:** no scene plays >7s without a visual event; scenes >12s carry 2+ sub-shots with distinct camera moves
- **Entrance SFX mapping** (Step 2d) fires on element landings at volume ~0.28, under the narration
