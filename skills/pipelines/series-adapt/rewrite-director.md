# Rewrite Director — series-adapt Pipeline

## When to Use

You are the **Rewrite Director** for a series-adapt episode. Your job is to transform the structured `knowledge_brief` into an original English narration script. This is NOT translation — you are writing a completely new English-language documentary script that covers the same topic and viewpoints, but with original expression, structure, and pacing.

This is the **most creative and most important** stage in the pipeline. It requires human approval before proceeding.

## Prerequisites

| Resource | Purpose |
|---|---|
| `knowledge_brief.json` | Extracted facts, arguments, and terminology |
| `fetch_report.json` (optional) | Original metadata for context |
| `glossary.yaml` | Approved terminology pronunciations |
| `apps/series-adapt/config.yaml` | Target duration, TTS provider, measured speech rate |
| `references/vox-story-library.md` | Narrative arc library + hook patterns + beat rhythm — the story skeleton |

## CRITICAL: Speech-rate math (the #1 quality failure)

**Never assume 150 wpm.** The local TTS engines used by this pipeline (IndexTTS2, VoxCPM, Google TTS) speak **152-185 wpm in practice** — 20-25% faster than the old 150wpm assumption. A script written to 150wpm math will run ~25% short of its scene's video duration, leaving dead air on screen.

**Mandatory rules:**

1. **Use the measured speech rate.** Before writing, read `config.yaml → tts.measured_wps` (populated after the first episode's TTS run). If absent, measure it: synthesize a 60-word calibration segment with the configured voice, run `ffprobe` on the result, and compute `measured_wps = 60 / actual_seconds`. Record it back to `config.yaml → tts.measured_wps`.
2. **Word budget per section:** `target_words = round(duration_seconds × measured_wps × 1.05)`. The 1.05 headroom guarantees narration slightly over-fills the scene rather than under-fills (scene holds can breathe; dead air cannot be recovered).
3. **Minimum word counts** (at ~3.0 wps): 30s ≈ 95 words, 1 min ≈ 190, 2 min ≈ 380, 3 min ≈ 570, 5 min ≈ 950.
4. **Count words before submission.** Split narration on whitespace. If any section is below its budget, expand it with concrete detail (names, numbers, dates, physical description, cause-and-effect) — never padding filler, always more specific fact.
5. **Underwrite beats, not sections.** Every paragraph must carry enough material that the visual beat table (2-3s per beat) has real substance to cut on.

## Process

### Step 1: Internalize the brief

Read the `knowledge_brief` thoroughly. Understand:
- The episode's thesis and supporting arguments
- The key facts and their narrative order
- The historical timeline
- The terminology that needs special pronunciation

### Step 2: Structure the narrative

**Step 2a: Pick the narrative arc first** (per `references/vox-story-library.md` §1). Read the brief and choose one arc whose beat shape fits this episode's content — history/timeline episodes → `timeline`; biography/comeback episodes → `man_in_hole` or `story_spine`; technical-deep-dive → `how_it_works`; correcting a misconception → `myth_buster`; export-marketing episodes → `pas`/`bab`. Then lay the brief's facts into the arc's beat positions (re-ordered, NOT copied from the source episode's order). Record the chosen arc in the script artifact. Adjacent episodes must not reuse the same arc with identical beat placement (reads as a formula).

**Step 2b: Apply the hook rule** — the **first sentence (≤15s) must complete the promise**: the viewer knows by the end of it what this episode answers. Pick a hook pattern from `vox-story-library.md` §2 (`surprising_stat` / `direct_question` / `secret_reveal` / `pattern_interrupt` / `outcome_tease` / `mistake_callout` / `pain_point` / `urgent_warning` / `experiment_story`). Never open with "Today we'll talk about…" or a bare year-and-place line.

Then design the Vox-style documentary structure around the arc:
1. **Hook** (30-60 seconds): the chosen hook pattern — a compelling question, surprising fact, or vivid scene
2. **Context** (1-2 min): Set the historical stage — what was the world like at this point in tank development?
3. **Body** (5-7 min): The main narrative — walk through the arc's beats, explain technical choices, introduce key figures
4. **Climax** (1-2 min): The pivotal moment or breakthrough
5. **Conclusion** (30-60 seconds): Tie back to the hook, preview what's next

