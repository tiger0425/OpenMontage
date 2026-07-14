# Fabric-Showcase 管线领域语言

> 在 OpenMontage 中，`fabric-showcase` 管线围绕"面料/纺织品"领域构建。
> 下方术语是管线 YAML 阶段和 review_focus 检查项的基础。

## 核心工件

### fabric_brief
在 `brief` 阶段产出的唯一工件。将"面料真理"与"广告意图"合为一体：
- `fabric_facts` 区块 — 由用户提供的、不可虚构的面料属性
- `ad_intent` 区块 — 目标平台、时长、风格导向
- `voiceover_script` — 旁白稿件（13-25 秒朗读量）
- `scene_structure` — 场景大纲（3-5 幕）

### fabric_facts

`fabric_brief.fabric_facts` 是 Truth-Gate 的数据载体。
在后续阶段中，agent 必须确保生成的画面、文案、不会奇妙地出口转手来的任何数据与该区块相矛盾。

| 字段 | 语义 | 示例 |
|------|------|------|
| `composition` | 成分比例（不可虚构） | `55% linen, 45% cotton` |
| `texture` | 触感/质感描述 | `亚麻筋骨，棉柔软，亲肤透气` |
| `applicable_products` | 用途/适用产品列表 | `衬衫, 连衣裙, 帆布包` |
| `reference_image` | 原始面料的参考图路径 | `assets/fabric-original.jpg` |
| `color_palette` | 面料色彩描述 | `复古红格（砖红+深棕）, 哑光` |
| `season` | 适用季节 | `三季皆宜` |
| `weight` | 面料克重（如有） | `中厚` |

### ad_intent

`fabric_brief.ad_intent` 是用户对广告产物的要求：
- `platform` — 目标平台（`xiaohongshu` | `douyin` | `bilibili`）
- `duration` — 目标时长（秒，通常 15-20）
- `aspect_ratio` — 画面比例（`9:16` | `16:9` | `1:1`）
- `style_direction` — 风格导向（如 `复古、文艺、质感`）

### voiceover_script

旁白稿件，必须忠于 fabric_facts。通常 20-40 字，覆盖：
- 品牌名（如 `铃月布行`）
- 面料名（如 `复古红格`）
- 成分复述
- 触感描述
- 适用产品

### scene_structure

场景大纲，通常 3-5 幕。每幕包含：
- `name` — 场景名
- `duration` — 时长（秒）
- `treatment` — 画面处理描述
- `assets_needed` — 需要的素材清单（图/视频/音频）

## 阶段术语

### Truth-Gate（真理门）

管线级别的约束机制：所有生成内容必须忠于 `fabric_brief.fabric_facts`。
这不是一个独立阶段或独立工件，而是内嵌在 `review_focus` 检查项中的校验逻辑。
违反 Truth-Gate（如生成画面中出现成分不符、质感描述偏离）属于 critical 发现。

### 产品线画（可选）

用户可在 `fabric_brief.fabric_facts.applicable_products` 中要求生成产品线画 SVG
（如衬衫、连衣裙、帆布包轮廓线稿）。这是可选输入，不是管线标配。

## 工具术语

### comfyui_image_gen

自定义 BaseTool 子类，通过 ComfyUI API（Klein 工作流）生成面料质感图片。
注册到 registry，`capability: image_generation`。

### comfyui_video_gen

自定义 BaseTool 子类，通过 ComfyUI API（LTX23 工作流）生成面料动态视频。
注册到 registry，`capability: video_generation`。

### cover_gen

封面生成工具。使用 HyperFrames snapshot 取帧 + Python Pillow 渲染中文文字。
注册到 registry，`capability: image_generation`，`runtime: LOCAL`。
支持的封面比例：
- 小红书 3:4 (1080×1440)
- B站 16:9 (1080×608)
- 抖音 9:16 (1080×1920)

## 和其他管线的区别

| 维度 | fabric-showcase | hybrid | animated-explainer | cinematic |
|------|-----------------|--------|---------------------|-----------|
| 源 footage | 无 | 有 | 无 | 可选 |
| Truth-Gate | 有（fabric_facts） | 无 | 无（话题是开放的） | 无 |
| 目标 | 商业种草广告 | 混合素材编辑 | 教育解说 | 氛围叙事 |
| 时长 | 15-20s | 30s-3min | 60s-3min | 30s-2min |
| 运行时 | 仅 hyperframes | remotion/hyperframes | remotion/hyperframes | remotion/hyperframes |
| 阶段数 | 4 | 8 | 8 | 8 |
