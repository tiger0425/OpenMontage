# Vox Look Library — 视觉层参考库（series-adapt）

图像提示词结构与主题预设库：为 series-adapt 单集生成"真实拼贴感"图像提供可执行规范。
与 `vox-story-library.md`（叙事层）、`vox-motion-library.md`（动效层）配套使用。
由 `scene-director.md`（写作 generation_direction）与 `asset-director.md`（拼接完整 prompt）引用。

> 来源：提炼自 vox-director（Alisa0808/vox-director, MIT）的 `references/prompt-guide.md`，
> 保留其经实战验证的提示结构与词库，并适配本项目 img2img（真实人物/车辆保真）与
> 1920×1080 输出制式。本项目不采用其 AI 视频模型动画路线。

## 0. 核心原则

> **拼贴的"真实感"诞生在图像步骤。** 如果图像不是一张信息丰富的拼贴，下游任何动效都救不回来。
> 每张图都必须看起来是"手工剪贴 + 分层 + 带纸阴影"，而不是一张平滑的插画。

两条不可破的规则（对每张图生效）：
1. **STYLE BLOCK 逐场景逐字复用** —— 这是 100 集"一部影片感"的第一来源。只换场景、背景色、标签，不换风格块。
2. **纸语言全系列锁定** —— 边缘粗糙度、halftone 密度、纸张基底可以随主题预设微调，但**纹理语言不变**。颜色可以变，纹理不能变。

## 1. 图像提示 5 部分结构（generation_direction 模板）

```
[1 STYLE BLOCK —— 逐字取自 styles/vox-collage.yaml → asset_generation.image_prompt_prefix]
  注意：本项目用 img2img 保真真实人物/车辆，风格块中"real-person and real-object
  references preserved via img2img"已内置，直接复用即可。

[2 SCENE —— 以独立剪贴片描述（这是 5 部分中最关键的一段）]
  SCENE as layered paper cut-outs: {主体，若为真实车辆/人物则写 "the exact {tank/person}
  from the reference photo, cut out as a black and white halftone print"}, {一个道具},
  {一条文字条/数字条}, {装饰碎片}; clear edges, distinct layers, each with its own
  drop shadow, visibly hand-cut.

[3 背景 —— 每场景一个大胆纯色]
  on a bold flat {颜色} paper background.    ← 相邻场景背景色必须不同（从 palette 轮换）

[4 标签 —— 烘烤进图的内嵌文字，≤4 词]
  A typewriter strip / rubber stamp reading "{LABEL}" (English only, max 4 words).
  文字由图像模型渲染（清晰），绝不交给动效阶段"后加文字"糊上去。

[5 技术参数]
  1920x1080, 2k resolution, matte finish, no gradients, no gloss.
```

**img2img 适配**：场景涉及真实人物/车辆/地点时，SCENE 段的主体必须写
"Keep the exact same [person/tank/place] from the reference photo"，其余 4 段不变。
整图缩放/构图类细节由 asset-director 的 `image_strength` 控制。

### 5 部分要点（每条都是教训）

| 要点 | 原因 |
|---|---|
| SCENE 必须写"独立剪贴片 + 可见边缘 + 各自阴影" | 有层次才像拼贴；且为动效阶段提供可分离图层（parallax 的前提） |
| 每场景一个**大胆纯色**背景 | 繁忙背景糊掉剪贴片轮廓，杀死 Vox 的 punch；也保证相邻场景视觉跳变 |
| 标签**烘烤进图**、≤4 词、英文 | 图像模型渲染文字清晰；动效阶段重排文字必糊 |
| 2k/1920×1080 | 缩放动画（push_in 1.07×）时剪贴片保持锐利 |
| 颜色可以跨场景旅行（如 泛黄档案 → 军绿 → 高光金） | 让 palette 承载情绪弧线（对应叙事层的高光节拍） |

## 2. 图像维度词库（自定义主题时逐轴挑选）

默认风格块之外想差异化时，每轴挑一个词填入 5 部分结构。⭐ = 最强主题杠杆。

