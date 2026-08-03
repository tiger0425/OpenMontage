# Scene Director — series-adapt Pipeline

## When to Use

You are the **Scene Director** for a series-adapt episode. Your job is to take the approved English script and break it into a sequence of visual scenes — each one specifying what the viewer sees, for how long, and with what Vox-style animation. You produce the `scene_plan` artifact that the asset and compose stages execute against.

## Prerequisites

| Resource | Purpose |
|---|---|
| `adaptation_script.json` | Approved English script with visual directions |
| `knowledge_brief.json` (optional) | Context for diagram design |
| `apps/series-adapt/config.yaml` | Visual style and color scheme |
| **`projects/<series>/DESIGN_SYSTEM.md`** | **Series design system (authoritative)** — the series'落地 design decisions: palette, typography minimums, composition, pacing, subtitles, SFX. Read it before planning scenes. |
| `styles/vox-collage.yaml` | Generic style-library playbook (shared across series) — the `image_prompt_prefix` style block |
| `references/vox-story-library.md` | Narrative arcs, hooks, beat rhythm — used to place highlight beats |
| `references/vox-look-library.md` | Image prompt 5-part structure + theme presets — how to write `generation_direction` |
| `references/vox-motion-library.md` | camera_move vocab + element_motion engine + GSAP paper-feel moves |

## Scene Types

You have five scene types available. Each forces a different kind of visual attention:

| Type | Best for | Example |
|---|---|---|
| `tank_illustration` | Featuring a specific vehicle or piece of hardware | "The 59式 tank rolls off the assembly line" |
| `stat_chart` | Comparing data, showing change over time | "Armor thickness increased from 100mm to 600mm" |
| `map_timeline` | Showing geographic context + historical progression | "Factories spread across Baotou, Luoyang, and Datong" |
| `text_card` | Full-screen key quote, statistic, or term definition | "祝榆生: '打個平手有什麼用，要打就打贏！'" |
| `comparison_grid` | Side-by-side comparison of two or more items | "59式 vs T-54A: What China changed" |

## Animation Types

Pair each scene with one Vox-style animation:

| Animation | GSAP implementation hint | Scene types |
|---|---|---|
| `pan-zoom-in` | Scale + translate on still image | tank_illustration |
| `pan-zoom-out` | Reverse scale + translate | tank_illustration |
| `chart-reveal` | Stagger bars/lines from zero | stat_chart |
| `map-marker` | Sequential pin drops + timeline labels | map_timeline |
| `typewriter` | Character-by-character text reveal | text_card |
| `slide-side-by-side` | Two panels slide in from left/right | comparison_grid |
| `label-overlay` | Callout lines + labels animate onto image | tank_illustration |

## Process

### Step 1: Parse the script

Walk through `adaptation_script.json` section by section. Each section's `visual_direction.type` gives you the starting scene type.

### Step 2: Assign scene types and durations

For each script section, assign:
- **scene_type**: One of the five types above
- **start_seconds**: When this scene begins (cumulative)
- **duration_seconds**: The **narration master clock**. The narration audio IS the scene length — do not derive duration from word count math. Use the section's planned duration from `adaptation_script.json`, and after TTS generation the asset stage measures each segment's actual duration; if the measured duration differs from the plan by more than 5%, the scene plan must be updated to the measured value (see asset-director DURATION CHECK).

Ensure variety: no 3+ consecutive scenes of the same type.

### Step 2b: Scene windows follow VOICE BOUNDARIES (documentary breathing)

The scene cut points must NEVER land mid-sentence. The narration is the master clock; a cut that happens while the voice is still talking reads as an error.

