# Assets Director — Vox Paper Collage (v2)

## 职责

执行 VOX 引擎资产生产：三层产物模式（多宫格参考 → beat 完整拼贴图 → 独立元素 PNG）+ TTS 旁白 + 音乐 + 纸 ASMR。产出 `asset_manifest`。

## 输入

- `scene_plan`（语义 scene/beat + 每 beat 的 core_idea / visual_metaphor / elements）
- `script`（旁白全文 + paragraph_label）
- `proposal_packet`（visual_direction / narration_language / data_authenticity_plan）

## 流程顺序（硬性）

```
0. TTS 全段合成 + whisper 时间戳（先于图像）
1. TTS 时间戳校准（对比 scene_plan 估算，≤5% 更新 / >5% 回退）
2. 素材库检索（asset_library search —— 每类素材先搜库）
3. 多宫格参考图（用户确认成品效果）
4. beat 完整拼贴图（每 beat 一张，含 Editorial Title）
5. 独立元素 PNG（以 beat 完整图为 img2img 参考重绘）
6. 真实照片获取（Real Photo Cascade，real_content 元素）
7. 音乐 + 纸 ASMR
8. 缺失照片清单汇总（C7 用户决策）
9. 产出 asset_manifest
```

## 0. TTS + whisper（先于图像）

**本阶段第一步**：TTS 全段合成 + whisper 时间戳提取，验证 scene_plan 字数估算。

```
script 定稿
  → scene_plan v1（timing_source: estimated）
  → assets 阶段：
      0a. TTS 全段合成（IndexTTS2，20-25s 批次）
      0b. whisper 提取词级/句级时间戳（timestamps JSON）
      0c. 偏差 = |tts_actual - estimated| / estimated
      0d. ≤5% → 更新 scene_plan 为 v2（timing_source: tts_actual）
      0e. >5% → 回到 script 阶段精简/扩充，重新生成 scene_plan
  → edit
  → compose
```

**偏差计算**：`error_ratio = |tts_actual_duration - estimated_duration| / estimated_duration`，用完整合成总时长，不是单句试读。

**校准记录**：写入 `asset_manifest.timing_calibration_ref`（估算时长、实际时长、偏差、状态）。状态 `calibrated` / `exceeds_threshold` / `rewind_required`。

**禁止**：不许用 speed 变速硬凑时长，不许硬塞时间码。超长先精简文本重生成。

## 0.5 图像生成工具绑定（2026-08 用户确认：仅 Klein 工作流）

**本管线图像生成只用本地 ComfyUI + Klein 工作流，不使用其他任何工作流或云图像服务。**

工具：`comfyui_image`（本地 ComfyUI，capability: image_generation，需服务器运行 + COMFYUI_SERVER_URL 配置）

| 用途 | 工作流文件 | output_node | 提示词节点 | 参考图 |
|---|---|---|---|---|
| 文生图（多宫格 / beat 完整图 / 独立元素纯生成） | `tools/_comfyui/workflows/Klein-txt2image.json` | `78` | `115:111` text | 无 |
| 图生图（元素重绘 B3 / real_content 风格化） | `tools/_comfyui/workflows/Klein-img2image.json` | `9` | `114:113` text | `76` image（`<UPLOADED_IMAGE>` 占位） |
| 双参考图生图（完整蓝图 + 当前状态） | `tools/_comfyui/workflows/Klein-img2image-dual-reference.json` | `9` | `114:113` text | `76` 锚点（`<UPLOADED_IMAGE_1>`）+ `77` 状态（`<UPLOADED_IMAGE_2>`） |

**调用约定**：

```python
# 文生图
tool.execute({
    "workflow_path": "tools/_comfyui/workflows/Klein-txt2image.json",
    "output_node": "78",
    "workflow_overrides": {
        "115:111": {"text": "<SCENE + STYLE BLOCK + CLOSER + negative>"},
        "115:108": {"noise_seed": <seed>}
    },
    "output_path": "assets/...png",
    "workflow_name": "klein-txt2image",
    "workflow_model": "flux-2-klein-9b"
})

# 图生图（参考图重绘）
tool.execute({
    "workflow_path": "tools/_comfyui/workflows/Klein-img2image.json",
    "output_node": "9",
    "reference_image_path": "assets/collages/sc1_b1.1.png",   # 参考图（beat 完整图 / 真实照片）
    "workflow_overrides": {
        "114:113": {"text": "<元素提示词>"},
        "76": {"image": "<UPLOADED_IMAGE>"},   # 必须！否则参考图不会注入 LoadImage 节点（实测失败）
        "114:112": {"noise_seed": <seed>}
    },
    "output_path": "assets/elements/...png",
    "workflow_name": "klein-img2image",
    "workflow_model": "flux-2-klein-9b"
})

# 双参考图生图（完整蓝图 + 当前状态）
tool.execute({
    "workflow_path": "tools/_comfyui/workflows/Klein-img2image-dual-reference.json",
    "output_node": "9",
    "reference_image_path": "assets/blueprints/b1.1_anchor.png",
    "reference_image_path_2": "assets/states/b1.1_state_0.png",
    "workflow_overrides": {
        "114:113": {"text": "<FULL PROMPT + STATE DELTA>"},
        "76": {"image": "<UPLOADED_IMAGE_1>"},
        "77": {"image": "<UPLOADED_IMAGE_2>"},
        "114:112": {"noise_seed": <seed>}
    },
    "output_path": "assets/states/b1.1_state_1.png",
    "workflow_name": "klein-img2image-dual-reference",
    "workflow_model": "flux-2-klein-9b"
})
```

