# Asset Director — series-adapt Pipeline

## When to Use

> **遇到问题先查 [known-issues.md](known-issues.md)（症状索引 K-01~K-13）**

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
| `references/vox-look-library.md` | 5-part image prompt assembly rules + consistency checklist |
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
   - the real place (cave dwellings, workshop, parade route),
   - **the real SCENE/EVENT (L-017 — verified on s04): battlefield, explosion, night combat, train, workshop. Source docs are full of archival war footage; a battlefield collage should be img2img'd from the real battlefield frame, not invented.**
   Re-extract those time windows at higher density (`ffmpeg -ss <start> -t <win> -vf fps=2`) into `assets/source/refs/`.
3. **Reference map.** For each scene in `scene_plan.json`, record which real frame it is based on. Scenes without a real reference (abstract ideas, night mood, title cards) may generate free-form but must not depict a real person's face or a real object's shape from imagination. **Always scan the frame library BEFORE deciding a scene is reference-free.** (Bonus: non-person frames also pass the MiniMax content filter more reliably.)
4. **Generate via img2img.** Call `image_selector` with `image_path` = the real reference frame and `generation_mode: edit`. The prompt must say "Keep the exact same [person/tank/cave] from the reference photo" and then restyle into the collage world. If the result drifts from the reference (e.g. a cave becomes a warehouse), regenerate with higher `image_strength` (0.85-0.9) and explicit "do NOT change the [feature]" language.

### Step 1: Generate images

For each scene in `scene_plan.json`, call `image_selector` with:
- Size: 1920×1080
- Provider: from config (`visual.image_provider`, default `flux_image`)
- **Model: from config `visual.image_model` (series-wide lock — currently `gemini-3.1-flash-lite-image`; pass as `model` to the selector). Never change the model mid-series without a logged decision + DESIGN_SYSTEM update.**
- Style guidance: read `styles/vox-collage.yaml` — the series' default style is **Vox Paper Collage** (aged newsprint, halftone cutouts, red string/pins, typewriter labels). The `image_prompt_prefix` field there is the verbatim style block for every prompt.
- `image_path`: the real reference frame from Step 0 when the scene depicts a real person/object (biography accuracy).

Save each image to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/assets/images/scene_{scene_index:03d}.png
```

**Filename consistency (L-013 — verified on s03):** the basename used in `asset_manifest.json` must be byte-identical to the `<img src>` in the composition. When scaffolding the HyperFrames workspace, copy images AS-IS (same basename, e.g. `s03_1.png`) and grep the HTML src against the copied filenames before rendering — a mismatched name (s3_1 vs s03_1) costs a full render cycle in lint failures.

**Consistency rules:**
- If two scenes show the same tank model, reuse the same reference frame and seed for consistent appearance
- Real person/object scenes MUST use img2img from a real source frame (Step 0); free-form generation is only allowed for abstract/mood scenes
- Charts and maps must have English labels only

### Step 1b: Assemble the 5-part image prompt (MANDATORY)

`scene_plan.generation_direction` is stored as a structured object (subject / props / background / label / tech — see scene-director Step 3). Assemble the final prompt with the 5-part structure from `references/vox-look-library.md`:

```
[1 STYLE BLOCK]  styles/vox-collage.yaml → image_prompt_prefix, verbatim (never paraphrase)
[2 SCENE]        "SCENE as layered paper cut-outs: {subject}, {props}; clear edges,
                  distinct layers, each with its own drop shadow, visibly hand-cut."
                 (subject already embeds the img2img keep-exact-same phrase for real subjects)
