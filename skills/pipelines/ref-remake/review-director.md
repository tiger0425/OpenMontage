# Review Director — ref-remake Pipeline (Human Gate)

## When to Use

You are the **Review Director** for a ref-remake episode. Your job is to
quality-check the rendered video (frame sampling + MiniMax-M3 visual QA), check
it against the script and the V2 style rules, and produce a `final_review` for
**human approval**. No delivery before this gate passes.

## Prerequisites

| Resource | Purpose |
|---|---|
| `composition_report` | Output path, duration, render metadata |
| `script` (approved) | What the video should say |
| `asset_manifest` (optional) | Image/anchor provenance for consistency checks |
| `minimax-m3-vision` skill | Frame analysis workflow (`.agents/skills/minimax-m3-vision/scripts/analyze_media.py`) |
| `background_library/ref-remake/README.md` | Anchor image for consistency comparison |

## Process

### Step 1: Extract frames

Sample keyframes from the render (e.g. one frame per scene at a stable moment).
Avoid sensitive frames that would 422 on the vision API — sample per-frame with
tolerance.

### Step 2: Visual QA (MiniMax-M3)

Check each sampled frame against:
1. **Character consistency vs anchor**: transparent glasses showing eyes, yellow
   capsule blob, thick black outline — the whole point of the anchor.
2. **Textless rule**: no AI-rendered text in image areas (text should come from
   the HTML overlay only).
3. **V2 点缀式**: 阿黄 focal 50%+, centered; <=3 decorations, content-relevant;
   clean background (no full-room clutter).
4. **Sync**: visual-to-audio sync frame-accurate.

### Step 3: Audio QA

- Voice fidelity: narration matches the cloned reference voice.
- No clipping, no static, no timing gaps.
- BGM (if any) under narration (-18dB), ducking correct.

### Step 4: Dual-platform suitability

- 9:16 vertical, safe-area respected.
- No in-video AI badge burned into the render (keeps the image professional); AI
  disclosure is handled at publish time via the platform checkbox + platform-side
  badge (《标识办法》2025-09-01, findings/05: creator-side checkbox is the primary
  mechanism, no need to draw a badge into the video).
- Health/science wording: no absolute claims slipped through (治疗/治愈/100%).

### Step 5: Produce final_review

Write `final_review.json`:
```json
{
  "output": "renders/final.mp4",
  "checks": {
    "character_consistency": {"passed": true, "notes": "..."},
    "textless_rule": {"passed": true, "notes": "..."},
    "v2_style": {"passed": true, "notes": "..."},
    "sync": {"passed": true, "notes": "..."},
    "voice_fidelity": {"passed": true, "notes": "..."},
    "audio_clean": {"passed": true, "notes": "..."},
    "platform_suitability": {"passed": true, "notes": "..."}
  },
  "approval_status": "approved" | "changes_requested",
  "revision_items": [{"stage": "assets", "item": "..."}]
}
```

## Review Notes

- Present the review summary + sampled frames to the human; wait for approval.
- If rejected, list concrete revision items with target stages — never vague
  "rework it".
- Lessons learned: if the episode deviated from a director skill or the
  playbook, note it (feed back into skills/playbook).