**尺寸约定（2026-08 实测）**：
- `Klein-txt2image.json`：`ResolutionSelector`（节点 `115:114`）控制比例。**B 站横屏 = `"16:9 (Widescreen)"`**（1360×768，megapixels=1）；竖屏 9:16 = `"9:16 (Portrait Widescreen)"`（768×1360）。管线内已默认为 16:9 横屏
- `Klein-img2image.json`：**无 ResolutionSelector**，输出比例 = 参考图比例（ImageScaleToTotalPixels 缩放到 1MP）。参考图是 16:9 时输出 1360×768

**实测教训（2026-08）**：
- 图生图漏传 `"76": {"image": "<UPLOADED_IMAGE>"}` → 报错 `Invalid image file: 6B2FAD77C6429F9D05EB55E57C361427A.jpg`（LoadImage 加载的是工作流模板里的旧参考图）
- 小装饰元素（图钉/胶带等 <5% 画面占比）经 img2image 重绘后 opaque 比例过低（<1%），**不要用 img2image 提取小装饰**——装饰走 CSS 或素材库 decal

**模型栈（Klein 固定）**：`flux-2-klein-9b_int8_convrot.safetensors`（UNET）+ `qwen_3_8b_fp8mixed.safetensors`（CLIP）+ `flux2-vae.safetensors`（VAE）。

**注意事项**：
- 自定义工作流会跳过默认模型检查（flux2-dev），直接使用工作流内模型名
- 图生图参考图经 `ImageScaleToTotalPixels` 缩放至 1MP（比例偏差可接受，B3 决策）
- 竖屏 9:16 由 `ResolutionSelector`（115:114 / 114:106 区域）控制
- 调用前必须阅读 Layer 3 技能（`comfyui` / `comfyui-auto-recovery` / `flux-best-practices`），记录到 `layer3_skills_read`

## 1. 素材库检索（asset_library，强制）

**每类素材生成前，必须先调用 `asset_library`（operation=search）搜索本地素材库**：

- 搜索图片：`{"operation": "search", "query": "...", "category": "photo"}`（texture / decal 同理）
- 搜索音乐/音效：`{"operation": "search", "query": "...", "category": "music" / "sfx"}`
- 命中 → 直接使用 + `touch` 计数
- 未命中 → 才允许生成/下载，外部来源素材获取后 `add` 归档

**防偷懒保障**：本工具在 YAML 中声明为 `required_tools`，asset_manifest 的 `layer3_skills_read` 与工具调用记录必须包含 asset_library 的 search 调用，否则产物不完整。

## 2. 多宫格参考图（蓝图预览层）

先生成多宫格参考图作为成品预览，用户确认视觉方向后进入元素生成：

- 布局：2×3（6 scene）或按 scene 数调整；横屏用 16:9（1360×768）
- 每格 = 该 scene 最终完整拼贴效果（含所有元素位置/叠压关系）
- 提示词：`SCENE + STYLE BLOCK + CLOSER` verbatim，每格独立描述
- 用户确认后，把多宫格路径写入 `asset_manifest.multi_grid_refs[]`
- 组装时元素位置以 scene_plan 的 `box` 为准（蓝图仅做视觉确认，不做像素级匹配）

## 3. Beat 完整拼贴图（视觉蓝图，方案 3 + A）

每个 beat 生成一张**完整拼贴图作为视觉蓝图**——它定义该 beat 的最终视觉效果（构图、风格、叠压关系），但**不要求 compose 终帧逐像素匹配**（元素是独立生成的，位置以 scene_plan box 为准）。

**位置驱动的生成（2026-08 决策）**：完整图的 prompt 必须**按 scene_plan 每个元素的 `box` 字段描述位置**，让模型按规划布局生成：

**box → prompt 文字转换规则**（必须遵循）：

