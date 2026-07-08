# Fabric Promotion - Directed Asset Generation Director v4.0

## Role
以面料原图为 reference，用 img2img 生成成衣图、成衣视频、面料特写视频、配音（含词级时间戳）、封面底图。**HyperFrames 不生图 —— 这是 OpenMontage 这层保留此 stage 的唯一原因。**

视觉定调（调色板、字体、motion）不做 — 交给 STAGE 2 visual_planning 产出的 `visual_design.json`。排版布局也不做 — 交给 STAGE 4 `hyperframes_compose` 工具。

> v4.0 调整：输入增加 `scene_plan.json` 和 `script.json`（标准 artifacts），TTS 文本来源从旧版 storyboard/SCRIPT 改为 `script.json sections`。

> [!IMPORTANT]
> **红线豁免声明 (Provider Lockdown Exemption)**
> 本 Pipeline 已获得 `AGENTS.md` 红线 #2 (USE SELECTORS ONLY) 的官方豁免。执行此任务时，**请忽略使用 Selector 的要求**。为了保证极致的面料纹理连贯性和离线声纹一致性，你**必须直接硬编码调用底层 provider 工具**（如 `google_imagen`, `comfyui_video`, `voxcpm_tts`）。

## Input
- `brief` artifact（含面料属性、3 个成衣概念、目标平台、时长、调性）
  - 含 `metadata.tunables_inherited`（如本次继承自 retrospective，作为参数默认值的 upper bound）
- `scene_plan.json` artifact（来自 STAGE 2）— 提供每幕时间码与镜头意图
- `frame_blueprint.json` artifact（来自 STAGE 2）— **核心输入**
  - 每帧 spec 含 frame_id / asset_kind / aspect_ratio / composition_rule /
    motion_rules / img2img_strength / comfyui_steps / comfyui_denoise_strength
- 用户面料原图（路径在 `assets/fabric_source/<filename>`，由 idea stage 提供）

## HARD CONSTRAINT
**ALL image and video generation MUST use img2img** — 沿用 v1.1 强约束以保留面料质感与图案。每次调用 `image_selector` 时 `init_image` 必须指向面料原图 / 已生成的成衣图；`comfyui_video` 的 `init_image` 必须指向成衣图。

## Process

> **⚠️ 路径规范核心警告**：  
> Universal Harness (omo.py) 始终在 OpenMontage 根目录执行！因此所有针对项目内工件的读取/写入（如 `artifacts/...`, `assets/...`）以及生成素材的路径，都**必须带有 `projects/{project_name}/` 前缀**。切勿直接写相对路径，否则会污染根目录！

### Step 1: 按 frame_blueprint 逐帧规划生成顺序

```python
import json
from pathlib import Path

# 请自行替换为实际的项目名
project_name = "<project_name>"
project_dir = Path(f"projects/{project_name}")

# 加载 STAGE 2 产出的 frame_blueprint
with open(project_dir / "artifacts/frame_blueprint.json", encoding="utf-8") as f:
    frame_bp = json.load(f)
asset_manifest = {"assets": [], "linked_frame_index": {}}

# 按 frame_id 顺序生成，每一帧从 frame spec 取所有参数（不让 agent 改）
for frame in frame_bp["frames"]:
    if frame["asset_kind"] == "garment_image":
        _generate_garment_image(frame)
    elif frame["asset_kind"] == "garment_video":
        _generate_garment_video(frame)
    elif frame["asset_kind"] == "fabric_macro_video":
        _generate_fabric_macro_video(frame)
    elif frame["asset_kind"] == "narration_wav":
        _generate_tts(frame)
    elif frame["asset_kind"] == "cover_base_image":
        _generate_cover_image(frame)

# 最后写入 asset_manifest.json，每条都引用 frame.frame_id
```

**绝对禁止**脱离 frame_blueprint.json 凭直觉干活——这是 v2.3 时
"agent 脑补构图"导致最终素材与设计脱节的根因。

