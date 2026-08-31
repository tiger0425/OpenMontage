# ref-remake 管线 manifest 与阶段设计定案

> 工单《管线 manifest 与阶段设计定案》决议（2026-08-26 人审确认，七项决策全部按推荐采纳）。

## 一、总览

- **name**: `ref-remake`，`category: custom`，`stability: beta`，`default_checkpoint_policy: guided`
- **reference_input**: `supported: true`，`analysis_depth: standard`，`analysis_tools: [video_downloader, transcriber, scene_detect, frame_sampler]`
- **extensions**: `custom_scripts: true`，`custom_playbooks: true`，`custom_skills: true`，`custom_tools: false`（MiniMaxImage 参考图参数属对既有工具类的补强，见工单《MiniMaxImage 工具补强 reference_image 参数》）
- **orchestration**: `mode: guided`，`budget_default_usd: 0.00`（生图按需计费，单集估算见下），`max_revisions_per_stage: 3`，`max_wall_time_minutes: 60`
- 人审点：script【闸门A】+ review【人审】共两处 `human_approval_default: true`；发布手动。
- 轻重拆分：assets（IndexTTS 配音 + MiniMax 生图）与 compose（HyperFrames 渲染）为重命令，按 AGENT_GUIDE 多代理协议派 Compute Worker 执行并以 `--json` 单行回报；其余阶段主会话直跑。

## 二、阶段表

| # | 阶段 | produces | 人审 | 关键工具 | 要点 |
|---|------|----------|------|----------|------|
| 1 | fetch | `fetch_report` + `video_analysis_brief` | 否 | video_downloader, transcriber, scene_detect, frame_sampler | yt-dlp 下载+字幕；Whisper 转录（`input_path` 参数）；抽帧供分析。本地文件输入同路径复用 |
| 2 | brief | `knowledge_brief`（含 `split_proposal` 字段） | 否 | — | 内嵌**参考视频分析子阶段**（sub_stages，condition 参考输入存在）：video-reference-analyst 五维分析 + 2-3 差异化概念 + 样片先行。拆集提案在此产出（何时拆/拆几集/内容边界） |
| 3 | script | `script` + `redline_scan` | **是（闸门A）** | — | 结构借鉴+改写中文脚本；相似度扫描 JSON（0.75/0.45）为闸门必需附件；**拆集提案随本闸门一并人审**。改写红线细则见工单《二创改写红线操作定义》 |
| 4 | scene_plan | `scene_plan` | 否 | — | 按脚本分幕，用**估算时长**（~250 字/分）；单集为主，超长拆集时各集独立出 scene_plan |
| 5 | assets | `asset_manifest`（TTS 实测时长回填） | 否 | tts_selector, image_selector | **先 TTS**（IndexTTS 克隆音色，固定 seed），ffprobe 实测每段时长回填；再 MiniMax 生图（V2 风格 + 参考图锚点，无字底稿）；3-4 张/幕按旁白语义切分。重命令 → Worker |
| 6 | compose | `composition_report` | 否 | hyperframes_compose, video_compose（+audio_mixer 可选） | 按 **TTS 实测时长**建时间轴（字数比例兜底）；HyperFrames index.html（无字图 + HTML 叠字；`data-layout-allow-overflow`；中文字体 `@font-face local()`）；`--resolution portrait --fps 30`。**默认无 BGM**，audio_mixer 仅在用户指定时启用。重命令 → Worker |
| 7 | review | `final_review` | **是（人审）** | minimax-m3-vision（抽帧质检） | 抽帧 + MiniMax-M3 视觉质检（逐张容错 422）；角色一致性、无文字图、与旁白同步 |
| 8 | package | `publish_copy` + `cover_manifest` + `note_manifest` + `publish_log` | 是（发布前确认成品包） | — | 双平台文案（抖音+小红书）+ 封面 + **图文笔记变体**（抽帧 6-9 张 + 文案，模板见工单《图文笔记文案模板》）；AI 标识声明内置；人工手动上传 |

## 三、产物与 schema 映射（全复用既有 schema）

| 产物 | schema | 备注 |
|------|--------|------|
| fetch_report | `schemas/artifacts/fetch_report.schema.json` | 复用 |
| video_analysis_brief | `schemas/artifacts/video_analysis_brief.schema.json` | 复用（参考视频分析） |
| knowledge_brief | `schemas/artifacts/knowledge_brief.schema.json` | 复用；执行期在 metadata 或新字段承载 `split_proposal`（拆集提案），或按需加字段 |
| script | `schemas/artifacts/script.schema.json` | 复用；redline_scan 作为同目录 JSON（或 script metadata 字段） |
| scene_plan | `schemas/artifacts/scene_plan.schema.json` | 复用 |
| asset_manifest | `schemas/artifacts/asset_manifest.schema.json` | 复用；TTS 段长回填 |
| composition_report | `schemas/artifacts/composition_report.schema.json` | 复用 |
| final_review | `schemas/artifacts/final_review.schema.json` | 复用 |
| publish_copy | `schemas/artifacts/publish_copy.schema.json` | **执行期需补 douyin 平台分支**（现仅 bilibili/xiaohongshu） |
| cover_manifest | `schemas/artifacts/cover_manifest.schema.json` | **执行期需补 douyin 封面分支**（9:16 竖版规格，数值以《图文笔记双平台规格调研》为准） |
| note_manifest | `schemas/artifacts/note_manifest.schema.json` | 复用（现为面料教育专用，执行期按 ref-remake 语境通用化或新建专用 schema） |
| publish_log | `schemas/artifacts/publish_log.schema.json` | 复用 |

## 四、费用估算基线（单集）

- 生图：幕数 × 3-4 张/幕 × $0.005/张（image-01）≈ 20-40 幕 → $0.3-0.8；含 30% 重试缓冲
- TTS：本地 GPU（IndexTTS），免费；渲染：本地，免费
- 预算默认 $0.00（按需），提案时给出实际估算

## 五、执行期落码清单（本图不落码，供落地会话使用）

1. `pipeline_defs/ref-remake.yaml`（按上表写满各阶段 review_focus / success_criteria）
2. `skills/pipelines/ref-remake/<stage>-director.md` × 8（fetch / brief / script / scene_plan / assets / compose / review / package）
3. `styles/ref-remake.yaml` playbook（V2 风格块，见工单《V2 风格规范与锚点沉淀》）
4. `publish_copy` / `cover_manifest` schema 补 douyin 分支；`note_manifest` 通用化
5. MiniMaxImage 工具补 `reference_image` 参数（工单《MiniMaxImage 工具补强 reference_image 参数》）
6. 脚本模板沉淀：gen_frames（带锚点）/ gen_tts / build_timeline / build_index（源自 `projects/outsmart-cn/scripts/`）
7. 改写相似度扫描脚本：轻量 n-gram 重合率 + LLM 逐句自查（红线 0.75/0.45，见《二创改写红线操作定义》），产出 `redline_scan` JSON
