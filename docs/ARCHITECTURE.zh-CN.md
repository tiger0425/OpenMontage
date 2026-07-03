# OpenMontage 架构

> 最后更新: 2026-03-28 | 基于代码探索推导，非既有文档。

OpenMontage 是一个**由 Agent 编排的视频制作平台**。LLM 编程助手（Claude Code、Cursor、Copilot 等）充当编排者——读取流水线清单、遵循技能指令、调用 Python 工具、记录检查点状态。系统中没有 Python 运行时编排器；Agent _本身就是_控制平面。

---

## 顶层流程

```
用户提供主题/创意
        |
        v
Agent 读取流水线清单（YAML）
        |
        v
对每个阶段：
   1. Agent 读取阶段导演技能（Markdown）
   2. Agent 通过工具注册表调用 Python 工具
   3. Agent 写入检查点（JSON）及产出物
   4. Agent 使用 meta/reviewer 技能进行自我审查
   5. 人工审批关卡（如已配置）
        |
        v
最终视频输出
```

---

## 仓库布局

```
OpenMontage/
├── lib/                    # 核心运行时基础设施（Python）
│   ├── config_model.py     # Pydantic 配置：LLM、预算、检查点、输出、路径
│   ├── checkpoint.py       # 流水线状态持久化与阶段转换
│   ├── pipeline_loader.py  # YAML 清单加载与校验
│   ├── media_profiles.py   # 平台化渲染配置（YouTube、TikTok 等）
│   ├── env_loader.py       # .env 变量管理
│   └── providers/          # （预留给未来的 provider 抽象层）
│
├── tools/                  # 57+ Python 工具实现
│   ├── base_tool.py        # 抽象基类——工具契约
│   ├── tool_registry.py    # 自动发现的单例注册表
│   ├── cost_tracker.py     # 预算治理（估算→预留→结算）
│   ├── analysis/           # 转写、场景检测、帧采样、视频理解
│   ├── audio/              # TTS（ElevenLabs、OpenAI、Piper）、音乐生成、混音、增强
│   ├── avatar/             # 数字人动画、口型同步
│   ├── enhancement/        # 超分、背景移除、人脸增强/修复、调色
│   ├── graphics/           # 图像生成（FLUX、DALL-E、Recraft、本地扩散模型）、素材库、图表、代码片段、数学动画
│   ├── publishers/         # （预留）
│   ├── subtitle/           # 基于时间戳的 SRT/VTT 字幕生成
│   └── video/              # 13 个视频生成 provider、合成、拼接、裁剪
│
├── pipeline_defs/          # YAML 流水线清单
├── schemas/                # JSON Schema 定义——用于校验
│   ├── artifacts/          # 11 个产出物 Schema（brief → publish_log）
│   ├── checkpoints/        # 检查点状态 Schema
│   ├── pipelines/          # 流水线清单 Schema
│   ├── styles/             # 风格手册 Schema
│   └── tools/              # 工具专属 Schema
│
├── skills/                 # 第二层：OpenMontage 专属 Agent 指令
│   ├── core/               # FFmpeg、Remotion、WhisperX、调色技能
│   ├── creative/           # 视频编辑、增强、数据可视化、提示词工程
│   ├── meta/               # reviewer、checkpoint-protocol、skill-creator
│   └── pipelines/          # 各流水线的阶段导演技能
│
├── .agents/skills/         # 第三层：外部技术技能（FFmpeg、HyperFrames、GSAP 等）
├── styles/                 # 视觉风格手册（YAML）+ 加载器
├── remotion-composer/      # Node.js/React——Remotion 视频合成渲染器
├── tests/                  # 契约测试、QA 集成测试、评估框架
├── docs/                   # 最佳实践指南、会话交接、审计
└── config.yaml             # 全局运行时配置
```

---

## 核心架构原则

### 1. Agent 优先的编排

