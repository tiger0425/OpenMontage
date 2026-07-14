# Publish Director — Fabric Showcase Pipeline

## When To Use

Package the fabric showcase video for platform delivery. This stage generates platform-appropriate cover images, builds the export package with metadata, and verifies platform fit before handoff.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["compose"]["render_report"]`, `state.artifacts["brief"]["fabric_brief"]` | Output video and fabric direction |
| Tools | `cover_gen` (aspirational — fall back to `custom_scripts` with Python Pillow) | Cover image generation |
| Playbook | custom_only | No fixed playbook |

## Process

### 1. Generate Platform Cover Images

Cover generation uses a HyperFrames snapshot frame + Python Pillow overlay. The `cover_gen` tool is the designated tool; if unavailable (not yet implemented), use `custom_scripts` with the same approach.

**Cover specs by platform:**

| Platform | Aspect | Resolution | Target |
|----------|--------|------------|--------|
| 小红书 | 3:4 | 1080 × 1440 | Cover |
| 抖音 | 9:16 | 1080 × 1920 | Cover |
| B站 | 16:9 | 1080 × 608 | Cover |
| B站 | 16:9 | 1920 × 1080 | Video (if horizontal) |

**Cover design rules:**

- **Title** = fabric_brief.fabric_facts name (e.g., "复古红格")
- **Subtitle** = fabric_brief.ad_intent.brand_name or composition (e.g., "铃月布行 · 55%麻45%棉")
- **Badge** = toolchain badge (e.g., "Klein + LTX23 + edge-tts + HyperFrames")
- **Font**: Use calligraphy fonts downloaded from Google Fonts (MaShanZheng, ZhiMangXing, LiuJianMaoCao). For Chinese text rendering, use Python Pillow — ffmpeg drawtext fails with Chinese on some platforms.
- **Color scheme**: Match fabric_brief.fabric_facts.color_palette. Extract dominant color from the snapshot frame.
- **Snapshot frame**: Take at the most visually striking moment in the video (typically scene 1's title reveal or scene 4's final frame).

### 2. Organize Export Package

Structure the output directory:

```
projects/<project-id>/export/
├── video.mp4              # Hero video
├── cover_xiaohongshu.jpg   # 小红书封面
├── cover_bilibili.jpg      # B站封面
├── title.txt              # 平台标题
└── description.txt        # 平台描述
```

**Naming convention:**
- Video: `{platform}_{product_name}_{timestamp}.mp4`
- Cover: `{platform}_{product_name}_{aspect}.jpg`

### 3. Verify Platform Content Fit

For each target platform from `fabric_brief.ad_intent.platform`:

**小红书:**
- Title ≤ 20 Chinese chars
- Description includes: fabric facts, applicable products, style direction
- Cover is 3:4 ratio

**抖音:**
- Video focus: first 3s hook should play without sound (add captions if needed)
- Cover is 9:16

**B站:**
- Video can be longer (up to 60s) if needed
- Cover is 16:9
- Description can include toolchain/detail notes

### 4. Build Publish Log

```json
{
  "version": "1.0",
  "entries": [
    {
      "platform": "xiaohongshu",
      "status": "exported",
      "export_path": "export/video.mp4",
      "timestamp": "2026-07-14T12:00:00Z",
      "metadata_used": {
        "title": "复古红格面料｜55%麻45%棉",
        "description": "铃月布行新款复古红格面料。55%亚麻45%棉，亲肤透气，适合衬衫、连衣裙、帆布包。设计师选品首选。",
        "hashtags": ["#面料", "#复古红格", "#亚麻棉混纺", "#设计师选品"]
      }
    }
  ]
}
```

### 5. Quality Gate

- Cover text checked against `fabric_brief.fabric_facts` — no unsubstantiated claims
- Cover dimensions match target platform
- Export directory is self-contained (video, cover, metadata)
- Platform descriptions are filled and appropriate

## Common Pitfalls

- **Cover text with unsubstantiated claims**: "有机棉" or "抗菌" in the cover text must be backed by fabric_facts. If fabric_brief doesn't have these claims, don't add them.
- **Cover-to-video style mismatch**: Cover font/style should feel like the video's opening frame. A sleek modern cover followed by a rustic video is jarring.
- **Wrong cover aspect ratio**: Uploading a 16:9 cover to B站 is fine; uploading a 16:9 cover to 小红书 gets cropped badly. Check the platform field.
- **Missing metadata**: Title and description are part of the deliverable. They should be written in the brief stage and finalized here.

## Cover Design Tips (from production experience)

- **Font hierarchy**: Title (bold calligraphy, large) + Subtitle (smaller, lighter) + Badge (smallest, at bottom)
- **Color**: Gold or white text works on dark fabric backgrounds; dark text on light backgrounds
- **Layout**: Center text, fabric texture in background with subtle blur
- **Fonts**: Chinese calligraphy fonts (ZhiMangXing for 行书 style, MaShanZheng for regular) give better brand feel than system fonts for fabric product covers
- **Pillow vs ffmpeg**: On Windows, ffmpeg drawtext with Chinese characters often fails silently. Python Pillow with `ImageFont.truetype()` is the reliable path.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
