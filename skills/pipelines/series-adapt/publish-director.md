# Publish Director — series-adapt Pipeline

## When to Use

You are the **Publish Director** for a series-adapt episode. Your job is to prepare the complete YouTube upload package: SEO-optimized metadata, chapter markers, thumbnail concept, source attribution, and AI disclosure. This is the final stage — the user reviews the package and approves it for manual upload.

## Prerequisites

| Resource | Purpose |
|---|---|
| `composition_report.json` | Final video path and technical specs |
| `final_review.json` | Confirmation that video passed human review |
| `adaptation_script.json` (optional) | For chapter titles |
| `knowledge_brief.json` (optional) | For description content |
| `glossary.yaml` | For tag generation |
| `export_bundle` tool | Package assembly |

## Process

### Step 1: Write YouTube title

**Formula:** `[Topic Hook]: [What Makes It Interesting] | [Series Name]`

- Hook must include searchable keywords (ZTZ-99, China, Tank, MBT, Military History)
- Keep under 70 characters for full display in search results
- Title case for English
- Include episode number for series organization

**Example:** `China's Tank Revolution: How the ZTZ-99 Was Born | Iron Dragon E01`

### Step 2: Write YouTube description

Structure:

```
[HOOK - 1-2 sentences teasing the episode content]

[EPISODE SUMMARY - 3-5 paragraphs covering what this episode teaches]
Paragraph 1: Historical context
Paragraph 2-3: Key developments covered
Paragraph 4: Why this matters / what's next

[TIMESTAMPS]
00:00 - [Chapter title]
01:23 - [Chapter title]
...

[SOURCE]
This episode is an original English recreation based on 人畜无害小托比's
【99追忆】series (@toby5906 on YouTube). The narration and visuals are
independently produced.

[DISCLOSURE]
This video features AI-generated visuals and synthetic voice narration
cloned from the creator's own voice using IndexTTS2 technology.
```

### Step 3: Generate tags

Compose 15-20 tags covering:
- Broad category: `tanks`, `military history`, `documentary`
- Specific vehicles: `ZTZ-99`, `Type 99`, `MBT`, `main battle tank`
- Country/era: `Chinese defense`, `PLA`, `Cold War tanks`
- Technical: `armor technology`, `tank design`, `military engineering`
- Series: `Iron Dragon`, `tank documentary`
- From glossary: vehicle model keywords

### Step 4: Create thumbnail concept

Write a text description for a thumbnail. The YouTube thumbnail rules:
- 1280×720 resolution
- High contrast, large readable text (max 5 words)
- One clear focal point (a tank, a face, a dramatic scene)
- Brand color: military green accent

**Example concept:**
```
Split composition: left side shows a flat-vector ZTZ-99 tank
in dramatic low-angle view. Right side has bold white text
"IRON DRAGON" with military-green underline. Background is
dark (#1a1a2e). Small gold "EP.01" badge in top-right corner.
```

### Step 5: Choose category and settings

- YouTube category: `Science & Technology`
- Language: English
- Captions: None (narration is English, no burned-in captions needed for Vox style)
- Visibility: Private or Unlisted (user decides at upload)
- Made for Kids: No

### Step 6: Assemble export bundle

Call `export_bundle` with the final video and all metadata. Output to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/publish/
├── final.mp4
├── metadata.json
├── thumbnail_concept.txt
├── publish_log.json
└── srt/
    ├── ep01.en.srt        # English captions (from script narration, not whisper text)
    └── ep01.zh.srt        # Chinese captions (aligned 1:1 with EN segments)
```

**SRT generation (mandatory — L-032):** videos ship WITHOUT burned-in subtitles; captions are SRT sidecars only. Generate `srt/ep01.en.srt` + `srt/ep01.zh.srt` from the per-scene word-level transcripts (whisper timestamps) + script narration text (EN display words) + `{sid}_zh.json` (ZH lines), offset by the merge timeline (s01 full, s02+ trimmed by head-trim seconds, 0.5s xfade overlaps between scenes).

### Step 7: Execute upload

Run the upload script (L-033 — verified on EP.01):

```bash
python bin/upload_youtube.py projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}
```

The script automatically: uploads the video (private), attaches `ep01.en.srt` + `ep01.zh.srt`, creates/reuses the series playlist ("Iron Dragon - The Story of China's Tanks") and adds the video, then updates `publish_log.json` (video_id, upload_status).

- **Human gate:** video uploads PRIVATE. The user reviews on YouTube Studio, then either runs the same command with `--publish` or flips visibility manually. Never upload public without user confirmation.
- **Metadata tweaks:** `python bin/upload_youtube.py <episode_dir> --update-only` re-applies title/description/tags to the already-uploaded video (no re-upload needed).
- One-time setup: `client_secret.json` (OAuth Desktop app) at `%USERPROFILE%\.youtube-upload\`, API enabled in Google Cloud Console, user added as test user on the OAuth consent screen.

### Step 7: Produce publish_log

```json
{
  "episode_num": 1,
  "youtube": {
    "title": "China's Tank Revolution: How the ZTZ-99 Was Born | Iron Dragon E01",
    "description": "...",
    "tags": ["tanks", "military history", ...],
    "category": "Science & Technology",
    "language": "en",
    "chapters": [
      {"time": "00:00", "title": "Introduction"},
      ...
    ],
    "thumbnail_concept": "..."
  },
  "source_credit": {
    "channel_name": "人畜无害小托比",
    "channel_url": "https://www.youtube.com/@toby5906",
    "series_name": "99追忆",
    "license": "Original English recreation, independently produced"
  },
  "disclosure": {
    "ai_visuals": true,
    "synthetic_voice": true,
    "voice_source": "Creator's own voice, cloned via IndexTTS2"
  },
  "published_at": "ISO timestamp",
  "upload_status": "ready_for_manual_upload"
}
```

Update tracking.db status to `published`.

## Quality Rules

- Title must be under 70 characters
- Description must include timestamp chapters
- Tags must contain at least 3 specific vehicle model names
- Source credit and AI disclosure are mandatory in description
- Thumbnail concept must describe a concrete, producible thumbnail
- Export bundle must contain all 4 files (video, metadata, thumbnail_concept, publish_log)
