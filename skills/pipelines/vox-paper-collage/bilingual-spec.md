# Bilingual Spec — Vox Paper Collage（中英双语规范）

本管线同时产出英文与中文视频。`narration_language`（proposal 阶段锁定，`en` 或 `zh`）决定**文案层**语言；**视觉层**规则两语言一致。

所有中英差异集中在本文档维护。各 director skill 引用对应章节编号，**禁止在 skill 内各自维护中英参数副本**（防止漂移）。

---

## §1 语速与字数常数（proposal / script 引用）

| 时长 | en 词数（2.5 wps） | zh 字数（4.7 字/秒） |
|------|------------------|---------------------|
| 30s  | ~75              | ~140                |
| 1min | ~150             | ~280                |
| 2min | ~300             | ~560                |
| 3min | ~450             | ~840                |
| 5min | ~750             | ~1400               |

- 容差：目标 ±5%（en 按空格分词计；zh 按字符计，标点计入）
- zh 基准来自 IndexTTS2 实测 4.7 字/秒；若 TTS 实测偏差 >5%，以实测为准重排
- **旁白总时长红线（两语言通用）**：语音总长 ≤ 目标时长 − 余量（60s 目标 → 语音 ≤ 53-55s，留结尾/音乐）
- 禁止用 speed<0.8 变速凑时长（产生杂音），字数超标先精简文本

## §2 Beat 长度（scene_plan 引用）

| | en | zh |
|---|---|---|
| 每拍长度 | 5-8 词（2-3s） | 8-14 字，按语义在逗号/句号处断句，不按字数硬切 |
| 一句一拍 | 短句 | 短句 |
| 长句拆分 | 在逗号或逻辑从句处拆 | 同左 |

Beat 数量 sanity range（30s≈12-15 / 1min≈22-30 / 2min≈45-60 / 3min≈70-90 / 5min≈115-150）按时间计，两语言通用。

## §3 标题句式库（idea 引用）

标题语言 = `narration_language`。两语言共用红线：具体钩子（日期/人名/数字/地点）、无 clickbait、无感叹号、无"震惊/惊人/shocking/insane"。

### §3.1 平台标题风格

`target_platform` 决定标题风格。字段 `platform_title_style` 取值如下：

| 平台 | platform_title_style | 标题气质 |
|---|---|---|
| youtube, tiktok, bilibili, xiaohongshu | `viral` | 好奇心驱动、强钩子、短标题、接近 YouTube 爆款纪录片 |
| linkedin, generic | `documentary` | 克制纪录片句式、专业、信息密度优先 |
| instagram | 按内容判断：知识类用 `viral`，品牌/产品类用 `documentary` | 可混合 |

### §3.2 viral 标题句式（爆款平台）

**en shapes：**
`Why [place/country/company] [is doing X]` / `How [X] Took Over [Y]` / `The [adjective] Story of [subject]` / `What Really Happened to [subject]` / `The [thing] Nobody Talks About` / `Inside [place/operation]` / `The [number] [things] That Changed [everything]` / `Why [common thing] Is Actually [surprising fact]` / `The Hidden World of [X]` / `How [company/brand] Tricked the World`

**zh shapes（禁止逐字翻译英文句式）：**
《为什么……正在……》/《……是如何统治……的》/《……不为人知的真相》/《……真正发生了什么》/《……背后的秘密》/《为什么……都是错的》/《那家控制了……的公司》/《为什么……永远不会……》/《……：一段被遗忘的……》/《世界上最危险的……》

Playbook 示例：
- `en "Why Japan Is Running Out of People"` → `zh 《为什么日本正在消失？》`
- `en "The Company That Owns Almost Everything"` → `zh 《那家悄悄控制了几乎一切的公司》`
- `en "How McDonald's Took Over the World"` → `zh 《麦当劳是如何统治全球的？》`

### §3.3 documentary 标题句式（克制纪录片风格）

**en shapes（引擎原始）：**
`How [event] Unfolded` / `The Hunt for [target]` / `The [adjective] Story of [subject]` / `Why [place] [did X]` / `[Event] Explained` / `The Man/Woman Who [impossible act]` / `What Really Happened to [subject]` / `The [number] Days That [changed everything]` / `Inside the [place or operation]` / `The [year] [event] Nobody Remembers`

**zh shapes（中文纪录片对应物，禁止逐字翻译英文句式）：**
《……始末》/《追缉……》/《……真相》/《……年……案》/《……年……事件》/《谁在……》/《……全记录》/《……之谜》/《最后一个……的人》/《……：一段被遗忘的……》

示例：`en "What Really Happened to D.B. Cooper"` → `zh 《D.B. 库珀劫机案始末》`

### §3.4 默认标题语言与风格

本次优化后默认 `narration_language = zh`，因此 `zh` 标题形状为默认。`target_platform` 默认若未指定，则使用 `documentary` 风格；爆款平台（youtube/tiktok/bilibili/xiaohongshu）必须使用 `viral` 风格。用户可显式指定 override。

## §4 冷开场（script 引用）

结构两语言通用：前 3-4 句（en 30-40 词 / zh 40-60 字）落在**精确日期 + 具名地点 + 一个具体小动作**。禁用"想象一下/Imagine"式开场。

- en 示例：`November 24, 1971. Portland International Airport. A man in a dark suit buys a one-way ticket to Seattle with cash. He gives the name Dan Cooper.`
- zh 示例：`1971年11月24日，波特兰国际机场。一个穿深色西装的男人用现金买了一张去西雅图的单程票。他登记的名字是丹·库珀。`
- zh 日期格式：`XXXX年X月X日`；en 日期格式：`Month D, YYYY`