```
box = [left%, top%, width%, height%]
- left%  → "left edge" (<25) / "center-left" (25-40) / "center" (40-60) / "center-right" (60-75) / "right edge" (>75)
- top%   → "top" (<25) / "upper-middle" (25-40) / "center" (40-60) / "lower-middle" (60-75) / "bottom" (>75)
- width% → "occupying about X% of frame width"
- height% → "occupying about X% of frame height"
- hero 层强制 "dominant, largest element"
- decor/css 层不进 prompt（CSS 渲染）
```

示例：
```
box = [20, 15, 40, 45]  →  "hero building positioned center-left, upper-middle of frame, occupying about 40% width, 45% height, dominant largest element"
box = [65, 60, 25, 20]  →  "supporting chart positioned center-right, lower-middle of frame, occupying about 25% width, 20% height"
```

**提示词结构**（每 beat 一张，自然散文块）：

1. **SCENE**：从 scene_plan 读取该 beat 的 `core_idea` + `visual_metaphor` + `visual_idea`，结合每个元素的 box 位置描述，构建完整构图描述。
2. **MOTION ENERGY（I1，2026-08）**：为每个 img 元素添加**动势描述**——根据元素的 family（入场动效）写出静态图能体现的运动感，让蓝图看起来有动势，compose 动画与之呼应：
   - `drop`/`slap` → "falling with impact energy, slight downward motion blur at edges"
   - `slide` → "appears to have slid in from the side, subtle directional motion streaks"
   - `pop` → "popped into place, tiny scale bounce implied, fresh placement"
   - `unfold` → "unfolding from a crease, slight fold shadow"
   - `wipe`/`mask_reveal` → "revealed by a wipe, edge partially masked"
   - `rotate` → "landed with a slight twist, micro-rotation energy"
   - `fade` → "materializing softly, gentle presence"
   - 装饰元素（decor）不需要动势描述（CSS 渲染）
3. **Editorial Title（必选，Playbook 要求）**：每张图必须有 1-4 词杂志封面级大字标题，融入构图，与 hero 叠压。标题 = 该 beat core_idea 的浓缩。
4. **STYLE BLOCK**：`templates/style_block.md` verbatim（视觉方向为 guofeng 时，风格以 `styles/vox-paper-collage-guofeng.yaml` 的 visual_language 为准）。
5. **CLOSER**：`templates/closer.md` verbatim。

## 3.5 蓝图动效标注版（I2，2026-08）

蓝图生成后，用 PIL 在**副本**上叠加动效标注，产出标注版蓝图（annotated blueprint）：

**标注内容**（每个 img 元素，数据来自 scene_plan）：
- **元素编号**：按 entrance_order 标 ①②③...（在元素 bbox 附近）
- **入场方向箭头**：按 family 画箭头（slide→左进右箭头、drop→顶部下箭头、rotate→弧线箭头）
- **动效名标签**：family 名（DROP/SLIDE/POP）+ 错峰时间（+0.4s）
- **装饰元素**（decor/css）：标注 "CSS" 字样（表示走 CSS 渲染）

**输出约定**：
- 干净版：`assets/blueprints/{beat_id}.png`（供 compose 视觉参考）
- 标注版：`assets/blueprints/{beat_id}_annotated.png`（供 compose 定位 + 动效参考）
- 两版都写入 `asset_manifest`（element_role: composed_ref 或新增 annotated_blueprint）

**标注脚本**：`scripts/annotate_blueprint.py`（PIL 实现：读 scene_plan box/family/entrance_order → 画编号/箭头/标签）

**compose 消费**：compose 读 scene_plan 的 box/family/entrance_order/stagger/build_on_ratio 结构化数据执行动画；标注版蓝图仅作人工/视觉校验参考。

**语言红线（bilingual-spec §10，硬性）**：
- 生图 prompt 一律英文，无论 narration_language
- 中文字符绝不进生图 prompt（中文标签/图章全部走 CSS 渲染）
- Recurring Subject Rule（§9）：同一主体跨 beat 复现时措辞逐字一致

**Negative Prompt（Playbook 要求，硬性）**：每个提示词必须包含 playbook 的 `image_negative_prompt`（from `styles/vox-paper-collage.yaml`），禁止省略。

**工具**：`comfyui_image` + `Klein-txt2image.json`（文生图，见 §0.5）。调用前必须阅读 Layer 3 技能（查工具 agent_skills 字段），并记录到 `layer3_skills_read`。

## 4. 独立元素 PNG（方案 3：独立文生图）

**2026-08 决策（替代原 img2img 提取方案）**：元素**独立文生图**生成，不再从完整图提取（Klein 图生图"提取"不可控：楼变 4 层/线稿化）。

每个元素用 `Klein-txt2image.json` 单独生成：

