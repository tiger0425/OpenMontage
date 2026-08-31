# 调研 05：google_imagen 无字底稿 prompt 模板（channel-stickman）

> 只读调研 + 模板起草，未实际出图（出图验证放到试点执行期）。
> 工具源码：`tools/graphics/google_imagen.py`（class `GoogleImagen`，version 0.1.0，BETA）。
> Layer 3 skill 来源：全局 `google-gemini-image` SKILL（Nano Banana 家族生产纪律）+ 项目内 `.agents/skills/nanobanana-poster-layer/SKILL.md`（对话式编辑纪律）。

---

## 一、google_imagen 入参契约（源码实读）

### 1.1 能力开关（`supports` 字典，原样记录）

```python
supports = {
    "negative_prompt": False,   # 不支持负面提示词参数
    "seed": False,              # 不支持 seed 固定
    "custom_size": False,       # 不支持任意像素尺寸（只能选宽高比）
    "aspect_ratio": True,
    "image_edit": True,         # 支持参考图 img2img
    "gemini_flash_image": True, # 支持 Gemini 图像模型路线
}
```

### 1.2 input_schema 参数表（参数名原样）

| 参数名 | 类型 | 默认值 | 约束 | 说明 |
|--------|------|--------|------|------|
| `prompt` | string | 必填 | max 480 tokens | 图像描述 |
| `aspect_ratio` | string enum | `"1:1"` | `"1:1"` `"3:4"` `"4:3"` `"9:16"` `"16:9"` | 共 5 档；`9:16` 近似 768×1344 |
| `width` / `height` | integer | — | — | 会被映射到最接近的支持档位（非精确像素） |
| `model` | string enum | `"gemini-3.1-flash-lite-image"` | `imagen-4.0-generate-001` / `imagen-4.0-fast-generate-001` / `imagen-4.0-ultra-generate-001` / `gemini-3.1-flash-lite-image` / `gemini-3.1-flash-image` | 工具注释明确：「imagen-4.0-\* endpoints return 404 as of 2026-08」→ 实际只能用两个 Gemini 图像模型 |
| `number_of_images` | integer | 1 | min 1, max 4 | 见 §2 陷阱：仅在已死的 Imagen 路径生效 |
| `output_path` | string | `generated_image.png` | — | 输出文件路径 |
| `image_path` | string | — | 本地路径 | img2img 参考图（jpg/jpeg/png/webp） |
| `image_strength` | number | 0.7 | 0.0–1.0 | 参考图影响力（0=忽略，1=完全照搬）；见 §2 陷阱 |

### 1.3 其他事实

- **认证**：`GOOGLE_API_KEY` 或 `GEMINI_API_KEY`（AI Studio 路线），或服务账号（`GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT`，Vertex 路线）。
- **成本估计**（工具内置）：`gemini-3.1-flash-lite-image` 与 `gemini-3.1-flash-image` 按 **$0/张** 计（免费层）；imagen ultra $0.06、fast $0.02、普通 imagen $0.04。
- **确定性**：`Determinism.STOCHASTIC`，幂等键字段为 `["prompt", "aspect_ratio", "model"]`——同样输入不保证同样输出。

---

## 二、关键实现陷阱（直接影响模板设计）

工具内部有**两条互斥代码路径**，行为差异巨大：

| 维度 | Gemini 路径（默认可用） | Imagen predict 路径 |
|------|------------------------|---------------------|
| 触发条件 | model 名同时含 `gemini` 和 `image` | model 名为 `imagen-4.0-*` |
| 端点 | `client.models.generate_content()` | `models/{model}:predict` |
| 实际传给 API 的内容 | **只有 prompt 文本 + 可选参考图字节** | prompt + `sampleCount` + `aspectRatio` |
| `aspect_ratio` 参数 | **静默忽略，未透传** | 生效 |
| `number_of_images` | **静默忽略**（每次恒 1 张） | 生效（但端点已 404） |
| `image_strength` | **静默忽略，未透传** | 未使用 |
| 现状 | ✅ 可用 | ❌ 2026-08 起 404，弃用 |

