# Map Director — Pipeline Forge

## 职责

把 style_dna 映射为可执行的管线蓝图：阶段结构、工具绑定、命名、审批点、预算。产出 `blueprint` + `decision_log`。这是**决策点**，产出后必须人工确认。

## 流程

### 1. 阶段映射

把引擎状态机映射到 OpenMontage 标准 8 阶段（idea → proposal → script → scene_plan → assets → edit → compose → publish），按引擎复杂度裁剪：

- 引擎的"选题生成/领域选择"状态 → `idea`
- 引擎的"时长/成本"状态 → `proposal`（此处锁定 `render_runtime` 与预算）
- 引擎的"脚本"状态 → `script`
- 引擎的"配音"状态 → **并入 `assets`**（脚本批准后才产生付费资产，这是 OpenMontage 惯例）
- 引擎的"节拍/句子拆分"状态 → `scene_plan`（节拍表：时间码 + 旁白词覆盖）
- 引擎的"每拍图像提示词"状态 → `assets`（agent 直调 `image_selector`，**不产 .txt 手动喂**）
- 引擎的"视频提示词"状态 → `edit` + `compose`
- 引擎的"缩略图"状态（若有）→ `publish`

映射规则：
- 每个引擎状态必须落在至少一个阶段；无状态被丢弃
- 引擎的"逐状态交互"（等待用户输入）统一翻译为"阶段 checkpoint + 人工审批"
- 引擎的"可选源材料 PDF"状态 → idea 阶段的可选输入（有则吸收，无则用内置默认）

### 2. 工具绑定

对每个需要生成物的阶段，从注册表绑定真实可用的工具。**必须运行时查询** `registry.provider_menu_summary()`，不得凭记忆：

| 能力 | 绑定方式 |
|------|----------|
| 图像 | `image_selector`（记录首选提供商与备选，如 google_imagen 默认 / FLUX 升级路径） |
| 旁白 | `tts_selector`（记录参考音色路径约定：spk_audio_prompt → INDEXTTS_VOICE_REF → repo/voice_reference.wav） |
| 音乐 | `music_gen` 或 `music_search`（pixabay）或 `music_library` |
| 音效 | `freesound_music` 或程序化合成 |
| 合成 | `video_compose` + `render_runtime`（hyperframes / remotion / ffmpeg，按引擎的视频提示词形态选择） |

每个绑定记录：`{tool, provider_preference, fallback, notes}`。

### 3. 命名与治理

- slug：kebab-case，语义化（如 `vox-paper-collage`），检查 `pipeline_defs/` 与 `styles/` 无冲突
- `default_checkpoint_policy: manual_all`（前期全人工，硬性）
- `budget_default_usd`：按引擎规模估（30s 冒烟 ≈ $0.6，1 分钟 ≈ $1.5，按图数 × $0.05 估算）
- 语言：`narration_language` 参数（默认英文；引擎规则需双语化时注明）
- 非标准阶段名（如果有）：列出需在 `lib/checkpoint.py` `CANONICAL_STAGE_ARTIFACTS` 补充的映射

### 4. 产出 `blueprint`：

```json
{
  "version": "1.0",
  "slug": "vox-paper-collage",
  "category": "custom",
  "description": "一句话描述",
  "stage_map": [{"engine_state": "STATE 4", "stage": "script", "note": "Fern 连续旁白"}],
  "tool_bindings": [{"stage": "assets", "capability": "image_generation", "tool": "image_selector", "provider_preference": "google_imagen", "fallback": "flux", "notes": "..."}],
  "render_runtime": "hyperframes",
  "narration_language": "en",
  "budget_default_usd": 3.0,
  "checkpoint_policy": "manual_all",
  "approval_defaults": {"idea": true, "proposal": true, "script": true, "scene_plan": true, "assets": false, "edit": false, "compose": false, "publish": true},
  "new_canonical_artifacts": []
}
```

同时产出 `decision_log`（category: "pipeline_forge_map"，记录命名、工具绑定、渲染路径选择与理由）。

## 质量要求

- 工具绑定的每个 provider 都要在注册表摘要里核实存在（不存在的标为"需配置"并在 notes 注明环境变量）
- 引擎要求但本机不可用的能力（如视频生成模型）→ 在 blueprint 里记录 `unavailable_capabilities` 与替代路径（如 HyperFrames 确定性动画替代视频模型），**不得静默丢弃**
- 引擎的"聊天式顺序"若有强制的审批节奏（如配音前必须听样音），映射为对应阶段的人工审批点

## 成功标准

- `blueprint` 含完整 stage_map（无引擎状态遗漏）、tool_bindings、slug、预算、审批默认值
- `decision_log` 记录命名与工具绑定决策
