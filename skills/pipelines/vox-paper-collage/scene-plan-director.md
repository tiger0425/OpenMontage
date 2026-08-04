# Scene Plan Director — Vox Paper Collage (v2)

## 职责

把脚本拆成节拍，**并为每个节拍定义完整的元素清单与动画规格**。
每一拍的元素清单是后续 assets/compose 阶段的唯一契约——assets 按清单生成素材，
compose 按清单组装 HTML+GSAP。

## 元素规格 (per element)

每个元素必须声明：

| 字段 | 说明 | 示例 |
|---|---|---|
| `kind` | `img` (图片素材) 或 `css` (CSS装饰: tape/pin/string/label/stamp/headline/arrow/underline) |
| `src` | img 类型的素材引用 (assets阶段填充路径) |
| `box` | [left, top, width, height] px |
| `rot` | 旋转角度 |
| `z` | z-index 叠放顺序 |
| `family` | 入场动画: slide/rise/drop/slap/press/draw/pop/fade |
| `micro` | 微动效: sway/lift/pulse/none |
| `sfx` | 落地音效: paper_slide/tape_press/stamp_thud/string_zip/pin_click/paper_tap |
| `text` | css 类型的内容文字 (label/stamp/headline 用) |

## 每拍元素数量

- 最少 **6 个**，通常 **8-12 个**（画面才不单调）
- 1 个背景底板 + 1-2 个 hero 主体 + 2-3 个支持元素 + 2-4 个装饰元素
- hero 占视觉权重 ~60%，不能有两个同等大小的 hero 抢视线
- **元素落位后覆盖画面 ≥85%**（2026-08 冒烟沉淀）：留白太多会像静态图。构图时先把 hero 区域定大，再用支持/装饰元素填满边角

## 全程动态原则（2026-08 冒烟沉淀）

分镜从开始到结束都不能有"静态图片感"：

1. **入场动画完成后立即接续微动效**，中间无静止窗口
2. **hero 图微动 = 整个分镜一次极慢缓动**（breathe: scale 1→1.07 覆盖全分镜，电影推镜感）。**仅 hero 图用慢缓动**；辅助/装饰元素用常规 yoyo 循环（sway/lift/pulse，周期 1.8-3.2s）
3. 元素入场错峰 0.35-0.45s，入场 settle 后 0.8s 微动接续——动态不间断
4. 画面覆盖不足时，用背景层（地图/报纸底纹/图表）+ 装饰（胶带/图钉/红绳）补足 85%
5. 禁止"全部入场后画面静止"——那等于 PPT

## 多图片层结构（用户核心要求，2026-08）

**一个分镜 = 多个独立图片元素层，不是"一张大图 + CSS 贴纸"**：

- **每拍 3-4 个独立图片层**（各自独立入场动画 + 微动）+ 3-4 个 CSS 装饰层
- hero 层（真实新闻图或 AI 元素）+ 2-3 个相关元素层（叙事关联，非随意堆砌）
- 素材策略（按内容判断）：
  - **真实新闻事件 → 真实新闻图作 img2img 风格参考**（image_path 传入），结合 VOX 拼贴风格提示词生成"保留真实内容 + 拼贴质感"的独立元素，不作为原图直接贴入；AI 元素作辅助层
  - 抽象数据 → AI 生成 VOX 风格元素或 matplotlib 图表
  - 装饰（胶带/图钉/印章/红绳/标签）→ CSS 纯渲染零成本
- 元素必须**叠压**（图章盖在图上、胶带跨接），不能平铺在中间
- hero 占视觉权重 ~60%，辅助层填满边角

## 动画节奏

- 每拍停留 **7-10s**，元素错峰入场：0.4-0.6s 间隔
- 入场完成后立即启动微动效（有限 repeat），画面保持活跃
- 板间交叉溶解 0.5s（奇偶 track 交替）

## 反模式

- ❌ 一个镜头只有 2-3 个元素 → 画面空，看不下去
- ❌ 所有元素堆在中央 → 没有构图
- ❌ 没有叠压关系 → 不像拼贴
- ❌ 没有微动效 → 元素落地后画面静止，像 PPT

## 语音驱动分镜规划（2026-08 用户确认，最高优先级）

**核心原则：scene_plan 用字数估算先行，TTS 推迟到 assets 阶段；若实测偏差 >5% 回到 scene_plan 重排。**

### 流程顺序（2026-08 修订：TTS 在 assets 阶段执行）

```
script 定稿
  → scene_plan（本阶段，时间戳 = 字数估算 4.7 字/秒）
  → assets 阶段（先 TTS 全段 → whisper 提取词级/句级时间戳 → 再生成图像）
  → 若 TTS 实测偏差 >5% → 回到 scene_plan 重排分镜
  → edit
  → compose
```