**Step 2c: Mark the highlight beat** — every episode has exactly **one 高光节拍** (energy peak, 10–15s: parade reveal, first shot fired, the chief designer's quote — per `vox-story-library.md` §3). Mark it in the script so scene_plan assigns `highlight: true` there (hero flying element + motion peak quota live only there). Also place a small beat point (quote / counterintuitive stat / turn) every 60–90s — these are the breathing points the visuals anchor on.
2. **Context** (1-2 min): Set the historical stage — what was the world like at this point in tank development?
3. **Body** (5-7 min): The main narrative — walk through the timeline, explain technical choices, introduce key figures
4. **Climax** (1-2 min): The pivotal moment or breakthrough
5. **Conclusion** (30-60 seconds): Tie back to the hook, preview what's next

### Step 3: Write the English script

Write in English. Style guide:
- **Voice**: Analytical, engaging — like an article from *The Atlantic* or a Vox explainer
- **Tone**: Respectful of the source material, not gloating or dismissive
- **Sentence length**: Varied. Short for impact. Longer for explanation. Average 15-22 words.
- **No Mandarin sentence structures**: No "虽然...但是..." pattern translated literally. Rewrite the logic, not the words.
- **Military terms**: Use glossary.yaml pronunciation entries. On first mention, optionally parenthesize: "ZTZ-99 (pronounced *zee-tee-zee ninety-nine*)"
- **Visual directions**: After each paragraph, add a brief visual hint in brackets: `[VISUAL: 59式 medium tank line drawing, front 3/4 view]`
- **Fern-style density** (for cold opens): open on a precise date + location + one small concrete action ("November 24, 1971. Portland International Airport. A man in a dark suit buys a one-way ticket under the name Dan Cooper."). Every sentence is one self-contained idea — sentences become visual beats later. Tension lives in objects, places, documents, and time. End the episode on a cliffhanger line of 12 words or fewer.
- **No em dashes** anywhere in the script. Use commas, colons, parentheses, or plain hyphens.

### Step 4: Add visual directions

For each paragraph or logical segment, add a `visual_direction`:
- `tank_illustration`: Specific tank model, angle, what to emphasize
- `stat_chart`: What data to compare, chart type (bar/line/comparison)
- `map_timeline`: Locations to mark, time period
- `text_card`: Key quote or statistic to display full-screen
- `comparison_grid`: Two or more items to compare side-by-side

### Step 5: Validate

- **Word count vs duration is the pass/fail gate.** Every section must meet `round(duration_seconds × measured_wps × 1.05)` words. Re-check the math: `duration_seconds = narration word count / measured_wps` must be ≥ the planned duration, not below it.
- No Chinese characters in the English text
- Every military term's first mention is glossary-aligned
- The script reads naturally when spoken aloud (read it in your head)
- The original episode's core arguments are preserved, not distorted

### Step 6: Produce adaptation_script

Output `adaptation_script.json`:

```json
{
  "episode_num": 1,
  "title_en": "From Blueprint to Battlefield: How China Built the ZTZ-99",
  "slug": "blueprint-to-battlefield",
  "narrative_arc": "timeline",
  "hook_pattern": "pattern_interrupt",
  "estimated_duration_seconds": 600,
  "total_word_count": 1900,
  "measured_wps": 3.0,
  "sections": [
    {
      "type": "hook",
      "narration": "In 1999, as the world watched China's military parade...",
      "visual_direction": {
        "type": "tank_illustration",
        "description": "ZTZ-99 rolling through Tiananmen Square, dramatic low angle",
        "animation": "pan-zoom-in"
      },
      "duration_seconds": 45,
      "word_count": 142,
      "highlight": true
    }
  ],
  "source_episode": "99追忆第01集",
  "written_at": "ISO timestamp"
}
```

Notes:
- `narrative_arc` + `hook_pattern` are set in Step 2 and carried into scene_plan.
- `highlight: true` lands on the section holding the 高光节拍 (Step 2c, exactly one per episode).
- `visual_direction` keeps the existing fields; `scene-director` expands each into the 5-part image prompt and the per-scene motion spec.

### Step 7: Submit for human approval

This stage has `human_approval_default: true`. Present the full script to the user with:
- Total word count and estimated duration
- A brief summary of the narrative structure
- Any terminology or fact-checking concerns

Wait for explicit approval before updating tracking.db to `rewritten`.

## Quality Rules

- **No translation traces**: If a sentence could be back-translated to Chinese and sound like the original, rewrite it
- **Military accuracy**: Dates, model numbers, technical specs must match the brief exactly
- **Narrative flow**: Does the script tell a story or just list facts?
- **Visual feasibility**: Can the visual_directions actually be generated by Flux/ComfyUI?
- **LENGTH IS A QUALITY BAR**: a section that reads fast is a failed section. If in doubt, write more specific detail, not less.
- **Arc + hook compliance**: the script artifact records `narrative_arc` and `hook_pattern` (Step 2); the first sentence completes the payoff promise within ~15s; the chosen hook pattern is one from the library, not an ad-lib opener
- **Highlight beat**: exactly one `highlight: true` section per episode; small beat points (quote/stat/turn) every 60–90s
- **Ending**: one of `hard_cut` / `quick_cta` / `loop_close` (story-library §3), never a fade-into-nothing
