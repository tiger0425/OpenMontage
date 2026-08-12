# Vox 逐帧定格提示词规范（series-adapt）

面向 series-adapt 的 **AI 逐帧定格动画**图像生产规范：如何在本地 ComfyUI + Klein 工作流上，
保证"同一锚点、跨状态帧像素级稳定、无随机抽卡"。

配套文档：`vox-look-library.md`（图像 5 部分结构 / 视觉词库）、`vox-motion-library.md`（动效层）、
`vox-story-library.md`（叙事层）。由 `asset-director.md` 与未来逐帧 stage 引用。

> 本规范由 `series-adapt-stopmotion-prototype` 实测失败复盘沉淀而来。**它取代一切"全画面重绘
> 保一致"的经验直觉。** 不再依赖"prompt 写 Keep same / anchor + 上帧双参考"来对抗错位。

## 0. 核心原则（两条不可破）

1. **锚点像素不可变。** 锚点图一旦验收，后续所有状态帧必须让模型只重绘变化区域，
   **不允许模型重新解释整幅画面**。任何"整图 I2I / 整图 dual-reference"方案都默认否决。
2. **变化越局部，越要用 mask。** 电线、点火、爆破、烟雾、缺口都是局部区域变化；
   仓库已有的 inpaint / mask-redraw 工作流是唯一被验证的稳定路径。

### 为什么之前的方案错位（复盘，避免重犯）

| 现象 | 根因 |
|---|---|
| 城门/门洞/透视地面跨帧错位 | 全画面 `Klein-img2image-dual-reference` 让模型对整幅图重新采样，即使参考锚点也扛不住像素级约束 |
| 爆破区域偏移、画布漂移 | prompt 只描述"添加 X"没有几何锚定；模型自由发挥布局 |
| 同构图却反复微变 | 状态 delta 用自然语言描述，模型对"多大变化"无约束 |
| 多次重试/换 seed 才接近 | 用"抽卡式重试"掩盖 prompt 无规范，成本与不可复现并存 |

**结论：用 mask 锁定"哪里可以变"，用 prompt 只描述"mask 内变成什么"。**

## 1. Workflow 选型表（必须先选对 workflow，再谈 prompt）

| 用途 | Workflow | output_node | 说明 |
|---|---|---|---|
| **锚点 / 首帧 / 蓝图** | `Klein-txt2image.json` | `78` | 固定 `115:108` seed；一次性验收，之后不改 |
| **局部状态变化（推荐默认）** | `Klein-img2image-inpaint.json` | `9` | `SetLatentNoiseMask` 锁定 mask 外像素，真 inpaint |
| **局部重绘（强控制变体）** | `Klein-img2image-mask-redraw.json` | `9` | 经 `Flux2KleinMaskRefController`，可调 `strength`/`feather` |
| **全局风格化（仅锚点生成阶段）** | `Klein-img2image.json` | `9` | 参考图重绘用；**不得用于逐帧状态序列** |
| ~~全画面双参考递推~~ | ~~`Klein-img2image-dual-reference.json`~~ | ~~`9`~~ | **弃用**：实测跨帧错位不可控 |

### 关键约束（写进任何调用）

- **mask 必须是黑白通道图，黑 = 要重绘的区域**（与 `Klein-img2image-mask-redraw.json`
  的 `LoadImageMask` `channel: red`、`invert_mask: false` 契约一致）。
- mask 尺寸必须与锚点/输出一致（1360×768）；mask 由外部生成并随调用上传，
  不通过 prompt 描述"变化区域在哪"。
- mask 越小越稳：只圈变化发生的物理位置（电线沿墙区域 / 爆破点周围），
  不要在 mask 里塞整面墙。
- 每次只变一个区域：一个状态帧只允许一个 mask + 一个 delta。
  多个同时变化 → 拆成多个状态帧。

## 2. 调用规范（comfyui_image / image_selector）

### 入参