**为什么不在 scene_plan 前跑 TTS**：TTS 是 GPU 重活（IndexTTS2 本地 GPU 推理），Executive Lead 不应阻塞在重活上。让 scene_plan 先行，TTS 推迟到 assets 阶段统一执行，符合 OpenMontage 主/子 Agent 分工模式（Executive Lead 轻、Compute Worker 重）。

**字数估算的可靠性**：中文 4.7 字/秒是 IndexTTS2 实测基准，准确到 ±5%。若 TTS 实测偏差 >5%（如某段读得特别慢/快），scene_plan 需要重排——但这在绝大多数情况下不会发生。

### 分镜边界 = 语音段边界（不固定 10s）

- 每段语音 = 一个分镜，分镜时长 = 语音段时长 + 余量（约 0.5-1s 呼吸空间）
- 语音长就长一点，短就短一点，**总时长仍在目标 ±5% 内**（60s 目标 → 语音总长 + 余量 ≤ 60s）
- 严禁"6 分镜 × 固定 10s"硬切——那必然导致语音与画面错位

### 句子元素规划（每句 = 一个视觉元素）

- 句子/节拍长度基准见 `bilingual-spec.md §2`（en 5-8 词/拍；zh 8-14 字/拍按语义断句）
- **本阶段时间戳 = 字数估算（4.7 字/秒）**；whisper 真实时间戳在 assets 阶段提取，若偏差 >5% 回到本阶段重排
- **每个句子 → 一个独立视觉元素**（hero 图/标签/图章/大字）
- 元素清单从语音文本提取：语音提到的每个关键名词（2.4万亿、TOP2、7%、未来已来、Fable 5…）自动成为元素
- **动画时长 = 句长 × 0.8**（句子说完前动画完成，留 20% 停顿呼吸空间）
- 元素入场 = 句子开始 + 0.2s 缓冲
- **特别短的句子/语气词（<1s）忽略或并入相邻句**，不单独做元素

### 语义 → 动画映射表（semantic_family）

**中英双语语义表见 `bilingual-spec.md §12`**（zh：发布→drop、上涨→rise…；en：release→drop、surge→rise…）。按 `narration_language` 匹配语义列，family 值两语言共用：

| 语义（zh 示例） | family | 效果 |
|------|--------|------|
| 发布/推出/登场 | `drop` | 落下+弹跳 |
| 上涨/大涨/飙升 | `rise` | 上浮升起 |
| 震惊/震动业界 | `shake` | 抖动+冲击 |
| 排名/第二/第一 | `pop` | 缩放弹出 |
| 相当/超越/并肩 | `slide` | 并排滑入 |
| 规模/拥有/参数 | `grow` | 生长展开 |
| 增加/数百亿 | `pulse` | 脉冲放大 |
| 未来/悬念结尾 | `slap` | 重拍定格 |
| 短句/语气词 | `fade`（并入前句） | 轻淡入 |

### 多宫格参考图流程（2026-08 用户确认）

1. **先生成 6 分镜多宫格参考图**（2×3 布局，每格=该分镜最终完整拼贴效果），交用户确认"最终样子"
2. 用户确认后，**按参考图拆分为独立元素图**（每元素一张：单物体、纯色底 #D8C7A3、居中）
3. **组装时元素按参考图中的位置出现**（HyperFrames 中定位）
4. 文字类装饰（图章/标签/胶带/红线/图钉）→ **CSS 纯渲染，零成本**，不生成图片

### 元素契约字段（spec-driven，compose 唯一契约）

每个元素必须声明：

```json
{"id": "s5-7", "kind": "img|headline|stamp|tstrip|tape|pin",
 "src": "assets/xxx.png",            // img 类型
 "box": [left, top, width, height],  // 竖屏 1080x1920 坐标
 "rot": 角度, "z": z-index,
 "family": "drop|rise|shake|pop|slide|grow|pulse|slap|fade",
 "micro": "breathe|sway|lift|pulse|none",
 "sfx": "paper_slide|stamp_thud|tape_press|pin_click|paper_tap",
 "sync_sentence": "盘中涨幅超过7%，",   // 绑定语音句子（元素在该句出现）
 "sentence_start": 44.86,              // 句子开始时间（全局秒）
 "sentence_dur": 1.44}                 // 句子时长
```

### CSS 标签尺寸红线（2026-08 用户确认：标签过小不醒目）

- 竖屏 1080×1920 下：`headline` 主标题 ≥ 100px（核心数字 150-200px）、`stamp` 图章 ≥ 64px（高潮章 88-90px）、`tstrip` 标签条 ≥ 38-44px
- 边框加粗（stamp 5-7px double）、加白色描边/投影增强可读性
- 过小的文字标签在手机上不可读，宁可少而大，不可多而小

## 多层结构规划（2026-08 用户确认，scene_plan 阶段必须完成）

