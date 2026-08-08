# Scene Director — repo-to-video Pipeline

## When to Use

You are the **Scene Director** for a repo-to-video episode. Your job is to break the
approved Chinese script into a sequence of visual scenes — each specifying what the
viewer sees, for how long, with what metro-map visual concept and animation. You
produce the `scene_plan` artifact.

## Prerequisites

| Resource | Purpose |
|---|---|
| `script.json` | Approved narration with sections |
| `knowledge_brief.json` | Context for diagram design |
| `apps/repo-to-video/config.yaml` | Visual config, color scheme |

## Visual Concept: 结构化地铁图

仓库表现为一座持续生长的"地铁图"：
- **文件 = 站点**，**函数 = 换乘节点**，**调用/导入/继承/测试 = 线路**
- AI 不再吞下整座城市，而是沿图只抵达与改动相关的区域

**默认配色（B号 硬核深色风）：**
```
画布深墨绿   #0B0D0A
深层底色     #10140E
面板        #171C14
主文字暖白   #F3F0E8
次文字灰绿   #A9B0A0
主强调酸性青柠 #C7F04B
风险强调珊瑚橙 #FF6B4A
图线        #35402F
弱网格      rgba(199,240,75,0.12)
```
禁止纯黑、纯白、蓝紫渐变、霓虹青色、全屏线性渐变。

**字体**：中文 `Noto Sans SC`（本地嵌入 assets/fonts/NotoSansSC-VF.ttf），
代码/数字 `JetBrains Mono`。标题 72-112px/700-900，正文 30-40px/400-500，
标签 20-24px/600，数字 80-156px/700。

## Scene Types

| Type | Best for | Motion |
|---|---|---|
| `code_window` | 展示代码、仓库结构、上下文 | path-reveal / typewriter |
| `graph_map` | 地铁图、节点点亮、影响半径 | node-light / edge-draw |
| `stat_band` | 数据对比、token 倍数 | bar-grow / scale-band |
| `terminal` | 安装/构图/查询命令 | keystroke-sequence |
| `text_card` | 关键句、边界声明、落版 | stamp-appear |

## Process

### Step 1: Parse the script

Walk through `script.json` sections. Each `visual_direction.type` maps to a scene type.

### Step 2: Assign scene types and durations

- **start_seconds**: cumulative.
- **duration_seconds**: **narration master clock** — the narration audio IS the
  scene length. Pre-TTS duration is an estimate only (`word_count / wps`); the
  asset stage re-measures and updates the plan.
- Variety: no 3+ consecutive scenes of the same type; ≥3 distinct types total.

### Step 3: Scene windows follow voice boundaries

- After TTS, align windows to **voice segment boundaries** (transcribe narration,
  anchor sub-shot windows to transcript segment start/end). Never cut mid-sentence.
- Window = `[voice_start - 0.4s lead, voice_end + hold]`, hold 0.5-0.7s regular,
  1.5-3.4s emotional beats.
- **Windows must be continuous** (L-009): `start_i = max(prev_end - 0.5, voice_start_i - 0.4)`;
  gap check: every `next_start - prev_end <= 0` (negative = dissolve overlap).
- Sub-split long segments (>12s) into sub-shots; every sub-shot needs a distinct
  visual event (different node / different line / different terminal command).

### Step 4: Motion per scene

Adjacent scenes MUST differ in entry animation. Palette:
`slow-push-in` / `node-pop` / `edge-draw` / `line-sweep` / `scale-in` /
`terminal-type` / `stamp-appear`. No orbit / roll / whip / fast_zoom.

### Step 5: Write generation directions

For each scene, write a `generation_direction` describing the metro-map visual:
subject (which node/edge/file), props, label (≤8 字中文), background (from palette),
tech. Code windows show real repo code from fetch stage; charts show real benchmark
numbers from the claim list (labeled with source).

### Step 6: Produce scene_plan

```json
{
  "slug": "code-review-graph",
  "scenes": [
    {
      "id": "scene01",
      "type": "code_window",
      "start_seconds": 0.0,
      "duration_seconds": 14.5,
      "generation_direction": {"subject": "...", "label": "...", "background": "#0B0D0A"},
      "motion": "path-reveal",
      "source_claims": []
    }
  ],
  "total_duration_seconds": 178,
  "generated_at": "ISO timestamp"
}
```

## Quality Rules

- Every scene has ≥1 main anchor + ≥1 secondary focus + background grid/ghost
- No centered stacking, no card-matrix layouts, no empty slides
- 80px+ safe margins
- Adjacent scenes differ in scene type AND motion
- All on-screen text ≤8 字 for labels, numbers in JetBrains Mono