**结论**：当前唯一实际可用的生图方式 = Gemini 图像模型 + prompt（+ 可选参考图）。这意味着：

1. **9:16 竖屏不能依赖 `aspect_ratio` 参数**——必须靠 prompt 措辞、参考图锚定或后期裁切（见模板 A 的三条策略，试点期实测择优）。
2. **一次调用只得一张图**，多候选需多次调用。
3. **一致性没有 seed 可用**——跨幕一致性只能靠「固定风格锚定词组 + 参考图 + 多次抽卡人工挑选」。
4. Layer 3 skill 补充事实：Gemini 图像模型**无输入图时默认输出 1:1；有输入图时输出趋向匹配输入图比例**（这是竖屏策略 S1 的依据）。

---

## 三、Layer 3 skill 提炼的 prompt 技巧

来自全局 `google-gemini-image` skill（面向 Gemini 3.1 Flash(-Lite) Image / Nano Banana 家族）：

1. **正向、具体、可观察的语言**。不用 "masterpiece / 8K / award-winning" 这类空洞质量堆砌；描述看得见的属性（"an empty pedestrian street at blue hour" 优于一长串否定清单）。
2. **结构化 prompt 八段式**：交付物与用途 → 主体与动作 → （参考图角色台账）→ 构图/相机/裁切安全区/空间关系 → 材质/环境/光照/配色/风格 → 引号内精确文案 → 不变量声明 → 输出要求（一张图、比例、尺寸）。本管线无文案需求，第 6 段反转为「禁止一切文字」。
3. **负面约束仍要显式声明关键两条**：`no text` 与 `no people` 无法用 negative_prompt 参数实现（工具不支持），只能在正向 prompt 里显式写出；但要用紧凑约束块而非长否定清单。
4. **防伪文字话术**：让画面中的招牌/书页/屏幕呈现为「空白表面」（blank surfaces），比单纯说 no text 更有效——不给模型画字的借口。
5. **参考图必须写角色台账**：声明 R1 只借构图、R2 只借配色……冲突时显式指定优先级，不让模型自行"融合"。
6. **多轮编辑必然漂移**（nanobanana-poster-layer 同款结论）：每轮重申锁定锚点；漂移扩大时**从上一张被接受的图重启**，不要修补坏掉的衍生图。
7. **Lite 模型定位**：仅 1K 输出、速度快成本零、适合批量概念探索；不适合长链多轮精编。正式资产可考虑升 `gemini-3.1-flash-image`（同为 $0 估计价）。
8. **验收纪律**：解码后全分辨率检查实际像素尺寸与比例（不信参数承诺）；模型不一定遵守请求的张数；所有 Gemini 出图内嵌 SynthID 水印（对本项目反而契合「AI 生成内容」标识义务）。
9. **免费层隐私**：unpaid 层 prompt 可能被 Google 用于产品改进/人工审查——本项目 prompt 为通用美术描述，不含敏感信息，可接受；不要把账号私密信息写进 prompt。

---

## 四、三套模板

**使用约定**：
- 模板中 `#` 开头的行是中文注释，**提交 API 前删除**（保留会占 token 并可能干扰模型）。
- `{{双花括号}}` 是每集/每次替换的变量槽。
- 调色板四色为**临时占位建议值**，待工单 02（SVG 角色圣经）定稿后统一替换，保证背景与矢量角色同色系。
- `STYLE_ANCHOR` 块在三套模板间逐字复用，是跨幕/跨资产一致性的核心手段（无 seed 情况下的替代方案）。

### 4.0 公共风格锚定块（跨幕一致性用，逐字复用）

```text
STYLE_ANCHOR =
Flat vector editorial illustration, clean rounded geometric shapes, bold uniform outlines,
limited flat palette: deep navy #1B2A41 base, warm cream #F5EFE0 ground,
coral red #E4572E accent, mustard yellow #F3A712 secondary accent,
simple two-tone cel shading, no gradients except flat two-tone steps,
subtle paper-grain texture, generous empty negative space,
modern minimalist poster aesthetic, consistent single illustration style.
```

