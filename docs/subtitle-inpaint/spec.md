# 硬字幕去除 + 新语言字幕重烧 · 架构规格

> 状态：**可据此开工**（wayfinder 地图 #33 的终点产物）
> 上游：3 份研究（`research-vsr-principles.md` / `research-detection-masking.md` / `research-inpainting.md`）+ 5 张决策票（#34–#38）
> 范围：为 OpenMontage 的 `auto-dub` 流水线新增「去字幕 → 换字幕」能力的技术规格。**本规格不实现任何代码**，只锚定「复用 vs 自研边界、模块接口、流水线嵌入、GPU 调度、失败处理」。

---

## 1. 目标与非目标

### 1.1 目标

搬运/翻译场景：去掉原视频（通常英文）的**硬字幕**，再烧新语言（中文）字幕。**精度优先，可接受慢**。本地单机 NVIDIA GPU（与 auto-dub 的 VoxCPM TTS 同机）。

### 1.2 非目标（明确不做 / 降级）

| 项 | 处置 |
|---|---|
| 多行字幕 / logo / 动态水印 / 闪烁字幕 / 重叠前景 | **标注降级**，规格只承诺「常规单行硬字幕」高质量处理 |
| 自建检测器（DBNet/EAST/CRAFT/TransDETR） | 不做（对视频字幕无预训练优势，成本高收益低） |
| Mask-Free 端到端去字幕（SEDiT/CLEAR/EVE） | v1 不引入（研究级） |
| 更高质量输出编码（ProRes/更低 CRF） | 不做（VSR CRF18 已视觉近无损） |
| auto-subtitle（无 GPU 轻量路线） | 暂不接，先只服务 auto-dub |

---

## 2. 决定汇总（Destination 决策栈）

| # | 决策 | 结论 |
|---|---|---|
| D1 | 补全引擎 | **ProPainter 主** + **LaMa/ffmpeg 轻量双轨**（#36） |
| D2 | 字幕检测 | **复用 VSR 后端 PaddleOCR-DBNet(PP-OCRv5)** + 矩形遮罩 + 时序分组（#35） |
| D3 | 遮罩生成 | **自研**：按检测框/笔画宽自适应 pad + MORPH_CLOSE 填孔 + 保持二值（#37） |
| D4 | 字幕 vs 场景文字判别 | **自研**：ROI 门控 + 时序持久化投票 + OCR-音频转写对齐（#37）；**三元化**：裸字幕 / 底卡 / 场景文字（#39） |
| D5 | 交互模式 | **自研**：候选图(PNG 带序号) + 勾选清单 `.md`，无 UI（#37） |
| D6 | 输出编码 | **复用** VSR libx264 CRF18/preset fast/yuv420p + 音轨 copy（#37） |
| D7 | 替换字幕文本 | **复用**翻译阶段供给（#37） |
| D8 | 流水线嵌入 | 新 stage，插在**转录/翻译后、烧字幕前**；先只 auto-dub（#38） |
| D9 | GPU 调度 | **严格串行 + GPU 锁**（ProPainter vs VoxCPM 分时互斥）（#38） |
| D10 | 失败处理 | `awaiting_review` 挂起，可逐处跳过/强制（#38） |
| D11 | 中间产物 | 保存去字幕视频 + 候选清单/遮罩，可复用（#38） |
| D12 | 坐标元数据 | JSON 中间产物 `subtitle_metadata.json`：bbox 归一化+像素双存、帧号+时间码双写、文本+风格+底卡主色；仅 replace 块带 style（#40） |

---

## 3. 技术底座（复用 VSR 的确认事实）

> 全部来源：`docs/subtitle-inpaint/research-vsr-principles.md`（源码行号级核对，VSR `main` 分支内部版本 1.4.0）

- **VSR 不是单一模型**，而是「检测 → mask → 视频修复 → ffmpeg 合成」流水线，可挂 5 种算法（`sttn-auto` 默认 / `sttn-det` / `lama` / `propainter` / `opencv`），入口 `backend/main.py:335-401`。
- **检测 = 自动**：PaddleOCR `TextDetection`（PP-OCRv5，server 默认 / mobile），只取文本框、不做文字识别；手选区域是可选的约束。
- **mask = 检测框画实心矩形 + `subtitleAreaDeviationPixel`(默认 10px) 膨胀**，非像素二值化。
- **输出「无损」= 尺寸不变 + libx264 CRF18/preset fast/yuv420p**（视觉近无损，非逐位）；音频真无损 copy。
- **ProPainter 显存硬约束**：720p @80 帧 ≈ 25GB，@50 ≈ 19GB；720×480 @80 ≈ 8GB（`config.py:98-99` + 官方 README）。

### VSR 已知短板（本项目要「更好」的地方）

| 短板 | VSR issue | 本项目对策 |
|---|---|---|
| 带内移动/重叠文字被误补（毁源） | #176 | 自研判别层（D4） |
| 固定 10px 全宽矩形带 → 吃内容/留残边 | #213 残影 / #194 模糊 | 自研自适应遮罩（D3） |
| 只内置中文检测模型 | #170 | 复用但扩展英文脚本检测 |