系统中**不存在 Python 编排器**。LLM Agent：
- 读取流水线清单以获知阶段顺序
- 读取每个阶段的导演技能获取详细指令
- 调用工具、评估结果、做出创意决策
- 写入检查点以在阶段间持久化状态

Python 仅提供**工具和持久化**。所有智能逻辑存在于技能指令（Markdown）和流水线清单（YAML）中。

### 2. 运行时无 LLM API Key

OpenMontage 在运行时不会调用 LLM API。用户 IDE 中运行的编程助手_本身就是_LLM。需要生成能力的工具（图像、视频、TTS）直接调用领域专属 API（ElevenLabs、fal.ai、HeyGen 等），而非通用 LLM 端点。

### 3. 双 Provider 支持

每个能力必须同时支持 **API provider**（云端、付费）和**本地/开源替代方案**（免费、依赖 GPU）。选择器模式强制执行这一原则，路由至可用的任何选项。

---

## 工具系统

### BaseTool 契约

所有工具继承自 `BaseTool`（ABC）并声明：

| 字段 | 用途 |
|-------|---------|
| `name`、`version` | 标识 |
| `tier` | CORE、VOICE、ENHANCE、GENERATE、SOURCE、ANALYZE、PUBLISH |
| `capability` | 功能描述（如 `tts`、`image_generation`、`video_post`） |
| `provider` | 服务提供方（如 `elevenlabs`、`ffmpeg`、`selector`） |
| `runtime` | LOCAL、LOCAL_GPU、API、HYBRID |
| `stability` | EXPERIMENTAL、BETA、PRODUCTION |
| `dependencies` | 所需二进制（`cmd:ffmpeg`）、环境变量（`env:ELEVENLABS_API_KEY`）、Python 包（`python:torch`） |
| `input_schema`、`output_schema` | 输入/输出的 JSON Schema |
| `fallback_tools` | 有序回退链 |
| `agent_skills` | 链接到第三层知识技能 |
| `resource_profile` | CPU、RAM、VRAM、磁盘、网络要求 |
| `retry_policy` | 最大重试次数、退避策略 |

**必需方法：** `execute(inputs) -> ToolResult`

`ToolResult` 携带：`success`、`data`、`artifacts`（文件路径）、`error`、`cost_usd`、`duration_seconds`、`seed`、`model`。

### 工具注册表

`ToolRegistry` 是一个单例，通过 `pkgutil.walk_packages()` 自动发现所有 `BaseTool` 子类。无需手动注册。

关键查询方法：
- `get_by_capability("tts")`——所有 TTS 工具
- `get_by_provider("elevenlabs")`——所有 ElevenLabs 工具
- `get_available()`——依赖项已满足的工具
- `find_fallback("elevenlabs_tts")`——解析回退链
- `support_envelope()`——供 Agent 消费的完整能力报告
- `gpu_required_tools()`、`network_required_tools()`

### 选择器模式

三个选择器工具抽象了多 provider 能力：

| 选择器 | 能力 | 选择方式 |
|----------|-----------|---------------------|
| `tts_selector` | 文字转语音 | 按任务匹配度、质量、可控性、可靠性、成本、延迟、连续性对已发现的 provider 排序 |
| `image_selector` | 图像生成 | 从实时注册表中对已发现的 provider 排序；不硬编码 provider 顺序 |
| `video_selector` | 视频生成 | 从实时注册表中对已发现的 provider 排序；用户显式指定时尊重用户偏好 |

选择器的路由依据：用户显式设置的偏好 > 跨可用 provider 的评分排序。它们在 provider 间透明地适配输入 Schema。

### 按类别划分的工具清单

**分析（4 个）：** transcriber（WhisperX）、scene_detect、frame_sampler、video_understand（CLIP/BLIP-2）

**音频（13 个）：** elevenlabs_tts、google_tts、openai_tts、piper_tts、doubao_tts、voxcpm_tts、tts_selector、music_gen、freesound_music、pixabay_music、suno_music、audio_mixer、audio_enhance

