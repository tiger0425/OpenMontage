# Scene Director — ref-remake Pipeline

## When to Use

You are the **Scene Director** for a ref-remake episode. Your job is to turn the
approved Chinese script into a `scene_plan`: ordered scenes mapped to narration
segments, with estimated durations, per-scene visual approach (V2 点缀式), and
asset requirements for the assets stage.

## Prerequisites

| Resource | Purpose |
|---|---|
| `script` (approved at Gate A) | Narration sections + visual_direction per section |
| `styles/ref-remake.yaml` | V2 点缀式 style rules (read before planning) |
| `background_library/ref-remake/README.md` | Anchor image + consistency rules |

## Process

### Step 1: Map scenes to narration segments

- Split the script into scenes along narration segment boundaries (~10-12
  segments typical, matching TTS segment granularity).
- Estimated duration per scene: ~250 chars/min (measured TTS durations replace
  these in assets/compose).

### Step 2: Visual approach per scene (V2 点缀式)

For each scene, specify:
- **Hero**: 阿黄 (yellow capsule blob) — focal point, 60%+ of frame, centered.
- **Decoration**: 1-3 content-necessary icons/props only (e.g. 耳膜破裂小图、
  病菌小圆球、血压计小图标). NO full rooms, no crowds, no street scenes.
- **No text in images**: all titles/numbers/captions come from the HTML overlay
  layer (无字底稿).
- **RED LINE**: never describe the original video's shots/composition — the
  reference analysis is concepts/style only (findings/02 §5).

### Step 3: Asset requirements per scene

Record `required_resources` per scene:
- narration text (the segment it covers)
- 3-4 image prompts by semantic split (style block + scene description)
- anchor reference flag (all scenes use the anchor)
- audio (TTS segment)

### Step 4: Produce scene_plan

Write `scene_plan.json`:
```json
{
  "scenes": [
    {
      "id": "s0",
      "narration": "..." ,
      "narration_chars": 45,
      "duration_estimate_s": 11,
      "visual": {
        "hero": "阿黄 阅读场景",
        "decorations": ["书本小图标 x2", "灯泡图标 x1"],
        "image_prompt_segments": 3,
        "anchor": "background_library/ref-remake/anchor/ahhuang_anchor.png"
      },
      "required_resources": ["image x3", "tts segment x1"]
    }
  ]
}
```

## Review Notes

- Continuous windows, no timeline gaps — the sum of scenes covers the full
  script.
- Split episodes each get their own scene_plan.
- Keep decorations minimal — "讲内容必需" is the test. If an icon isn't
  necessary to the narration, drop it.