```text
HARD_CONSTRAINTS =
Absolutely no text anywhere: no letters, no numbers, no words, no logos, no watermarks;
any sign, book page, screen or label must appear as a blank surface.
No realistic people, no photographic humans, no detailed faces, no hands.
No borders, no frames, no watermark marks.
Return exactly one image.
```

> 注释：HARD_CONSTRAINTS 同时覆盖「无文字」与「无真实人物」两条红线；背景类还要追加「无任何人物剪影」（见模板 A），因为火柴人是 SVG 层另加的，背景里哪怕出现剪影小人都会打架。

### 4.1 模板 A：9:16 竖屏背景底稿

用途：每集分幕的场景背景，扁平插画风，顶部留给集数标题、底部留给字幕，中部偏一侧留角色活动区。

#### 竖屏达成策略（试点期按序实测）

| 策略 | 做法 | 依据 | 风险 |
|------|------|------|------|
| S1（推荐先试） | 预制一张 768×1344 米白纯色 PNG 画布作 `image_path` 参考，prompt 声明"以此画布为底" | skill 事实：有输入图时输出趋向匹配输入比例 | 参考图可能压平细节；需试 2-3 张校准 |
| S2 | 仅在 prompt 中写明 "vertical 9:16 tall frame" | Gemini 3.1 图像模型官方本身支持 9:16，但本工具未传 ImageConfig，服务端默认行为未知 | 大概率回落 1:1，需解码验尺寸 |
| S3（兜底） | 按 4:3 或 1:1 出图，构图设计为"中心竖带承载全部内容"，后期 FFmpeg 居中裁切成 9:16 | 完全可控 | 有效分辨率损失；构图需预设计 |

#### 正向 prompt 全文（S2 措辞版，S1 时在开头加一句 "Use the supplied blank canvas as the base layer and fill it with the scene below."）

```text
# 【第一段：交付物 + 风格锚】逐字复用 STYLE_ANCHOR
One flat vector editorial illustration background for a short-form psychology video episode.
[此处插入 STYLE_ANCHOR 全文]

# 【第二段：场景主体】每集替换 {{场景描述}}
Scene: {{场景描述，示例：a quiet night city rooftop under a large crescent moon,
simple geometric skyline, a few flat clouds}}

# 【第三段：竖屏构图与安全区】
Vertical 9:16 tall composition.
All meaningful visual content lives in the middle band of the frame.
Keep the top 25% of the frame almost empty with only faint flat texture
(reserved zone for the episode title).
Keep the bottom 30% of the frame as calm low-detail ground
(reserved zone for subtitles).
Leave a clear empty pocket in the center-left area for an animated
character to be composited in later.

# 【第四段：硬约束】逐字复用 HARD_CONSTRAINTS 并加严人物禁令
[此处插入 HARD_CONSTRAINTS 全文]
Additionally: absolutely no human figures, no character silhouettes,
no shadows shaped like people, no crowds, no mannequins.

# 【第五段：输出要求】
One image only, no caption, no border.
```

#### 建议参数

```json
{
  "tool": "google_imagen",
  "model": "gemini-3.1-flash-lite-image",
  "prompt": "<上述全文，剥除注释行>",
  "aspect_ratio": "9:16",
  "number_of_images": 1,
  "image_path": "(策略S1时) assets/canvas_9x16_blank.png",
  "output_path": "outputs/stickman/bg_<ep><scene>.png"
}
```

> 注释：`aspect_ratio` 在 Gemini 路径不生效但仍建议照填——保持幂等键语义正确，且未来工具修复透传后无需改配置。

### 4.2 模板 B：封面图形底稿

用途：抖音封面（9:16）。一个强视觉隐喻主体居中，上下留白给后期大字标题。封面允许象征性图形（含抽象人头轮廓这类符号），但禁止写实人物照片感。

#### 正向 prompt 全文