**数字人（2 个）：** talking_head（SadTalker/MuseTalk）、lip_sync（Wav2Lip）

**增强（5 个）：** upscale（Real-ESRGAN）、bg_remove（rembg/U2Net）、face_enhance、face_restore（CodeFormer/GFPGAN）、color_grade（FFmpeg LUTs）

**图形（13 个）：** flux_image、grok_image、google_imagen、openai_image、recraft_image、local_diffusion、pexels_image、pixabay_image、image_selector、code_snippet、diagram_gen、math_animate（ManimCE）、image_gen（已弃用）

**字幕（1 个）：** subtitle_gen

**视频（18 个）：** grok_video、heygen_video、higgsfield_video、veo_video、kling_video、runway_video、minimax_video、wan_video、hunyuan_video、cogvideo_video、ltx_video_local、ltx_video_modal、pexels_video、pixabay_video、video_selector、video_compose（FFmpeg）、video_stitch、video_trimmer

---

## 流水线系统

### 流水线清单

每个流水线是 `pipeline_defs/` 中的 YAML 文件，定义：

```yaml
name: animated-explainer
version: "2.0"
category: generated          # talking_head | generated | hybrid | screen_recording | animation | cinematic | custom
default_checkpoint_policy: guided

orchestration:
  mode: executive-producer
  skill: pipelines/explainer/executive-producer
  budget_default_usd: 2.00
  max_revisions_per_stage: 3

compatible_playbooks:
  - clean-professional
  - flat-motion-graphics

stages:
  - name: research
    skill: pipelines/explainer/research-director
    produces: [research_brief]
    tools_available: []
    checkpoint_required: false
    human_approval_default: false
    review_focus: [...]
    success_criteria: [...]
  # ... 直至 publish
```

### 可用流水线

| 流水线 | 类别 | 描述 |
|----------|----------|-------------|
| `animated-explainer` | generated | AI 驱动的解说视频，含调研、旁白、视觉、音乐 |
| `animation` | animation | 动态图形、动态排版 |
| `avatar-spokesperson` | talking_head | 数字人驱动的演讲视频 |
| `character-animation` | animation | 本地装配卡通角色，含 SVG 骨架、姿势库、GSAP 时间线、HyperFrames 渲染 |
| `cinematic` | cinematic | 预告片、先导片、情绪驱动剪辑 |
| `clip-factory` | custom | 从长素材批量生成短视频片段 |
| `hybrid` | hybrid | 源素材 + AI 生成辅助视觉 |
| `localization-dub` | custom | 给现有视频添加字幕、配音和翻译 |
| `podcast-repurpose` | hybrid | 播客精彩片段转视频 |
| `screen-demo` | screen_recording | 软件屏幕录制和演示 |
| `talking-head` | talking_head | 以实拍素材为主的演讲视频 |
| `framework-smoke` | custom | 最小化冒烟测试——用于框架验证 |

### 标准阶段流程

大多数生产流水线遵循规范的 8 阶段流程：

```
research → proposal → script → scene_plan → assets → edit → compose → publish
```

每个阶段：
1. 拥有一个**阶段导演技能**（给 Agent 的 Markdown 指令）
2. 声明 `tools_available`（Agent 可调用哪些工具）
3. **产出**一个或多个规范产出物
4. 设有 `review_focus` 标准和 `success_criteria`
5. 可要求在进入下一阶段前获得**人工审批**

专用流水线可插入领域专属阶段。例如，
`character-animation` 在 `scene_plan` 之前增加
`character_design` 和 `rig_plan`，
然后将 HyperFrames 工作区和最终交付物输出到
`projects/<project-name>/renders/final.mp4`。

---

## 检查点系统

检查点将流水线状态以 JSON 形式持久化到项目的 `pipeline/` 目录中。