---

## 4. 模块规格

### 4.1 复用层（不改，直接调用 VSR 后端能力）

- **检测**：`SubtitleDetect`（PaddleOCR PP-OCRv5 det）→ 输出字幕候选框 `(xmin,xmax,ymin,ymax)`。
- **时序分组**：采样(`SAMPLE_STEP`，≈≥8帧/秒) + 插值 + `unify_regions`(±20px) + 分镜切段 + 前后扩展(±3帧)。
- **编码合成**：`FFmpegVideoWriter`（CRF18/preset fast/yuv420p）+ 音轨 copy。

### 4.2 自研层（本项目独有价值，即差异化锚点）

1. **自适应遮罩膨胀**（替代 VSR 固定 10px）：
   - 先 pad 检测框（下缘额外加 descender 余量）→ 再膨胀，膨胀量按**笔画宽**（≈1px + 0.25–0.5×笔画宽，非字号）自适应；
   - `MORPH_CLOSE` 填字形内部计数孔；
   - 保持 mask 二值（深模型期望硬边界）；
   - **同一字幕事件的每帧 mask 必须同一 footprint**（ProPainter 流传播要求 mast 时序一致）。

2. **字幕 vs 场景文字判别（三元）**：
   - 三层信号：ROI 门控（底部带先验）→ 时序持久化投票（字幕屏幕锁定、跨镜存续；场景文字随相机动）→ OCR-音频转写对齐（字幕文本 = 对白）。
   - **三元分类**：`裸字幕` / `底卡` / `场景文字`。底卡判别信号 = 颜色同质性(HSV/颜色距离聚类) + 连通域面积/矩形度 + 规则边缘先验。
   - **只把「确定是字幕/底卡」的框入遮罩**，场景文字（招牌/屏幕/衣服印花）一律不入。底卡误判双向都毁源（当场景文字→漏删底板；场景文字当底卡→误抹画面内真实卡牌）。

3. **无 UI 交互（候选图 + 勾选清单）**：
   - Agent 生成一张**带序号标注的全景候选图**（叠出所有检测到的字幕/文字区域）；
   - 同目录生成 `subtitle_candidates.md` 勾选清单，每候选一行，人填三态：`留` / `消` / `替换`；
   - Agent 解析 `.md` 里的序号 + 三态回写。
   - **底卡 = 整块一个候选**（一个序号），不拆逐字。

4. **带底板文字卡片（不规则底卡）处理分支**（#39）：
   - **去除策略** = 整块底板抠掉（遮罩 = 整个底板轮廓），**不是**「背景色覆盖」、**不是**「保留底板只换字」。
   - **轮廓提取** = 纯 CV：连通域 + 颜色同质性，**不引入实例分割模型**（前提：底卡多为连通实心色块 + 允许轻微痕迹）。
   - **补全选型** = 按背景动静：静止 → 插值/扩展(ffmpeg/CV)；运动 → ProPainter（与 §5 双轨一致）。
   - **相对难度的关键洞察**：底卡是大面积连通实心色块，比裸字的细笔画**更好补**，是「简单路径」，应优先路由而非畏难。

#### 底卡处理小结（开工速查）

**一句话口诀**：*底卡不是「用底色盖字」，是「整块当遮罩抠掉、补背后的画面」——而且它比裸字更好补。*

```
                  检测到文字区域
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    [颜色同质 + 连通域大 + 规则边缘]
        │
      「底卡」          「裸字幕」      「场景文字」
        │               │               │
   整块一个候选      逐字/逐条候选     一律不入遮罩
        │               │               (保留，不处理)
   遮罩=底板轮廓    遮罩=自适应膨胀
        │               │
   按背景动静路由       │
   ┌────┴────┐          │
   ▼         ▼          ▼
 静止      运动       补全(§5 双轨)
   │         │
 插值/扩展  ProPainter
   └────┬────┘
        ▼
   补背后的画面（非盖底色）
```

**三条铁律**：
1. **整块抠，不盖色**——遮罩永远是「底板轮廓」这块实心区域，补的是「底板遮住的画面」，不是往字上刷底色。
2. **优先路由**——底卡比裸字好补，检测到连通大色块就优先走「插值/ProPainter 整块补」这条简单路径，别当难题。
3. **双向防误判**——底卡当场景文字=漏删底板；场景文字当底卡=误抹画面内真实卡牌。两个方向都毁源，靠颜色同质性 + 面积/矩形度硬门控兜底。

---

## 5. 流水线嵌入（auto-dub 新 stage）

```
download → transcribe → translate →【去字幕(新)】→ burn_subtitle → archive
                                              ↑硬依赖转录(判别用OCR-音频对齐)
```

