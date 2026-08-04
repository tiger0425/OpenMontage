# Idea Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 0/1/2：吸收可选的 Source Material PDF（若有），确定领域（niche），产出 10 个带钩子的视频选题，用户选定一个。产出 `brief` artifact。

## 输入

| 来源 | 处理方式 |
|------|----------|
| 用户提供 Source Material PDF（可选） | 吸收写作 DNA / 风格块 / 节拍规则 / 缩略图 DNA 覆盖内置默认（本管线 forge 时未附 PDF，使用内置默认） |
| 用户输入领域 | 走引擎 STATE 1 选项或自定义 |

## 流程

1. **可选源材料**：若用户提供 PDF，读取并吸收；无则用内置规则（本 skill 即内置默认）
2. **领域选择（STATE 1）**：向用户呈现引擎选项
   ```
   "What niche are we in today? Options:
   1. crime and documentary (house default)
   2. history
   3. money and power
   4. disasters and survival
   5. mysteries and the unexplained
   6. technology
   7. sports
   8. your own: type it
   Reply with a number or a niche."
   ```
3. **十选题（STATE 2）**：在该领域生成恰好 10 个选题。规则：
   - 没有两个选题落在同一子领域
   - 标题为陈述或疑问式，轻标点，无 clickbait。句式库见 `bilingual-spec.md §3`：**标题语言 = narration_language**——en 用引擎原始 title shapes（`How [event] Unfolded` 等）；zh 用中文纪录片句式（《……始末》《追缉……》《……真相》等），禁止逐字翻译英文句式
   - 每个选题必须有具体钩子：日期、名字、数字或地点
4. **用户选择**：呈现编号列表，用户挑选一个（或描述不同话题）
5. 产出 `brief`：包含 niche、10 个候选选题（各带 hook）、用户选定项，以及 `brief.schema.json` 要求的 `design_system` 和 `beat_plan` 前期意图

## `brief` 必填字段

按 `schemas/artifacts/brief.schema.json` 校验，确保包含：

- `version`: "1.0"
- `title`: 用户选中的选题标题
- `hook`: 选题的具体钩子（日期/名字/数字/地点）
- `key_points`: 3-5 个核心事实点
- `tone`: 如 "calm deadpan documentary"
- `style`: 拼贴风格名称，如 "vox-paper-collage"
- `target_platform`: 目标平台（youtube/instagram/tiktok/linkedin/bilibili/xiaohongshu/generic 之一）
- `target_duration_seconds`: 用户预期时长（若用户未指定，先留白或 proposal 阶段再填；若 schema 强制要求，则给出 30s/60s 等合理默认值）
- `design_system`: 全局视觉基调（与 schema 字段名一致）
  - `background_color`: 旧报纸档案色，如 "#D8C7A3 aged newsprint paper texture"
  - `lighting_style`: 柔和漫射、无硬阴影，如 "soft flat diffused light, no dramatic shadows"
  - `global_mood`: 如 "old-newspaper archival paper collage, documentary gravitas"
- `beat_plan`: 前期构图意图数组（每幕至少 `scene_name` + `composition_rule`）
  - 条目数与预期节拍数一致（例如 30s 约 12-15 个节拍）
  - `composition_rule` 用一句话描述，如 "Hero cutout centered on newspaper texture, headline stamp upper-left, red string connects to small map pin"
- `angle_options`: 10 个候选选题（含 `name` 和 `description`）
- `selected_angle`: 用户选中的选题名称

## 质量要求

- 标点红线见 `bilingual-spec.md §8`（en 禁 em dash；zh 少用破折号/省略号）
- 钩子必须具体（"November 24, 1971" / "1971年11月24日" 优于 "1970s" / "上世纪70年代"）
- 输出编号列表，无多余修饰
- `brief` 通过 `schemas/artifacts/brief.schema.json` 校验
- `design_system` 和 `beat_plan` 与 VOX 拼贴引擎一致（旧报纸/档案/柔和光影）

## 成功标准

- `brief` 含 niche、10 个候选选题（各带 hook）、用户选定项
- `brief` 含 `design_system` 和 `beat_plan` 前期意图
- 校验通过 `schemas/artifacts/brief.schema.json`
