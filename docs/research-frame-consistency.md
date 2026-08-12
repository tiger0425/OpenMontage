# AI 逐帧生成跨帧一致性手段研究

## 摘要

本文研究"AI 逐帧生成图片时如何保证跨帧（跨镜头/跨分镜）一致"这一 ticket #2 问题，并结合 OpenMontage 当前工具栈与 `series-adapt`（Vox 纸拼贴）管线已验证经验给出结论：本地 ComfyUI 已提供 Klein 文生图、单参考图生图和双参考图生图工作流；逐帧方案应以 `Klein-img2image-dual-reference.json` 为主，采用「固定视觉锚点 + 当前状态递推 + 独立 seed + 状态增量提示词」。云端 `google_imagen` 只作为备用路径。同时，管线已有反向证据（L-036/K-03）：同参考帧 + 同主语会产出过度一致的雷同画面，故设计上需用「状态增量 + 子镜头内容多样性」对冲。

## 背景

跨帧一致性是指同一角色/物体/场景在多个独立生成的画面中保持外观、姿态、风格不漂移。在逐帧（每分镜一张图）生成模式下，每张图是一次独立的模型调用，缺乏视频模型那样的时序约束，一致性完全依赖输入侧控制。

## 一致性手段谱系

| 手段 | 原理 | 对"外观一致"的力度 | 对"内容雷同"的风险 |
|---|---|---|---|
| A. 固定 seed | 相同 prompt+seed → 相同潜空间起点 | 高（仅同 prompt 时成立） | 低 |
| B. 参考帧 img2img | 用真实/已生成的参考图做条件，`image_strength` 控制保留度 | 中高 | 高（L-036/K-03 已验证） |
| C. Prompt 主语锁定 | 反复写 "Keep the exact same [subject] from the reference photo" | 中（依赖模型跟随） | 高 |
| D. 风格块（STYLE BLOCK）逐字一致 | 所有图共享同一风格段落 | 中（风格层，非个体层） | 低 |
| E. 后处理统一 | HTML/合成层统一拼贴语言（纸片、halftone、drop shadow） | 中（视觉语言层） | 低 |
| F. 语义一致性 | 脚本/词典层统一名称、数字、服装词 | 低（个体层靠词） | 低 |

## OpenMontage 当前栈能力盘点

### Provider 与本地工作流（实测，2026-08）

| provider | 状态 | 备注 |
|---|---|---|
| `comfyui_image` | **条件可用** | 本地 GPU；服务可达即可运行自定义 workflow；Klein 支持 seed 与参考图 |
| `google_imagen` | **available/备用** | 模型 `gemini-3.1-flash-lite-image`；不支持 seed |
| `pexels_image` | available | stock 图，与一致性生成无关 |
| `image_selector` | available | 路由/透传外壳 |
| `flux_image` | unavailable | `FAL_KEY` 未配置 |
| `local_diffusion` / `grok` / `minimax` / `recraft` / `openai` | unavailable | 无对应密钥 |

### `comfyui_image` 与 Klein 一致性能力

`tools/graphics/comfyui_image.py` 已实现：

- `runtime = LOCAL_GPU`、`determinism = SEEDED`、本地生成成本 `0.0`。
- `workflow_path` / `workflow_json` + `output_node` 执行自定义 ComfyUI API workflow。
- `reference_image_path` 与 `reference_image_path_2` 上传一或两张参考图。
- `workflow_overrides` 替换上传图片占位符，并覆盖 prompt、seed 等节点参数。
- `workflow_provenance` 记录 workflow hash、model stack 和 output node，满足逐帧复现记录要求。

现有 Klein 工作流：

| 工作流 | 作用 | 关键节点 |
|---|---|---|
| `Klein-txt2image.json` | 生成首帧、角色卡、蓝图 | output `78`；prompt `115:111`；seed `115:108` |
| `Klein-img2image.json` | 以上一帧递推下一状态 | output `9`；参考图 `76`；prompt `114:113`；seed `114:112` |
| `Klein-img2image-dual-reference.json` | 同时锁定长期视觉锚点和当前状态 | output `9`；锚点 `76`；当前状态 `77`；prompt `114:113`；seed `114:112` |

双参考 workflow 的 prompt 已定义为保持锚点构图和当前状态不变、只应用请求的状态增量，与逐帧定格的状态递推模型直接匹配。

### `google_imagen` 一致性相关参数（`tools/graphics/google_imagen.py`）

- **img2img**：`image_path`（本地参考图路径）+ `image_strength`（0-1，默认 0.7，`asset-director` 建议 0.85-0.9）+ `generation_mode: edit`
- **不支持 seed**：`input_schema` 无 `seed` 字段，`supports` 不含 `seed`，`idempotency_key_fields = ["prompt", "aspect_ratio", "model"]`
- 其余：`aspect_ratio` / `width` / `height`（映射到最接近比例，非精确像素）、`number_of_images`

