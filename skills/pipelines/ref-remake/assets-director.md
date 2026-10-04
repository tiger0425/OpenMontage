# Assets Director — ref-remake Pipeline

## When to Use

You are the **Assets Director** for a ref-remake episode. Your job is to produce
the `asset_manifest`: TTS narration segments (IndexTTS cloned voice, measured
durations) and MiniMax generated images (V2 点缀式 + reference anchor). This is
a **HEAVY STAGE** — dispatch to a Compute Worker with `--json` single-line
report per AGENT_GUIDE multi-agent protocol.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan` | Per-scene narration + image prompt segments |
| `script` (approved) | Narration source text |
| `styles/ref-remake.yaml` | `image_prompt_prefix` style block (verbatim) |
| `background_library/ref-remake/README.md` | Anchor image + call convention |
| Layer 3 skills | `voxcpm-tts`/IndexTTS, `visual-style` — read before generating |

## Process

### Step 1: TTS FIRST — narration segments

1. Generate narration via `tts_selector` → IndexTTS cloned voice
   (`voice_ref_futian3.wav`, fixed `seed=20260825`).
2. Measure each segment with ffprobe; backfill measured durations into
   `asset_manifest.narration_segments[].duration_s`.
3. Timing calibration: if total deviates >5% from scene_plan estimate, note it —
   compose builds from measured durations (word-ratio fallback).

### Step 2: Image generation (MiniMax, anchor + V2)

1. For each scene's image segments, build prompts:
   `STYLE_BLOCK (from styles/ref-remake.yaml image_prompt_prefix, VERBATIM) + scene description`.
2. Call `minimax_image` with:
   - `reference_image`: `background_library/ref-remake/anchor/ahhuang_anchor.png`
   - `aspect_ratio`: `9:16`
   - `seed`: per-segment fixed seed (reproducibility)
   - `prompt_optimizer`: OFF in reference mode (default behavior)
3. 3-4 images per narration segment, by semantic split.
4. **Textless only**: no text/numbers/words in any AI image.
5. MiniMax 422 sensitive frames: skip that frame, continue the batch — do NOT
   block the whole episode.

### Step 3: Produce asset_manifest

Write `asset_manifest.json`:
```json
{
  "narration_segments": [
    {"scene_id": "s0", "text": "...", "audio_path": "assets/audio/s0.wav", "duration_s": 11.2}
  ],
  "images": [
    {"scene_id": "s0", "prompt_segment": 0, "path": "assets/images/s0_0.png", "seed": 6001}
  ],
  "anchor": "background_library/ref-remake/anchor/ahhuang_anchor.png",
  "style_block_source": "styles/ref-remake.yaml",
  "layer3_skills_read": ["voxcpm-tts", "visual-style"]
}
```

## Review Notes

- All paths must resolve to existing files on disk.
- No silent WAV segments — RMS check on each audio file.
- Reference-image mode: verify the anchor was actually passed (consistency is
  the whole point).
- HEAVY: run via Compute Worker; never block the lead session on TTS/生图.
