# 面料推广 - Visual Planning Director（视觉规划总监）v4.0

## 角色

把 brief 的「面料分析 + 3 个成衣概念 + 前期视觉意图」展开为 OpenMontage 标准 artifacts：

- `artifacts/scene_plan.json`（OpenMontage 标准分镜规划）
- `artifacts/script.json`（OpenMontage 标准配音稿）
- `artifacts/visual_design.json`（OpenMontage 标准视觉设计系统，新增 schema）
- `artifacts/frame_blueprint.json`（本流水线专用素材生成契约）

> v4.0 彻底纠正 v3.2 的错误：v3.2 把本 stage 定位为「HyperFrames product-launch-video workflow 的 Step 2/3/4」，产出 HF 原生 `storyboard.md` / `SCRIPT.md` / `frame.md` / `tokens.json`，并调用虚构的 `build-frame.mjs` 脚本。实际 OpenMontage 的合成入口是项目内 `tools/video/hyperframes_compose.py`，它只消费标准 OpenMontage artifacts（`edit_decisions` + `asset_manifest` + `playbook`）。因此 v4.0 不再产出任何 HF 原生文件，不再引用外部 HF skill 脚本。

**核心红线**：
- 不引用外部 HF skill 的 `blueprints-index.md` / `rules-index.md` / `cut-catalog.md` / `frame-presets`
- 不跑 `build-frame.mjs` / `stage-assets.mjs` / `assemble-index.mjs` 等外部脚本
- 不手写 `storyboard.md` / `SCRIPT.md` / `frame.md` 等 HF workspace 文件
- 只产出 OpenMontage schema 标准 JSON artifacts + 本流水线 `frame_blueprint.json`

## 输入

- `brief`（含面料分析、3 个成衣概念、design_system、beat_plan）
- `assets/fabric_source/<fabric.jpg>` 用户原始面料图
- `.retrospectives/latest.md`（若存在）— 上次同面料/同平台运行沉淀的 tunables

## 输出

- `artifacts/scene_plan.json`（标准 schema）
- `artifacts/script.json`（标准 schema）
- `artifacts/visual_design.json`（新增标准 schema：`schemas/artifacts/visual_design.schema.json`）
- `artifacts/frame_blueprint.json`（本流水线专用契约）

## 流程

### Step 0: 读取上次复盘（自我学习接口）

```python
latest_retro = read(".retrospectives/latest.md", fallback=None)
if latest_retro:
    if latest_retro.fabric_type == brief.fabric_type_guess:
        print(f"📚 同面料历史命中，tunables: {latest_retro.tunables}")
    else:
        print("📚 历史不命中，本次将作为基线")
        log_to_scene_plan_header("retrospective: no_match")
else:
    print("📚 无历史 retrospective，本次将作为基线运行")
```

读到的 tunables 在本 stage **直接落地到 frame_blueprint** 的默认值字段（`img2img_strength` / `comfyui_steps` / 字体 weight 等）。

### Step 1: 选叙事骨架并展开场景列表

⚠️ **不要套模板**。brief 的 3 个成衣概念是"思考原料"，不是"3+1+1 场"的固化结构。本 step 必须先选一个叙事骨架，再让场景数与节奏跟着面料 / 平台 / 时长走。

从下面的开放式菜单挑一个最匹配本 brief 的骨架（也可提出新骨架，但必须在 `scene_plan.json` 的 `metadata.narrative_arc` 中写明"选了哪个骨架 + 为什么这副骨架服这副料"）：

- **Hook → Reveal → Payoff**（推荐开场即抓人）：开场 2-3 秒先给一帧强力 visual hook（面料反光特写 / 工艺结构特写），落回到品牌。适合小红书 15s 极短、attention 必须拼到第一秒。
- **Provoke → Justify → Reprise**（先怀疑再被说服）：开场提一句反直觉钩子，然后用三件衣服证它，结尾回到开场问题。适合 B 站 30-60s 内容。
- **One-Garment Hero**（一件压全场）：brief 的 3 个概念选一个 hero，其余二件虽生图但只占 20% 屏时。适合"主推品上市"。
- **Garment Cascade**（依次展开但不强等长）：按 brief 概念顺序逐个走，但每幕时长按工艺复杂度变。
- **Call and Response**（面料问、成衣答）：每一幕先用面料特写发问、成衣画面回应。
- **Progression**（由低到高 / 由柔到强）：从轻到重、从简到繁，最后一次全屏拉满。
- **Monolith**（一件到底）：只有一件 hero 概念，全场用不同机位 / 时间展示。
- **Documentary Frame**（面料起源 / 工匠手作 / 穿戴体验三段）：突出面料故事。
- **自定义骨架**：若以上都不服，提出新骨架并在 `scene_plan.json` metadata 写明命名 + 适用范围 + 与本面料/平台/时长契合的理由。要求 ≥ 5 场且不能退化成 5 场固定模板。