### 文档与实现落差（关键矛盾）

- `skills/pipelines/series-adapt/asset-director.md:59`：「If two scenes show the same tank model, reuse the same reference frame **and seed** for consistent appearance」
- 同文件 `:176` 示例里出现 `"image_seed": 42`
- **现实**：`image_selector` 按下游 provider schema 过滤参数；`google_imagen` schema 没有 `seed`，因此 seed 到达不了该 provider。该限制不适用于 `comfyui_image`，其 schema 明确支持 `seed` 和自定义 workflow。
- 推论：seed 复用不是全局不可用，而是仅对本地 ComfyUI/Klein 等支持 seed 的 workflow 生效。

## series-adapt 已验证经验（`skills/pipelines/series-adapt/`）

### 有效的一致性手段

1. **首帧/锚点生成**：用 `Klein-txt2image.json` 固定首帧 seed，保存为长期视觉锚点。
2. **双参考递推**：用 `Klein-img2image-dual-reference.json`，第一参考图固定角色/场景锚点，第二参考图使用上一状态，prompt 只写本帧 state delta，seed 每帧显式记录。
3. **单参考递推**：若不需要长期锚点，使用 `Klein-img2image.json`，仍然显式覆盖节点 `76`、`114:113`、`114:112`。
4. **STYLE BLOCK 逐字一致**（`references/vox-look-library.md` §4 反一致性红线第 1 条：可 diff）。
5. **纸拼贴语言统一**：cut-outs / clear edges / drop shadow 三要素、单一纯色背景、禁 3D render/CGI 词 —— 风格层一致性由"拼贴世界"兜底，个体漂移被强视觉语言吸收。
6. **人物脸保护**（L-037/L-038）：禁止 label 混入人物图、剥离红绳/图钉措辞，保证脸清晰 —— 个体层一致性与可读性。

### 反模式（过度一致 → 雷同）

- **L-036 / K-03**（`scene-director.md:96`、`known-issues.md` K-03）：同参考帧 + 同主语 img2img → 输出近乎相同的图（MD5 不同但视觉雷同）。**当前一致性手段恰恰会引发雷同**，因此管线强制"每个 sub-shot 必须不同视觉主体/不同参考帧/不同事件时刻"，用多样性对抗一致性过度。
- 结论：逐帧生成的一致性目标不是"每张图完全一样"，而是"同主体跨帧可辨识 + 相邻帧内容不同"。

### 其他已登记问题

- K-10：批量生图非幂等（清空目录互相覆盖）—— 一致性研究需保证输出路径稳定。
- K-13：`google_imagen` 请求 1920×1080 实际产出 1365-1376×768，放大 1.4x 变糊 —— 逐帧一致性还应含**尺寸一致性**校验。

## 结论与建议

1. **首选路径**：本地 `comfyui_image` + `Klein-txt2image.json` 生成锚点，随后 `Klein-img2image-dual-reference.json` 逐状态递推；这条路径零 API 图片成本，并具备 seed、参考图和 workflow hash 复现能力。
2. **降级路径**：仅需单一参考帧时使用 `Klein-img2image.json`；ComfyUI 不可用时才降级到 `google_imagen` 的参考图编辑，但不宣称 seed 可复现。
3. **一致性 vs 雷同是同一根杠杆**：一致性手段越强（双参考+同主语+高参考权重），雷同风险越高。必须用明确的 state delta、相邻帧差异规则和子镜头多样性对冲。
4. **资产记录**：每帧保存 anchor/state 输入路径、prompt delta、seed、workflow hash、model stack 和尺寸；这是批量返工与定位漂移的最低复现契约。
5. **尺寸与质量**：统一 16:9 参考图尺寸；每帧执行尺寸、主体漂移、空白图和脸部遮挡 QA。K-13 的尺寸偏差风险仍适用。
6. **逐帧 vs 视频模型**：若目标是严格的无缝连续运动，逐帧生成配合 stop-motion 节奏仍是折中；本方案承诺的是可辨识主体 + 离散状态变化，不是连续运动。

## 风险与约束

- 本地 ComfyUI/Klein 的可用性取决于服务、模型文件和自定义节点；资产阶段前必须检查 `/system_stats`、模型列表和 workflow 节点。
- `image_strength` 与 prompt 措辞对输出影响非线性，需逐图 QA（K-04 人脸遮挡、K-11 空白误报等已有前例）。
- 双参考输入与 prompt delta 对输出影响非线性，需要用 2-4 帧小样本校准；锚点约束过强会压制状态变化。