1. **Transcribe the TTS audio first.** Before finalizing scene windows, run the transcriber on each narration WAV (see asset-director). The scene plan's `start_seconds`/`duration_seconds` are then aligned to the **voice segment boundaries** (transcript segment start/end + any lead-in offset).
2. **No mid-sentence cuts.** A scene's window = [voice_start - 0.4s lead (picture settles first), voice_end + hold]. The `hold` is the breathing room after the sentence ends — documentary pacing demands 0.5-0.7s on regular beats, more on emotional beats (tears, reveal, closing): 1.5-3.4s.
3. **Zero-gap sentence pairs** (two segments with no pause between them, e.g. "...climbed" → "the stony path") must either merge into one scene window or cut exactly at the boundary — never insert hold that would swallow the next sentence's start.
4. **Scene transition = cross dissolve.** Boards fade in/out over the overlap (0.4-0.5s). See compose-director. Avoid hard cuts and avoid full-screen wipe flashes.
5. **WINDOWS MUST BE CONTINUOUS (L-009 — verified on s02).** Compute windows in sequence, never independently: `start_i = max(prev_end - 0.5, voice_start_i - 0.4)`, `end_i = min(voice_end_i + hold_i, next_voice_start - 0.4 + 0.5)` (last scene: `voice_end + hold`). Whisper sentence pauses (0.5-2.7s) are NOT covered by voice segments — if each window is computed as voice+hold alone, dead air appears between scenes. After planning, run a **gap check**: every `next_start - prev_end` must be ≤ 0 (negative = dissolve overlap). Zero-gap + overlap is the only correct state.
6. **Long-segment sub-splits use a FLAT range list (L-025 — verified on s09).** When a voice segment is 8-13s+ and must be split into sub-scenes (L-015): first flatten to a plain list of audio sub-ranges `(start, end)`, THEN run the L-009 formula over the flat list. Never nest split metadata inside the window computation (a nested GROUPS structure produced 7 tiny 4s windows + one 27.6s monster). After computing, run both gates: all gaps ≤ 0 AND all window durations ≤ 12s (re-split any sub-range that still exceeds 12s).

### Step 2c: Distinct motion per adjacent scene (anti-repetition)

Consecutive scenes MUST NOT use the same entry animation. Repeated "slide in from bottom" reads as copy-paste. Assign each scene a different motion script from this palette, cycling so neighbors differ:

| Motion | Feel | Used for |
|---|---|---|
| `slow-push-in` | Ken Burns scale 1.0→1.07 over full scene | panoramas, establishing |
| `drop-in` | y -260→0 with bounce | mid shots, action |
| `scale-in` | 1.25→1 emerge | close-ups, reveals |
| `torn-unfold` | scaleX 0→1 from left | extreme close-ups, documents |
| `still-then-push` | hold 0.8s then micro push 1.0→1.04 | emotional beats |
| `pin-in` | scale 0.6→1 with back.out + pin drop | portraits, archive cards |
| `symmetric-slide` | labels slide in from both sides, photo breathes | static/symmetric comps |
| `vignette-in` | dark vignette fades in + slow push | night scenes |
| `poster-rise` | y 260→0 rise | widescreen letterbox |
| `gate-press` | arch foreground presses down + push | gate/arch compositions |
| `stamp-appear` | sequential scale+opacity pops | title/closing cards |

### Step 2d: Composition variety + negative space

