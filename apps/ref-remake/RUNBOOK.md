# ref-remake 会话内执行手册（RUNBOOK）

> 用 agent 会话（不经 bin/omo.py harness 强制）直接驱动 ref-remake 管线跑一条视频的完整操作指南。
> 与 wrc 的 `bin/wrc.py` CLI 模式不同：ref-remake 没有独立 CLI，执行契约 = `pipeline_defs/ref-remake.yaml`（manifest）+ 各阶段 director skills + `lib/checkpoint.py` 断点。
> 设计定案：`issues/wayfinder-ref-remake/findings/01-pipeline-manifest-design.md`。

## 一句话

**「跑 ref-remake + YouTube URL」** → 下载转录抽帧 → 参考分析+拆集提案 → 中文脚本（红线扫描挂脚本闸门人审）→ IndexTTS 配音 + MiniMax 锚点生图 → HyperFrames 合成渲染（9:16）→ M3 抽帧质检人审 → 双平台成品包 + 小红书图文卡片 → 人工手动上传。

## 会话内执行流

| 步骤 | 阶段 | 动作 | 谁执行 | 产出 |
|---|---|---|---|---|
| 1 | fetch | `video_downloader` 下载（yt-dlp，URL/本地文件）→ `transcriber` Whisper 转录（`input_path` 参数）→ `frame_sampler`+`scene_detect` 抽帧 | 主 Agent（轻）| `fetch_report` + `video_analysis_brief` + `assets/source/` |
| 2 | brief | 读 director skill；五维参考分析（video-reference-analyst：content/pacing/structure/style/hook，**只出差异化概念，不进分镜**）；拆集提案（>8min 可分时）；知识提取 | 主 Agent（轻）| `knowledge_brief`（含 `split_proposal`） |
| 3 | script【闸门A】 | 读 director skill + findings/02 红线；写中文脚本（结构借鉴+改写）；跑 `apps/ref-remake/scripts/redline_scan.py` 产出 `redline_scan` | 主 Agent + LLM（轻）| `script` + `redline_scan`（JSON）|
| 4 | **人审闸门A** | 用户审/改脚本 + 扫描结果 + 拆集提案（或口述，agent 代改）| **用户** | 放行或打回 |
| 5 | scene_plan | 分幕映射旁白段、V2 点缀式视觉方案、估算时长（~250 字/分）| 主 Agent（轻）| `scene_plan` |
| 6 | assets【重】 | TTS 优先（IndexTTS 克隆音色，seed 20260825，ffprobe 实测段长回填）→ MiniMax 生图（V2 风格块 verbatim + 锚点 `background_library/ref-remake/anchor/ahhuang_anchor.png`，3-4 张/幕，无字底稿，422 跳过）；可用 `apps/ref-remake/scripts/gen_tts.py` / `gen_frames.py` 模板 | **Compute Worker**（重，`danger-full-access`）| `asset_manifest` |
| 7 | compose【重】 | 按实测时长建时间轴（`build_timeline.py`）→ HyperFrames index.html（`build_index.py`，无字图+HTML 叠字、`data-layout-allow-overflow`、`@font-face` 中文声明、删 index.sample.html）→ check → render `--resolution portrait --fps 30` | **Compute Worker**（重，`danger-full-access`）| `composition_report` + `renders/final.mp4` |
| 8 | review【人审】 | 抽帧 + MiniMax-M3 视觉质检（逐张容错 422）；角色一致性/无文字图/与旁白同步/音频干净/平台适配 | 主 Agent + 用户 | `final_review` |
| 9 | **人审闸门B** | 用户验收成片（可要求重跑指定阶段）| **用户** | 放行或打回 |
| 10 | package | 双平台文案（抖音标题+1-3 话题；小红书标题≤20 字+3-6 话题）+ 3:4 封面 + 图文卡片（6-9 张 3:4，生成原图+文字卡片排版层合成）+ AI 声明（正文+发布勾选）| 主 Agent（轻）| `publish_copy` + `cover_manifest` + `note_manifest` + `publish_log` |
| 11 | 交付 | 打开成品包验收；改 → 定位重跑对应阶段 | 主 Agent | 成品包 `exports/<slug>/` |
| 12 | 发布 | **手动上传**抖音/小红书（标题/简介/封面/图文）；发布时勾选「AI 生成」声明 | 用户 | — |

## 每阶段必读

