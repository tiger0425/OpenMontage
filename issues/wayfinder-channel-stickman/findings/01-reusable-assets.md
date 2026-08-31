# 01 本机可复用资产盘点

## 1. auto-dub 下载/转录/混音/字幕可复用

**结论：直接复用 CLI 为唯一合规入口，不直接 import 底层函数。**

* 入口：`bin/auto_dub.py`（SKILL `.agents/skills/auto-dub/SKILL.md:22`）+ `apps/auto-dub/batch/batch_runner.py` + `apps/auto-dub/config.yaml` + `projects/auto-dub/tracking.db`
* 可复用阶段：
  * `downloading`：yt-dlp 下载（`resume_download.py:13 yt-dlp`，`bin/auto_dub.py scan/downloading`）
  * `transcribing`：Whisper 本地转录（`.agents/skills/video-understand/scripts/understand_video.py:312 load_model`，`apps/auto-dub` 内置 `transcriber`）
  * `mixing`：100ms 串行排队混音（`SKILL.md:274`，禁止拉伸/压缩帧率，SRT 重同步）
  * `rendering`：FFmpeg 字幕烧录 + `concat filter` 拼接（已修复 time_base 跳变，禁止回退 `concat demuxer + -c copy`）
* 禁止项：`AGENTS.md:NG` 禁止写 ad-hoc 脚本直调 `yt-dlp/whisper/ffmpeg`，必须走 `bin/auto_dub.py` 或 `bin/omo.py`；重算力 `render-assets/run-heavy/render-video` 必须派 Compute Worker 子 Agent 并以 `--json` 回报（SKILL.md:102-125）。
* 缺口：auto-dub 为英文→中文配音全流程，本管线需「选片→分集→结构借鉴改写」在上游，需新增轻任务阶段，复用其后期能力。

## 2. 角色动画 SVG rig

**结论：不应复用旧 character-animation 手调 rig，应直接复用 `ink-theater` + `InkPuppet` 动捕方案。**

* 引擎：`ink-theater/README.md:15-18` 五能力：`inkPath/inkRibbon` 手绘线、`boil`、`springEase`、`fabrik/ mascot` IK、`parts` 构件；确定性 seek-safe（闭式弹簧、boil 走 GSAP stepped-seed、IK via onUpdate）。
* 角色正确路径：`ink-theater/README.md:53` **Ink Puppet**：`mocap/bvh2clip.mjs` 离线将 BVH→2D clip（hips 相对 + root motion），`ink-puppet.js:create/maso t/drawIn/choreograph` 运行时播放。
  * 调用：`InkPuppet.create(mount,{cx,ground,boil})` → `p.drawIn(tl,{start})` → `InkPuppet.choreograph(tl,p,[{clip:"wave"},{clip:"walk"}])`（`ink-puppet.js:33,57,76`）
  * 动作库：`mocap/catalog.json` 12 个 CMU 免费 clip：`walk/run/climb/march/shuffle/jump/kick/sit/wave/dance_spin/dance_glide/twist`（README.md:73），Agent 只选名不手调；扩展 `node mocap/add-motion.mjs`。
* 预览与 QA：`ink-theater/examples/mocap-figure/index.html` 为可 lint 自包含范例（同 `waving-stickman.html` 已验证）；HyperFrames 单 paused GSAP timeline → MP4。
* 缺口：需为 channel-stickman 复制 `ink-theater.js + ink-puppet.js + clips.js + assets/patrickhand.ttf` 到产线项目，并按本频道固定 `cx/ground/headR/strokeWidth`。

## 3. google_imagen 契约

**结论：经 `image_selector` 路由，契约见 `tools/graphics/google_imagen.py:94-144`。**

* 必需：`prompt`（≤480 tokens）；可选：`aspect_ratio ∈ 1:1,3:4,4:3,9:16,16:9`（默认 1:1）、`width/height` 自动映射最近 ratio（`_dims_to_aspect_ratio`）、`model ∈ imagen-4.0-generate/fast/ultra, gemini-3.1-flash-lite-image/gemini-3.1-flash-image`（默认 `gemini-3.1-flash-lite-image` 免费层）、`number_of_images 1-4`、`image_path + image_strength 0-1` 支持 img2img、`output_path`。
* 不支持：`negative_prompt`、`seed`、`custom_size`（`supports.seed=False` `supports.custom_size=False` `supports.aspect_ratio=True`）。
* 调用：必须走 `image_selector`（`AGENTS.md:NG`），底层 provider 为 `google_imagen`；`TOOL_STATUS` 取决于 `GOOGLE_API_KEY/GEMINI_API_KEY` 或 Vertex SA（`get_status`）。
* 缺口：本管线要求「无字底稿 + 后期叠字」，需用 `gemini-3.1-flash-image`（文字更稳）但仍走无字 prompt，中文文字一律后期 HTML/FFmpeg 叠加。

## 4. wrc-pipeline 分集经验可复用

* 规格：`apps/wrc/specs/` + `schemas/artifacts/wrc_episode.schema.json` 定义分幕；CLI `bin/wrc.py` 流程：下载→转录→LLM 脚本（**脚本闸门人审**）→ IndexTTS 配音（emotion 0.325）→ 抽帧/截片→ hyperframes 合成→ BGM 混音→ 成品包。
* 可复用：**按叙事内容拆集** 而非等长切；脚本闸门后才放行重算力；`LESSONS.md` 实战经验；轻/重拆分与 `--json` 回报契约与 auto-dub 一致。
* 缺口：wrc 为竖屏 9:16 拉力解说，本管线为横屏心理学科普，需调整分集阈值（约 2min/集）与标题/简介模板。

## 5. LLM 脚本改写先例

* auto-dub：`translating` 阶段 LLM 英→中翻译（术语表 `config.yaml:glossary`），多人访谈有 `translation_review.md` 人审（`SKILL.md:350`）。
* wrc：LLM 生成分幕脚本，**人审后** 才进入 TTS/合成（SKILL 路由）。
* 本仓库无独立「文本改写工具」，LLM 调用由各管线 `pipeline_automator` 内置；channel-stickman 应新增「结构借鉴+改写」LLM 阶段，复用术语表与 `approve-review` 人审模式，产出 `script.json` 供下游 `choreograph` 选 clip。
