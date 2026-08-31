# Publish Director — Explainer Pipeline

## When to Use

You are the Publisher for a generated explainer video. You have a `render_report` with the final video file. Your job is to prepare the video for distribution: generate SEO metadata, create thumbnails, package exports, and log the publish event.

This is where a great video reaches its audience. Without proper metadata and packaging, even the best content gets buried.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["compose"]["render_report"]`, `state.artifacts["proposal"]["proposal_packet"]`, `state.artifacts["research"]["research_brief"]` | Video file and original proposal |
| Playbook | Active style playbook | Visual style for thumbnail |

## Process

### Step 1: Gather Context

Collect everything needed for metadata:
- **Proposal packet**: title, hook, key points, target platform, tone
- **Render report**: output path, duration, resolution
- **Script**: section summaries for description/chapters

### Step 2: Generate SEO Metadata

**Title** (max 60 characters for YouTube):
- Include the primary keyword from the proposal packet
- Lead with a hook or number
- Avoid clickbait but be compelling
- Examples: "Vector Databases Explained in 60 Seconds" > "About Vector Databases"

**Description** (first 150 chars are critical — shown in search):
- Opening line: restate the hook with the main value proposition
- Body: key topics covered, with relevant keywords naturally included
- Chapters: timestamp markers for each major section (from script sections)
- Call to action: subscribe/like/follow
- Links: relevant resources mentioned in the video

**Tags/Keywords** (platform-dependent):
- 5-10 specific tags derived from proposal packet's key_points
- Mix broad and specific: "machine learning" + "vector database tutorial"
- Include the topic, format ("explainer"), and related terms

**Hashtags** (for social platforms):
- 3-5 relevant hashtags
- Mix trending and niche

### Step 3: Generate Thumbnail Concept

Describe a thumbnail that:
1. Uses the playbook's visual style
2. Features the video's core concept visually
3. Includes 3-5 words of text (the hook or key stat)
4. Has high contrast and is readable at small sizes
5. Uses the playbook's accent colors for text

```json
{
  "thumbnail": {
    "concept": "Split screen: left side shows slow SQL query (red X), right shows fast vector search (green check). Large text: '100x FASTER'",
    "text_overlay": "100x FASTER",
    "style_notes": "Use playbook accent colors, bold Inter font, dark background"
  }
}
```

*Note: Actual thumbnail generation happens via image_selector if available, otherwise it's a concept for manual creation.*

### Step 4: Create Chapter Markers

From the script sections, generate YouTube-style chapters:

```
0:00 - Introduction
0:15 - What are Vector Databases?
0:45 - How Embeddings Work
1:20 - The Search Algorithm
1:55 - Real-World Examples
2:30 - When to Use Vector DBs
```

Each chapter maps to a script section's `start_seconds`.

### Step 5: Package Export

> ⚠️ **必须先完成 Step 4b（封面/标题自动生成），再打包**——封面与标题是门面，禁止从成片抽帧当封面（见 `lessons-learned.md` 铁律 F）。

### Step 4b: 封面与标题自动生成（MANDATORY）

用仓库工具自动产出封面和标题，**不要**手搓或从成片抽帧：

```bash
# 1. 标题候选（B 站 hook 公式：反直觉/悬念/求知 三式）
python bin/make_title.py --topic "<主题词>" --claim "<核心结论>" \
    --duration "<时长承诺>" --partition "编程" \
    [--file "<悬念对象>"] [--surprise "<意外>"] [--misconception "<误解>"]

# 2. 设计封面（渲染模板 → hyperframes snapshot → PNG）
python bin/make_cover.py --project <project> \
    --series "<系列名>" --topic "<系列主题>" --episode "第 N 节" \
    --title-main "<主标题前半>" --title-accent "<主标题 accent>" \
    --duration "<时长>" --subtitle "<副标题>" \
    [--plugs "A,B,C"] [--ring "能力"]

# 3. 视觉审封面（必做）：minimax-m3-vision 确认文字清晰/无裁切/吸睛
python .agents/skills/minimax-m3-vision/scripts/analyze_media.py \
    projects/<project>/renders/cover_design.png -p "..."
