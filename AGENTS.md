# OpenMontage

**MANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## Universal Harness Enforcement (For ALL Agents)

**MANDATORY**: Any external intelligent agent (Cursor, Windsurf, OpenClaw, Codex, etc.) is strictly FORBIDDEN from attempting to execute the workflow manually or writing custom ad-hoc scripts to generate assets. 

To create or progress a video project, you MUST use the Universal Harness CLI (`bin/omo.py`). This CLI wraps the state machine and ensures you cannot bypass the pipeline.

**Usage:**
1. Check state: `python bin/omo.py status --project <name> --pipeline <type>`
2. Get strict stage prompt: `python bin/omo.py start-stage --project <name> --pipeline <type>`
3. Submit JSON artifact: `python bin/omo.py submit-artifact --project <name> --stage <stage> --file <path> --pipeline <type>`

You are a worker responding to the Harness. Do not guess the next steps. Do what `start-stage` tells you to do, submit it, and stop if the harness tells you to wait for human approval.

## Orchestration Red Lines (ABSOLUTE RULES)

To prevent agents from hallucinating code or skipping the pipeline, you MUST follow these constraints for every video request:
1. **NO AD-HOC SCRIPTS**: Do NOT write custom Python scripts (e.g. `generate_garment.py`, `test_imagen.py`) in the project directory to call tools. You must act as the pipeline orchestrator: read the YAML manifest, call tools interactively (e.g. via `python -c` or temporary scratch scripts), and write the canonical JSON artifacts.
2. **USE SELECTORS ONLY**: When generating media, you MUST route through `image_selector`, `video_selector`, or `tts_selector`. NEVER hardcode or directly import underlying providers (e.g. `GoogleImagen`, `ElevenLabsTTS`) in your tool calls.
3. **RESPECT CHECKPOINTS**: You MUST stop and wait for user approval at the stages defined by `human_approval_default: true` in the pipeline manifest (e.g. the `idea` stage). Do NOT generate final assets before the creative brief and render_runtime are explicitly approved.
4. **NO SINGLE-SHOT HTML GENERATION**: When building HyperFrames videos, you are strictly FORBIDDEN from writing `index.html` manually in one go. You MUST follow the 6-step pipeline: generate STORYBOARD.md -> await approval -> use `audio.mjs` for timestamps -> design `visual-design.md` -> use individual sub-agents per frame -> assemble via `assemble-index.mjs` and `transitions.mjs`. Bypassing this pipeline is a critical failure.
5. **PRE-FLIGHT CHECKLIST (MANDATORY)**: Before executing ANY stage from the harness, you MUST stop and complete these 4 steps in your mind:
   - **Step 1 (Read)**: Read the pipeline YAML definition and the schema of the artifact you are required to produce.
   - **Step 2 (Understand)**: Understand the holistic context. Do not just look at your current stage; understand what the previous stages produced and what the next stages need.
   - **Step 3 (Cross-Reference Assets)**: Explicitly list out all required asset types (Images, Video, Text Overlays, Audio). Cross-reference the input JSONs (e.g., `frame_blueprint`) against your target schema to ensure no field (like `overlay_notes`) is dropped.
   - **Step 4 (Execute)**: Only AFTER mapping the data completely may you begin writing code or calling tools to generate the JSON artifact.

## Auto-Dub Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/auto-dub/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 搬运视频 / 搬运 / 自动配音 / 中文配音
- auto-dub / auto dub / autodub
- 处理视频 / 处理队列 / 推进流水线
- 查看配音进度 / 配音状态
- 导入播放列表 / 添加频道
- 发布视频 / 标记已发布
- 有哪些视频没完成 / 还有多少视频

**What the skill teaches you:**
- Full directory layout and database schema
- All CLI commands (`bin/auto_dub.py`)
- VoxCPM TTS silent-file detection and repair
- 100 ms serial-queue mixing strategy
- Natural-language → CLI command mapping
- Quick-start checklist for new sessions