```json
{
  "version": "1.0",
  "project_id": "my-video",
  "stage": "script",
  "status": "completed",
  "timestamp": "2026-03-28T10:00:00Z",
  "checkpoint_policy": "guided",
  "human_approval_required": false,
  "human_approved": true,
  "artifacts": { "script": { ... } },
  "review": { ... },
  "cost_snapshot": { ... }
}
```

**状态值：** `pending` | `in_progress` | `awaiting_human` | `completed` | `failed`

**检查点策略：**
- `guided`——在关键创意阶段检查点，机械阶段自动推进
- `manual_all`——每个阶段都需人工审批
- `auto_noncreative`——自动推进，除非阶段是创意性的（assets、edit）

**函数：** `write_checkpoint()`、`read_checkpoint()`、`get_latest_checkpoint()`、`get_completed_stages()`、`get_next_stage()`

### 规范产出物（11 种类型，全部经 JSON Schema 校验）

| 产出物 | 阶段 | 包含内容 |
|----------|-------|----------|
| `research_brief` | research | 领域分析、数据点、受众洞察、切入角度 |
| `proposal_packet` | proposal | 概念选项、制作计划、成本估算、审批关卡 |
| `brief` | idea | 标题、钩子、要点、风格、调性、平台、时长 |
| `script` | script | 带时间戳的分段，含增强提示、发音指导 |
| `scene_plan` | scene_plan | 场景定义，含类型、描述、时长 |
| `asset_manifest` | assets | 生成的资产，含路径、来源工具、场景关联 |
| `edit_decisions` | edit | 编辑剪切决策，含出入点时间 |
| `render_report` | compose | 输出元数据（格式、分辨率、时长） |
| `publish_log` | publish | 平台发布条目及状态 |
| `review` | （任意） | 审查者反馈和审批记录 |
| `cost_log` | （任意） | 预算追踪条目 |

---

## 预算治理

`CostTracker` 在流水线全程强制执行开销控制。

### 生命周期

```
estimate(tool, operation, $) → entry_id
        |
reserve(entry_id)          # 锁定预算
        |
reconcile(entry_id, $)     # 记录实际消费
```

### 预算模式

| 模式 | 行为 |
|------|----------|
| `observe` | 追踪开销，不强制执行 |
| `warn` | 超支时记录警告，允许执行 |
| `cap` | 拒绝超出剩余预算的操作 |

### 控制项
- **总预算**（默认：$10.00）
- **预留保留金**（默认：10%）——作为安全余量保留
- **单次操作审批阈值**（默认：$0.50）——超过此金额暂停等待审批
- **新付费工具审批**——首次使用任何付费工具需确认
- 持久化到各项目的 `cost_log.json`

---

## 三层知识架构

```
第三层: .agents/skills/          外部技术知识（47 个技能）
        "技术如何运作"               FFmpeg、ElevenLabs API、FLUX、Remotion、Three.js 等
              ^
              | agent_skills[] 引用
              |
第二层: skills/                  OpenMontage 惯例
        "本项目如何使用该技术"       流水线集成、质量检查清单、产出物映射
              ^
              | 阶段技能引用
              |
第一层: tools/ + pipeline_defs/  可执行能力 + 编排定义
        "存在什么以及何时使用"       BaseTool 契约、流水线清单
```

每个工具的 `agent_skills[]` 字段将第一层链接到第二层和第三层。例如：
- `video_compose.agent_skills = ["remotion-best-practices", "remotion", "ffmpeg"]`
- `tts_selector.agent_skills = ["text-to-speech", "elevenlabs", "openai-docs"]`

---

## 配置

### config.yaml

```yaml
llm:
  provider: anthropic
  temperature: 0.7
  max_tokens: 4096

budget:
  mode: warn
  total_usd: 10.00
  reserve_pct: 0.10
  single_action_approval_usd: 0.50

checkpoint:
  policy: guided
  storage_dir: pipeline

output:
  default_format: mp4
  default_codec: libx264
  default_audio_codec: aac
  default_resolution: 1920x1080
  default_fps: 30
  default_crf: 23

paths:
  pipeline_dir: pipeline
  library_dir: library
  styles_dir: styles
  skills_dir: skills
  output_dir: output
```

