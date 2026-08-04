# Script Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 4（SCRIPT, FERN STYLE）：写出 Fern 式连续旁白稿，字数在目标 ±5% 内。产出 `script` artifact（script.sections[] 承载连续旁白）。

## 中英双语规则（先读 `bilingual-spec.md`）

本管线中英文视频都产出。写稿前按 `narration_language` 查 bilingual-spec：

- **字数数学**：§1（en 2.5 wps / zh 4.7 字/秒，两套常数，±5%）
- **冷开场**：§4（结构通用，日期格式与示例分语言）
- **过渡连接词**：§5（then/by morning ↔ 随后/次日清晨）
- **争议事实归因句式**：§6（The FBI believed ↔ 警方认为；禁止陈述为事实）
- **悬念结尾**：§7（五种模式通用；en ≤12 词 / zh ≤15 字）
- **标点红线**：§8（en 禁 em dash；zh 少用破折号与省略号）

## Fern DNA 规则（逐字要求）

**字数数学（2.5 words per second）：**

30s 约 75 词。1 min 约 150。2 min 约 300。3 min 约 450。5 min 约 750。目标 ±5% 内。

**脚本规则（Fern DNA）：**

1. 仅连续旁白。单一流动散文块。无章节标签、无标题、无镜头指示、无视觉提示。
2. 冷开场：前 3 到 4 句（约 30-40 词）落在精确日期、地点、一个小的具体动作上。示例形状："November 24, 1971. Portland International Airport. A man in a dark suit buys a one-way ticket under the name Dan Cooper."
3. 平静、精确、纪录片腔调。短陈述句与每段一个较长的解释句混合。时间与因果连接词承载故事：then, by morning, three days later, because of this, which meant.
4. 每个句子干净地以句号结束。每个句子是一个自足的想法，因为句子后来会变成视觉节拍。
5. 事实保持准确。细节不确定时绕开写，绝不编造名字、日期或数字。
6. 真实悲剧克制：无血腥、无苦难特写、无对受害者的嘲讽。张力存在于物体、地点、文件与时间中。
7. 无赞助文案、无订阅提示、无签名落款。
8. 强制悬念结尾。最后一行 ≤12 词，以名词、名字、日期或短陈述句结束。使用源材料中五种模式之一。

**输出格式：**

```
TARGET: [N] words / [length]
[the script as one continuous block]
FINAL: [actual N] words
```

## 流程

1. 从 proposal_packet 取 word_target 与 narration_language
2. 按 Fern DNA 写连续旁白（narration_language=en 时全英文；zh 时全中文但保持同样规则）
3. 数词核对 ±5%（英文按空格分词；中文按字计数）
4. 将脚本存入 script artifact：sections[] 中放连续旁白块，section 级 timing 按实际语速折算
5. 自检：冷开场、悬念结尾、无 em dash

## 冒烟片沉淀（2026-08）：中文语速基准

（常数表已并入 `bilingual-spec.md §1`，此处保留经验备注）

- **中文自然语速 ~4.7 字/秒**（IndexTTS2 实测），不是英文的 2.5wps
- 目标字数：1 分钟 ≈ 230-250 字，2 分钟 ≈ 460-500 字
- 时间码按 4.7 字/秒累计；如 TTS 实测偏差 >5%，以实测为准重排节拍
- **禁止用 speed<0.8 变速凑时长**（产生杂音）；宁可调整字数

## 语音驱动流程（2026-08 用户确认）：TTS 与时间戳必须在 scene_plan 之前

**本阶段产出 script 后，紧接执行 TTS 合成与时间戳提取，再进入 scene_plan。** 这是语音驱动流程的根基——分镜规划必须基于真实语音时间戳，而非文字估算。

### 顺序硬约束

```
script 定稿（本阶段）
  → TTS 合成全部段落（assets 阶段提前执行此项）
  → whisper 提取词级/句级时间戳（timestamps JSON）
  → scene_plan（分镜边界 = 语音段边界，元素 = 句子，入场 = 句时间戳）
```

### 句子切分规则（为 scene_plan 提供句子级输入）

- 按标点（，。！）把每段旁白切成短语/句子
- whisper segments 提供句级时间戳；短语时间 = 段内按字符比例分配
- 关键句（含数字/专名/情绪词的句子）标记为 `emphasis`——这些句子对应的元素要用更醒目的动效（pop/shake/slap）
- 短句（<1s）标注 `merge`，scene_plan 阶段并入相邻句

### 字数红线（经验教训）

- **旁白总时长必须 ≤ 目标时长 - 余量**：60s 目标 → 语音 ≤ 53-55s，留 5-7s 结尾/音乐
- 每段语音时长 ≤ 对应分镜时长上限（分镜 = 语音段边界），否则下一段语音侵入下一个分镜 → 声音错位
- 字数超标时先精简文本再 TTS，**禁止直接改时间码硬塞**（多段重叠 = 声音错乱事故根因）

## 质量要求

- 无章节标题、无镜头指示、无视觉提示（纯旁白）
- 句子以句号干净结束
- 无 em dash（引擎禁止），用逗号/冒号/括号/普通连字符
- 字数 ±5% 硬性

## 成功标准

- `script` 通过 schema 校验
- 总字数在 word_target ±5%
- 冷开场与悬念结尾存在