**CRITICAL**: For Auto-Dub tasks, the ONLY permitted execution entry point is
`python bin/auto_dub.py <subcommand>`. Do NOT write ad-hoc Python scripts
to call pipeline internals directly.

## Chinese-Subtitle Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/chinese-subtitle/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 加中文字幕 / 中文字幕 / 加字幕 / 烧字幕
- 字幕版 / 字幕搬运 / 中英字幕
- subtitle only / chinese subtitle / burn subtitles
- 给视频加字幕 / 只加字幕不配音
- 原视频加中文字幕

**What the skill teaches you:**
- 只给原视频加中文字幕（不生成配音、不替换音轨）的完整流程
- CLI 命令（`bin/auto_subtitle.py`）
- 与 auto-dub 的区别：无 TTS、无 GPU、无数据库，单视频轻量处理
- Natural-language → CLI command mapping

**CRITICAL**: For Chinese-subtitle tasks, the ONLY permitted execution entry point is
`python bin/auto_subtitle.py <subcommand>`. Do NOT write ad-hoc Python scripts
to call pipeline internals directly.

## ErChuang（抖音二创）Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/erchuang/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 二创 / 抖音二创 / 做成抖音版 / erchuang / 复用二创管线
- 去原作头像和广告 / 拆集连载 / 换我的音色做解说
- 把这条 auto-dub 视频做成抖音节奏片 / 日产那种二创
- **任何「已有中文成品/原片 + 抖音横屏 + 重写文案 + 换音色」的二创意图**

**What the skill teaches you:**
- 六步流程：zones 禁区 → 拆集文案(humanizer-bilibili) → synth 逐句原片情感配音 → montage 干净素材 → overlay(hyperframes) → mux → auto-dub 成品包确认归档
- CLI 命令（`bin/erchuang.py` zones/synth/montage/mux）、manifest 示例、桥协议 emo_audio_prompt
- 规格（音色/情感 0.6/两集 96-100s/禁区 SFace）与已踩坑速查

**CRITICAL**: For ErChuang tasks, use `bin/erchuang.py` + `apps/indextts-bridge` client（emo_audio_prompt 已入协议）。
GPU TTS / hyperframes render 须派 Compute Worker 以 `--json` 单行回报。文案须过 humanizer-bilibili。

## WRC-Pipeline Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/wrc-pipeline/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 跑WRC管线 / wrc管线 / wrc.py / 跑拉力管线
- 处理拉力视频 / 搬运WRC视频 / 拉力视频转中文 / 拉力视频转竖屏
- WRC 视频转中文 / 拉力赛车视频中文配音 / 做拉力解说视频
- 用 wrc 管线跑这个视频 / 发个 YouTube 拉力链接处理
- **任何「YouTube URL + 中文/抖音/竖屏/搬运/拉力/赛车解说」组合意图**——用户给出 YouTube 链接并要求转中文/竖屏/配音/搬运时，若内容为 WRC/拉力题材即路由本管线（拿不准先读 SKILL.md 判断）

**What the skill teaches you:**
- 完整流程：下载 → 转录 → LLM 脚本（**脚本闸门人审**）→ IndexTTS 配音（情绪 0.325）→ 抽帧/截片 → hyperframes 合成渲染 → BGM 混音 → 成品包 → 人工上传抖音
- CLI 命令（`bin/wrc.py`）与会话内执行流（轻/重拆分）
- 各环节规格（`apps/wrc/specs/`）+ 分幕 schema（`schemas/artifacts/wrc_episode.schema.json`）+ 背景库（`background_library/wrc/`）
- 实战经验（`apps/wrc/specs/LESSONS.md`，跑管线前必读）

**CRITICAL**: For WRC pipeline tasks, the ONLY permitted execution entry point is
`python bin/wrc.py <subcommand>`. Do NOT write ad-hoc Python scripts to call
pipeline internals directly. 重命令（render-assets / render-video / run-heavy）
必须派 Compute Worker 执行并以 `--json` 单行回报；脚本闸门必须等用户确认后才放行。