```text
# 【第一段：交付物定义】
One bold cover artwork background for a Chinese psychology-themed
short-video channel. Graphic poster style, not a scene illustration.
[此处插入 STYLE_ANCHOR 全文]

# 【第二段：核心隐喻主体】每期替换 {{隐喻主体}}
Central subject: {{隐喻主体，示例：a human head outline built from scattered
jigsaw pieces, some pieces drifting away}}
Render it as one large symbolic flat-graphic shape.

# 【第三段：构图与留白】
Subject centered slightly above middle, occupying about 45-55% of the
frame height.
Top 25% and bottom 20% stay as clean flat-color negative space
(reserved for large headline typography added later).
Strong instant readability even at small thumbnail size:
one dominant shape, high color contrast against the cream ground.

# 【第四段：硬约束】
[此处插入 HARD_CONSTRAINTS 全文]
Symbolic geometric shapes are allowed; photographic or realistic
people are not. No facial features.

# 【第五段：输出要求】
Vertical 9:16 poster proportions. One image only.
```

#### 建议参数

```json
{
  "tool": "google_imagen",
  "model": "gemini-3.1-flash-image",
  "prompt": "<上述全文，剥除注释行>",
  "aspect_ratio": "9:16",
  "output_path": "outputs/stickman/cover_<ep>.png"
}
```

> 注释：封面是门面资产，建议用 `gemini-3.1-flash-image`（标准版）而非 lite；两者工具估价同为 $0。竖屏同样受 §2 陷阱影响，沿用模板 A 的策略 S1/S3。可选：把上一版被采纳的封面作为 `image_path` 参考传入，强化系列封面的一致性。

### 4.3 模板 C：logo 图形底稿

用途：频道 logo 概念探索稿（1:1）。极简几何标志、居中、纯色或双色。**定位是灵感稿**：AI 位图稿选定方向后，最终 logo 应由人工矢量化重绘（保证缩放清晰度与精确几何），不直接采用位图。

#### 正向 prompt 全文

```text
# 【第一段：交付物定义】
One minimalist geometric logo mark concept for a Chinese psychology
short-video brand called {{品牌名}}. Do NOT render the name itself —
the mark must work without any lettering.
[此处插入 STYLE_ANCHOR 全文，但删去 paper-grain 一句，logo 要纯净底]

# 【第二段：创意方向】按批次替换 {{创意方向}}
Core motif: {{创意方向，示例：a tiny matchstick-figure drawn as one
single continuous line, standing inside an open circle}}
Explore the idea with pure geometry: circles, lines, arcs, dots.

# 【第三段：构图】
Single centered emblem, symmetrical or near-symmetrical,
occupying about 60% of the frame, surrounded by wide flat margin.
Maximum 3 colors from the given palette, solid fills, no gradients.

# 【第四段：硬约束】
[此处插入 HARD_CONSTRAINTS 全文]
The mark must remain recognizable when shrunk to 48 pixels.

# 【第五段：输出要求】
Square 1:1. One image only, flat solid background.
```

#### 建议参数

```json
{
  "tool": "google_imagen",
  "model": "gemini-3.1-flash-image",
  "prompt": "<上述全文，剥除注释行>",
  "aspect_ratio": "1:1",
  "output_path": "outputs/stickman/logo_concept_<n>.png"
}
```

> 注释：logo 是三套里唯一用 1:1 的。因无 seed，同一 {{创意方向}} 连跑 4-6 次攒候选池再挑；选中后走人工矢量化（SVG 重绘），并与角色圣经（工单 02）的线条粗细规范对齐——「单线小人」母题可与 SVG 火柴人形成视觉呼应。

---

## 五、已知限制与风险登记

