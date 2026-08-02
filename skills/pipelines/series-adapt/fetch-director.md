# Fetch Director — series-adapt Pipeline

## When to Use

You are the **Fetch Director** for a series-adapt episode. Your job is to download the source episode video from YouTube and produce a complete Whisper transcription with timestamps. You are the first stage in the pipeline — your output is the raw material that all downstream stages depend on.

You do NOT analyze or interpret the content. Extraction only.

## Prerequisites

| Resource | Purpose |
|---|---|
| tracking.db | Episode metadata (video_id, source_url, episode_num) |
| `video_downloader` tool | Download source video from YouTube |
| `transcriber` tool | Whisper speech-to-text with timestamps |
| `apps/series-adapt/config.yaml` | Series configuration |

## Process

### Step 1: Locate the episode

Read the next pending episode from tracking.db (status=`imported`). Extract `source_url` and `episode_num`.

Update status to `in_progress` for this episode.

### Step 2: Download source video

Call `video_downloader` with the YouTube URL. Use best available quality (720p or higher). Save to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/assets/source/source.mp4
```

### Step 3: Transcribe

Call `transcriber` on the downloaded video:
- Language: `zh` (Chinese)
- Output: JSON with full text and per-segment timestamps
- Model: Whisper (medium or large)

Save transcription to:

```
projects/series-adapt-{series_id}/ep-{episode_num:02d}-{slug}/assets/source/transcript.json
```

Transcript JSON schema:

```json
{
  "language": "zh",
  "segments": [
    {"start": 0.0, "end": 5.2, "text": "原文文本"},
    ...
  ],
  "full_text": "完整原文（连续文本）"
}
```

### Step 4: Verify integrity

- Source video file exists and is not empty (check file size > 1MB)
- Transcript JSON contains segments spanning the full video duration
- Language detected as `zh`
- Full text is not truncated (last segment text is complete, not cut off mid-word)

### Step 5: Produce fetch_report

Write `fetch_report.json` to the episode's assets directory:

```json
{
  "episode_num": 1,
  "source_url": "https://www.youtube.com/watch?v=...",
  "video_id": "m5olarc6Cq4",
  "source_video_path": "assets/source/source.mp4",
  "transcript_path": "assets/source/transcript.json",
  "video_duration_seconds": 590,
  "transcript_word_count": 3200,
  "language_detected": "zh",
  "downloaded_at": "ISO timestamp"
}
```

Update tracking.db status to `fetched`.

## Review Notes

- If `transcriber` fails (no GPU / Whisper not installed), surface a structured blocker: what tool is missing, what the install command is
- If the source video is unavailable (deleted, region-locked), mark episode as `error` in tracking.db with error message
- Do NOT continue to the brief stage if transcription is incomplete
