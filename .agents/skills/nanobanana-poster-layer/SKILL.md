# 海报图层拆分 · Nano Banana 版（Nano Banana Poster Layer）

将海报或营销参考图拆分为完整、可独立编辑的全画布图层。适用于主体抠图、遮挡区域修复、基于原图证据的图形/UI 拆分、绿幕图层准备和重新合成。

> 由 `xiongrubing335100-beep/poster-layer`（Lovart Poster Layering v3.1）改造为适配 Google Nano Banana（Gemini 原生图像模型）的版本。Nano Banana 是对话式编辑模型，与 poster-layer 原版依赖的 `image_gen`（Codex）行为不同——用多轮编辑 + 源图权威保持，而非一次生成一个候选。

## 核心原则

- 每个图层保留原始画布尺寸与坐标。
- 仅补全结构明确的遮挡区域；锁定可见角色、文字、Logo 和背景锚点。
- 标题、日期、CTA、Logo、图标和前景特效按独立编辑需求拆分。
- 每层一次编辑请求；不自动重试。重试需用户明确指令（如"重试 03 层"）。
- 文字突变、位置漂移、角色重绘、错误解剖、未见图形效果或背景重绘会被拒绝，不交付。

## 与 Nano Banana 适配的关键差异

| 维度 | 原版（image_gen 一次生成） | Nano Banana 版 |
|---|---|---|
| 生成方式 | 每层一次独立生成 | **对话式多轮编辑**：同一会话内连续"去掉某层" |
| 源图权威 | prompt 里声明"source is only authority" | **上传源图作为输入参考**，编辑时引用它 |
| 画布保持 | prompt 强制原尺寸 | 以源图输入，**输出默认匹配源图尺寸** |
| 遮挡修复 | repair envelope 描述 | 每轮编辑声明"只修这个区域，其他锁定" |
| 透明区 | 绿幕 #00FF00 | Nano Banana 支持**透明背景（alpha）**或绿幕，按需选 |

## 输入

- 源海报 PNG/JPG（上传为唯一视觉权威）
- `layer_plan`（可选，预先规划的分层清单；缺省则先规划）

## 执行契约

```text
inspect → evidence map → independent-layer plan → one edit per layer
→ source comparison → accept/reject → normalize → deliver
```

### 1. Inspect & Plan（检查与规划）

1. 记录源图真实尺寸、宽高比、路径。
2. 建立 front-to-back 图层所有权图（前到后编号，`layer_index` 从 1 前景到 N 背景）。
3. 每个图形支撑组件（阴影/描边/发光/衬底）必须记录**源图证据**（形状、颜色、边缘行为、位置、属主）。证据缺失或含糊 → 不生成该组件。
4. 标题、日期/CTA、品牌标识、图标、图形特效按**独立可动性**拆分，不按便利性。
5. 每层声明：`asset_role`、`occludes`、`occluded_by`、`source_evidence`、`support_components`、`ui_independence`、`repair_envelope`、`locked_visible_anchors`、`completion_required`、`completion_regions`、`risk_level`。
6. 合成从最大 index 到 1（先底后顶）。

### 2. 每层一次编辑（Nano Banana 对话）

对每个 `PENDING` 层，在**同一对话会话**中发起一轮编辑：

```text
以输入的源图作为唯一视觉权威。

第 N 层：[层名]。资产角色：[asset_role]。位置：[position]。
只移除：[要移走的前景层清单]。
保持这些源图可见锚点不变：[locked_visible_anchors]。
只补全这个修复包络：[repair_envelope]，依据这些锚点：[preserve_anchors]。
排除：[excluded_content]。

保持所有锁定内容的几何、身份、颜色、材质、位置、裁剪完全忠实于源图。
不要移动、重裁、重缩放、重设计、重着色、美化、模糊或重风格化任何锁定内容。
这是唯一请求的这一层。输出完整源图画布尺寸。
```

