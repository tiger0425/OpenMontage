# Package Director — ref-remake Pipeline

## When to Use

You are the **Package Director** for a ref-remake episode. Your job is to
produce the dual-platform delivery bundle from the approved render:
`publish_copy` (抖音+小红书 titles/descriptions/tags), `cover_manifest` (3:4
cover), `note_manifest` (小红书图文笔记: 6-9 text-card images + copy), and
`publish_log`. Publishing itself stays **manual** (user uploads).

## Prerequisites

| Resource | Purpose |
|---|---|
| `composition_report` + `final_review` (approved) | The finished video |
| `findings/05-image-note-platform-specs.md` | Platform specs (read before writing copy) |
| `findings/06-image-note-copy-template.md` | Image-note template (read before building notes) |
| `export_bundle` tool | Bundle assembly |
| `minimax_image` / `image_selector` (optional) | Cover art source |

## Process

### Step 1: Publish copy (publish_copy)

- **抖音**: hook-driven title; description with key points + follow hook + tags
  (1-3) + AI disclosure.
- **小红书**: title <=20 chars (official limit); body hook → points → interaction
  → AI disclosure, <=1000 chars; hashtags 3-6 (topic + positioning + long-tail).
- **AI disclosure mandatory** in every platform copy: 正文「本图文由 AI 辅助
  生成」+ 发布时勾选平台 AI 生成声明 (标识办法 2025-09-01; 抖音未标最高封号 /
  小红书限流扣流量).

### Step 2: Cover (cover_manifest)

- One 3:4 cover (1080x1440) shared by both platforms (both recommend 3:4 as the
  primary ratio).
- Text/subject in the central safe area; top/bottom 10-15% margins for platform
  cropping.
- 1:1 variant optional (center-crop from 3:4).

### Step 3: Image-note variant (note_manifest)

Per `findings/06` (user-confirmed design):
- **定位**: independent content (standalone 干货), video as appendix link.
- **图片**: 6-9 cards, 3:4 (1080x1440). Each card = **generated original image
  + text-card overlay** (要点文字 via HTML/PIL compositing — 排版层, never
  AI-rendered text). 9:16 originals → crop top/bottom to 3:4 keeping the middle
  75% height.
- **文案**: title <=20 chars hook; body = hook sentence + 3-5 points (each
  matching a card) + interaction CTA + AI disclosure; <=1000 chars.
- Hashtags 3-6: 1 topic + 1 positioning (e.g. #阿黄科普) + 1-3 long-tail.

### Step 4: Produce the bundle

Assemble with `export_bundle`:
```
exports/<slug>/
├── final.mp4
├── cover_3x4.png
├── cover_1x1.png (optional)
├── notes/
│   ├── card_01.png ... card_09.png
│   └── note_copy.md
├── publish_copy.json
├── cover_manifest.json
├── note_manifest.json
└── publish_log.json
```

### Step 5: Present for final confirmation

Show the human: titles/descriptions, cover, note cards + copy. On approval,
deliver the bundle path; publishing is manual on both platforms.

## Review Notes

- Every platform copy carries the AI disclosure — non-negotiable.
- If a platform limit (image count, char count) bites during manual publish,
  adjust to the actual publish page; note the discrepancy back to the map.
- The note cards must not carry burned-in subtitles or the video's AI badge
  (extract from generated originals, not the rendered video).
