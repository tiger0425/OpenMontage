# Script Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 4（SCRIPT）：基于 `proposal_packet` 的段落结构、字数目标、旁白语言，写出**6 段式检查清单下的 Fern 式连续旁白稿**。产出 `script` artifact。

核心原则：**形式是 Fern DNA（连续旁白、无章节标签、无镜头指示），内容是 6 段式（Viral Hook → Quick Introduction → Main Story → Turning Point → Big Picture → Powerful Ending）**。输出仍为一段连续旁白，但每个 section 必须带有 `paragraph_label`，供 scene_plan 阶段做段落级视觉切换。

## 中英双语规则（先读 `bilingual-spec.md`）

写稿前按 `narration_language` 查 bilingual-spec：

- **字数数学**：§1（en 2.5 wps / zh 4.7 字/秒，两套常数，±5%）
- **冷开场**：§4（精确日期 + 具名地点 + 一个具体小动作）
- **过渡连接词**：§5（then/by morning ↔ 随后/次日清晨）
- **争议事实归因句式**：§6（The FBI believed ↔ 警方认为；禁止陈述为事实）
- **悬念结尾**：§7（五种模式；en ≤12 词 / zh ≤15 字）
- **标点红线**：§8（en 禁 em dash；zh 少用破折号与省略号）
- **标题句式**：§3（按平台选择 viral / documentary 风格）

## 段落结构（6 段式检查清单）

脚本内容必须覆盖以下 6 个功能段落，但根据 `proposal_packet.paragraph_structure.compressed_to` 动态压缩：

| 段落 | 功能 | 在压缩形态中的处理 |
|---|---|---|
| **Viral Hook** | 前 3-4 句，强好奇心钩子，含精确日期/地点/动作 | 必须保留，可合并入 Quick Introduction |
| **Quick Introduction** | 快速建立 stakes，告诉观众为什么重要 | 3 段式中合并入 Hook；5 段式中独立存在；6 段式中完整保留 |
| **Main Story** | 循序渐进讲故事，每句引出新问题 | 必须保留 |
| **Turning Point** | 最大反转或出人意料的事实 | 必须保留 |
| **Big Picture** | 宏观意义，连接当下现实 | 5 段式中合并入 Ending；6 段式中独立存在 |
| **Powerful Ending** | 结尾悬念，令人回味 | 必须保留 |

## 压缩规则

- **3 段式**（30s–1min）：Hook + Intro → Story → Ending（Big Picture 合并入 Ending）
- **4 段式**（1–2min）：Hook → Story → Turning → Ending
- **5 段式**（3–5min）：Hook → Intro → Story → Turning → Ending（Big Picture 合并入 Ending）
- **6 段式**（8min+）：Hook → Intro → Story → Turning → Big Picture → Ending

## Fern DNA 形式规则（逐字要求）

1. **仅连续旁白**：单一流动散文块。无章节标题、无镜头指示、无视觉提示、无 `# SCENE` 标记。
2. **section 切分**：按压缩后的段落边界切分 `sections[]`，每个 section 是一段连续文本，并标注 `paragraph_label`。
3. **冷开场**：前 3-4 句落在精确日期、地点、一个小的具体动作上。示例："1988年，纽约一间小公寓里，两个男人创立了一家资产管理公司。37年后，这家公司管理着超过10.5万亿美元的资产。它叫贝莱德。"
4. **平静、精确、纪录片腔调**：短陈述句与每段一个较长的解释句混合。用时间与因果连接词承载故事：随后、正因如此、这意味着、三天后。
5. **每个句子以句号干净结束**：每个句子是一个自足的想法，因为句子后来会变成视觉 beat。
6. **事实准确**：细节不确定时用归因句式（警方认为 / 调查人员最终认定），绝不编造名字、日期或数字。
7. **真实悲剧克制**：无血腥、无苦难特写、无对受害者嘲讽。张力存在于物体、地点、文件与时间中。
8. **无赞助文案、无订阅提示、无签名落款**。
9. **强制悬念结尾**：最后一行 ≤15 字（中文），以名词、名字、日期或短陈述句结束。使用五种模式之一：未解物体 / 时间跳跃 / 缺失碎片 / 静默矛盾 / 代价追问。