## Lofi-Tiger Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/lofi-tiger/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 做条lofi / 做一条lofi / 做小老虎视频 / 做小老虎音乐 / lofi-tiger
- Tiger & Tea / lofi tiger / 生成lofi / lofi视频 / 森林木屋 / 雨夜咖啡馆
- **任何「小老虎 / Tora + lofi / 音乐 / 放松 / 学习 / YouTube」意图**——用户要求制作治愈系小老虎电台内容时即路由本技能

**What the skill teaches you:**
- 频道全景与凭证（Tiger & Tea / Channel ID / 已授权的专用 OAuth Token）
- 角色圣经铁律（小圆耳、严禁耳机、宽松绿卫衣、角落复古收音机、35mm 胶片电影质感）
- 5×5×5 内容组合矩阵与单集装配
- 四步生产闭环：主图（视觉人审）→ 微动母本（Mid-Crossfade 闭环）→ 音频自回环混音（-14 LUFS）→ 秒级极速混流成片（1~3h）→ YouTube 全自动发布
- 自然语言指令映射与执行规范

## VOX-Course Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/vox-course/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 生成课程视频 / 做课程视频 / 录课程视频 / 做个课程
- vox-course / course.py / 课程管线 / 跑课程管线
- 硬核技术视频 / 技术课程视频 / VOX科技视频 / 科技解说视频
- 把这段技术文档做成视频 / 课程内容生成视频 / 把课程大纲转成视频
- **任何「课程内容/技术文档/大纲 + 视频/VOX/中文配音/字幕」意图**——用户要求制作专业技术或课程视频时即路由本管线

**What the skill teaches you:**
- 完整流程：创建项目（`new`）→ 去AI化剧本（`script`，**脚本闸门人审**）→ 剧本校验放行（`approve-script`）→ IndexTTS2 纯净克隆配音与毫秒级字幕对齐（`synth`）→ HyperFrames 纸张剪贴风装配（`compose`）→ 1080P/4K HEVC 渲染（`render`）→ 发布成品包（`package`）
- 四大铁律：文案 38 条彻底去AI化与年份汉字化、IndexTTS2 纯净克隆与稳态采样参数锁死、画面卡片与台词 100% 咬合、全屏毫秒级高对比度同步字幕条 + 片尾 4.0 秒视觉与音乐优雅留白
- CLI 入口：`python bin/course.py <subcommand>`（轻量 `run` 直达闸门，重量 `run-heavy` 算力压制）
- 规范与模板：`apps/vox-course/specs/`（`LESSONS.md`, `course_episode.schema.json`）与 `apps/vox-course/template/`

**CRITICAL**: For VOX-Course tasks, the ONLY permitted execution entry point is
`python bin/course.py <subcommand>`. Do NOT write ad-hoc Python scripts to call
pipeline internals directly. 涉及重任务（synth / render / run-heavy）可派 Compute Worker 执行并以 `--json` 单行回报；脚本闸门必须经用户或规范审查后方可放行。

## Console-Remake（深色控制台设计复刻）Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/console-remake/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- 控制台复刻 / console-remake / 深色控制台 / 跑控制台管线 / 控制台设计复刻
- 把这条视频做成控制台版中文 / 用控制台世界做二创 / HUD 风格讲解
- **任何「参考视频（纯动效讲解、无人物无实拍）+ 中文版 + 控制台/HUD/终端视觉」意图**——路由本管线
- 触发词与 WRC/erchuang（实拍搬运）重叠时：内容为纯动态图形讲解视频即路由本管线

