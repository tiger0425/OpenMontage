# Asset Director — series-adapt Pipeline

## When to Use

You are the **Asset Director** for a series-adapt episode. Your job is to generate all visual and audio assets for the scene plan: AI images for every scene, English narration via zero-shot voice-cloned TTS, and optional background music. You produce the `asset_manifest` artifact that the compose stage references.

This is a **generation-heavy** stage — every call to image_selector or tts_selector costs time. Batch wisely.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan.json` | Scene definitions with generation_direction per scene |
| `adaptation_script.json` | Full narration text per scene |
| `apps/series-adapt/config.yaml` | Voice reference path, image provider, color scheme |
| **`projects/<series>/DESIGN_SYSTEM.md`** | Series design system — real-reference rule, palette, composition |
| `styles/vox-collage.yaml` | Generic style-library playbook |
| `glossary.yaml` | Pronunciation overrides for military terminology |
| `image_selector` → `flux_image` | AI image generation |
| `tts_selector` → `indextts_tts` | English voice synthesis |

## Process

### Step 0: Extract real reference frames (MANDATORY for biography series)

This pipeline produces **personal biography documentaries**. Every person, vehicle, place, and object shown on screen MUST derive from the actual source episode footage — never from imagination. A face the model invented is a factual error in a biography.

1. **Probe the source video.** Run scene detection over `reference_video.mp4` and extract frames (e.g. `ffmpeg -vf fps=1/3` at 1280px wide) into `assets/source/frames/`.
2. **Locate the real subjects.** Use the vision model (see `minimax-m3-vision` skill) to identify which frames contain:
   - the real person (interview close-ups are the gold standard for face reference),
   - the real vehicle/object (tank, mortar, factory, map),
   - the real place (cave dwellings, workshop, parade route).
   Re-extract those time windows at higher density (`ffmpeg -ss <start> -t <win> -vf fps=2`) into `assets/source/refs/`.
3. **Reference map.** For each scene in `scene_plan.json`, record which real frame it is based on. Scenes without a real reference (abstract ideas, night mood, title cards) may generate free-form but must not depict a real person's face or a real object's shape from imagination.
4. **Generate via img2img.** Call `image_selector` with `image_path` = the real reference frame and `generation_mode: edit`. The prompt must say "Keep the exact same [person/tank/cave] from the reference photo" and then restyle into the collage world. If the result drifts from the reference (e.g. a cave becomes a warehouse), regenerate with higher `image_strength` (0.85-0.9) and explicit "do NOT change the [feature]" language.

### Step 1: Generate images

For each scene in `scene_plan.json`, call `image_selector` with:
- The scene's `generation_direction` as the prompt
- Size: 1920×1080
- Provider: from config (`visual.image_provider`, default `flux_image`)
- Style guidance: read `styles/vox-collage.yaml` — the series' default style is **Vox Paper Collage** (aged newsprint, halftone cutouts, red string/pins, typewriter labels). The `image_prompt_prefix` field there is the verbatim style block for every prompt.
- `image_path`: the real reference frame from Step 0 when the scene depicts a real person/object (biography accuracy).

Save each image to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/assets/images/scene_{scene_index:03d}.png
```

**Consistency rules:**
- If two scenes show the same tank model, reuse the same reference frame and seed for consistent appearance
- Real person/object scenes MUST use img2img from a real source frame (Step 0); free-form generation is only allowed for abstract/mood scenes
- Charts and maps must have English labels only

### Step 2: Generate narration

The TTS workflow uses IndexTTS2 with the user's cloned voice.

**Voice reference:** Read `voice_reference` path from `apps/series-adapt/config.yaml`. This is the user's recorded voice sample.

**Segmentation:** Split the full script into sentence-level segments. Each sentence becomes one TTS call. Use sentence boundaries (`.!?`) as split points, not mid-sentence breaks.

For each narration segment, call `tts_selector` → `indextts_tts`:

