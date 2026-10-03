# Scene Plan Director — Vox Paper Collage (v3)

## 职责

把脚本拆成**语义场景（scene）和语义节拍（beat）**，并为每个 beat 定义完整的元素清单与动画规格。每一拍的元素清单是后续 assets/compose 阶段的唯一契约。

核心原则：
- **分镜边界由语义决定**，不是由语音 segment 边界或固定 10s 决定。
- **真实 TTS 时间戳决定最终 timing**，script 阶段的估算 timing 仅用于初排。
- **段落级视觉切换**：不同 `paragraph_label` 的 scene 使用不同的视觉功能（hook 用强冲击、turning point 用对比、ending 用留白等）。

## 语义分镜结构

### Scene = 段落

每个 scene 对应 script 的一个 `paragraph_label` 段落。scene 的边界由语义内容决定，scene 时长由该段落的语音时长决定（初排用估算，最终用 TTS 时间戳）。

### Beat = 段落内的语义单元

一个 scene 内可包含 1-N 个 beats。每个 beat 表达一个完整小意思：
- 简单 beat：3-5s（1-2 个短句）
- 标准 beat：5-8s（2-4 个短句）
- 复杂 beat：8-10s（长句、数据解释、对比；关键 reveal 也在这一档）
- **硬上限（2026-10）：每个 beat ≤ 10s**——一个 beat = 一个生成片段，超过 10s 视频生成会失败；超过 10s 的语义单元必须在句子边界继续拆分为连续 beats

### Beat 切分规则

1. 按**语义完整性**切分，不严格按字数或固定秒数。
2. 中文优先在逗号/句号处切分；英文优先在逗号/句号/从句处切分。
3. 短句（<1s）并入相邻 beat。
4. 长句（>3s 语义量）可拆分为 2 个 beats。
5. 每个 beat 只表达一个视觉 idea。

## 画面叙事写作（Playbook 导演能力，2026-08 核心新增）

**每个 beat 必须写出一段 Playbook 级 `image_prompt`（完整画面描述），让模型直接生成蓝图。** 这是导演阶段最重要的产出——不是元素装配表，而是"导演看到的画面"。

### 写作五件套（Playbook 提示词 2 结构）

每个 beat 必须明确：

1. **Sentence（原句）**：该 beat 的旁白原句。
2. **Core Idea（核心概念）**：抛弃字面，提炼含义（如：老龄化危机/巨大财富/经济崩溃）。已有 `core_idea` 字段。
3. **Editorial Title（排版大字标题）**：1-4 词杂志封面级大标题。已有。
4. **Visual Metaphor（视觉隐喻）**：最强象征图形代替字面（财富→金库/皇冠）。已有 `visual_metaphor` 字段。
5. **Image Prompt（图像提示词）**：**一段完整的画面描述**（写进 `image_prompt` 字段），必须包含：

### Image Prompt 写作规则（硬性）

```
1. 背景: 纸张材质（warm beige/cream paper + grain + halftone texture）+ 氛围词
   （museum-quiet / archival / dramatic / ominous）
2. 主体: 位置（LEFT/RIGHT/CENTER + 前景/背景/中景）+ 大小关系（tiny/huge/dominant）
        + 材质（black-and-white cut-out / halftone）
3. 细节元素: 每个辅助元素必须与主体/其他元素有叙事关联
   （标本标签钉在图钉上、红线连接两物、手伸向硬币——元素构成场景，不是孤立堆叠）
4. 排版: Editorial Title 的字体/颜色/位置/叠压（"towers slightly occluding two letters"）
        + 占画面比例（text occupying 30% of frame）
5. 氛围与构图: layered paper collage, soft drop shadows, generous negative space,
        flat print, premium VOX-style documentary editorial collage, 16:9
6. 负向提示词: 完整长版（no clutter...no distorted anatomy...maintain a clean premium VOX-style...）
```

### 画面写作 vs 元素装配（两者并存）

- **`image_prompt`** → assets 阶段直接生成蓝图（模型按完整描述画）
- **`elements[]`（box/rot/z/family/micro）** → compose 阶段动画装配
- 两者服务于不同目的，都要写。image_prompt 是"画面长什么样"，elements 是"画面怎么动"。

### 写作质量标准（对照 Playbook 示例 THE LAST COIN）

| 维度 | 合格标准 |
|---|---|
| 叙事关联 | 元素互相作用（遮挡/连接/互动），不是孤立清单 |
| 细节密度 | ≥5 个具体视觉元素，每个有明确位置和角色 |
| 构图比例 | 明确主体大小关系 + 文字占画面比例 |
| 氛围词 | 每个 beat 有情绪基调（museum-quiet/ominous/triumphant）|
| 叠压关系 | 具体描述（"coin slightly occluding one letter"）|

## 元素规格（per element）

每个元素必须声明：

| 字段 | 说明 | 示例 |
|---|---|---|
| `layer` | L1 bg / L2 hero / L3 element / L4 decor | 必填 |
| `kind` | `img` (图片素材) 或 `css` (CSS 装饰/素材库贴图) | 必填 |
| `src` | img 类型的素材引用（assets 阶段填充路径） | 必填于 img |
| `data_class` | real_data / real_content / creative / css | 必填 |
| `data_source` | 真实数据来源或生成策略 | real_data/real_content 必填 |
| `box` | [left, top, width, height] px | 必填 |
| `rot` | 旋转角度 | 可选 |
| `z` | z-index 叠放顺序 | 必填 |
| `family` | 入场动画：slide/rise/drop/slap/press/draw/pop/fade | 必填 |
| `micro` | 微动效：sway/lift/pulse/none | 必填 |
| `sfx` | 落地音效：paper_slide/tape_press/stamp_thud/string_zip/pin_click/paper_tap | 可选 |
| `text` | css 类型的内容文字 | 必填于 css |
| `sync_sentence` | 该元素对应 narration 的句子/beat 文本 | 必填 |
| `semantic_family` | 视觉语义：drop/rise/shake/pop/slide/grow/pulse/slap/fade | 必填 |