**What the skill teaches you:**
- 世界宪法 `apps/console-remake/specs/design-system.md`：九种控制台零件（空心描边框/数据格阵/等宽胶囊/发丝线/巨型数字/连接箭头/刻度槽/米白纸面板/通知 toast）+ 三类连接件（引线/括线/端刻度）+ 动作动效库（travel/push/shift/erase/leak/stack/grow） + 色彩语义（红=问题·成本｜琥珀=占用｜蓝=模型·查询｜青=结果）+ 常驻 HUD 框架（章节翻页/进度轨/画框/颗粒底纹）+ 禁用清单（圆角实心卡片一律禁）
- 两条设计铁律：**元素不许孤立**（每幕至少一处联系：引线/括线/箭头/同色呼应/发丝线分区）；**动词必须演出来**（台词说"塞/删/漏/叠"时对应 motion 动作必须落在同一句窗口内）
- 完整流程：`new`（下载/转录/抽帧）→ 写 `artifacts/episode.json`（中文脚本+控制台分幕+chapters，**先样片验收世界**）→ `script`（校验+红线扫描，**脚本闸门人审**）→ `approve-script` → `synth`（IndexTTS2 克隆配音，重）→ `compose`（烘焙音频+装配 HyperFrames 子合成）→ `render`（重）→ `package`（AI 底稿+排版封面 16:9/4:3 + 单文档 publish_copy.txt）→ `archive`（exports/<id>/）
- 零 AI 生图（封面除外）、零实拍、几乎零 API 成本；音画咬合 = 零件入场由旁白句起点驱动；样式/HUD/背景改动必须全片重渲

**CRITICAL**: For Console-Remake tasks, the ONLY permitted execution entry point is
`python bin/console_remake.py <subcommand>`. Do NOT write ad-hoc Python scripts to call
pipeline internals directly. 重命令（synth / render / run-heavy）必须派 Compute Worker
执行并以 `--json` 单行回报；脚本闸门（approve-script）必须等用户确认后才放行。

## VOX-Collage（纸质拼贴科普与纪录片）Skill Routing

When the user's message contains ANY of the following triggers, you MUST read
`.agents/skills/vox-collage/SKILL.md` BEFORE taking any action:

**Trigger phrases (Chinese or English):**
- VOX拼贴 / 纸片拼贴 / 纪录片拼贴 / vox-collage / 跑拼贴管线
- 拼贴科普视频 / 纸质纪录片 / 9:16拼贴 / 16:9拼贴
- **任何「真实素材/照片 + 纸质拼贴 + 调查/纪录片/科普短视频/长视频」意图**——路由本管线

**What the skill teaches you:**
- 完整流程：`new`（创建项目、双画幅 16:9/9:16、预设母版）→ `refs`（Wikimedia Commons 抓取真实照片+版权清单）→ `script`（去AI化剧本、**脚本闸门人审**）→ `approve-script` → `synth`（IndexTTS 纯净配音、读 WAV 头精确秒数）→ `dataliao`（16:9/9:16 资料图生成）→ `stills`（Qwen-Image-Edit 2.1 风格化，锁定项目 master_sheet）→ `motion`（MiniMax H3 核心幕图层动画）→ `compose`（HyperFrames 装配、2% 呼吸慢漂移）→ `render`（无字幕纯净母版）→ `subtitle`（FFmpeg ASS 3D 挤出立体字幕）
- 四大铁律：真实素材入画（拒绝 AI 臆造）、基准图母版前置风格锚定、6 类构图范式轮转与动静混编策略（hero_motion + 2% slow drift）、读 WAV 头真实秒数排布时间轴
- CLI 入口：`python bin/vox_collage.py <subcommand>`（轻量 `run` 直达闸门，重型 `run-heavy` 算力压制）

**CRITICAL**: For VOX-Collage tasks, the ONLY permitted execution entry point is
`python bin/vox_collage.py <subcommand>`. Do NOT write ad-hoc Python scripts to call
pipeline internals directly. 涉及重任务（synth / stills / motion / render / run-heavy）
可派 Compute Worker 执行并以 `--json` 单行回报；脚本闸门必须经用户或规范审查后方可放行。