```python
tts.infer(
    spk_audio_prompt="voice_reference.wav",  # from config
    text="segment text with glossary-applied pronunciations",
    output_path=f"seg_{index:03d}.wav",
    emo_vector=[0, 0, 0, 0, 0, 0, 0, 1.0],  # calm=1.0 for documentary
    use_fp16=True  # 3090 recommended
)
```

Save each WAV to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/assets/audio/seg_{index:03d}.wav
```

**Pronunciation:** Before synthesizing each segment, apply glossary.yaml overrides:
- Replace each glossary term in the text with its pronunciation form
- For IndexTTS2: use the model's phoneme override syntax if the normalizer doesn't handle it

**Silence check:** After all segments are generated, scan each WAV:
- Compute RMS amplitude
- If RMS < 100 → mark as silent → regenerate that segment
- This is the VoxCPM silent-file pattern applied to IndexTTS2

**Transcribe the final narration (MANDATORY — feeds scene plan + subtitles):**
After the narration WAVs pass the duration check, run the transcriber on each segment (or the concatenated episode audio) with **word-level timestamps** enabled:
- Scene plan stage uses segment start/end to align scene windows to voice boundaries (never cut mid-sentence)
- Compose stage uses word timestamps for the karaoke subtitle highlight
- Store the transcript JSON in `assets/audio/` and reference it from the manifest (`narration_segments[].transcript_path`)

**Paper-craft SFX:** see compose-director Step 2d — the 6 ffmpeg-synthesized SFX WAVs live in the HyperFrames workspace `assets/sfx/`.

**DURATION CHECK (mandatory gate — this catches underwritten scripts):**
After every segment is synthesized, measure actual duration with `ffprobe`:
- `actual_duration = ffprobe(seg_N.wav)`; `target_duration = scene_plan duration for that section`
- **If `actual_duration < target_duration × 0.95`, the script is UNDERWRITTEN. Do not pad audio.** Go back to the rewrite stage: expand the narration text with more specific factual detail (names, numbers, dates, physical description) so the word count meets `target_duration × measured_wps`, then regenerate the segment.
- If `actual_duration > target_duration × 1.10`, trim the scene duration in the scene plan to match (narration is the master clock; visual scenes flex to it).
- Record `actual_duration_seconds` per segment in the manifest.
- The measured speech rate (`measured_wps`) must be written back to `config.yaml → tts.measured_wps` on the first episode so future rewrites budget words correctly.

### Step 3: Optional background music

If `music_gen` is available and configured, generate a subtle documentary BGM:
- Style: "ambient military documentary background, low intensity, no percussion, string pads"
- Duration: match total episode duration
- Volume: mixed at -18dB relative to narration

### Step 4: Produce asset_manifest

Output `asset_manifest.json`:

```json
{
  "episode_num": 1,
  "scene_assets": [
    {
      "scene_index": 1,
      "image_path": "assets/images/scene_001.png",
      "image_prompt": "...",
      "image_provider": "flux_image",
      "image_seed": 42
    }
  ],
  "narration_segments": [
    {
      "index": 1,
      "audio_path": "assets/audio/seg_001.wav",
      "text": "In 1999, as the world watched...",
      "duration_seconds": 5.2
    }
  ],
  "music": {
    "path": "assets/audio/bgm.mp3",
    "provider": "music_gen",
    "volume_db": -18
  },
  "voice": {
    "provider": "indextts_tts",
    "reference_wav": "my_voice.wav",
    "all_segments_clean": true,
    "silent_segments_regenerated": 0
  },
  "generated_at": "ISO timestamp"
}
```

Update tracking.db status to `assets_ready`.

## Quality Rules

- Every scene in scene_plan has a corresponding image file
- No narration segment has RMS amplitude below threshold
- All image files are 1920×1080 minimum resolution
- Image style is consistent (flat vector across all images)
- All chart labels and map text are in English
- Voice clone reference WAV is the same file used for all segments (no mid-episode voice drift)
