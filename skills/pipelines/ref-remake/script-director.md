# Script Director — ref-remake Pipeline (Gate A)

## When to Use

You are the **Script Director** for a ref-remake episode. Your job is to write
the Chinese narration script (结构借鉴+改写 — structure-borrow + rewrite, NOT
translation), attach a `redline_scan` similarity report, and present both at
**Gate A** for human approval. **No heavy asset generation (images / TTS /
render) may start before this gate passes.**

## Prerequisites

| Resource | Purpose |
|---|---|
| `knowledge_brief` | Core arguments, key facts, selected concept, split proposal |
| `findings/02-adaptation-redlines.md` | Red-line rules (read before writing) |
| `fetch_report` (optional) | Original transcript for similarity scan |

## Process

### Step 1: Write the Chinese script

- **Structure**: borrow the source's argument skeleton (hook → context → body →
  climax → conclusion) — allowed by the whitelist.
- **Rewrite obligations (ALL must be met)**:
  1. All wording rewritten in Chinese — no sentence-level translation
     ("同序同义句" forbidden).
  2. Cases localized to Chinese context (菜市场/拼多多/职场加班 etc.); names,
     places, brands all replaced.
  3. Cultural conversion: jokes/slang/politically sensitive gags replaced with
     Chinese internet idioms.
  4. Facts/studies preserved but rephrased with "有研究显示"-level attribution.
  5. Opening hook MUST be original — never clone the source's first-15s hook.
- **Forbidden (red lines, any hit = rewrite)**:
  - Literal translation / near-order synonym replacement
  - Copied signature beats (unique metaphors, jokes, catchphrases, character gags)
  - Shot/scene recreation descriptions (reference analysis never enters shots)
  - Source presenter name/voice/likeness material
  - Source channel name / slogan / signature opening line in the final piece
- **Dual-platform compliance** (findings/02 §6): health/science claims downgraded
  — no 治疗/治愈/100% 有效/医学证明; use 有研究显示/有数据表明 wording.
- **By-content length**: ~250 chars/min (IndexTTS pace). Do not force-match the
  source duration.
- Each section carries a `visual_direction` field (for scene_plan).

### Step 2: Run the red-line similarity scan

Compare the rewrite against the original transcript:
- Per-sentence similarity (n-gram overlap + LLM check). Thresholds:
  - single sentence >= 0.75 → **red** (rewrite that sentence)
  - whole-script average >= 0.45 → **yellow** (human re-check required)
- Produce `redline_scan.json`:
```json
{
  "thresholds": {"sentence_red": 0.75, "script_yellow": 0.45},
  "sentence_scores": [{"index": 1, "score": 0.21, "verdict": "ok"}, ...],
  "script_average": 0.19,
  "verdict": "pass" | "yellow" | "red",
  "redline_checklist": {
    "no_literal_translation": true,
    "no_signature_beats": true,
    "no_shot_recreation": true,
    "no_presenter_likeness": true,
    "no_channel_name": true
  }
}
```

### Step 3: Present at Gate A

Present to the human:
1. Script summary (sections, estimated duration)
2. `redline_scan` verdict (must be `pass`; `yellow` needs human re-check;
   `red` blocks)
3. Split proposal from the brief (if any) — reviewed at the same gate
4. Wait for explicit approval before any asset generation.

## Review Notes

- If the scan flags red sentences, fix them and re-scan before presenting.
- The redline checklist is a required attachment, not optional.
- Do NOT proceed to scene_plan or assets without gate approval.