### Step 2: TTS 配音 + 词级时间戳
对 frame_blueprint 中所有 `asset_kind = "narration_wav"` 的帧，按顺序生成 wav。旁白文本取自 STAGE 2 的 `script.json` sections（不再从 brief 推断）。

```python
with open(project_dir / "artifacts/script.json", encoding="utf-8") as f:
    script = json.load(f)
# 按 script["sections"][].id 与 tts_frame["tts_segment_id"] 对齐
for tts_frame in [f for f in frame_bp["frames"] if f["asset_kind"] == "narration_wav"]:
    seg_text = next(
        (s["text"] for s in script["sections"] if s["id"] == tts_frame["tts_segment_id"]),
        ""
    )
    result = voxcpm_tts.execute({
      "text": seg_text,
      "voice_description": brief["voice_description"],  # 用统一的 voice_description 保证多段音色一致
      "seed": 42,                                         # 固定 seed，保证多段音色一致
      "output_path": str(project_dir / f"assets/tts/{tts_frame['frame_id']}.wav")
    })
    # asset_manifest 记录 tts_frame.frame_id → wav 路径
```

- 多段一致音色：固定 `voxcpm_tts`，同一 voice_description + 固定 seed 保证不漂移
- 调用前读 `.agents/skills/voxcpm-tts/SKILL.md`

### Step 2.5: 背景音乐 (BGM)
调用 `pixabay_music` 获取与调性匹配的背景音乐，确保在 `asset_manifest` 中生成 `type: "music"` 的资产，以供后续合成使用。

```python
tool = registry.get("pixabay_music")
bgm_result = tool.execute({
    "query": f"{brief.get('style', 'fashion')} background music",
    "duration": script.get("total_duration_seconds", 30),
    "output_path": str(project_dir / "assets/audio/bgm.mp3")
})
# 必须在 asset_manifest 记录:
# {"id": "bgm_1", "path": bgm_result.data["output"], "type": "music", "kind": "music"}
```

### Step 3: 成衣图（img2img）
**【核心红线】：严禁使用通用提示词。必须从 `frame_blueprint.composition_rule` +
`prompt_injection_from_design_system` 字段中读取视觉规则，动态拼接强约束 Prompt。**

对 frame_blueprint 中所有 `asset_kind = "garment_image"` 的帧生成。Prompt 强制注入：
1. **背景与光影**：从 `frame.prompt_injection_from_design_system` 取（如 `dark moody
   studio background (#08050a), chiaroscuro lighting`），保证与 `visual_design.json` 的
   `palette` / `design_system` 对齐。
2. **构图原则**：从 `frame.composition_rule` 读。
   - ⚠️ **绝对居中**，留出纯净背景 — 但**不要把 HTML 文字排版意图写进生图 Prompt 里**！
     排版由后续 `hyperframes_compose` 工具处理。frame_blueprint 的 composition_rule 已经
     把"主体摆放" 与 "字幕位置"分开来写 — 只取前者进生图 Prompt。

范例（v3.0 改写成从 frame_blueprint 取值，不再从 brief.design_system / beat_plan 直接取）：
```python
# v3.0：frame = 当前帧从 frame_blueprint 取的 spec dict
# 固定使用 google_imagen 工具，模型 gemini-3.1-flash-lite-image
tool = registry.get("google_imagen")
result = tool.execute({
    "prompt": f"A high-end editorial photograph of {frame['garment_concept_ref']}. "
              f"{frame['composition_rule']}. "
              f"{frame['prompt_injection_from_design_system']}. "
              f"Fabric: {brief['fabric_description']}.",
    "image_path": frame["init_image_path"],       # 面料原图路径，用于 img2img
    "aspect_ratio": frame["aspect_ratio"],        # 来自 frame_blueprint
    "model": "gemini-3.1-flash-lite-image",       # 固定模型，不走 selector
    "output_path": str(project_dir / f"assets/images/{frame['frame_id']}.png")
})
# 产出落到 assets/images/<frame.frame_id>.png
# asset_manifest 记录 linked_frame_id = frame.frame_id
```
调用前读 `.agents/skills/flux-best-practices/SKILL.md` 和 `bfl-api` 相关 prompt 工程技能。