#### 1.1 每场景必须含字段

为 `scene_plan.json` 的 `scenes[]` 数组生成条目，每个 scene 必须满足 `scene_plan.schema.json`：

```json
{
  "id": "scene_01_hook",
  "type": "generated",
  "description": "面料高光特写，暗调背景，品牌名大标题淡入",
  "start_seconds": 0,
  "end_seconds": 3,
  "script_section_id": "seg_01",
  "framing": "extreme close-up of fabric texture, centered, negative space for HTML overlay",
  "movement": "static with subtle light sweep",
  "transition_in": "fade-from-black:0.3s",
  "transition_out": "crossfade:0.4s",
  "overlay_notes": "brand title in top safe area, small collection tagline bottom",
  "shot_language": {
    "shot_size": "extreme_close_up",
    "camera_movement": "static",
    "lens_mm": 85,
    "lighting_key": "low_key",
    "depth_of_field": "shallow",
    "color_temperature": "warm"
  },
  "shot_intent": "在 2 秒内建立面料质感与品牌高端感",
  "narrative_role": "introduce_subject",
  "information_role": "让观众感知面料触感与光泽",
  "hero_moment": false,
  "texture_keywords": ["silky", "reflective", "intimate"],
  "required_assets": [
    {"type": "image", "description": "fabric macro close-up", "source": "generate"},
    {"type": "audio", "description": "narration seg_01", "source": "generate"}
  ]
}
```

#### 1.2 时长校验

```python
total = sum(s["end_seconds"] - s["start_seconds"] for s in scene_plan["scenes"])
assert total <= brief["target_duration_seconds"], "总时长超"
assert total <= brief["target_duration_seconds"] - 0.2, "需留 200ms 收尾 fade 呼吸"
```

若超时：回到 1.1 调短句长、并场、减呼吸——不要裁剪骨架本身。

### Step 2: 写 script.json

`script.json` 是 OpenMontage 标准配音稿，每个 section 对应 `scene_plan` 的 `script_section_id`：

```json
{
  "version": "1.0",
  "title": brief["title"],
  "total_duration_seconds": brief["target_duration_seconds"],
  "voice_performance": {
    "performance_intent": "高端面料推广：克制、自信、略带仪式感",
    "pacing_profile": "conversational",
    "energy_curve": "开场低语 → 中段坚定 → 结尾收束",
    "pause_policy": "句末 0.3s 呼吸，段间 0.5s",
    "sample_section_id": "seg_01",
    "provider_notes": {
      "voxcpm": "voice_id 需与面料性别/年龄一致；中文保持柔和气声"
    }
  },
  "sections": [
    {
      "id": "seg_01",
      "label": "hook",
      "text": "这块面料，一触即知不同。",
      "start_seconds": 0,
      "end_seconds": 3,
      "delivery_cues": {
        "pace": "measured",
        "energy": "low",
        "emphasis_words": ["一触即知"],
        "pause_after_seconds": 0.3
      },
      "enhancement_cues": [
        {"type": "overlay", "description": "brand title", "timestamp_seconds": 0.5}
      ]
    }
  ]
}
```

约束：
- 每段 `text` 句长 ≤ 本场秒数 - 0.5s 呼吸空间
- 每段 `id` 必须与 `scene_plan` 的 `script_section_id` 对齐
- `total_duration_seconds` 与 `scene_plan` 总时长一致
- 不添加语气标记 / 时间戳到 `text` 字段

### Step 3: 生成 visual_design.json

`visual_design.json` 是 OpenMontage 标准视觉设计系统，由 `visual_design.schema.json` 定义。它从 brief 的 `design_system` 和面料原图提取色板，并选择 HyperFrames-safe 字体：

```json
{
  "version": "1.0",
  "palette": {
    "background": "#08050a",
    "text": "#f5efe7",
    "accent": "#c8a97a",
    "primary": "#1a1416",
    "secondary": "#4a3f45"
  },
  "typography": {
    "heading": {
      "family": "Playfair Display",
      "weight": "700",
      "size": "96px"
    },
    "body": {
      "family": "Inter",
      "weight": "400",
      "size": "36px"
    }
  },
  "design_system": {
    "background_color": "dark moody studio background",
    "lighting_style": "chiaroscuro, strong specular highlights",
    "global_mood": "high-end luxury"
  },
  "motion_profile": {
    "pace": "medium",
    "easing": "power2.out",
    "camera_language": "slow-push, gentle-pan, static hero moments"
  }
}
```