| # | 风险 | 严重度 | 缓解 |
|---|------|--------|------|
| R1 | `aspect_ratio` 在默认 Gemini 路径**未透传**，竖屏可能回落 1:1 | 高 | 模板 A 策略 S1/S3；每次出图后用 ffprobe/PIL 解码验证实际像素 |
| R2 | `number_of_images`、`image_strength` 同样只在死路径生效 | 中 | 多候选靠多次调用；参考图影响强度不可调，只能换参考图内容控制 |
| R3 | 无 `seed`、无 `negative_prompt` | 中 | 一致性靠 STYLE_ANCHOR 逐字复用 + 参考图 + 人工抽卡；负面约束写进正向 prompt |
| R4 | `imagen-4.0-*` 三个 model 值已 404（2026-08） | 高 | 配置只允许 `gemini-3.1-flash-lite-image` / `gemini-3.1-flash-image`；管线 manifest 里做枚举白名单 |
| R5 | 「无文字」服从度不完美：招牌/书页易出伪文字乱码 | 中 | blank-surfaces 话术；出图后人工目检，出现即重 roll（预期废片率待 V2 实测） |
| R6 | 「无人物」服从度：街景/人群语境易混入剪影 | 中 | 场景选题避开人流语境；prompt 加严禁令（模板 A 第四段） |
| R7 | 分辨率：Lite 仅 1K 级；9:16 档约 768×1344 < 抖音 1080×1920 | 中 | 后期统一放大到 1080×1920（扁平插画对轻度放大不敏感）；或标准版模型试更高输出 |
| R8 | 多轮编辑漂移（若用 img2img 迭代改图） | 中 | 每轮重申锁定项；漂移即回退到上一张被接受版本重启 |
| R9 | 免费层 prompt 可能被 Google 留存/审查 | 低 | prompt 只含通用美术描述，禁止夹带任何账号/个人敏感信息 |
| R10 | 所有产出内嵌 SynthID 水印 | 信息 | 与平台 AI 内容标识义务方向一致，无需处理 |
| R11 | 调色板当前为占位值，可能与角色圣经定稿冲突 | 中 | 角色圣经定稿后同步更新 STYLE_ANCHOR 四色并回归测试 |

---

## 六、试点期验证清单

- [ ] **V1 竖屏实测**：S2（纯 prompt 9:16）→ 解码查像素；失败则 S1（空白画布参考图）→ 再失败用 S3（4:3 出图后期裁切）。确定唯一管线策略并记入决议。
- [ ] **V2 无文字服从度**：模板 A 连续出 10 张，统计伪文字出现率；>30% 则升级 blank-surfaces 话术措辞迭代。
- [ ] **V3 无人物服从度**：同批 10 张统计人物/剪影混入率。
- [ ] **V4 风格锚定一致性**：同一 STYLE_ANCHOR + 5 个不同场景出图，人工并排打分（色调/笔触/质感三项各 1-5 分），均分 ≥4 视为锚定有效。
- [ ] **V5 色彩还原**：任选 3 张成品，取色器核对 navy/cream 两主色与 hex 目标偏差（ΔE 目测可接受即可）。
- [ ] **V6 安全区验证**：把 9:16 字幕框模板（顶 25% / 底 30%）叠加到出图上目检留白是否达标。
- [ ] **V7 封面缩略图可读性**：模板 B 出图缩到抖音 feed 缩略图尺寸目检主体是否一眼可读。
- [ ] **V8 logo 流程**：模板 C 出 6 张候选 → 选 1 → 人工 SVG 重绘计时，评估单 logo 制作成本。
- [ ] **V9 凭据与配额**：确认 `GOOGLE_API_KEY`（或 `GEMINI_API_KEY`）在本机可用，摸清单日免费配额上限，估算单集背景用量（预估 ≤8 幕 × 2 次抽卡）是否触顶。
- [ ] **V10 lite vs 标准 bake-off**：同一 prompt 各跑 3 张对比，决定背景（量大）与封面/logo（质优先）分别固定哪个 model 值。
- [ ] **V11 输出规格**：核验输出为 PNG、无 alpha 通道、色彩空间无意外；确认 `output_path` 目录约定与管线资产目录兼容。

---

## 七、结论

- **能力边界一句话**：本机 google_imagen 当前唯一可用路径是 Gemini Flash(Lite) 图像模型 + 纯 prompt（+可选参考图），`aspect_ratio`/`number_of_images`/`image_strength` 参数在该路径被静默忽略，且无 seed、无负面提示词——竖屏与一致性都要靠模板技巧补齐。
- 三套模板（竖屏背景 A / 封面 B / logo C）已就绪，含公共 STYLE_ANCHOR 与 HARD_CONSTRAINTS 复用块、逐段中文注释与建议参数；待试点期按第六节清单实测后固化。
