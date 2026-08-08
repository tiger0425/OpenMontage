# Asset Director — repo-to-video Pipeline

## When to Use

You are the **Asset Director** for a repo-to-video episode. Your job is to generate
all audio assets: IndexTTS2 narration with the **user's cloned voice**, background
music, and synthesized SFX. You produce the `asset_manifest` that compose stage
references. Every TTS call costs GPU time — batch wisely and check for silent files.

## Prerequisites

| Resource | Purpose |
|---|---|
| `scene_plan.json` | Scene windows with durations |
| `script.json` | Full narration text per section |
| `apps/repo-to-video/config.yaml` | voice_reference, emo_vector, audio config |
| `tts_selector` → `indextts_tts` | Voice synthesis (user's cloned voice) |
| `music_gen` / `freesound_music` | Background music |
| `audio_mixer` | Mix + duck narration under BGM + SFX |
| `video_compose` (ffmpeg) | Audio encode / loudnorm / probe |

## Process

### Step 1: Generate narration with IndexTTS2 (user's voice)

**Voice reference:** `config.yaml → tts.voice_reference = "D:/index-tts/my_voice.wav"`.
Use the SAME file for every segment (no mid-episode voice drift).

**Segmentation:** Split narration by scene (one WAV per scene). Use sentence
boundaries (`.。！？`) as split points.

For each scene, call `tts_selector` → `indextts_tts`:
```python
tts.infer(
    spk_audio_prompt="D:/index-tts/my_voice.wav",  # user's cloned voice
    text="scene narration text",
    output_path=f"seg_{scene_index:03d}.wav",
    emo_vector=[0, 0, 0, 0, 0, 0, 0, 1.0],  # calm=1.0 (documentary read)
    use_fp16=True
)
```
> 语义：显式传 `emo_vector` = 固定 calm 情感、关闭自动文字判情感。repo-to-video
> 要求平稳知识解读，禁止自动情感跳跃。

Save WAVs to:
```
projects/repo-to-video/{slug}/assets/audio/seg_{scene_index:03d}.wav
```

### Step 2: Trim leading silence (MANDATORY)

IndexTTS2 WAVs carry 1.2-7.2s leading silence. Trim BEFORE measuring duration or
transcribing: `silencedetect -50dB`, cut lead − 0.15s. Verify each trimmed WAV
starts with ≤0.2s silence.

### Step 3: Silence check + duration gate

- Scan each WAV: RMS < 100 → silent → regenerate that segment.
- Measure duration with ffprobe:
  - `actual < target × 0.95` → script UNDERWRITTEN → return to script stage (expand
    with factual detail), do not pad audio.
  - `actual > target × 1.10` → trim scene duration in scene_plan (narration is the
    master clock).
- Write back `measured_wps` to config if it drifts.

### Step 4: Transcribe final narration (for scene sync)

Run transcriber on each trimmed WAV with **word-level timestamps**; store JSON in
`assets/audio/`. Scene plan windows MUST be re-aligned to these voice boundaries
(see scene-director Step 3) — update `scene_plan.json` durations to measured values.

### Step 5: Background music

1. Check `music_library/` first — if a suitable track exists, use it.
2. Else generate via `music_gen` (or `freesound_music`):
   - Style: `config.yaml → audio.bgm.style` ("subtle tech documentary background,
     low intensity, no percussion, synth pads")
   - Duration: match total narration duration
3. Save to `assets/audio/bgm.mp3`.

### Step 6: Synthesize SFX

No SFX provider configured → synthesize with ffmpeg tones/noise (map to
`config.yaml → audio.sfx.set`):

| SFX | ffmpeg synth | Used at |
|---|---|---|
| `synthetic-ui-swipe` | filtered noise sweep 0.9s | code window / graph enter |
| `soft-boop` | 600Hz sine 0.08s | node light-up |
| `line-draw` | 1200Hz chirp 0.35s | edge/graph draw |
| `pop` | 220Hz 0.09s | stat pop |
| `keystroke` | 2000Hz click 0.05s | terminal typing |
| `thud` | 75Hz 0.22s | end slam |

Save to `assets/sfx/`. Level `audio.sfx.volume` (~0.28) — under the voice.

### Step 7: Mix (full_mix with ducking)

Use `audio_mixer` `operation=full_mix`:
- tracks: narration (role=speech), bgm (role=music), per-scene sfx (role=sfx)
- ducking: music_volume_during_speech 0.15, attack 200ms, release 500ms
- normalize true; loudnorm I=-16 LUFS
- Output: `assets/audio/mix.wav`

> SFX placement must match the composition's element landing times. Keep SFX +
> narration in separate tracks in the manifest so compose can align them.

### Step 8: Produce asset_manifest

```json
{
  "slug": "code-review-graph",
  "narration_segments": [
    {"index": 1, "audio_path": "assets/audio/seg_001.wav", "text": "...", "duration_seconds": 14.5, "transcript_path": "assets/audio/seg_001.json"}
  ],
  "music": {"path": "assets/audio/bgm.mp3", "provider": "music_gen", "volume_db": -18},
  "sfx": {"path": "assets/sfx/", "provider": "ffmpeg_synth", "volume": 0.28, "set": {"code_window": "synthetic-ui-swipe", ...}},
  "mix": {"path": "assets/audio/mix.wav", "duck_level_db": -18},
  "voice": {"provider": "indextts_tts", "reference_wav": "D:/index-tts/my_voice.wav", "all_segments_clean": true, "silent_segments_regenerated": 0},
  "generated_at": "ISO timestamp"
}
```

## Quality Rules

- Same voice reference for ALL segments (no drift)
- No silent WAVs (RMS ≥ 100)
- Leading silence trimmed before transcription
- Scene durations updated to measured narration durations (narration is master clock)
- BGM at -18dB, SFX at ~0.28, both under narration
- loudnorm target I=-16 LUFS on the final mix