## 输出格式

```
TARGET: [N] 字 / [language] / [paragraph_structure] / [duration]
[section 1 text - paragraph_label: viral_hook]
[section 2 text - paragraph_label: quick_intro]
[section 3 text - paragraph_label: main_story]
[section 4 text - paragraph_label: turning_point]
[section 5 text - paragraph_label: big_picture/powerful_ending]
FINAL: [actual N] 字
```

## 流程

1. 从 `proposal_packet` 读取 `word_target`、`narration_language`、`paragraph_structure`。
2. 按 6 段式检查清单和 Fern DNA 写连续旁白（narration_language=en 时全英文；zh 时全中文）。
3. 将旁白按压缩后的段落边界切分为 `sections[]`，每个 section 标注 `paragraph_label`。
4. 计算总字数，核对 ±5%（英文按空格分词；中文按字符计数，标点计入）。
5. 估算每个 section 的 `start_seconds` / `end_seconds`：按 `narration_language` 语速常数（zh 4.7 字/秒，en 2.5 wps）累计。这些时间是**估算值**，不是最终事实。
6. 将脚本存入 `script` artifact，包含 `paragraph_structure`、`narration_language`、`word_count`（target/actual/unit）。
7. 自检：冷开场、悬念结尾、无破折号/省略号滥用、段落标签完整。

## TTS 时间戳校准与回退规则（强制）

script 阶段的字数估算是**规划工具**，真实旁白时长由 assets 阶段 TTS 输出决定。以下规则必须执行，不能跳过：

1. **误差阈值**：
   - 若 TTS 实测总时长与 script 估算总时长偏差 **≤5%**：scene_plan 阶段用真实时间戳重新标定 `start_seconds` / `end_seconds`，调整 beat 内部时长，但**不回到 script 阶段**。
   - 若偏差 **>5%**：必须回到 **script 阶段**精简或扩充旁白，重新生成 script 后再次进入 scene_plan。
2. **误差计算方式**：
   - `error_ratio = |tts_actual_duration - script_estimated_duration| / script_estimated_duration`
   - 使用 TTS 完整合成后的总时长，不是单句试读。
3. **脚本产物必须声明**：`word_count` 包含 target、actual、unit；`sections` 包含估算 timing。不能省略这些字段。
4. **回退记录**：若发生回退，必须在 `decision_log` 中记录 `category: "tts_calibration_rewind"`，说明原因和调整内容。

## 与 Scene Plan 的关系

**估算 timing 仅用于 scene_plan 初排。最终 timing 必须以 TTS 时间戳为准。**

- 第一轮 scene_plan 使用 `timing_source: "estimated"`。
- TTS 完成后，scene_plan 必须重新生成或更新为 `timing_source: "tts_actual"`。
- 只有 `timing_source == "tts_actual"` 且偏差 ≤5% 时，才允许进入 edit 阶段。


## 质量要求

- 无章节标题、无镜头指示、无视觉提示（纯旁白）。
- 每个 section 有且仅有一个 `paragraph_label`。
- `paragraph_label` 取值：viral_hook, quick_intro, main_story, turning_point, big_picture, powerful_ending。压缩形态中合并的段落可用复合标签如 `viral_hook+quick_intro` 或 `big_picture+powerful_ending`。
- 句子以句号干净结束。
- 中文禁用破折号"——"和省略号"……"；英文禁用 em dash。
- 字数 ±5% 硬性。

## 成功标准

- `script` 通过 schema 校验。
- 总字数在 `word_target ±5%`。
- 每个 section 都有 `paragraph_label`。
- 冷开场与悬念结尾存在。
- 内容与 `proposal_packet.data_authenticity_plan` 一致，不编造关键事实。
