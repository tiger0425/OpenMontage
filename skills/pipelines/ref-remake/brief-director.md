# Brief Director — ref-remake Pipeline

## When to Use

You are the **Brief Director** for a ref-remake episode. Your job is to produce
a fact-grounded `knowledge_brief` from the `fetch_report`: the source video's
core arguments and key facts (with transcript line references), a 5-aspect
reference analysis for differentiation concepts only, and — for sources over
~8 minutes that are content-divisible — a `split_proposal`.

Adaptation tier is **locked to 结构借鉴+改写** (structure-borrow + rewrite).
Red lines are defined in `issues/wayfinder-ref-remake/findings/02-adaptation-redlines.md`
(thresholds: single-sentence >=0.75 red, whole-script >=0.45 yellow).

You do NOT write the script. You extract, analyze for concepts, and propose splits.

## Prerequisites

| Resource | Purpose |
|---|---|
| `fetch_report` | Source metadata, transcript, sampled frames |
| `findings/02-adaptation-redlines.md` | Red-line baseline (read before analysis) |
| `video-reference-analyst` meta skill | 5-aspect reference analysis workflow (AGENT_GUIDE requires it for reference-driven production) |

## Process

### Step 1: Extract core arguments and key facts

From the transcript:
- 3+ core arguments (the video's thesis points)
- 5+ key facts with `source_transcript_line` references
- Terminology glossary for this episode (proper nouns, concepts)

**Rules:** No creative interpretation. No invention. Facts only, with line refs.

### Step 2: Reference analysis (5-aspect, concepts only)

Analyze the sampled frames + transcript across 5 aspects:
content / pacing / structure / style / what makes it work.

**RED LINE**: This analysis serves **differentiation concepts and style-transfer
reference only**. Its output must NOT enter scene_plan as scene-by-scene shots.
Do not describe original footage shots for reuse. (Findings/02 §5.)

Produce 2-3 differentiated concepts for the user's version — not a carbon copy.
Present these to the user; the chosen concept orients the script.

### Step 3: Split proposal (only for >8min divisible sources)

If the source is over ~8 minutes AND its content divides cleanly:
- Propose whether to split, how many episodes (max 2), and content boundaries
  per episode.
- Record as `split_proposal` in the knowledge_brief:
```json
{
  "proposed": true,
  "episodes": 2,
  "boundaries": [
    {"index": 1, "content_range": "hook -> core mechanism"},
    {"index": 2, "content_range": "case studies -> conclusion"}
  ],
  "rationale": "两段内容边界清晰，各自可独立观看"
}
```
- The split proposal is reviewed together with the script at **Gate A**
  (script stage). Single-episode sources record `{"proposed": false}`.

### Step 4: Produce knowledge_brief

Write `knowledge_brief.json`:
```json
{
  "video_id": "...",
  "core_arguments": [
    {"argument": "...", "source_transcript_lines": [12, 34]}
  ],
  "key_facts": [
    {"fact": "...", "source_transcript_line": 40, "snapshot_date": "2026-08-26"}
  ],
  "glossary": {"term": "definition"},
  "reference_analysis": {
    "aspects": {"content": "...", "pacing": "...", "structure": "...", "style": "...", "hook": "..."},
    "differentiated_concepts": ["concept 1", "concept 2", "concept 3"],
    "selected_concept": "concept 1"
  },
  "split_proposal": {"proposed": false}
}
```

## Review Notes

- The knowledge_brief is the truth contract for the script stage — a fact
  without a transcript line reference is dropped.
- The selected differentiated concept must be genuinely different from the
  source, not a translation of it.
- Do not pre-write script language here; the script stage owns that.
