# Publish Director — repo-to-video Pipeline

## When to Use

You are the **Publish Director** for a repo-to-video episode. Your job is to package
the rendered video for Bilibili (B号): B站 标题、简介、标签、章节时间码、封面概念，
以及 AI 披露声明。你产出 `publish_log` 与 B站 投稿配套文件。

## Prerequisites

| Resource | Purpose |
|---|---|
| `composition_report.json` | Render path |
| `final_review.json` | Approval + findings |
| `script.json` | Narration text + section titles |
| `scene_plan.json` | Scene timings for chapters |
| `apps/repo-to-video/config.yaml` | Channel config, default tags, disclosure |
| `fetch_report.json` | Repo URL for attribution |

## Process

### Step 1: Title (套 bilibili-channel-strategy 标题公式)

```
【分区】好奇钩子 + 具体细节 + 情感锚
```
- 分区建议: 【开源项目】/【硬核开源】/【开发者工具】
- 例: `【开源项目】AI 不必重读整个仓库：这个工具给代码审查建了一张"地图"`
- 长标题 ≤80 字符
- 不虚构原仓库内容（保真）

### Step 2: Description (简介模板)

```
首行钩子（复述标题情绪点，不重复标题）
- 要点1（最有价值的信息）
- 要点2
- 要点3
关注我，<config follow_hook>。
<3-5 个相关标签>

# 数据口径说明（必填）
- 仓库地址、License、版本
- 数字来源（README 快照日期）
- AI 披露声明（config.bilibili.disclosure）
```

### Step 3: Tags

从 `config.yaml → bilibili.default_tags` + repo 相关标签组合（12-15 个）：
仓库名、GitHub、开发者工具、AI编程、具体技术栈（如 #GraphRAG #MCP #Tree-sitter）。

### Step 4: Chapters

从 `scene_plan.json` 提取章节时间码，格式：
```
00:00 上下文吞噬
00:14 持久代码图
...
```

### Step 5: Cover concept

B号 硬核深色风封面（深墨绿底 + 大字 ≤8 字 + 关键视觉）：
- 主体视觉来自最终渲染的关键帧或"地铁图"概念图
- 大字标题 ≤8 字（如 "AI 先查图再读码"）
- 通过滚动测试（20 图中一眼认出）

### Step 6: Export bundle + publish_log

导出到 `projects/repo-to-video/review/{slug}/`：
- `{slug}.mp4`、`{slug}_cover.png`、`{slug}_bilibili.md`（标题/简介/标签/章节）、`{slug}_meta.json`

写 `publish_log.json`：
```json
{
  "slug": "code-review-graph",
  "title": "【开源项目】...",
  "long_title": "...",
  "description_path": "...",
  "tags": [...],
  "chapters": [{"title": "上下文吞噬", "start": "00:00"}],
  "cover_path": "...",
  "video_path": "...",
  "disclosure": "本视频由 AI 辅助生成，配音为创作者本人音色的 IndexTTS2 克隆语音。",
  "repo_url": "https://github.com/owner/repo",
  "generated_at": "ISO timestamp"
}
```

## Quality Rules

- 标题不标题党、保真（数字与 fetch_report 一致）
- 简介含数据口径说明 + AI 披露
- 封面 B号 风格（深色硬核），与其他号封面互不混用
- 章节时间码来自 scene_plan（与视频实际一致）