所有配置通过 `lib/config_model.py` 中的 Pydantic 模型进行校验。

### 环境变量（.env）

| 变量 | 使用者 | 用途 |
|----------|---------|---------|
| `ELEVENLABS_API_KEY` | elevenlabs_tts、music_gen | TTS、音乐、音效 |
| `OPENAI_API_KEY` | openai_tts、openai_image | TTS 回退、DALL-E 3 |
| `XAI_API_KEY` | grok_image、grok_video | Grok 图像编辑/生成、Grok 视频生成 |
| `FAL_KEY` | flux_image、kling_video、veo_video、minimax_video、recraft_image | fal.ai 托管模型（FLUX、Veo、Kling、MiniMax、Recraft） |
| `HEYGEN_API_KEY` | heygen_video | 多 provider 视频生成 |
| `PEXELS_API_KEY` | pexels_image、pexels_video | 素材库媒体资源 |
| `PIXABAY_API_KEY` | pixabay_image、pixabay_video | 素材库媒体资源 |
| `GOOGLE_API_KEY` | google_imagen、google_tts | Google Imagen 图像、Google Cloud TTS |
| `RUNWAY_API_KEY` | runway_video | Runway Gen-3/Gen-4 直连 |
| `HIGGSFIELD_API_KEY` + `HIGGSFIELD_API_SECRET` | higgsfield_video | Higgsfield 多模型视频 |
| `MODAL_LTX2_ENDPOINT_URL` | ltx_video_modal | 自托管 LTX-2 |
| `VIDEO_GEN_LOCAL_ENABLED` | 本地视频工具 | 启用本地 GPU 生成 |
| `VIDEO_GEN_LOCAL_MODEL` | wan、hunyuan、ltx、cogvideo | 选择本地模型 |

---

## 视觉风格系统

`styles/` 中的风格手册为流水线定义视觉语言：

- `clean-professional.yaml`——企业、精致外观
- `flat-motion-graphics.yaml`——现代扁平设计
- `minimalist-diagram.yaml`——技术、极简图表

由 `styles/playbook_loader.py` 加载。每条流水线在其清单中声明 `compatible_playbooks`。依据 `schemas/styles/playbook.schema.json` 进行校验。

---

## 媒体配置

`lib/media_profiles.py` 中定义了各平台专属的渲染配置：

| 配置 | 分辨率 | 宽高比 | 备注 |
|---------|-----------|--------|-------|
| `youtube_landscape` | 1920x1080 | 16:9 | 标准 YouTube |
| `youtube_4k` | 3840x2160 | 16:9 | 4K YouTube |
| `youtube_shorts` | 1080x1920 | 9:16 | 最长 60 秒 |
| `instagram_reels` | 1080x1920 | 9:16 | 最长 90 秒 |
| `instagram_feed` | 1080x1080 | 1:1 | 正方形 |
| `tiktok` | 1080x1920 | 9:16 | 竖屏 |
| `linkedin` | 1920x1080 | 16:9 | 横屏 |
| `cinematic` | 2560x1080 | 21:9 | 超宽 |

每种配置指定编解码器、音频编解码器、CRF、像素格式、最大文件大小、最大时长和字幕格式。`ffmpeg_output_args(profile)` 生成对应的 FFmpeg 参数。

---

## 合成运行时

OpenMontage 拥有多运行时合成层。三个引擎运行在 `video_compose` 背后，在提案阶段选定并锁定在 `edit_decisions.render_runtime` 中：

### Remotion（基于 React）