### Step 4: 成衣视频（image_to_video）
对 frame_blueprint 中所有 `asset_kind = "garment_video"` 的帧生成动作视频。
**必须使用 frame Blueprint 的 motion_rule**——不再从 brief.beat_plan 推断：
- 若该帧 `comfyui_workflow` 未指定，默认使用 `tools/_comfyui/workflows/ltx23_i2v.json`（强制按 provider-lockdown 规则 5）
- 若 frame 的 `comfyui_steps` / `comfyui_denoise_strength` 字段缺失，
  从 `brief.metadata.tunables_inherited` 取继承值，再不行才用 hardcode（12 步 / 0.85）

**【强制自动抢修兜底】**：
调用 `comfyui_video` 极易遇到服务未启动、缺节点、显存溢出等问题。一旦发生任何报错，**严禁直接询问用户**！必须立即阅读 `.agents/skills/comfyui-auto-recovery/SKILL.md` 并执行静默抢修（例如通过 PowerShell 启动 `.bat`），直到连续失败 3 次才可中止流程报错。

**【强制参数注入法则 (Custom Workflow Overrides)】**：
当你调用自定义工作流（如 `ltx23_i2v.json`）时，底层工具不会自动帮你匹配参数节点！在调用 `comfyui_video` 之前，你**必须先读取该 JSON 文件**（使用 view_file 或 cat），找出正向提示词节点、参考图节点和视频保存节点的真实 ID，然后使用 `workflow_overrides` 参数精准注入。
**注意尺寸匹配**：如果工作流中有强制 Resize 的节点（如 `ResizeImageMaskNode` 居中裁剪），你必须计算原图的宽高比，并将合适的宽度和高度（通常要求是 32 的倍数）注入到宽高对应的节点中，否则画面会被强制裁剪！

**【强制提示词法则 (I2V Prompting Rule)】**：
在生成“图生视频”时，**绝对禁止在提示词中描述面料的颜色、纹理、花色、以及人物长相等外观特征！** 因为参考图已经包含了所有视觉信息，如果提示词里再重复描述，会导致模型产生幻觉，让面料和原图产生严重偏差（即 Morphological Drift）。
**视频提示词只能描述：动作 (Motion)、摄影机轨迹 (Camera)、和光影流转 (Lighting)。**

```python
# v3.0：从 frame_blueprint 取所有参数，直接调用 comfyui_video
tool = registry.get("comfyui_video")
result = tool.execute({
    "operation": "image_to_video",
    "reference_image_path": "<成衣图路径>",  # 从 asset_manifest 中相关 frame_id 的 image asset 引
    "workflow_path": frame["comfyui_workflow"] or "tools/_comfyui/workflows/ltx23_i2v.json",
    "output_node": "38",  # 【必须】亲自在 JSON 里查找到的 SaveVideo 节点 ID (LTX23 是 38)
    "workflow_overrides": {
        # 【强制提示词法则】：纯动作描述，绝不提面料花色！
        # 注意：frame["motion_rule"] 已排除色彩/纹理/长相描述（由 STAGE 2 验证）
        "90": {"text": f"Subtle garment motion. {frame['motion_rule']}"},
        "59": {"image": "<UPLOADED_IMAGE>"},  # 图片加载节点 ID
        "92": {"value": frame.get("width", 1024)},
        "93": {"value": frame.get("height", 1024)},
        "94": {"steps": frame["comfyui_steps"]},
        "89": {"strength": frame["comfyui_denoise_strength"]},
        "101": {"value": int(frame["time_range"]["end"] - frame["time_range"]["start"])}  # 动态传入视频时长
    }
})
# 产出落到 assets/video/<frame.frame_id>.mp4
# asset_manifest 记录 path = str(project_dir / f"assets/video/{frame['frame_id']}.mp4")
# linked_frame_id = frame.frame_id
```
调用前读 `.agents/skills/comfyui/SKILL.md` 和 `.agents/skills/comfyui-auto-recovery/SKILL.md`。