| 参数 | 值 | 说明 |
|---|---|---|
| `workflow_path` | `tools/_comfyui/workflows/Klein-img2image-inpaint.json` | 或 mask-redraw |
| `output_node` | `9` | |
| `reference_image_path` | 锚点/上一已验收状态图 | 作为 `76` 锚点 |
| `reference_image_path_2` | 本次 mask 图 | 作为 `78` 遮罩上传 |
| `workflow_overrides["76"]["image"]` | `"<UPLOADED_IMAGE_1>"` | 注入锚点 |
| `workflow_overrides["78"]["image"]` | `"<UPLOADED_IMAGE_2>"` | 注入 mask |
| `workflow_overrides["114:113"]["text"]` | 见 §3 状态增量模板 | mask 内变化描述 |
| `workflow_overrides["114:112"]["noise_seed"]` | 固定 seed | 每状态独立固定，可复现 |
| `workflow_name` / `workflow_model` | 如实填写 | 进入 provenance |

> 与 `image_selector` 的 custom-workflow 透传键一致：`reference_image_path`、
> `reference_image_path_2`、`workflow_overrides`、`workflow_path`、`output_node` 均已透传。

### 质量门禁（每帧必过，不满足即阻断，不做随机重试）

- [ ] 输出尺寸 == 锚点尺寸（1360×768）
- [ ] 遮罩外像素与锚点 diff 为 0（或极小）——**这是"像素级稳定"的直接证据**
- [ ] 遮罩内变化符合 delta 描述（用 MiniMax-M3 对"锚点 vs 状态帧"做 diff 检查）
- [ ] 无新人物 / 新建筑 / 布局漂移
- [ ] workflow hash、seed、mask 路径全部落 ledger
- [ ] 任一帧失败 → 整批 BLOCKED，记录失败原因，**不换 seed 重试**

## 3. 状态增量提示词模板（mask 内只写变化）

```
In the masked area only: {具体变化，一句话，带几何/量级约束}.
Everything outside the mask stays exactly as in the reference image.
Same medium, halftone paper texture, lighting and palette as the rest of the collage.
```

**量级约束词（写进 prompt，避免"爆炸过大"类失控）：**

| 目标 | 约束写法 |
|---|---|
| 小变化 | `small / tiny / localized`、`below the roofline`、`within the right third` |
| 范围锁定 | `no debris above the wall`、`no smoke above the roof`、`no left-side change` |
| 主体保护 | `central gate and tower fully readable`、`preserve the same camera` |
| 防人物/新建筑 | `no people, no new buildings`（mask 只圈变化区时通常自然满足） |

**示例（爆破局部状态）**：
```
In the masked area only: a localized demolition flash and compact smoke at the right
wall base, small debris low on the ground, all fire below the roofline.
Everything outside the mask stays exactly as in the reference image.
Same halftone paper texture, lighting and palette as the rest of the collage.
```

## 4. 状态序列工程规范（工业化前提）

1. **锚点先行验收**：`Klein-txt2image` 生成 → 人工/MiniMax 验收 → 冻结锚点。
2. **每状态 = 一个 mask + 一个 delta + 一个固定 seed**，一次性生成，不自动重试。
3. **ledger 记录**：state、seed、mask 路径、reference、workflow hash、输出路径、
   diff 校验结果。缺任一字段 = 该状态不可接受。
4. **任何"重新生成"都必须是显式人工决定**（改 mask / 改 delta 措辞），
   绝不静默换 seed 或重复同 prompt。
5. 状态帧全部验收后，才进入 HyperFrames 合成（30fps 硬切 hold）。

## 5. 反模式清单（这些做法已证明失败，禁止）

- ❌ 全画面 dual-reference 递推保一致（错位，已弃用）
- ❌ 用自然语言让模型"保持相同构图"而不给 mask（模型不保证像素）
- ❌ 变化区域靠 prompt 描述而非 mask 指定（模型自由布局）
- ❌ 爆炸/大事件用一句话让模型"自由发挥"（量级失控，需量级约束词）
- ❌ 失败后随机换 seed 重试（掩盖 prompt 缺陷，破坏可复现）
- ❌ 多变化同帧一次出（应拆状态帧）
- ❌ 跳过锚点验收直接进序列

## 6. 引用与更新

- 上游图像结构/词库：`vox-look-library.md`
- 动效节奏：`vox-motion-library.md`；Vox 12fps 硬切感由 `hold 2-3 帧` 实现，
  渲染仍 30fps（见 `compose-director.md` L-045）
- 工作流文件：`tools/_comfyui/workflows/Klein-img2image-inpaint.json`、
  `Klein-img2image-mask-redraw.json`
- 本规范任何新的失败/成功经验，追加到"失败复盘"或反模式清单，并同步 `known-issues.md`。