## §5 过渡连接词（script 引用）

| en | zh |
|---|---|
| then | 随后 |
| by morning | 次日清晨 |
| three days later | 三天后 |
| within the hour | 不到一小时 |
| because of this | 正因如此 |
| which meant | 这意味着 |
| what nobody knew was | 没人知道的是 |

## §6 争议事实归因句式（script 引用，2026-08 新增）

细节有争议时**禁止陈述为事实**，必须用归因句式：

| 场景 | en | zh |
|------|----|----|
| 官方立场 | The FBI believed... | 警方认为…… |
| 证人说法 | Witnesses reported... | 目击者称…… |
| 调查结论 | Investigators concluded... | 调查人员最终认定…… |
| 悬而未决 | The case remains unsolved. | 至今没有定论。 |

两语言同红线：绝不编造名字、日期、数字。

## §7 悬念结尾（script 引用）

五种模式（Unresolved Object / Dated Forward Jump / Missing Piece / Quiet Contradiction / Price Line）两语言通用。

- 末句长度：en ≤12 词 / zh ≤15 字
- 落点：物体、人名、日期，或一句短事实陈述

## §8 标点红线（script 引用，全管线通用）

- en：禁 em dash（—— 或 —），用逗号/冒号/括号/普通连字符
- zh：**少用破折号"——"和省略号"……"**（LLM 中文写作高发滥用），多用逗号句号；每句以"。"干净收尾，一句一意

## §9 Recurring Subject Rule（scene_plan / assets 引用）

同一人物/地点/物体跨多拍复现时，**生图 prompt 中对该主体的描述措辞逐字一致**（每次复用同一段英文描述串），保证全片视觉连续。语言无关。

## §10 生图 prompt 与文字红线（assets 引用，硬性；2026-10 全面 Qwen 后修订）

1. **生图 prompt 结构一律英文**——无论旁白语言；引号内标签原文可以是中文（Qwen-Image 2.1 系列支持中文字形直出，2026-10 已实测：生产静帧大标题字形正确）。STYLE BLOCK / CLOSER 英文模板 verbatim 拼接不变
2. **中文文字：内容驱动，不设数量上限（2026-10 修订）**：
   - 画面上需要几处中文就写几处（标题、标签、地名、年份、印章、图注……），由该拍内容决定；Qwen 直出，字形融入纸张质感
   - 字号越大越稳；必须 100% 正确的关键小字（细节编号等）推荐 CSS / PIL 叠加兜底
   - **所有生成文字逐张质检**（放大目检或 OCR 比对预期文案），错字 / 乱码重掷
3. **辅助元素内容策略（2026-10 修订）**：纸片 / 胶带 / 标签 / 图章不要全部留白（画面会空、模型也会乱填），按内容需要填充——中文短标（如 已售 / 证物 / 机密）、英文短语（FILE / ARCHIVE / NO. 03）或图标（箭头 / 索引圆点 / 条形码 / 无字图章）；**prompt 中显式写出各元素文案**，未指定处模型会自创伪文字；负向词带乱码护栏（no fake or corrupted characters / no garbled caption text）；**照片重绘（edit 路线）伪文字风险更高，须逐张抽检**，发散严重时重绘或降级
4. TTS 语音方向：en = calm deadpan male, ~155 wpm；zh = 同音色同参考音频（spk_audio_prompt 不变），~4.7 字/秒，speed=1.0 零变速。**保持 calm 必须每次显式传 `emo_vector=[0,0,0,0,0,0,0,1.0]`**——indextts_tts 默认"不传即自动从文字判情感"，漏传会破坏平静纪录片语感（见 `assets-director.md` 旁白节）

## §11 缩略图文字（publish 引用）

| 规则 | en | zh |
|------|----|----|
| 文字元素数 | ≤2 个 | ≤2 个 |
| 每元素长度 | ≤3 词 | ≤4-6 字 |
| 字形 | condensed ALL CAPS | 粗黑体/紧凑字形（无大写概念） |
| 金额 | 带美分（如 $200,000.00） | 用万/亿单位（如 20万美元 / 2.4万亿） |
| 200px 可读 | 必须 | 必须 |

两语言通用：真人主体加**黑色审查条遮眼**；**单一强调装置**（红圈 / 红下划线 / 图章框 / 黄高亮条，四选一，不堆叠）；缩略图文字推荐 CSS/后期叠加（可编辑、可 A/B、零错字）；走 Qwen 直出时必须逐张字形质检。

## §12 语义 → 动画 family 映射（scene_plan / compose 引用）

| family | en 语义 | zh 语义 |
|--------|---------|---------|
| `drop`  | release / launch / debut | 发布 / 推出 / 登场 |
| `rise`  | surge / soar / climb | 上涨 / 大涨 / 飙升 |
| `shake` | shock / rocks the industry | 震惊 / 震动业界 |
| `pop`   | ranking / No.1 / key number | 排名 / 第一 / 第二 |
| `slide` | on par / surpass / side by side | 相当 / 超越 / 并肩 |
| `grow`  | scale / parameters / size | 规模 / 参数 / 拥有 |
| `pulse` | billions / surge in numbers | 增加 / 数百亿 |
| `slap`  | future / cliffhanger ending | 未来 / 悬念结尾 |
| `fade`  | short phrase / filler | 短句 / 语气词 |