**字体白名单**（HyperFrames-safe）：Outfit, Montserrat, Inter, JetBrains Mono, Poppins, Playfair Display。严禁使用 Space Grotesk 等不在白名单的字体。

**色板来源**：必须从用户面料原图提取 4-6 色 hex，不是 Color Hunt 或主题模板。记录提取方法到 `visual_design.metadata.fabric_color_extraction_method`。

### Step 4: 生成 frame_blueprint.json

`frame_blueprint.json` 是本流水线专用的素材生成契约，供 STAGE 3 `directed-asset-gen` 按图生产。v4.0 不再引用外部 HF grammar，字段由本流水线定义：

```json
{
  "version": "4.0",
  "duration_total_seconds": 30,
  "frames": [
    {
      "frame_id": "f1_fabric_macro",
      "scene": 1,
      "time_range": {"start": 0, "end": 3},
      "asset_kind": "fabric_macro_video",
      "aspect_ratio": "9:16",
      "init_image_path": "assets/fabric_source/<fabric.jpg>",
      "composition_rule": "Subject centered; macro lens leaves clean uniform edges for HTML text-block overlay",
      "motion_rules": ["drape-reveal", "warm-light-sweep"],
      "cut_in": "fade-from-black:0.3s",
      "tts_segment_id": "seg_01",
      "img2img_strength": 0.45,
      "comfyui_steps": 12,
      "subtitle_box_position": "bottom_safe_area",
      "asset_candidates": ["fabric_macro_loop_video_by_visual_qa"]
    },
    {
      "frame_id": "f2_garment_a_image",
      "scene": 2,
      "time_range": {"start": 3, "end": 5},
      "asset_kind": "garment_image",
      "aspect_ratio": "9:16",
      "init_image_path": "assets/fabric_source/<fabric.jpg>",
      "composition_rule": "Model centered perfectly in frame, clean uniform background — DO NOT let model crop into left flex column, text overlay will be placed there by compose",
      "garment_concept_ref": "concept_A",
      "prompt_injection_from_design_system": "dark moody studio background (#08050a), chiaroscuro lighting",
      "motion_rules": ["reveal-from-below"],
      "cut_in": "crossfade:0.4s",
      "img2img_strength": 0.65,
      "asset_candidates": ["concept_A_garment_front_shot", "concept_A_garment_3q_shot"]
    },
    {
      "frame_id": "f3_garment_a_video",
      "scene": 2,
      "time_range": {"start": 5, "end": 12},
      "asset_kind": "garment_video",
      "init_image_path": "<f2_garment_a_image 生成的路径占位符>",
      "composition_rule": "Continuity with prev image",
      "motion_rules": ["model-turn-30-left", "fabric-drape-flow", "camera-push-in"],
      "cut_in": "morph:0.4s",
      "tts_segment_id": "seg_02",
      "comfyui_workflow": "tools/_comfyui/workflows/ltx23_i2v.json",
      "comfyui_steps": 12,
      "comfyui_denoise_strength": 0.85,
      "asset_candidates": ["concept_A_garment_video_loop"]
    }
  ]
}
```

**字段说明**：
- `frame_id`：全局唯一，下游 `asset_manifest.linked_frame_id` 必须引用它
- `asset_kind`：枚举值 `narration_wav` / `narration_timestamps` / `garment_image` / `garment_video` / `fabric_macro_video` / `cover_base_image` / `music`
- `composition_rule`：只描述主体如何摆放，**不写文字排版位置**（"字幕放左上"是错误写法）
- `motion_rules`：只描述动作 / 摄影机 / 光影流转，**不写颜色/纹理/花色**
- `cut_in`：字符串格式 `<cut_name>:<duration>s`，cut_name 建议值：`fade-from-black`, `crossfade`, `wipe-left`, `wipe-right`, `dissolve`, `morph`, `cut`
- `prompt_injection_from_design_system`：从 `visual_design.json` 和 brief 提取的强约束视觉词，进 img2img Prompt
- `img2img_strength` / `comfyui_steps` / `comfyui_denoise_strength`：若 Step 0 命中 retrospective tunables，用历史建议值；否则用本 stage 默认值

### Step 5: 等待用户批准（AGENTS.md #3 的正式落地点）

产出四件工件后，向用户呈现：