- **形态**：新 stage，有自己的 stage director + 输入输出契约 + checkpoint。
- **checkpoint 语义**：
  - 正常：去字幕阶段生成候选图 + `subtitle_candidates.md`，checkpoint → `awaiting_human`；
  - 人编辑 `.md`（留/消/替换）后，agent 解析序号回写，checkpoint → `completed`，进入烧字幕；
  - 与现有 `speaker_review.md`/`translation_review.md` → `approve-review` 同构。
- **重算力归属**：去字幕（ProPainter inpainting）是重算力 → 走 **Compute Worker**（`run-heavy`），主 Agent 不阻塞。

### 5.1 GPU 调度（严格串行 + GPU 锁）

- ProPainter（720p@80帧≈25GB）与 VoxCPM TTS（8–16GB）**同机必冲突**，必须分时。
- 复用 `lib/gpu_lock.py`：进入去字幕推理前 acquire，跑完 release；VoxCPM TTS 期间互相等待。
- 建议时序：**先 TTS（音频）→ 再去字幕（视频）**，或反序但严格不重叠。

### 5.2 失败处理

去字幕遇到「检测不到 / 判别不清 / 勾选无解」→ 置 `awaiting_review`（非失败），人在 `.md` 里对每处决定：**跳过（保留原字幕）** 或 **强制消**。

### 5.3 中间产物复用

保存：去字幕后的视频 + 候选清单 + 遮罩 + **坐标元数据 JSON**。人批准后可重复烧不同语言字幕**不重补**、**不重定位**。

#### 5.3.1 坐标元数据中间产物（供原坐标重烧，D12 / #40）

去字幕阶段精确定位出的坐标/样式数据，若用完即丢，后续「原坐标重烧硬字幕/文字卡片」就只能重新检测——而**补全后原底板已消失、检测已不可得**。因此必须落成 JSON 中间产物。

- **载体**：`subtitle_metadata.json`，与去字幕视频/候选清单/遮罩同目录。
- **用途边界**：**按需使用**（非强依赖烧字幕阶段）；只有 `decision == "replace"` 的块才携带完整 `style` 供重烧。
- **坐标空间**：归一化 `bbox_norm` [0,1]（主，分辨率无关） + 像素 `bbox_px`（兼容）双存。
- **时间**：帧号 + 时间码(秒)双写，`segment_id` 引用转录段对齐。
- **与 `.md` 同源**：JSON 块 `id` ↔ 候选清单序号，自增不漂移；agent 解析 `.md` 回写时按 `id` 对齐。

```json
{
  "id": "c023",
  "decision": "replace",               // keep | remove | replace
  "type": "subtitle",                  // subtitle | card
  "bbox_norm": [0.08, 0.86, 0.84, 0.09],
  "bbox_px": [153, 927, 1613, 97],
  "time": {
    "start_frame": 412, "end_frame": 500,
    "start_sec": 13.73, "end_sec": 16.67,
    "segment_id": "u0"
  },
  "text": { "original": "the original line", "replacement": "替换后的中文" },
  "style": {
    "font_size_ratio": 0.045,          // 必填：相对帧高
    "color": "#FFFFFF",                // 必填
    "align": "center",                 // 必填：center | left | right
    "font_family": null,               // 选填：烧录时模板/默认补
    "outline": null,                   // 选填：描边
    "shadow": null,                    // 选填：阴影
    "card": {                          // 仅 type=card；bg_color = 底卡主色(#39)
      "shape": "rect",
      "bg_color": "#000000B3"
    }
  }
}
```

**要点**：
- `type=card` 的块的 `bbox_norm`/`bbox_px` 是**整个底板轮廓**（#39），`style.card.bg_color` 存底卡主色供重烧还原底板。
- `keep`/`remove` 块只留 `id/decision/type/bbox/time/text.original`，无 `style`（不再重烧）。
- 底卡坐标/底色**必须存**：补全后原底板消失，错过即不可恢复，只能人肉对位。


---

## 6. 关键未决（给下一个 effort 的 fog）

> 这些不在本规格承诺内，未来若要推进需另开地图/票：

- **质量验收门槛**：什么算「干净」（PSNR/SSIM/主观 MOS/漏检字数），缺实测基线。
- **GPU 时延画像**：ProPainter 单分钟视频的真实 GPU 时延（缺实测，仅有 issue 区间）。
- **失败模式分类**：哪些视频/场景 100% 失败、哪些可救（依赖实测）。

---

## 7. 附：研究来源

- `docs/subtitle-inpaint/research-vsr-principles.md` — VSR 端到端原理（#34）
- `docs/subtitle-inpaint/research-detection-masking.md` — 检测/遮罩深潜（#35）
- `docs/subtitle-inpaint/research-inpainting.md` — 补全选型（#36）

关键一手来源：VSR 源码（`backend/*.py` 行号，缓存 `_tmp/vsr/*`）；STTN(ECCV2020 arXiv:2007.10247)；ProPainter(ICCV2023 arXiv:2309.03897)；LaMa(WACV2022)；VSR issues #108/#178/#236/#232/#220/#204/#194/#48/#10/#213/#78/#96/#176/#170。