| 阶段 | director skill | 关键约束 |
|---|---|---|
| fetch | `skills/pipelines/ref-remake/fetch-director.md` | 事实提取，无幻觉；转录为空即 blocker |
| brief | `skills/pipelines/ref-remake/brief-director.md` | 参考分析只服务概念与风格，产出不进分镜（红线）|
| script | `skills/pipelines/ref-remake/script-director.md` | 红线 0.75/0.45；改写义务五项全满足；健康措辞降级；闸门必需附件=redline_scan |
| scene_plan | `skills/pipelines/ref-remake/scene-director.md` | V2 点缀式；无字底稿；不描述原片镜头 |
| assets | `skills/pipelines/ref-remake/assets-director.md` | TTS 先；锚点必传；422 跳过不阻塞；派 Worker |
| compose | `skills/pipelines/ref-remake/compose-director.md` | workdir=根目录；实测时长时间轴；lint+validate 通过才 render |
| review | `skills/pipelines/ref-remake/review-director.md` | M3 抽帧质检；对照锚点 |
| package | `skills/pipelines/ref-remake/package-director.md` | AI 声明不可省略；图文卡片=原图+文字卡片 |

## 硬纪律（同 AGENTS.md / AGENT_GUIDE）

- **主 Agent 不跑重命令**：assets / compose 派 Compute Worker，回报 `--json` 单行，禁止粘贴完整 stdout。
- **沙箱**：IndexTTS 生成、hyperframes 渲染、npm 命令必须 `danger-full-access`；npm 前设 `$env:npm_config_cache="E:\YifuAIForge\OpenMontage\.npm-cache"`。
- **GPU 锁**：`lib/gpu_lock.py`，勿并行两个 TTS 任务（IndexTTS 占 8-16GB VRAM）。
- **脚本闸门是人的环节**：脚本+红线扫描+拆集提案用户确认后才进资产生成，不得跳过。
- **无字底稿**：AI 图内禁止文字；中文文字全部 HyperFrames/排版层叠加。
- **AI 标识**：成片**不烧录角标**（保持画面专业）；发布时双平台勾选「AI 生成」声明，平台侧自动叠加角标（《标识办法》2025-09-01，findings/05：创作者侧以勾选声明为主）。
- **workdir 坑**：build_index 类脚本的 index.html 路径相对根目录，必须从 OpenMontage 根目录运行。

## 工具/脚本速查

```bash
# 转录
python -c "from tools.analysis.transcriber import Transcriber; print(Transcriber().execute({'input_path': r'projects/<slug>/assets/source/video.mp4', 'output_path': r'projects/<slug>/assets/source/transcript.json'}))"

# 红线扫描（脚本闸门必需附件）
python apps/ref-remake/scripts/redline_scan.py --rewrite <script.md> --original <transcript.txt> --out <redline_scan.json>

# 配音 / 生图 / 时间轴 / 合成（config 驱动模板，见各脚本 docstring）
python apps/ref-remake/scripts/gen_tts.py --config projects/<slug>/artifacts/tts_config.json
python apps/ref-remake/scripts/gen_frames.py --config projects/<slug>/artifacts/frames_config.json
python apps/ref-remake/scripts/build_timeline.py --config projects/<slug>/artifacts/timeline_config.json
python apps/ref-remake/scripts/build_index.py --config projects/<slug>/artifacts/index_config.json

# 校验（改完任何落地文件后跑）
python apps/ref-remake/scripts/validate_pipeline.py

# 断点（lib/checkpoint.py，可选；omo.py 也走同一套）
python bin/omo.py status --project <slug> --pipeline ref-remake
```

## 项目目录约定

```
projects/<slug>/                      # kebab-case 取自视频标题
├── artifacts/                        # 每阶段 canonical JSON（fetch_report, knowledge_brief, script, redline_scan, scene_plan, asset_manifest, composition_report, final_review, publish_copy, cover_manifest, note_manifest, publish_log）
├── assets/
│   ├── source/                       # video.mp4, transcript.json, frames/
│   ├── audio/                        # seg_*.wav（IndexTTS）
│   ├── images/                       # s*_*.png（MiniMax 锚点生图，无字）
│   └── notes/                        # 图文卡片 card_*.png + note_copy.md
├── index.html                        # HyperFrames 合成（build_index 产物）
├── exports/<slug>/                   # 成品包（final.mp4, cover_3x4.png, publish_copy.json, ...）
└── renders/final.mp4                 # 定版
```

## 断点续跑

- 每阶段完成写 `pipelines/<slug>/checkpoint_<stage>.json`（lib/checkpoint.py 协议），`completed`/`awaiting_human` 需带 canonical artifact。
- 会话中断后：`omo.py status` 看完成阶段 → 从 next stage 继续；闸门阶段停在 `awaiting_human`。
- 预算/成本：单集生图约 $0.3-0.8（幕数 × 3-4 张 × $0.005，含 30% 重试缓冲）；TTS/渲染本地免费。