- prompt 结构：`该元素的视觉描述` + `isolated single subject, solid flat tan background color #D8C7A3, no other objects, no text` + STYLE BLOCK + CLOSER
- 元素视觉描述必须与完整图 prompt 中该元素的描述**逐字一致**（Recurring Subject Rule，保证元素与蓝图风格统一）
- 生成后 PIL 抠透明（色彩距离阈值 + bbox 裁剪）→ 透明 PNG
- 连通域检查：元素数 >1 的弃用或改 CSS
- `asset_manifest` 中元素记录 `layer` + `element_role: independent_element`（**不再要求 derived_from 指向完整图**）

**位置在 compose 阶段使用**：元素的摆放位置来自 scene_plan 的 `box` 字段，完整图仅作视觉参考。

**数据真实性（data_class 规则）**：
- `real_data`（数字/排名/行情）：真实数据源（yfinance/官方文档）→ matplotlib 参照图 → 以 matplotlib 图为参考用 Klein-img2image 风格化（此场景参考图=数据图，语义明确，img2image 可控）→ PIL 抠图。禁止 AI 编造数字，提示词显式写精确值
- `real_content`（真实人物/地点/产品）：走 Real Photo Cascade 获取真实照片，用 Klein-img2image 以照片为参考重绘。**不允许纯生成**
- `creative`（抽象概念）：纯文生图
- `css`（装饰）：优先素材库 decal 贴图，CSS 负责定位动画

## 5. 真实照片获取（Real Photo Cascade，C4）

real_content 元素必须基于真实照片。级联渠道，按顺序尝试：

```
1. 用户上传/提供（优先，版权最干净）
2. 素材库检索（asset_library search，category=photo）
3. Wikimedia Commons（public domain / CC 授权，版权安全）
4. OpenMontage 内置搜图（image_selector: search_image → pixabay_image / pexels_image，仅下载真实照片）
5. Bing/Google（仅作为参考确认存在性，不归档商用）
6. 生图描述生成（标注 stylized representation，仅当用户批准）
```

**获取到真实照片后**：用 `comfyui_image` + `Klein-img2image.json`（reference_image_path = 真实照片）重绘为 VOX 拼贴风格。绝不用云图像服务。

**版权记录**：每个照片归档时填写 `license`（public_domain / cc0 / cc_by / commercial / unknown），Wikimedia 优先，Bing/Google 默认 unknown。

**找不到照片（C7）**：级联全部失败的元素，写入 `asset_manifest.missing_photos[]`，汇总后提交用户决策（放弃、换图、或降级为 creative）。**不允许自行纯生成**。

## 6. 旁白（TTS）

- 工具：`tts_selector` → indextts_tts 首选
- 参考音色：`spk_audio_prompt` → `INDEXTTS_VOICE_REF` → `voice_reference.wav`
- 中文：~4.7 字/秒，speed=1.0 零变速；英文 ~155 wpm
- **情感语义（硬性）**：每次旁白调用显式传 `emo_vector=[0,0,0,0,0,0,0,1.0]`（calm=1.0），关闭自动判情感
- 生产规则：20-25 秒批次合成；每批 2-5 次重生成取最佳；冷开场批次最高优先级
- 每段时长硬校验：ffprobe 实测每段 ≤ 对应 beat 时长上限，超长先精简重生成

## 7. 音乐 + 纸 ASMR

- 音乐：`pixabay_music`，搜索词来自 `templates/music_prompt.md`
- 纸 ASMR：`freesound_music`，paper slide / tape press / stamp thud / string zip / pin click
- 先搜素材库（asset_library search，category=music/sfx），命中直接使用
- 音乐仅用于成片混音，不进 clip 动画

## 8. 缺失照片清单（C7）

assets 阶段结束时，若有 `missing_photos[]`，汇总展示给用户：

```
以下真实照片未能找到，请决策：
1. [element_id] [描述] — 尝试渠道: [列表]
   A. 用户提供照片
   B. 换用其他元素
   C. 降级为 creative（stylized representation）
```

用户决策前不进入 edit 阶段。

## 质量要求

- 模板红线：STYLE BLOCK 与 CLOSER 必须 verbatim，禁止改写/缩写
- **Editorial Title 每拍必选**（Playbook）
- Negative Prompt 每图必带（Playbook）
- 每 beat 一张完整图 + 独立元素 + 多宫格参考，对应关系可追溯
- 所有生成物记录 provenance（model、seed、prompt 路径、derived_from）
- 物理校验：所有资产文件存在且非空
- Layer 3 技能在写提示词前阅读并记录到 `layer3_skills_read`
- asset_library 的 search 调用记录必须存在（防偷懒）

## 成功标准

- `asset_manifest` 通过 schema 校验
- 每 beat 完整图 + 独立元素 + 多宫格参考 + 旁白 + 音乐 + ASMR，文件全部存在
- `timing_calibration_ref` 存在且状态为 calibrated（或记录 rewind_required）
- `missing_photos[]` 为空或已提交用户决策
- 独立元素均记录 `derived_from` 和 `layer`
- `layer3_skills_read` 完整，包含 asset_library