| 维度 | 控制什么 | 词库 |
|---|---|---|
| **媒介/技法** | 最强风格杠杆 | paper collage · torn-paper · photomontage · screenprint · risograph · letterpress · linocut/woodcut · lithograph · halftone print · gouache · photocopy/xerox · rubber-stamp |
| **年代/运动** ⭐ | 一键切换调色+排版+布局 | Swiss/International Typographic · Bauhaus · mid-century modern · Russian Constructivism · Dada · Pop Art · punk zine · Art Deco · WPA poster · Soviet · atomic-age · retro-futurism |
| **构图/布局** ⭐ | 海报层级与留白 | modular grid · asymmetric · strong negative space · diagonal dynamic · fg-mid-bg depth · hero headline hierarchy · full-bleed · radial · stacked bands · off-center focal |
| **配色** ⭐ | 最干净的区分器（杜绝渐变糊） | limited 2-3 color · duotone · monochrome + 1 accent · riso fluorescent-pink + federal-blue · Bauhaus primaries · 70s mustard/rust/avocado · 60s pop · teal-&-orange · cream/kraft base · named hex |
| **字体** ⭐ | 标题观感 | bold condensed grotesque (Helvetica/Akzidenz) · geometric sans (Futura) · slab serif · 70s display serif · wood-type · hand-lettered · ransom-note cut letters · stencil · all-caps · knockout/reversed |
| **印花/质感** | "手工制作，不是 AI 丝滑" | halftone dots · Ben-Day dots · riso misregistration · letterpress deboss · newsprint · kraft/cardstock · aged/foxed paper · fold creases · coffee stains · deckled vs scissor-cut edges |
| **氛围** | 情绪锚点 | playful · bold · urgent · editorial/serious · nostalgic · optimistic · ominous · satirical · archival |

**单行结构**（需要压缩成一段时）：
`[MEDIUM] + [ERA] of [SUBJECT + SCENE as cut-outs], [COMPOSITION], straight-on scanned-flat framing + flat even light, paper drop-shadows, [limited COLOR PALETTE], [PRINT FINISH], label "{WORDS}" in [NAMED TYPE STYLE], [MOOD], 1920x1080` —— 正面表述，不给 negative 词（Flux 系列不需要；`styles/vox-collage.yaml` 的 `image_negative_prompt` 仅在 provider 支持时追加）。

## 3. 主题预设表（系列设计系统选型用）

预设 = 从 §2 每轴取一值 + 一个动效幅度，叠在公共 Vox 约束之上。**供创建
`projects/<series>/DESIGN_SYSTEM.md` 时选型，也供单集微调**（如"本集是苏联背景 →
暂时切到 soviet-constructivist 的调色轴"，但纸语言不变）。

| 预设 | 年代/运动 | 调色 | 字体 | 印花 | 动效幅度 | 适合题材 |
|---|---|---|---|---|---|---|
| `american-retro` | 1950s 美式广告/pulp | 大胆复古原色 | wood-type / bold slab | halftone, aged | punchy | 军工外贸、商业故事、金钱 |
| `swiss-modern` | 瑞士国际主义 | 双色 + 红点缀 | Helvetica/Akzidenz | 干净平涂、微 grain | calm | 技术解析、系统讲解 |
| `soviet-constructivist` | 俄国构成主义 | 红/黑/奶油 | 粗体斜向压缩体 | letterpress, newsprint | punchy | 苏联背景集、工业史、政治 |
| `wpa-propaganda` | 1930s WPA 海报 | 低饱和三色 | stencil / gothic | screenprint grain | calm | 抗战史、公共工程、劳模 |
| `70s-groovy` | 1970s | mustard/rust/avocado | 圆润 display serif | riso grain | punchy | 文化、怀旧、民用装备 |
| `chinese-ink` | 中国木刻/水墨 | 墨色 + 朱红 | 中文毛笔字 + 红印 | rice-paper, seal | calm/punchy | 中国历史/文化集（民族品牌底色） |
| `atomic-age` | 1950s 未来主义 | teal/orange/cream | atomic script | halftone | punchy | 航天、未来科技、电子装备 |
| `newsprint-editorial` | 世纪中叶报纸特稿 | cream/deep red/mustard/charcoal | 粗体压缩新闻大标题 | 陈年纸、重 halftone | punchy | 新闻事件、争议话题、深度特稿 |
| `gilded-deco` | 1920s 装饰艺术奢华 | 陈年奶油/香槟金/炭黑 | didone 衬线宽字距 | 金箔、细 halftone | calm | 阅兵仪式、勋章、高光节拍 |

**系列级规则**：一个系列锁定 1 个主预设（如 99 追忆默认 `newsprint-editorial` + 军绿调色轴），
单集最多临时借用相邻预设的**调色轴**，纸语言（边缘/纹理/halftone）永不切换。

## 4. 反一致性红线（每张图自查）

- [ ] STYLE BLOCK 与原文件逐字一致（可 diff）
- [ ] SCENE 段包含"cut-outs / clear edges / drop shadow"三要素
- [ ] 背景是单一纯色词（bold flat {color}），非"复杂场景背景"
- [ ] 标签 ≤4 词、英文、烘烤进图（prompt 中带引号原文）
- [ ] 无 "3D render / CGI / glossy / gradient" 等词（正面表述，若 provider 需要 negative 则用 `image_negative_prompt`）
- [ ] 涉及真实人物/车辆时含 "Keep the exact same [subject] from the reference photo"
