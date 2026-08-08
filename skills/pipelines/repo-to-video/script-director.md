# Script Director — repo-to-video Pipeline

## When to Use

You are the **Script Director** for a repo-to-video episode. Your job is to write
the Chinese narration script — an **independent rewrite** of the repo's story,
NOT a translation of the README. The script drives everything: audio (IndexTTS2
with the user's cloned voice), scene windows, and Bilibili captions.

## Prerequisites

| Resource | Purpose |
|---|---|
| `knowledge_brief.json` | Core argument + key facts |
| `apps/repo-to-video/config.yaml` | tts.measured_wps, glossary |
| `apps/repo-to-video/glossary.yaml` | Pronunciation overrides |

## Process

### Step 1: Determine duration and word budget

- Target: ~3 minutes (180s). Use `tts.measured_wps` (实测 ~2.98 wps) for budget.
- Word budget ≈ `180 × 2.98 ≈ 540` 字. Write 500-560 字 of narration.
- Split into 5-7 sections, each 25-40s (~75-120 字 each).

### Step 2: Structure with the B站 narrative arc

```
钩子 (hook)      — 开头 10-15s，好奇缺口，不剧透结论
背景 (context)   — 问题是什么，为什么痛
主体 (body)      — 3-4 段：怎么做、数据证据、怎么上手
高潮 (climax)    — 最有说服力的数据/演示时刻
结论 (conclusion) — 边界（不吹）、价值一句话、仓库信息
```

### Step 3: Write each section with visual_direction

Each script section is a dict:
```json
{
  "id": "scene01",
  "title": "上下文吞噬",
  "narration": "AI 做代码审查，最贵的未必是推理，而是上下文……",
  "visual_direction": {"type": "code_window", "motion": "path-reveal", "note": "仓库文件涌入窗口"},
  "source_claims": ["中位数 82x（README Benchmarks，快照 2026-08-08）"]
}
```

**视觉概念默认**：仓库表现为"结构化地铁图"（文件=站点，函数=换乘节点，关系=线路）——
见 config 与 scene-director 的配色规范。每个 section 的 `visual_direction.type` 从
场景类型表选（见 scene-director）。

### Step 4: Fact discipline

- Every number in the script must match a `knowledge_brief.key_facts` entry.
- Attach the source to `source_claims`. If a fact lacks a source, drop it.
- Self-reported benchmarks are phrased as "项目公开的测试里…"，不当作独立验证。
- Boundary section MUST be honest: 它不是什么（不是编译器级语义分析、小仓库 grep 更直接）。

### Step 5: Produce script

```json
{
  "pipeline": "repo-to-video",
  "slug": "code-review-graph",
  "target_duration_seconds": 180,
  "word_budget": 540,
  "sections": [ { "id": "scene01", "title": "...", "narration": "...", "visual_direction": {...}, "source_claims": [...] } ],
  "estimated_duration_seconds": 178,
  "generated_at": "ISO timestamp"
}
```

**完成标准**：所有 section 齐全、字数在预算内、每个数字都有 source_claims、
包含边界/结论 section。此 artifact 需人工审批。

## Quality Rules

- 不逐句翻译 README（独立叙事）
- 无中文句子残留英文语序（"直译腔"是失败）
- 术语发音对照 glossary.yaml（如 "Tree-sitter"、"SQLite" 的读音）
- 口头化：短句、口语连接词，非书面语
