# Vox Form Contract — 形态一致性契约（series-adapt）

解决**蓝图与元素不一致**问题：蓝图中斜置 / 半身 / 被遮挡的形态，如何落到元素生成与
组合阶段，保证"元素长得和蓝图画的一样"。
与 `vox-look-library.md`（视觉）、`vox-motion-library.md`（动效）、
`vox-layout-library.md`（布局）配套；由 `asset-director.md`（元素生成）与
`compose-director.md`（GSAP 装配）引用。

> 本契约服务 series-adapt 的两条硬约束：
> 1. **真实帧派生**（传记真实性）——元素资产必须从源视频参考帧 img2img 派生，非纯生成
> 2. **元素资产干净**（合成确定性）——独立元素 PNG 保持完整、正面、无遮挡，
>    所有形态（斜/裁剪/遮挡）在组合阶段用 CSS/GSAP 实现

## 0. 核心原则（两条不可破）

1. **元素资产保持"出厂干净态"。** 独立元素 PNG 一律完整主体、正面朝向、无遮挡、
   无预倾斜。模型不擅长画"被切掉一半的坦克"或"被纸片盖住半张脸的人"——
   任何形态必须在组合阶段叠加实现，不进生成 prompt。
2. **形态是 CSS/GSAP 的职责，不是生图的职责。** 斜 → `transform: rotate`；
   裁剪 → `overflow: hidden` 容器；遮挡 → 前置元素 z 叠压。生成阶段只保证主体本身清晰。

### 为什么不能在生成阶段画形态（复盘，避免重犯）

| 想做 | 生成阶段硬画 | 组合阶段实现 |
|---|---|---|
| 斜置主体 | img2img prompt 写 "rotated 30°" → 模型画歪/透视崩 | `rotate()` 精确任意角度 |
| 半身裁剪 | prompt 写 "half body visible" → 模型自由裁切位置 | 容器 `overflow:hidden` + 精确裁剪区域 |
| 被遮挡 | prompt 写 "partly covered by tape" → 遮挡物位置失控/糊脸 | 前置元素 z 更高，叠压位置精确 |
| 边缘融入 | prompt 写 "blending into paper" → 边缘糊，抠图失败 | 元素外留透明，由 CSS 阴影/叠压营造 |

**结论：生成阶段只生成干净主体，形态全部后置到合成。**

## 1. 形态契约字段（scene_plan 落库）

每个元素在 `box/rot/z` 之外补充形态字段（schema 用 `form` 对象，可含于 `elements[]`）：

```json
{
  "element_id": "s01e02",
  "kind": "img",
  "box": [30, 20, 40, 60],
  "rot": -2,
  "z": 3,
  "form": {
    "source_region": [x, y, w, h],      // 从真实参考帧裁剪的区域（px，对应 box）
    "crop_style": "none | partial | bleed",  // none=完整主体 / partial=半身裁切 / bleed=出血满幅
    "occlusion": {                        // 该元素被什么叠压（可空）
      "by": "decor_tape_s01e02",
      "region": [left, top, w, h]
    }
  },
  "family": "drop",
  "micro": "sway",
  "sfx": "paper_slide"
}
```

**验收**：`form.source_region` 必须指向真实参考帧的一个已确认区域（asset-director 用
MiniMax-M3 视觉确认主体在其中），否则该元素 BLOCKED。

## 2. 元素生成阶段（asset-director 执行）

### 2.1 真实帧裁剪（source_region → 主体）

1. 从源视频参考帧按 `form.source_region` 裁剪出主体区域
2. 用该裁剪图作为 img2img 参考，prompt 必须带 `Keep the exact same [tank/person]
   from the reference photo`（L-024/era/ethnity 约束不变）
3. 输出**完整主体**：即使 `crop_style=partial`，生成时仍保留完整主体（不裁），
   半身效果由组合阶段的裁剪容器实现
4. 独立元素输出统一 `solid flat tan` 底 → PIL 抠透明（vox-paper-collage 已验证路径）

### 2.2 禁止进 prompt 的形态词（红线）

- ❌ 任何角度词（rotated / tilted / at an angle）——斜置走 CSS
- ❌ 任何裁切词（cropped / half visible / cut off）——裁剪走容器
- ❌ 任何遮挡词（covered / partly hidden / behind）——遮挡走 z 叠压
- ❌ 任何"融入背景"词（blending / merging into paper）——破坏抠图

### 2.3 人脸保护（继承 K-04）

- 人物元素：prompt 禁止 label（标签走 HTML 叠加）；脸必须干净完整
- `occlusion` 若覆盖到脸部区域 → 视觉校验拒绝（前置装饰不得盖脸）

## 3. 组合阶段（compose-director 执行）

形态按契约字段逐项装配，不临场发挥：

| 契约字段 | CSS/GSAP 实现 | 说明 |
|---|---|---|
| `rot` | `transform: rotate(rot deg)` | 斜置在此实现，非生成 |
| `crop_style=partial` | 父容器 `overflow:hidden` + 子元素定位到 `source_region` 裁剪窗口 | 半身效果精确可控 |
| `crop_style=bleed` | 元素宽 > 容器（如 120%），`object-fit: cover` | 满幅出血，边缘无白缝 |
| `occlusion.region` | 前置装饰元素（z 更高）落在该 region，`position:absolute` 精确叠压 | 遮挡位置精确 |
| 边缘融入 | 元素自带透明边缘 + drop-shadow；叠压处由前置元素自然遮盖 | 不额外糊边 |

**组合校验（FINAL RULE 延伸）**：装配后抽帧，主体形态与蓝图一致——
斜角 ≈ `rot`、半身裁剪窗口 = `source_region`、遮挡位置 = `occlusion.region`。
任一不符 → 回 compose 调整，不做随机重排。

## 4. 形态与 layout_intent 的配合

- `compare`（对比面板）：两主体均 `crop_style=partial`，各自容器裁剪 → 对称半身对比
- `hero`（主体展示）：`crop_style=none`，完整主体 + 小 rot（≤3°）
- `sequence`（时序条带）：节点元素 `occlusion` 指向红绳/图钉装饰（z 叠压），
  体现"钉在时间轴上"
- `change_zone`（变化区）：变化区标记元素 `occlusion` 指向主体边缘，精确指向变化点

## 5. 与 mask/inpaint 的关系（vox-stopmotion-prompt-spec 配套）

- 本契约管**元素资产**（独立 PNG，静态形态）
- mask/inpaint 管**局部状态变化**（同一元素随时间的状态帧，如爆破/点火）
- 两者正交：先按形态契约生成干净元素资产并冻结 → 对需要状态变化的元素，
  用 `vox-stopmotion-prompt-spec.md` 的 mask/inpaint 生成状态帧 → 组合阶段按
  layout 契约做元素级切换/硬切

## 6. 词表（copy-paste）

```
FORM: 元素资产保持干净态（完整/正面/无遮挡）；斜=css rotate / 裁=overflow容器 / 遮挡=z叠压
SOURCE: source_region 必须指向真实参考帧已确认区域（视觉校验），否则 BLOCKED
PROMPT: 禁角度/裁切/遮挡/融入背景词；真实主体一律 keep-exact-same
COMPOSE: rot→rotate / partial→overflow+source_region窗口 / bleed→120%+cover / occlusion→z叠压
RULE: 生成阶段只出干净主体，形态全部后置到合成；装配后抽帧校验形态一致
```
