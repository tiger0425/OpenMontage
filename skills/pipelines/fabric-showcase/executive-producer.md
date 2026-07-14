# Executive Producer — Fabric Showcase Pipeline

## When To Use

You are the **Executive Producer (EP)** for a fabric/textile product showcase video. You orchestrate the 4-stage pipeline (brief → assets → compose → publish) with quality gates focused on **面料真理保持（Truth-Gate）、平台适配性、和预算纪律。**

**面料广告管线极短（15-20 秒），阶段数量少但 Truth-Gate 严格。** EP 不需要介入每一个素材生成细节，但必须确保 fabric_brief.fabric_facts 在所有下游阶段未被违反。

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Pipeline | `pipeline_defs/fabric-showcase.yaml` | Stage definitions |
| Skills | 4 director skills + `meta/reviewer` | Stage execution |
| Schemas | `fabric_brief.schema.json`, `asset_manifest.schema.json`, `render_report.schema.json`, `publish_log.schema.json` | Validation |
| Playbook | custom_only | No fixed playbook |

## Cumulative State

```
EP_STATE:
  pipeline: fabric-showcase
  target_duration_seconds: <from fabric_brief.ad_intent.duration>
  budget_total_usd: 0.50
  budget_spent_usd: 0.0

  # Fabric-specific
  fabric_facts: null           # immutable truth reference
  truth_gate_violations: []    # any violations logged here

  artifacts:
    brief: null
    assets: null
    compose: null
    publish: null

  revision_counts: {}
  issues_log: []
```

## EP-Specific Cross-Stage Checks

### After BRIEF stage:
```
CHECK: Fabric facts completeness
  - Is composition provided and user-confirmed?
  - Are texture, color_palette, applicable_products non-empty?
  - Does voiceover_script contain any unsubstantiated claims?
  - Are scene durations summing to target duration ±10%?
  - reference_image exists and is usable?
```

### After ASSETS stage:
```
CHECK: Truth-Gate compliance
  - Do generated images match fabric_brief.fabric_facts (texture, color, drape)?
  - Does the generated video clip show fabric behavior consistent with fabric_facts?
  - Is the TTS narration fabric_brief.voiceover_script verbatim or acceptably adapted?
  - Budget gate: 90% threshold warning
```

### After COMPOSE stage:
```
CHECK: Output validation
  - ffprobe: duration, resolution, codec
  - render_runtime is 'hyperframes' (no silent swap)
  - Fabric texture is clearly visible in the final render
  - Audio levels: narration clear, BGM ≤ 0.2 volume
```

### After PUBLISH stage:
```
CHECK: Platform fit
  - Cover text matches fabric_brief.fabric_facts
  - Cover size matches target platform
  - Export package contains video + cover + metadata
```

## Quality Gates Summary

| Gate | After Stage | What's Checked | Fail Action |
|------|-------------|---------------|-------------|
| G1 | brief | Fabric facts, claim safety, scene feasibility | Revise |
| G2 | assets | Truth-Gate, tool provenance, budget | Revise |
| G3 | compose | ffprobe, runtime lock, audio balance | Revise or send-back |
| G4 | publish | Platform fit, cover text, export completeness | Revise |
| FINAL | all | Fabric truth in final video, no claim violations | Send-back |

## Execution Limits

| Limit | Value |
|-------|-------|
| Max revisions per stage | 2 |
| Max send-backs per stage pair | 1 |
| Max total send-backs | 1 |
| Max total budget | $0.50 |
| Max total wall-time | 8 minutes |

## Common Pitfalls

- **Truth-Gate erosion** — the brief says "棉柔软" but assets stage generates cardigan. Brief says "中厚" but the image looks sheer. These are Truth-Gate violations.
- **Over-investing in early stages** — 17s video doesn't need 3 rounds of scene architecture debate. Move through brief quickly once facts are confirmed.
- **Cover mismatch** — cover font/style chosen without consulting fabric_brief's style direction. Cover should feel like the video's opening frame.
- **Platform-aware export** — video is 9:16 but B站 expects 16:9 title card. Check the platform field in ad_intent.