**每个分镜 = 4 层结构，在 scene_plan 中逐层设计，不是 compose 阶段临场决定：**

```
┌─────────────────────────────┐
│ L1 底图层（背景图 bg）        │ ← 主题纹理（报纸/坐标纸/地图/网格），低调不抢
│ L2 Hero 层（透明异形贴图）    │ ← 最大最明显，内容轮廓即形状
│ L3 元素层（透明异形贴图/CSS）  │ ← 随语音出现的数字/印章/标签
│ L4 CSS 装饰层（胶带/图钉/线） │ ← 零成本
└─────────────────────────────┘
```

### 每层设计要点

**L1 底图层（背景图）：**
- 每分镜 1 张背景底图（`bg_sN.png`），按分镜主题设计：报纸头版/坐标纸/榜单版面/档案纸/行情网格/航海地图
- 生成提示词：纹理描述 + "mostly empty negative space in the center, no objects, no text"（中心留白给 hero）
- 背景低调（低对比、muted 色调），是氛围不是主体

**L2 Hero 层（透明异形贴图）：**
- **hero 图必须透明底 PNG（内容轮廓即形状）**——不是矩形图，不是 CSS 蒙版裁出的几何形状
- 获取方式：AI 生成纯色底（#D8C7A3）单一主体 → PIL 色彩阈值抠透明 + bbox 裁剪
- hero 图分镜开始 0.3s 最先出现，画面最大最明显
- 无边框无蒙版，`drop-shadow` 投影产生分层感

**L3 元素层：**
- 内容元素（数字/印章/标签）随语音句子出现（入场 = 句开始 + 0.2s，时长 = 句长×0.8）
- 图片类元素同样透明底；文字类（印章/标签条）CSS 渲染

**L4 CSS 装饰层：** 胶带/图钉/红线，纯 CSS 零成本

### 元素契约字段扩展（spec-driven，compose 唯一契约）

每个元素必须声明：

```json
{"id": "s5-7", "kind": "img|headline|stamp|tstrip|tape|pin|bgimg",
 "src": "assets/xxx.png",            // img/bgimg 类型
 "box": [left, top, width, height],
 "rot": 角度, "z": z-index,
 "layer": "bg|hero|element|decor",   // 所属层（L1-L4）
 "family": "drop|rise|shake|pop|slide|grow|pulse|slap|fade",
 "micro": "breathe|sway|lift|pulse|none",
 "sfx": "paper_slide|stamp_thud|tape_press|pin_click|paper_tap",
 "sync_sentence": "盘中涨幅超过7%，",   // 绑定语音句子
 "sentence_start": 44.86,
 "sentence_dur": 1.44,
 "data_class": "real_data|real_content|creative|css",  // 数据真实性分类（proposal 继承）
 "data_source": "yfinance 9988.HK",    // 真实数据类必填
 "data_points": "+7.01% (125.20 vs 117.00)"}  // 关键数据点
```

### 数据真实性逐元素标记（scene_plan 阶段）

- 每个元素继承 proposal 的 `data_class` 分类
- **真实数据类元素在 scene_plan 中锁定数据来源 + 关键数据点**（如 K线 +7.01% / 参数 2400B / 排名 #2）
- 生成方式：`matplotlib 真实数据参照图 → img2img VOX 风格化 → 抠透明`
- 这是 compose 阶段的唯一数据契约——compose 不临场改数据

## 元素入场节奏设计（2026-08 沉淀，用户确认）

**规划元素时就要确定它的入场节奏，分三层，不是所有元素都跟语音：**

| 层 | 元素 | 入场时间 | 跟语音？ |
|---|---|---|---|
| 视觉骨架 | hero | `scene_start + 0.3s`（短场景 +0.2s）| ❌ 固定 |
| 视觉骨架 | l3 支撑图 | `scene_start + 1.2s`（短场景 +0.8s）| ❌ 固定 |
| 视觉骨架 | decor 装饰 | `scene_start + 2.0s` 起错峰 0.5s（短场景 +1.3s）| ❌ 固定 |
| 内容标签 | voice（数字/关键词）| 语音句子时间 + 0.2s | ✅ 跟语音 |

**三条红线（防"一闪就没"）：**
1. **短场景判定 `dur <= 7s`**：所有元素快速入场（hero 0.2 / l3 0.8 / voice 1.2 / decor 1.3），**绝不跟语音**——短场景语音句在末尾，跟语音必然一闪
2. **voice 可见时间 ≥2.5s**：`v_t = min(句子时间+0.2, end - 2.5)`
3. **所有入场 clamp**：`t + 动画时长 <= scene_end`，否则动画被截断 = 元素一闪

**为什么 hero 不跟语音**：whisper 句子时间戳常落在场景后段（最长可达场景末尾），hero 若绑语音会导致场景开场只有背景的空窗（用户多次反馈）。hero 是视觉锚点，必须开场即现。