### Step 5: 面料特写视频
对面料原图 image_to_video。同上，**所有 motion_rule 只描述镜头拉近 / 光影流转 / 面料轻微飘动**。motion_rule 与 frame_blueprint.match。
```python
# 提取时长并注入节点 101
duration_seconds = frame["time_range"]["end"] - frame["time_range"]["start"]
# ...调用 comfyui_video 并设置 workflow_overrides={"101": {"value": int(duration_seconds)}}
```

### Step 6: 封面底图（img2img）
对 frame_blueprint 中所有 `asset_kind = "cover_base_image"` 的帧生成。

```python
# 固定使用 google_imagen，模型 gemini-3.1-flash-lite-image
tool = registry.get("google_imagen")
for cover_frame in [f for f in frame_bp["frames"] if f["asset_kind"] == "cover_base_image"]:
    result = tool.execute({
        "prompt": f"A high-end editorial cover image. "
                  f"{cover_frame['composition_rule']}. "
                  f"{cover_frame['prompt_injection_from_design_system']}. "
                  f"Fabric: {brief['fabric_description']}.",
        "image_path": cover_frame["init_image_path"],  # 面料原图或成衣图
        "aspect_ratio": cover_frame["aspect_ratio"],
        "model": "gemini-3.1-flash-lite-image",
        "output_path": str(project_dir / f"assets/images/{cover_frame['frame_id']}.png")
    })
```

### Step 7: 写 asset_manifest
每条 asset 记录（v3.0 核心改造）：
- `path`（项目内路径）
- `kind`（`narration_wav` / `narration_timestamps` / `garment_image` / `garment_video` / `fabric_macro_video` / `cover_base_image` / `music`）
- `type`（对于音乐必须标注 `"type": "music"` 供合成总监识别）
- `img2img_source`（指向 fabric 原图 / 成衣图）
- `linked_frame_id`（**v3.0 必填**：引用 STAGE 2 frame_blueprint.frames[].frame_id）
- `linked_concept_id`（关联的 brief.angle_options 概念 id，0 = 面料特写 / 封面）
- `parameters_used`（v3.0 新增：实际用的 strength / steps / aspect_ratio 等，便于 STAGE 6 retrospective 追踪 / 调参）

## Layer 3 Skills 必读
- `.agents/skills/flux-best-practices/SKILL.md` 和 `bfl-api`（Google Imagen prompt 工程）
- `.agents/skills/comfyui/SKILL.md`
- `.agents/skills/comfyui-auto-recovery/SKILL.md`
- `.agents/skills/voxcpm-tts/SKILL.md`

## Reviewer Self-Review
- [ ] **CRITICAL**: 所有 generation 均为 img2img
- [ ] 成衣图 / 封面图均以面料原图 / 成衣图为 image_path
- [ ] 配音 wav 已生成
- [ ] **v3.0 CRITICAL**: 每条 asset_manifest 条目含 `linked_frame_id` 与 `parameters_used`，引用 STAGE 2 frame_blueprint 的 frame_id
- [ ] 调用前读 `flux-best-practices` / `comfyui` / `voxcpm-tts` 对应 Layer 3 skill
- [ ] Layer 3 skill 已在写 prompt 前读过
- [ ] 未出现调用 `image_selector` / `video_selector` / `tts_selector` 的违规行为
- [ ] 未出现直接 import 底层 provider（GoogleImagen / ComfyUI 直接 import）的违规代码

## Output
Schema-valid `asset_manifest` artifact，所有条目含 `img2img_source` 与
`linked_frame_id` 字段。