```

产出：
- `projects/<project>/renders/cover_design.png` —— 设计封面（export_bundle 的 `thumbnail_path`）
- 标题候选 JSON（选一个/让用户挑，作为 `title`）

工具位置：`bin/make_title.py`、`bin/make_cover.py`；模板：`templates/hyperframes-cover/index.template.html`。
铁律与配方：`skills/pipelines/explainer/lessons-learned.md` → 铁律 F。

### Step 5b: Package Export（原 Step 5）

> ⚠️ **必须先完成 Step 4b（封面/标题自动生成），再打包**——封面与标题是门面，禁止从成片抽帧当封面（见 `lessons-learned.md` 铁律 F）。

用 `export_bundle` 工具（capability `publish`）做确定性打包——把最终 `video_path`（来自 `render_report`）、定稿 `title`（Step 4b）和元数据（`description`、`tags`、`hashtags`、`chapters`、`thumbnail_path` = Step 4b 的设计封面）传给它。它布局导出目录、写元数据文件，返回 schema-valid 的 `publish_log`（`status: "exported"`）在 `data["publish_log"]`，直接持久化为阶段 artifact。

It produces this structure:

```
exports/
  <project_name>/
    video/
      output.mp4            # Final rendered video (subtitles.srt alongside if provided)
    metadata/
      metadata.json         # All SEO metadata
      chapters.txt          # Chapter markers
      description.txt       # Ready-to-paste description (+ chapters)
      tags.txt              # One tag per line
    thumbnails/
      concept.json          # Thumbnail concept (or the copied thumbnail image)
```

`export_bundle` is a local, offline packager — it does not upload. A networked
publisher (e.g. a YouTube uploader) would be a separate `publish`-capability
provider.

### Step 6: Build Publish Log

`export_bundle` already returns a schema-valid `publish_log` in `data["publish_log"]` — persist that directly rather than hand-building one. Do **not** add extra entry fields (the schema sets `additionalProperties: false`; only `platform`, `status`, `url`, `video_id`, `visibility`, `export_path`, `timestamp`, `metadata_used`, `error` are allowed). The shape it returns:

```json
{
  "version": "1.0",
  "entries": [
    {
      "platform": "youtube",
      "status": "exported",
      "export_path": "projects/vector-db-explainer/exports",
      "timestamp": "2026-01-15T10:30:00+00:00",
      "metadata_used": {
        "title": "Vector Databases Explained in 60 Seconds",
        "description": "What vector databases are and when to use them.",
        "hashtags": ["#ai", "#vectordb"],
        "chapters": [{ "start_seconds": 0, "title": "Introduction" }]
      }
    }
  ]
}
```

### Step 5c: 生成交付包（MANDATORY — 用户只认这一个文件夹）

用 `bin/make_deliverables.py` 产出 `projects/<name>/deliverables/`——**用户要求最终成品集中在一个文件夹、全部顶层、文案一份搞定**（铁律 G）：

```bash
python bin/make_deliverables.py --project <name> \
    --title "<定稿标题>" --description "<简介>" \
    --chapters "0:00 标题,0:10 标题,..." --tags "标签1,标签2,..." \
    [--series "<系列>"] [--episode "第 N 节"] [--cost "0.00"] [--duration "101.5s"]
```

产出（4 件套，全顶层）：`final.mp4` + `cover.png` + `发布文案.txt`（标题/简介/章节/标签一份搞定）+ `README.md`。
这是**用户侧唯一交付入口**——上传 B 站从这个文件夹取件，不要让他们去翻 renders/exports/artifacts。

### Step 7: Self-Evaluate

Score (1-5):

| Criterion | Question |
|-----------|----------|
| **SEO quality** | Would this title and description rank well for the topic? |
| **Description completeness** | Does the description include chapters, CTA, and keywords? |
| **Thumbnail concept** | Would this thumbnail stand out in a feed? |
| **Export package** | Is everything a creator needs in the export directory? |
| **Platform fit** | Is metadata tailored to the target platform? |

If any dimension scores below 3, revise.

### Step 8: Submit

Validate the publish_log against the schema and persist via checkpoint.

## Common Pitfalls

- **Generic titles**: "Video About X" loses to "X Explained in 60 Seconds" every time. Be specific and compelling.
- **No chapters**: YouTube rewards videos with chapters. Always include them.
- **Description keyword stuffing**: Write for humans first, search engines second. Natural language with keywords woven in.
- **Forgetting the CTA**: Every description should end with a call to action.
- **Wrong platform format**: YouTube descriptions differ from TikTok captions. Tailor to the target platform.