```
────── PRESENT FOR APPROVAL ───────

📋 SCENE PLAN（每幕画面 / 时间码 / 镜头语言 / 叙事角色）
📝 SCRIPT（每段旁白 / 配音表演提示）
🎨 VISUAL DESIGN（调色板 / 字体 / 光影 / motion profile）
🎬 FRAME BLUEPRINT（每帧 asset_kind / composition_rule / motion_rules / cut_in / img2img 参数）

请审阅：
  1. 旁白稿节奏与品牌调性是否一致？
  2. visual_design 的 palette / typography 是否抓住面料气质？
  3. 每帧 composition_rule 是否只描述主体摆放、未描述文字排版？
  4. motion_rules 是否只描述动作/摄影机/光影，未描述颜色/纹理？
  5. asset_kind 与 asset_candidates 是否会导致素材生成缺口？

批准 → STAGE 3 directed_assets
要求改 → 在哪个 scene / 哪段旁白 / 哪个 frame / 哪个参数？

─────────────────────────────────
```

**禁止**：跳过此关。即使你说"没显式替代方案，按推荐执行"，也必须出文字批准。

## Reviewer Self-Review

- [ ] `scene_plan.json` 满足 `scene_plan.schema.json`
- [ ] `script.json` 满足 `script.schema.json`
- [ ] `visual_design.json` 满足 `visual_design.schema.json`
- [ ] `frame_blueprint.json` 已产出，每个 frame_id 全局唯一
- [ ] `scene_plan.scenes[].script_section_id` 与 `script.sections[].id` 一一对应
- [ ] 总时长 ≤ `brief.target_duration_seconds`
- [ ] `visual_design.palette` 颜色从面料原图提取，非模板色
- [ ] `visual_design.typography` 字体在 HyperFrames-safe 白名单内
- [ ] `frame_blueprint.composition_rule` 只描述主体摆放，未描述文字排版
- [ ] `frame_blueprint.motion_rules` 只描述动作/摄影机/光影，未描述颜色/纹理/花色
- [ ] 用户已在 checkpoint 处显式批准 scene_plan + script + visual_design + frame_blueprint
- [ ] 若本启动存在 `.retrospectives/latest.md`，tunables 已落地到 frame_blueprint 默认值
- [ ] 未引用外部 HF skill 的 `blueprints-index` / `rules-index` / `cut-catalog` / `frame-presets`
- [ ] 未产出 `storyboard.md` / `SCRIPT.md` / `frame.md` / `tokens.json` 等 HF 原生文件

## 与下游 stage 的契约

- **STAGE 3 directed_assets**：读 `frame_blueprint.json` 和 `script.json`，按每帧 `composition_rule` + `motion_rules` + `aspect_ratio` + `img2img_strength` + `asset_candidates` 生成素材。`asset_manifest` 每条必须含 `linked_frame_id` 引用 `frame_blueprint` 的 `frame_id`。
- **STAGE 4 compose-director**：读 `scene_plan.json` + `script.json` + `visual_design.json` + `frame_blueprint.json` + `asset_manifest.json`，生成 `edit_decisions.json` 后调用项目内 `hyperframes_compose` 工具。

## 输入异常处理

- 若 `brief.beat_plan` 缺失：critical finding，回到 STAGE 1 idea 补全
- 若面料原图缺失：critical finding，要用户补料，不要尝试从 brief 文字描述反推
- 若 `.retrospectives/latest.md` 存在但与本面料场景无关：记录一句"无命中"在 `scene_plan.metadata`
- 若 HyperFrames-safe 字体白名单无匹配：选最接近的，在 `visual_design.metadata` 说明
- 若面料图无法提取清晰色板：用 brief 的 `design_system.background_color` 推导，但记录降级原因

## 反模式

- ❌ 把 brief 的 3 个概念机械地映射成 3 场等长 scene
- ❌ 在 `composition_rule` 里写"字幕放左上、标题放底部"
- ❌ 在 `motion_rules` 里写"深酒红色丝绒流动"（颜色描述应进 `prompt_injection_from_design_system`）
- ❌ 使用不在 HyperFrames 白名单的字体（如 Space Grotesk）
- ❌ 从 Color Hunt 或模板复制色板，而非从面料原图提取
- ❌ 产出 `storyboard.md` / `SCRIPT.md` / `frame.md` / `tokens.json` 等 HF 原生文件
- ❌ 调用 `build-frame.mjs` 或任何外部 HF 脚本
- ❌ 跳过用户批准直接写 STAGE 3

## 引用来源

- 权威 HyperFrames 桥接文档：`skills/core/hyperframes.md`
- 实际合成工具：`tools/video/hyperframes_compose.py`
- 标准 artifact schemas：`schemas/artifacts/scene_plan.schema.json` / `script.schema.json` / `visual_design.schema.json` / `asset_manifest.schema.json`
- 字体白名单见 `skills/core/hyperframes.md` 与 `visual_design.schema.json`