## 4 层结构（L1-L4）

每个 scene 必须设计 4 层：

1. **L1 bg**：背景纹理（报纸/蓝图/羊皮纸/账本）。每个 scene 单独生成一张 bg texture。
2. **L2 hero**：最大主体 cutout（真实照片参考后生成透明 PNG）。
3. **L3 elements**：与语音同步的支持元素（数据图、图标、标签等）。
4. **L4 decor**：CSS 装饰或素材库贴图（胶带、图钉、印章、红绳、标签）。

## 段落级视觉功能

根据 `paragraph_label` 设计视觉功能：

| 段落标签 | 视觉功能 | 构图特征 |
|---|---|---|
| `viral_hook` | 强冲击、大数字/大标题、高对比 | 全屏大标题 + 1 个 hero |
| `quick_intro` | 建立 stakes、连接观众 | 人物/物体特写 + 标签说明 |
| `main_story` | 叙事推进、信息叠加 | 多元素拼贴、时间线/关系图 |
| `turning_point` | 反转揭示、对比冲突 | 对比构图、红绳/断裂/重叠 |
| `big_picture` | 宏观意义、连接现实 | 地图/网络/宏观图、留白 |
| `powerful_ending` | 悬念、留白、思考 | 极简、单元素、重负空间 |

压缩形态中合并的段落（如 `viral_hook+quick_intro`）需要同时承载两个视觉功能，但视觉风格必须统一。

## 动画节奏

- **Build-on 阶段**：约 70% beat 时长，元素按叙事顺序逐个入场。
- **Living-paper 阶段**：约 30% beat 时长，构图完整，仅微动效。
- **入场错峰**：0.35-0.45s。
- **相机**：绝对锁定，禁止 zoom/pan/tilt/rotation/orbit/cut。
- **微动效**：hero 2-5px / 1°-2° / 1%-2% 缩放；辅助元素 yoyo 循环。

## 全程动态原则

- 入场动画完成后立即接续微动效，中间无静止窗口。
- 画面覆盖 ≥85%：留白太多会像静态图。
- 禁止"全部入场后画面静止"——那等于 PPT。
- 元素必须叠压（图章盖在图上、胶带跨接），不能平铺。

## TTS 时间戳校准（强制，不能跳过）

### 流程顺序

```
script 定稿（估算 timing）
  → scene_plan v1（timing_source: estimated，基于 4.7 字/秒或 2.5 wps）
  → assets 阶段：TTS 合成 → whisper 提取真实时间戳
  → 计算偏差：|tts_actual - estimated| / estimated
  → 若偏差 ≤5%：更新 scene_plan v2（timing_source: tts_actual）
  → 若偏差 >5%：回到 script 阶段精简/扩充，重新生成 scene_plan v1
  → edit 阶段只接受 timing_source: tts_actual 的 scene_plan
```

### 校准规则

1. **第一轮 scene_plan** 使用 `timing_source: "estimated"`，`start_seconds` / `end_seconds` 由 script 估算常数计算。
2. **TTS 完成后**必须重新计算每个 scene/beat 的真实 `start_seconds` / `end_seconds`。
3. **偏差 ≤5%**：直接更新 timing，保持语义 scene/beat 边界不变，仅调整绝对时间。
4. **偏差 >5%**：必须回到 script 阶段修改字数，然后重新生成 scene_plan。不能通过 speed 变速或硬切时间码弥补。
5. **进入 edit 阶段的红线**：`scene_plan.timing_source` 必须是 `"tts_actual"`，否则拒绝进入。

### 元素入场时间

- 元素入场时间 = 对应 narration sentence 的真实开始时间 + 0.2s。
- 动画 duration = sentence_len × 0.8（呼吸空间）。
- 短句（<1s）合并到相邻 beat；长句（>3s）可拆分为 2 个元素。

## 反模式

- ❌ 用固定 10s/beat 硬切。
- ❌ 用语音 segment 边界直接作为 scene 边界（旧 voice-led 方式）。
- ❌ 所有元素在 scene 开始时同时 dump 出现。
- ❌ 真实 TTS 偏差 >5% 时不回退 script。
- ❌ scene_plan 使用 estimated timing 直接进入 edit。
- ❌ 画面元素少于 6 个或覆盖 <85%。
- ❌ 相机移动或元素定位后漂移。

## 质量要求

- 每个 scene 有明确的 `paragraph_label`。
- 每个 beat 有明确的 `sync_sentence` 和 `semantic_family`。
- 每个元素声明 `layer` 和 `data_class`。
- 每个 scene 设计 L1-L4 四层。
- 真实悲剧克制：无血腥、无苦难特写。

## 成功标准

- `scene_plan` 通过 schema 校验。
- 每个 scene 映射到 script 的一个 `paragraph_label`。
- 每个 beat 有 `sync_sentence` 和 `semantic_family`。
- **每个 beat 有 Playbook 级 `image_prompt`**（叙事关联、细节密度 ≥5 元素、构图比例、氛围词、叠压关系、负向提示词完整）。
- 每个元素声明 `layer` 和 `data_class`。
- 偏差 ≤5% 时 `timing_source` 为 `tts_actual`；偏差 >5% 时记录回退原因。
- 进入 edit 阶段前 `timing_source` 必须是 `tts_actual`。