- **Vary layout per scene**: full-bleed panorama / left-third + right content / centered close-up / portrait-left + text-right / symmetric / widescreen letterbox. Never two adjacent scenes with the same layout family.
- **SUB-SHOT CONTENT DIVERSITY (L-036 — verified EP.02, the #1 visual-failure mode):** every sub-shot inside a scene MUST be a DIFFERENT PICTURE — different visual subject, different visual event, different reference frame. Camera wording alone ("wide establishing" / "medium" / "close-up" on the same subject) does NOT count: image models produce near-identical output from identical subjects+references. Design sub-shots as distinct visual beats: each one names a DIFFERENT element in the scene (the mortar, the firing cord, the officer's hand, the muzzle flash, the stretcher) or a different event moment. Rule of thumb: if two sub-shot descriptions share the same subject noun + same reference frame, they will render as the same picture — rewrite until the subject differs. See EP.01 s01 (11 beats: climb/cave/sleeve/tank-gate — 11 different subjects). 
- **Negative space ≥ 30%**: images should occupy roughly 55-65% of frame width (e.g. 1180/1920 for a panorama, 820/1920 for a close-up), leaving generous paper margin around every photo. Full-bleed only for the establishing panorama and the night widescreen.
- **Typography minimums** (at 1920×1080): typewriter strips ≥ 40px, headlines ≥ 64px (title card ≥ 110px), stamps ≥ 46px, captions ≥ 28px, subtitles ≥ 34px. Small animated text is unreadable at 1080p.

### Step 3: Write generation directions (5-part structure)

For each scene, write a concrete `generation_direction` that the asset stage can pass to `image_selector`. Use the **5-part structure** from `references/vox-look-library.md` — the collage look is born in the image step; every scene must read as a *real layered collage*, not a smooth illustration:

1. **Style block**: append the Vox Paper Collage style block from `styles/vox-collage.yaml` → `asset_generation.image_prompt_prefix` verbatim to every prompt (the asset stage does the concat — see asset-director).
2. **Scene as layered paper cut-outs** (the most important part): describe the scene as *separate cut-out pieces* with clear edges and their own drop shadows: `{subject}, {a prop}, {a text strip}, {a decorative scrap}`. If the scene depicts a real person/vehicle/place, the subject phrase is `Keep the exact same [person/tank/place] from the reference photo, cut out as a black and white halftone print` (img2img — see asset-director Step 0).
3. **One bold flat background color per scene**: pick from the series palette (`DESIGN_SYSTEM.md`); **adjacent scenes must use different background colors** (rotating the palette).
4. **Baked-in label**: one English typewriter-strip/rubber-stamp label, ≤4 words, with the exact words in quotes — the text is rendered by the image model, never added later.
5. **Tech**: 1920×1080, 2k resolution, matte finish.

**Per-type starting points** (then fill into the 5-part structure):
  - **tank_illustration**: "Keep the exact same [tank/person] from the reference photo. [composition] as a black and white halftone cutout..."
  - **stat_chart**: "Halftone cutout diagram on newsprint, [metric] across [items], typewriter labels in English"
  - **map_timeline**: "Torn paper map of China highlighting [locations], red string and pins between [year] markers, typewriter labels"
  - **text_card**: "Typewriter strip and rubber stamp on aged newsprint, [text], red signal accent"
  - **comparison_grid**: "Two torn-paper panels on newsprint showing [item A] vs [item B], red string connecting labeled points"

### Step 3b: Assign camera_move + element_motion (per-scene motion spec)

Pair each scene with motion fields per `references/vox-motion-library.md`:

- **`camera_move`** (one per scene, hard-constrained vocab): `static` | `push_in` | `pull_out` | `pan` | `tilt` | `parallax` | `element`. **Banned: orbit, dolly_zoom, roll, whip, handheld, fast_zoom** (break the flat paper language). Adjacent scenes must NOT reuse the same camera_move; `timeline`-arc scenes pan the same direction beat-to-beat; reserve `static` for the highlight/payoff scene.
- **`element_motion`** (the energy engine): every scene needs **≥2 elements moving simultaneously** — safe verbs: drift/sway/ripple/flutter/slide/pivot/bob/pulse/shimmer/settle/parallax. **Banned: morph/warp/vortex/explode** (rigid paper only). Shot-size gating: WIDE → several elements move; CLOSE/DETAIL → that one element animates strongly. Elements settle then hold static (stop-motion cadence).
- **`highlight: true`** (max ≤2 per episode): mark the episode's energy peak scene from `references/vox-story-library.md` (the 高光节拍). Highlight scenes get the hero flying element quota and the motion peak; use `static` camera + `pop_settle` entrances there.
- **`visual_beat_seconds`**: scene-internal rhythm — at least one visual event (element entrance / chart update / sub-shot switch) every **4–7s**. Any scene longer than **12s must be split into 2+ sub-shots** (wide establishing + detail cut-in), each with its own camera_move/entrance — narration stays continuous, the picture cuts mid-sentence (this is the single biggest rhythm win from vox-director). **Enforce at WINDOW PLANNING time (L-015 — verified on s03):** when merged voice windows exceed 12s, split the underlying voice segments into separate scenes BEFORE building the composition. A 16s scene with one camera move is a dead scene; three 5s sub-shots with different entrances is rhythm.

### Step 4: Produce scene_plan

Output `scene_plan.json`:

```json
{
  "episode_num": 1,
  "total_duration_seconds": 600,
  "scenes": [
    {
      "index": 1,
      "scene_type": "tank_illustration",
      "animation_type": "pan-zoom-in",
      "camera_move": "push_in",
      "element_motion": "the tank's road wheels bob, dust scraps drift, a paper label strip slides in from the right, halftone pulses gently",
      "highlight": true,
      "visual_beat_seconds": 6,
      "start_seconds": 0,
      "duration_seconds": 45,
      "narration_text": "In 1999, as the world watched...",
      "generation_direction": {
        "subject": "Keep the exact same ZTZ-99 main battle tank from the reference photo, cut out as a black and white halftone print",
        "props": "a folded parade map strip, scattered rivet scraps, a torn '1999' number cutout",
        "background": "bold flat military green",
        "label": "PARADE 1999",
        "tech": "1920x1080, 2k resolution, matte finish"
      },
      "overlay_text": null
    }
  ],
  "visual_style": {
    "palette": "military-green",
    "font_heading": "system-ui",
    "font_body": "system-ui"
  },
  "created_at": "ISO timestamp"
}
```

> `generation_direction` is stored as a structured object (subject/props/background/label/tech)
> — the asset stage assembles the final prompt by prepending the verbatim style block
> (`styles/vox-collage.yaml` → `image_prompt_prefix`) and mapping these 4 fields into the
> 5-part structure (see asset-director Step 1b).

Update tracking.db status to `scene_planned`.

## Quality Rules

- Total scene duration must equal `adaptation_script.estimated_duration_seconds` (within 2 seconds)
- No scene shorter than 4 seconds (too fast to register)
- At least 3 different `scene_type` values used
- Each generation_direction must be concrete enough for `image_selector` to produce a usable image
- Overlay text (on-screen labels/captions) must be in English
- **No consecutive asset reuse**: two adjacent scenes MUST NOT use the same image asset. Reuse is allowed for non-adjacent scenes (e.g. scene 3 and scene 7 may share a doorway), but back-to-back reuse of the same image reads as a cut error and breaks the "one continuous space" illusion. Check the previous scene's `generation_direction`/asset reference before assigning a new one; if an adjacent scene would repeat an asset, either generate a new variant (new angle/crop/subject detail) or swap scene order.
- **No consecutive camera_move**: adjacent scenes MUST NOT reuse the same `camera_move` (vocab + banned list in `references/vox-motion-library.md`); `static` reserved for the highlight/payoff scene
- **element_motion on every scene**: ≥2 elements moving per scene (rigid-paper verbs only — no morph/warp/vortex/explode); CLOSE/DETAIL scenes may concentrate motion on the single hero element
- **Visual rhythm**: every scene has a visual event at least every 4–7s (`visual_beat_seconds`); scenes >12s carry 2+ sub-shots (wide + detail)
- **Highlight quota**: `highlight: true` on ≤2 scenes per episode (the 高光节拍 from `references/vox-story-library.md`)
- **Baked-in labels**: every `generation_direction.label` is ≤4 words, English, quoted — text rendered by the image model, never added in compose
- **Adjacent background colors differ**: consecutive scenes pick different flat background colors from the series palette