**Nano Banana 特有写法**（对话式）：
- 第一层编辑后，后续层用"在上一步结果基础上，把刚才去掉的 X 恢复为源图样子，再去掉 Y"——但**始终以源图为权威**，必要时重新引用源图。
- 每轮编辑都要**重申锁定锚点清单**（Nano Banana 多轮会漂移，重述是必要的）。
- 透明需求：若该层用于合成，请求"保留透明背景（alpha 通道）"；若用于绿幕，请求"透明区用纯绿 #00FF00"。

### 3. 验收门（Release Gate）

逐层对比候选与源图，命中以下任一条件即拒绝（不自动重试）：

- `UNSUPPORTED_GRAPHIC_EFFECT`：凭空出现源图没有的黑底板/笔刷/衬底/阴影/发光/挤出/装饰。
- `UI_BUNDLING_ERROR`：可独立移动的徽章/CTA/日期/Logo/图标被并进别的层。
- `VISIBLE_ANCHOR_MUTATION`：锁定的源图可见特征几何/身份/颜色/材质/位置/裁剪变了。
- `WHOLE_ASSET_REGENERATION`：修复明显重绘了比 repair envelope 更大的区域。
- `REPAIR_ENVELOPE_EXCEEDED`：生成的修复超出声明的包络/接缝带。
- `COMPLETION_MISSING`：声明的被遮挡区域留空、被抠掉或含移除的遮挡物。
- `ANATOMY_OR_STRUCTURE_BROKEN`：人/手/肢体/道具/建筑/产品几何不合理。
- `TEXT_OR_LOGO_MUTATED`：措辞、字形、Logo 结构、层级或位置变了。
- `BACKGROUND_LAYOUT_DRIFT`：可见透视、地平线、建筑线、图案、结构、颜色关系漂移。
- `OCCLUDER_OWNERSHIP_ERROR` / `EFFECT_CONTINUITY_BROKEN` / `FOREIGN_CONTENT_LEAK` / `REGISTRATION_UNCERTAIN` / `CANVAS_OR_GREEN_FIELD_INVALID`。

仅当无上述失败且存在艺术偏好取舍时，标记 `NEEDS_USER_REVIEW`。

### 4. 交付

- 每个通过的层存为 `layers/layer_<index>_<slug>.png`（完整画布 + alpha 或绿幕）。
- 生成 `layer_manifest.json` 记录每层状态。
- 重组审计：将各层从大到小叠加，确认重建源图无重复对象、无泄漏 UI、无发明特效。

## 合成模式参考（Nano Banana prompt 用语）

| 模式 | 适用 | prompt 要点 |
|---|---|---|
| full_asset_completion | 人物/产品/道具/实心装饰 | 补全隐藏的连续结构，锁定脸/发/手/服装接缝/材料锚点；禁止整件重绘 |
| graphic_completion | 标题/文字/Logo/UI/图标 | 保持确切措辞与布局；只含证据支撑组件；不发明衬底/阴影 |
| effect_completion | 丝带/光束/发光/粒子/烟/影 | 只重连观察到的效果轨迹与范围；不增加效果量 |
| background_completion | 前景后场景 | 继续被遮挡的场景，保持可见几何/透视/母题/色调/锚点 |

## 关键禁忌（Nano Banana 版特有）

- Nano Banana 是对话模型，多轮编辑**必然累积漂移** → 每轮重述锁定锚点；漂移扩大时**从上一版被接受图重启**，不要修坏掉的衍生图。
- 文字：先冻结批准的文案，再让模型渲染；渲染后用 OCR 核对，不许"差不多"。
- 品牌/Logo：要求权威母版文件作为参考，模型不得凭记忆重建。
- 透明背景是 Nano Banana 支持的，但不要假设它一定输出 alpha——**实际检查**。

## 文件结构

```text
outputs/poster_layers/<source-stem>/
├── source.png
├── layer_manifest.json
├── candidates/          # 待验收的候选
└── layers/              # 已通过验收的最终层
```