[3 BACKGROUND]   "on a bold flat {background} paper background."
[4 LABEL]        "A typewriter strip / rubber stamp reading "{label}" (English, max 4 words)."
[5 TECH]         "{tech}"
```

Rules:
- The style block is byte-identical across every prompt of the episode (diff against the source file). Only parts 2–4 change per scene.
- Positive phrasing only — do NOT append negative words to Flux-style models; if the provider needs a negative prompt, use `styles/vox-collage.yaml` → `image_negative_prompt` in the tool's negative field, never inline.
- Record the final assembled prompt in the manifest (`image_prompt`).
- Self-check each prompt against the §4 checklist in `references/vox-look-library.md` (cut-outs/clear edges/drop shadow, single bold color, ≤4-word quoted label, no 3D/CGI words).
- **ERA ARMY + ETHNICITY constraint (L-024 — verified s04/s06/s07):** every person-containing SCENE part MUST embed (a) East Asian Chinese facial features, and (b) the correct era army uniform. For 1937-1945 scenes: "East Asian Chinese soldiers of the Eighth Route Army in 1940s grey cotton uniforms, cloth peaked caps, puttee leg wraps" — NOT the Red Army (red-star octagonal cap = 1927-1937), NOT US/Western uniforms (steel helmets). Image models default to Western soldiers in US gear if unconstrained. **Vision-verify each person scene for ethnicity + uniform BEFORE rendering.**
- **ERA-FIDELITY MATRIX (L-034 — verified EP.02, spans 1945-1959):** scenes must match their exact period, not just "Chinese soldier." Per-era defaults: **1937-1945** → Eighth Route Army grey cotton, cloth peaked caps, puttees (L-024); **1945-1949** → PLA beige/yellow cotton uniforms, no star badges before 1949, cloth caps; **1949-1953** → PLA 50-style olive uniforms with red collar tabs + red star cap badge; **1953-1959** → Soviet-influenced dress: olive uniforms, shoulder boards, peaked caps with star (HMEI students), Soviet-style architecture (Harbin campus = Stalinist brick with green roof). Also era-check props: no TV antennas/satellite dishes before 1960, no modern vehicles (cars/trucks post-1960 designs) in pre-1950 scenes, classrooms with chalkboards and wooden desks (no plastic). **Write the era constraint into every prompt string; vision-verify at least one frame per scene for era fidelity BEFORE rendering.**
- **EVERY SUB-SHOT GETS ITS OWN IMAGE (L-035 — verified EP.02 regression):** NEVER generate one hero image per scene and copy it to fill sub-shot slots. Each sub-shot in `scene_plan.json` has its own `generation_direction` (distinct shot size / angle / focus / label) — the asset stage MUST consume EVERY sub-shot's direction and generate a distinct image for it. File-copy duplication produces a dead, repetitive scene (same picture for 40-80s with only camera tween). If scene_plan sub-shots lack distinguishing directions, STOP and fix the scene plan first — never fall back to duplication. Verify by size: distinct generated images have different file sizes; identical sizes = copies = failure. The API cost of independent images is mandatory, not optional.
- **DISTINCT REFERENCES + DISTINCT SUBJECTS (L-036 — verified EP.02 regression #2):** unique files are NOT enough — 63 unique files all img2img'd from the SAME reference frame with the SAME subject noun still render as the same picture. Two hard requirements: (a) each sub-shot's `image_path` must use the reference frame matching ITS content (spread the frame library: interview frames for portrait beats, explosion frames for blast beats, factory frames for production beats — NOT one person frame for everything); (b) verify by vision model or by content check that adjacent sub-shots differ in subject — if two consecutive renders show the same person/same object as the center, regenerate with a different reference + different subject phrasing. Uniqueness = different reference + different subject + different composition family, not different file bytes.
- **NO LABEL TEXT IN PERSON IMAGES (L-037 — verified EP.02):** never put the typewriter-label instruction in prompts for images whose reference frame contains people. Image models draw the label AT RANDOM POSITIONS (often over the face) and hallucinate names (the model once wrote "Dr. Zhao Tianlin" on a portrait that was actually Zhu Yusheng). For person frames: generate CLEAN images, add labels as HTML overlay elements in compose. Labels in prompts are allowed ONLY for non-person images (maps, charts, blueprints, objects).
- **FACE-PROTECTED STYLE FOR PERSON IMAGES (L-038 — verified EP.02):** the shared Vox style block contains "red string and brass pins" decoration instructions — image models draw these ACROSS THE FACE at uncontrolled positions. For any image whose reference frame contains people, strip ALL red-string/brass-pin decoration phrases from the style block (the yaml has them in MULTIPLE phrasings: "red string and brass pins where the story calls for connections,", "red string and brass pins,", "red string connections", "brass pins") and append: "The face of any person must be completely clear and unobstructed: no lines, no pins, no string, no text, no elements crossing or covering the face." Body/background decorations are fine — only the FACE must stay clean. Verify with a vision model that no red line crosses the face before rendering.

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
    # 语义：显式传 emo_vector = 固定情感、关闭自动文字判情感。
    # 若省略 emo_vector，indextts_tts 默认从文字自动判情感（use_emo_text）。
    # 本管线要求纪录片平静语感，必须保持显式传 calm 向量。
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

**Idempotent batch generation (L-046 — verified EP.02):** batch image scripts MUST only generate MISSING files (skip existing). Never clear the output directory inside a batched loop — chunked runs wiped earlier batches (55/63 images lost). Clear once via an explicit env flag (`CLEAN_FIRST=1`) then run the FULL batch in one pass.

**Transcribe the final narration (MANDATORY — feeds scene plan + subtitles):**
After the narration WAVs pass the duration check, run the transcriber on each segment (or the concatenated episode audio) with **word-level timestamps** enabled:
- Scene plan stage uses segment start/end to align scene windows to voice boundaries (never cut mid-sentence)
- Compose stage uses word timestamps for the karaoke subtitle highlight
- Store the transcript JSON in `assets/audio/` and reference it from the manifest (`narration_segments[].transcript_path`)
- **TRIM LEADING SILENCE FIRST (L-050 — verified EP.02):** IndexTTS2 WAVs carry 1.2-7.2s leading silence (measured: s09 7.17s, s06 4.2s, s08 4.3s). Trim it (silencedetect -50dB, cut lead − 0.15s) BEFORE transcribing — timestamps shift and scene windows must be built on the TRIMMED audio, otherwise narration appears 3-7s late and the tail gets cut. Verify each trimmed WAV starts with ≤0.2s silence.

**VOICE-AUDIO PIPELINE (mandatory tool chain — EP.02 root-cause fix, prevents K-01/K-02/K-06):**
```
python tools/trim_audio_lead.py <episode_dir>      # 1. 裁前导静音 -> *_clean.wav（K-02）
python tools/gen_voice_windows.py <episode_dir>    # 2. 转写 -> 语音边界窗口（K-01，禁止词数均分）
python tools/build_episode_parts.py ...            # 3. 组装（用语音窗口）
python tools/verify_sync.py <episode_dir>          # 4. 合并前强制验证（K-01/K-02/K-05/K-06，FAIL 则 exit 1）
```
These three tools are the ONLY sanctioned way to produce scene windows and audio for compose. Never divide windows by word count; never use untrimmed WAVs; never merge before `verify_sync.py` passes.

**Paper-craft SFX:** see compose-director Step 2d — the 6 ffmpeg-synthesized SFX WAVs live in the HyperFrames workspace `assets/sfx/`.

**DURATION CHECK (mandatory gate — this catches underwritten scripts):**
After every segment is synthesized, measure actual duration with `ffprobe`:
- `actual_duration = ffprobe(seg_N.wav)`; `target_duration = scene_plan duration for that section`
- **If `actual_duration < target_duration × 0.95`, the script is UNDERWRITTEN. Do not pad audio.** Go back to the rewrite stage: expand the narration text with more specific factual detail (names, numbers, dates, physical description) so the word count meets `target_duration × measured_wps`, then regenerate the segment.
- If `actual_duration > target_duration × 1.10`, trim the scene duration in the scene plan to match (narration is the master clock; visual scenes flex to it).
- **RE-APPLY AFTER EVERY PLAN REWORK (L-039 — verified EP.02):** if scene_plan.json is regenerated for ANY reason (composition rework, family changes), the audio-duration correction MUST be re-run — regenerating from word-count math silently drops the correction and truncates narration (EP.02 lost up to 19.4s on one scene). Final gate: every scene's plan duration must be >= its actual audio duration + hold.
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
