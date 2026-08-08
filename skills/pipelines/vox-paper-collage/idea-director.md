# Idea Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 0/1/2：吸收可选的 Source Material PDF（若有），确定领域（niche），产出**动态数量**的带钩子视频选题，过滤已发布选题黑名单，用户选定一个。产出 `brief` artifact。

## 输入

| 来源 | 处理方式 |
|------|----------|
| 用户提供 Source Material PDF（可选） | 吸收写作 DNA / 风格块 / 节拍规则 / 缩略图 DNA 覆盖内置默认（本管线 forge 时未附 PDF，使用内置默认） |
| 用户输入领域 | 走扩展领域选项或自定义 |
| 已发布选题黑名单 | 在生成候选前读取，过滤重复选题 |
| `target_platform` | 决定标题风格（好奇心爆款 vs 克制纪录片） |

## 流程

1. **可选源材料**：若用户提供 PDF，读取并吸收；无则用内置规则。
2. **读取已发布选题黑名单**：从 `data/used_ideas.json` 读取已发布选题列表，过滤时检查标题语义重复（不只看字符串，要检查核心主题/钩子重复）。
3. **领域选择（STATE 1）**：向用户呈现扩展领域选项
   ```
   "What niche are we in today? Options:
   1. crime and documentary
   2. history
   3. money and power
   4. disasters and survival
   5. mysteries and the unexplained
   6. technology
   7. sports
   8. business and corporations
   9. billionaires and wealth
   10. countries and geopolitics
   11. geography
   12. economics and finance
   13. artificial intelligence
   14. space and astronomy
   15. science
   16. nature and wildlife
   17. psychology and human behavior
   18. military and war
   19. ancient civilizations
   20. luxury and fashion
   21. internet and social media
   22. transportation and aviation
   23. maritime and shipping
   24. food and cuisine
   25. health and medicine
   26. the human body
   27. the future and futurism
   28. politics and society
   29. brands and marketing
   30. your own: type it
   Reply with a number or a niche."
   ```
4. **候选选题数量（STATE 2 动态规则）**：
   - 根据领域广度和主题丰富度决定数量，**不是固定 10 个**。
   - 规则：
     - 通用/高热度领域（crime, history, technology, money, business, countries, AI, military, internet, brands）→ **20-30 个候选**。
     - 中等热度领域（disasters, sports, geography, economics, space, science, nature, psychology, ancient civilizations, transportation, health, future, politics）→ **15-20 个候选**。
     - 小众/垂直领域（mysteries, maritime, food, human body, luxury, fashion）→ **10-15 个候选**。
     - 用户自定义领域 → 根据用户提供的关键词自动判断，通常 10-20 个。
   - 所有候选必须满足：无两个选题落在同一子领域；每个选题有具体钩子（日期、人名、数字、地点）；无 clickbait；无感叹号；无"震惊/惊人/shocking/insane"。
5. **标题风格**：由 `target_platform` 决定，见 `bilingual-spec.md §3.1`。
   - 爆款平台（youtube, tiktok, bilibili, xiaohongshu）→ 好奇心驱动、强钩子、短标题。
   - 专业/企业平台（linkedin, generic）→ 克制纪录片句式。
   - instagram 根据内容类型判断：知识类用爆款，品牌类用克制。
6. **用户选择**：呈现编号列表，用户挑选一个（或描述不同话题）。
7. **过滤已发布选题**：若用户选择的选题与黑名单中已有选题核心主题重复，提示用户选择另一个或明确允许覆盖。
8. 产出 `brief`：包含 niche、候选数量、候选选题（各带 hook、平台标题风格）、用户选定项、黑名单检查状态，以及 `brief.schema.json` 要求的 `design_system` 和 `beat_plan` 前期意图。

## 已发布选题黑名单

- 文件位置：`data/used_ideas.json`
- 内容：所有进入 publish 阶段的选题标题和核心主题标签。
- 更新时机：publish 阶段完成后，由 publish-director 写入。
- 去重粒度：检查核心主题（例如"D.B. 库珀劫机案"和"那个在飞机上消失的劫匪"应视为重复），不只看字符串匹配。
- 未发布选题、proposal/script 阶段放弃的选题不进入黑名单。

## `brief` 必填字段

按 `schemas/artifacts/brief.schema.json` 校验，确保包含：

- `version`: "1.0"
- `title`: 用户选中的选题标题
- `hook`: 选题的具体钩子（日期/名字/数字/地点）
- `key_points`: 3-5 个核心事实点
- `tone`: 如 "calm deadpan documentary"
- `style`: "vox-paper-collage"
- `target_platform`: 目标平台
- `target_duration_seconds`: 用户预期时长（若用户未指定，先留白或 proposal 阶段再填；若 schema 强制要求，则给出 30s/60s 等合理默认值）
- `niche`: 用户选中的领域
- `platform_title_style`: 本次标题风格（viral / documentary / brand）
- `design_system`: 全局视觉基调（与 schema 字段名一致）
  - `background_color`: 旧报纸档案色，如 "#D8C7A3 aged newsprint paper texture"
  - `lighting_style`: 柔和漫射、无硬阴影，如 "soft flat diffused light, no dramatic shadows"
  - `global_mood`: 如 "old-newspaper archival paper collage, documentary gravitas"
- `beat_plan`: 前期构图意图数组（每幕至少 `scene_name` + `composition_rule`）
  - 条目数与预期节拍数一致（例如 30s 约 12-15 个节拍）
  - `composition_rule` 用一句话描述，如 "Hero cutout centered on newspaper texture, headline stamp upper-left, red string connects to small map pin"
- `angle_options`: 候选选题数组（每个含 `name`, `description`, `hook`, `style`）
- `selected_angle`: 用户选中的选题名称
- `blacklist_check`: 黑名单检查结果（`passed` 或 `duplicate_detected` + 重复项说明）
- `candidate_count`: 本次生成的候选数量
- `candidate_count_reason`: 数量决定原因（领域广度/主题丰富度）

## 质量要求

- 扩展领域覆盖 Playbook 中列出的 30+ 领域。
- 标题风格必须按 `target_platform` 区分，禁止所有平台使用同一套标题句式。
- 标点红线见 `bilingual-spec.md §8`（en 禁 em dash；zh 少用破折号/省略号）。
- 钩子必须具体（"November 24, 1971" / "1971年11月24日" 优于 "1970s" / "上世纪70年代"）。
- 输出编号列表，无多余修饰。
- `brief` 通过 `schemas/artifacts/brief.schema.json` 校验。
- `design_system` 和 `beat_plan` 与 VOX 拼贴引擎一致（旧报纸/档案/柔和光影）。
- 黑名单检查必须显式执行，并在 `brief` 中记录结果。

## 成功标准

- `brief` 含 niche、扩展领域、候选数量及原因、候选选题（各带 hook 和平台标题风格）。
- `brief` 含用户选定项、blacklist_check 状态。
- `brief` 含 `design_system` 和 `beat_plan` 前期意图。
- `brief` 通过 `schemas/artifacts/brief.schema.json` 校验。
- 无两个候选选题落在同一子领域。
- 所有标题符合 platform_title_style 和 bilingual-spec 红线。