`remotion-composer/` 中的独立 Node.js/React 子项目，使用 [Remotion](https://www.remotion.dev/)。

- **React 18** + **Remotion 4.0** + **TypeScript 5.3**
- 处理现有的场景组件栈（`text_card`、`stat_card`、图表、字幕、`TalkingHead`、`CinematicRenderer`）
- 脚本：`start`（预览工作室）、`build`（渲染）、`upgrade`

### HyperFrames（HTML/CSS/GSAP）

通过 `npx hyperframes` 消费（无需拉取 monorepo）。运行时要求：Node.js ≥ 22、FFmpeg、`npx`。

- 处理动态排版、产品宣传片、发布短片、网站转视频、注册表区块以及 SVG/GSAP 角色骨架
- 驱动：`tools/video/hyperframes_compose.py` 在 `projects/<name>/hyperframes/` 下构建工作区，然后运行 `lint → validate → render`
- 第三层技能位于 `.agents/skills/hyperframes*/`；第二层指南位于 `skills/core/hyperframes.md`
- `character-animation` 流水线使用 HyperFrames 作为生产渲染包。浏览器预览仅作为 QA/调试产物，不是渲染路径。

### FFmpeg（回退 / 简单剪切）

- 当无需合成时处理纯拼接/裁剪
- 也作为后处理操作处理字幕烧录

`video_compose` 读取 `edit_decisions.render_runtime` 并通过 `_render_via_hyperframes`、`_remotion_render` 或 `_render_via_ffmpeg` 进行分发。禁止静默运行时替换——当选定的运行时不可用时，工具返回结构化阻断信息。完整决策矩阵见 `AGENT_GUIDE.md` → "Composition Runtimes (Inside video_compose)" 和 `skills/core/hyperframes.md`。

---

## 测试架构

```
tests/
├── contracts/              # 阶段 0-3：工具契约校验、Schema 检查、注册表测试
├── qa/                     # 集成测试：TTS、图像生成、音乐、音频混音、视频合成/拼接、端到端
├── eval/                   # 金标准场景回放框架——用于回归测试
├── pipelines/              # 流水线级测试
├── tools/                  # 各工具测试
└── styles/                 # 风格手册测试
```

**契约测试**验证每个工具满足 `BaseTool` 契约：标识字段、Schema、依赖声明、继承关系。

**QA 测试**调用真实工具（使用真实 API/二进制），检查输出质量。

**评估框架**（`tests/eval/replay_harness/`）使用基于容差的对比方式回放金标准场景，以适用随机性输出。

---

## 系统依赖

**必需：**
- Python >= 3.10
- FFmpeg（约 15 个工具使用）

**可选（扩展能力）：**
- Node.js（用于 Remotion 合成器）
- GPU + CUDA（用于本地视频/图像生成）
- Piper（离线 TTS）
- ManimCE（数学动画）
- Mermaid CLI（图表生成）

**Python 包：** pyyaml、pydantic、jsonschema、python-dotenv（核心）；pytest、pytest-asyncio（开发）；torch、torchvision、torchaudio（GPU）

---

## 关键设计决策

1. **无运行时编排器**——LLM Agent 读取 YAML + Markdown 并驱动一切。这使系统可调试（只需阅读技能文件）且与模型无关。

2. **基于检查点的续传**——任何阶段都可以失败，流水线从最后一个检查点恢复。无需重新运行已完成的阶段。

3. **Schema 校验的产出物**——每个阶段的输出在写入检查点之前都要经过 JSON Schema 校验。防止错误传播。

4. **预算作为一等概念**——执行前进行成本估算、预算预留和结算。Agent 无法静默超支。

5. **选择器模式替代硬编码 provider**——能力优雅降级。缺少某个 API Key？选择器自动回退到下一个 provider 或本地替代方案。

6. **技能文件而非代码承载智能**——创意决策、质量检查清单、审查标准、提示词模板存在于 Markdown 技能文件中，而非 Python 代码。这意味着 Agent 的行为可以通过编辑文本文件来调整，无需改代码。
