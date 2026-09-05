---
name: auto-dub
description: >
  YouTube 视频自动搬运与中文 AI 配音系统（Auto-Dub）的完整操作指南。
  适用于：下载英文 YouTube 视频、自动转录（Whisper）、LLM 中文翻译、
  本地 GPU TTS 配音（VoxCPM）、混音合成（FFmpeg）、字幕烧录与归档。
  触发词：搬运视频、自动配音、auto-dub、处理视频、中文配音、
  导入播放列表、查看进度、发布视频。
metadata:
  tags: "auto-dub, youtube, localization, tts, voxcpm, ffmpeg, bilibili, chinese-dub"
---

# Auto-Dub — YouTube 视频自动搬运与中文 AI 配音系统

## 📌 系统概述

Auto-Dub 是内置于 OpenMontage 的批量视频搬运与中文配音系统。
它从 YouTube 下载英文视频，经过 **转录 → 翻译 → 配音 → 混音 → 压制** 五个阶段，
输出可直接上传至 B 站的中文配音版视频（含字幕）。

**项目根目录：** `e:/YifuAIForge/OpenMontage`  
**主入口 CLI：** `bin/auto_dub.py`  
**App 源码：** `apps/auto-dub/`  
**配置文件：** `apps/auto-dub/config.yaml`  
**数据库：** `projects/auto-dub/tracking.db`

---

## 🗂️ 目录结构

```
OpenMontage/
├── bin/
│   └── auto_dub.py              # CLI 主入口（所有操作都走这里）
├── apps/auto-dub/
│   ├── config.yaml              # 频道订阅、筛选规则、术语表
│   ├── batch/
│   │   └── batch_runner.py      # 批量处理核心逻辑
│   └── discovery/               # 视频发现与筛选模块
└── projects/auto-dub/
    ├── tracking.db              # SQLite 状态数据库
    ├── review/                  # 成品视频（待审核）+ 封面图
    ├── published/               # 已归档发布文件
    └── auto-dub-{video_id}/     # 每个视频的工作目录
        ├── assets/
        │   ├── audio/           # VoxCPM 合成的单句 WAV 文件
        │   ├── video/           # 原始下载视频
        │   └── subtitles.srt    # 中文字幕
        └── renders/
            └── final.mp4        # 最终压制成品
```

---

## 📊 数据库状态机（tracking.db → videos 表）

```
pending → downloading → transcribing → translating → tts_synthesis
       → mixing → rendering → review → published
        （多人/强制审：transcribing 后 → awaiting_review → 人审通过后继续）
```

| 状态 | 含义 |
|------|------|
| `pending` | 待处理队列 |
| `downloading` | yt-dlp 正在下载 |
| `transcribing` | Whisper 转录英文 |
| `translating` | LLM 翻译为中文 |
| `tts_synthesis` | VoxCPM GPU 配音合成 |
| `mixing` | FFmpeg 100ms 串行排队混音 |
| `rendering` | FFmpeg 字幕烧录 + 音画压制 |
| `review` | 成品已生成，等待人工审核 |
| `published` | 已标记发布 |
| `awaiting_review` | 人审闸门挂起（非失败）：说话人/翻译审校（script checkpoint）或多人合成失败（assets checkpoint）等待人工批准 |

---

## 🚀 CLI 命令速查

所有命令在 `e:/YifuAIForge/OpenMontage` 目录下执行：

```bash
# 一键全流程（scan + filter + process；process 为轻任务模式）
python bin/auto_dub.py run

# 仅扫描新视频（更新候选池）
python bin/auto_dub.py scan

# 仅筛选候选视频（LLM 相关性判断）
python bin/auto_dub.py filter

# 轻任务：仅推进 script + scene_plan checkpoint（绝不碰 TTS/FFmpeg）
# 完成后会打印下一步应派发的 run-heavy 命令
python bin/auto_dub.py process

# 查看当前状态统计
python bin/auto_dub.py status

# 标记某视频为已发布
python bin/auto_dub.py mark-done {video_id}

# ---- 重算力子命令（必须由 Compute Worker 子 Agent 执行，禁止主 Agent 内联跑） ----
# 仅 TTS 合成 + 混音 + SRT（IndexTTS2 本地 GPU，重算力）
python bin/auto_dub.py render-assets --video-id {video_id} [--json]

# 仅 FFmpeg 压制 + 片尾 + 归档（重算力）
python bin/auto_dub.py render-video --video-id {video_id} [--json]

# assets + edit + compose 打包一条龙（20~40 分钟，漂移超标自动缩短重翻）
python bin/auto_dub.py run-heavy --video-id {video_id} [--json]

# ---- 人审闸门（ticket #8/#9/#11，轻任务，主 Agent 可执行） ----
# 应用 speaker_review.md + translation_review.md + synthesis_review.md 人工修正
# → 回写 transcript.json/script.json → 放行 script/assets 审校闸门
python bin/auto_dub.py approve-review --video-id {video_id} [--json]
```

> ⚠️ **AGENTS.md 红线**：禁止写 ad-hoc 脚本直接调用工具。
> 所有生产操作必须通过 `bin/auto_dub.py` 或 `bin/omo.py`。
> **长短解耦硬边界（机制强制，非自觉）**：
> - `process` / `run` 已改为**纯轻任务**——只跑到 script + scene_plan checkpoint，
>   **在代码层面不可能执行 TTS/FFmpeg**。任何主 Agent 跑 process 都不会阻塞在重算力上。
> - 重算力命令（render-assets / render-video / run-heavy）**只能由 Compute Worker
>   子 Agent 执行**，回报用 `--json` 摘要，禁止把完整 stdout 进度流粘贴给主 Agent
>   （见 AGENT_GUIDE.md「Multi-Agent Task Delegation & Log Barrier Protocol」）。

---

## 🤖 跨智能体派发 Compute Worker 指南（OpenCode / OpenClaw / Cursor 通用）

任何 Agent 客户端读取本 SKILL 后，遇到以下情况**必须派发子 Agent 执行重命令**，
而不是自己内联运行：

**触发条件（必须派发）：**
- `process` 输出 `🚀 下一步：请派发 Worker 执行重算力` 提示后
- 用户要求"处理/跑完 {video_id}"且 script+scene_plan 已就绪
- 任何需要 GPU TTS 合成或 FFmpeg 压制的时刻

**各客户端派发方式：**

| 客户端 | 派发机制 | 主 Agent 动作 |
|--------|---------|--------------|
| OpenCode | `task` 工具 / 子 Agent | 派发 Worker 执行 `run-heavy --json`，只接收 JSON 摘要 |
| OpenClaw | 子 Agent / Worker 任务 | 同上 |
| Cursor | Background Agent / Subagent | 同上 |
| Claude Code | Agent / Task 工具 | 同上 |
| 通用 | 独立终端进程 | `python bin/auto_dub.py run-heavy --video-id X --json > worker.log 2>&1`，主 Agent 只读 `worker.log` 末行 JSON |

**Worker 回报契约（子 Agent 必须遵守）：**
1. 在自身会话中保留完整 `[AutoDub]` 心跳流（可被人工检查）
2. 向主 Agent 只回报**最后一行 JSON**（`success`/`output_path`/`drift_seconds`/`error`）
3. 禁止粘贴心跳/ffprobe 原始输出

**典型两段式流程（推荐给任何客户端）：**
```
主 Agent:  python bin/auto_dub.py process          # 轻任务，秒级~分钟级
主 Agent:  看到 "🚀 派发 Worker 执行 run-heavy"
主 Agent:  派发子 Agent → Worker 执行 run-heavy --json → 回报 JSON 摘要
主 Agent:  用 status 复核，向用户汇报成品路径
```

---

## 🎙️ TTS 引擎：IndexTTS2 本地 GPU（默认）

- **引擎**：IndexTTS2（本地 GPU，无需 API Key），`config.yaml → pipeline.tts_engine: indextts`
- **调用方式**：auto-dub 通过 `pipeline_automator` 的 subprocess 常驻服务桥接调用；桥在 `apps/indextts-bridge/indextts_server.py`（支持 `--version 2.5|2`），不要直接 import 底层模块
- **⚠️ 任何 Agent 手动调用 IndexTTS 前，必须先读**：`apps/indextts-bridge/CALLING.md`（正确启动命令、UTF-8 编码、情感参数、排障——违反会产杂音/乱码/女声化）
- **特性**：中文/多语言语音、零样本音色克隆（自动从原视频提取声纹）、字符级时间戳
- **GPU 互斥**：IndexTTS2 常驻服务占 8-16GB VRAM；服务启动时自动获取跨智能体 GPU 锁（`lib/gpu_lock.py`），合成结束/异常时自动释放
- **备选引擎**：`tts_engine: voxcpm` 时走 `voxcpm_tts` 工具（见 `.agents/skills/voxcpm-tts/SKILL.md`）

### 已知问题与修复方案

**问题：生成内容为杂音**

升级 IndexTTS 2.5 后（2026-08-13），若生成音频是杂音（whisper 转录出 `Maze Maze Selling` 等无意义音节）：
- **根因**：用了旧桥 `D:/index-tts/indextts_server.py`（加载 2.0 `infer_v2` 模型）+ 2.5 权重 → 权重错位（日志 `missing keys (212)` / `skipping spk_emb_proj`）
- **修复**：改用 `apps/indextts-bridge/indextts_server.py`，启动带 `--version 2.5 --checkpoints D:/index-tts/checkpoints`。详见 CALLING.md。

**问题：中文变 `?` 乱码**

PowerShell `Write-Output ... | python` 管道按 GBK 传中文，桥按 UTF-8 读 → 乱码。
**必须用 Python `subprocess` + `encoding="utf-8"` 传 stdin**。详见 CALLING.md。

**问题：男声被克隆成女声**

2.5 下传了 `emo_vector`（触发情感-音色混合 `emovec_mat + (1-sum)*emovec`）会削弱声纹。
**固定 calm 只传 `use_emo_text: false`，不传 `emo_vector`**（官方纯净克隆）。详见 CALLING.md。

**问题：静音伪文件**

批量合成时，TTS 引擎在某些句子上可能生成静音 WAV（`rms_amplitude < 100`）。

```python
# 检测静音文件
from scipy.io import wavfile
import numpy as np
rate, data = wavfile.read(wav_path)
rms = np.sqrt(np.mean(data.astype(np.float32)**2))
if rms < 100:  # 静音阈值
    # 删除并重新合成
```

**修复步骤：**
1. 扫描所有 WAV 文件，找出 `rms < 100` 的静音伪文件
2. 删除静音伪文件
3. 重新触发 `process` 命令，系统会自动重新合成

**问题：多人访谈音色错配（同一人两种音色）**

pyannote 在重叠访谈上常把 3 个真实说话人分裂成 4 个 cluster，旧流程给每个 cluster 克隆一个声纹 → 主持人出现两种音色。

**修复（已实现，tt-test 验证）**：
1. **Cluster Merge**：对每个 cluster 的 voice_ref 提 speaker embedding，相似度 ≥ 0.7 合并（SPEAKER_03 并入 SPEAKER_02）
2. **Word-Level Split**：同一句子内跨说话人按词切分（`transcriber._assign_speakers`）
3. **合并归一化**：被合并 cluster 的句子重定向到目标声纹
4. **一人一音轨**：`dub_{SPEAKER_N}.wav` 独立 stem

**问题：短句合成超长导致漂移**

IndexTTS2 短句真实 cps（3.1-4.2）远低于长文本校准值（~5.8），固定 15 字下限会让 1-2s 短句译文过长。

**修复**：`cps_safety_factor=0.7` 打折 + 短句预算随时长缩放 + 翻译长度硬约束 + 确定性截断兜底（`_truncate_to_budget`）。详见 `skills/pipelines/localization-dub/lessons-learned.md` 多人访谈章节。

**问题：男声音高锚定破坏音色**

旧 `_pitch_anchor` 用 asetrate 降调修复"短句克隆成女声"，但强制降调引入机械感/变调。**已彻底删除**（含测试）。正确做法：声纹参考多段择优拼接至 ~30s，源头稳定克隆。

**多人访谈人审闸门（已落地，见 GitHub wayfinder map #7）**：
多人（≥2 说话人）全自动完成率差，前期需人工校验：说话人审校（音色数量 + 每音色说的话，`speaker_review.md`）+ 翻译审校（全量中英对照，`translation_review.md`）。单人默认自动通过但留档。由 [wayfinder map](https://github.com/tiger0425/OpenMontage/issues/7) 规划落地（ticket #8/#9/#10）。

---

## 🎨 封面生成（两种方式，按需选择）

### 方式 A：HyperFrames 模板渲染（默认，流水线自动执行）

- `pipeline_automator._generate_cover_images` → `apps/auto-dub/templates/cover.html`
- **系列一致性（铁律）**：全系列共用同一 HTML 母版；右侧用 HTML/CSS 固定技术视觉，**不要**回退到每期视频缩略图，**不要**用 image_selector 每期生图
- **单母图双画幅**：母版是 `1920x1080`，**中央 `1440x1080` 为完整 4:3 主封面区**（x=240..1680），左右各 240px 仅作延展背景；4:3 场景用中央区域等比输出，禁止临时裁 16:9 成品
- 左侧内容与右侧面板统一 `top:115 / bottom:115` 垂直居中；底部金句放进内容容器（`margin-top:auto`），不绝对定位
- 渲染后输出 16:9 母图到 `review/` 与 `published/` 的 `{中文标题}_cover.png`
- 更多排版/渲染避坑见 `skills/pipelines/localization-dub/lessons-learned.md` →「系列封面设计」章节

**默认模板动态布局基线（2026-08-26 重构，三画幅统一）**：

- 右侧原封面卡片：内容区严格 16:9（完整显示不裁切）+ 主题色渐变背板（与外框同色系）+ `rotate(-2.5deg)` 倾斜 + 保留 3D 透视
- 9:16 竖屏（cover_vertical.html）：卡片在 `.content` flex 流内紧跟标题（`margin: 60px auto 0`），整体 `justify-content: center` 动态居中——**禁止**底部绝对定位
- 16:9 / 4:3：`.footer-quote` 用固定 `margin-top`（60px/48px），**不要 `margin-top: auto`**（会把标题群组顶到左上角）
- 详细经验见 `skills/pipelines/localization-dub/lessons-learned.md` →「封面模板动态布局」

### 方式 B：AI 生图工具直接生成标题党封面（推荐用于高流量选题）

2026-08-03 验证可行，效果优于模板。流程：

1. **工具路由**：必须走 `image_selector`（禁用直接 import 底层 provider，遵守 AGENTS.md 红线）。
   当前可用：`google_imagen`（GOOGLE_API_KEY / GEMINI_API_KEY 已配置）。
2. **模型选择**：封面核心是中文大字标题 → 选 `gemini-3.1-flash-lite-image` 的上级
   `gemini-3.1-flash-image`（文字渲染更强）；勿用默认 lite 做标题党封面。
3. **prompt 要点**：
   - 明确 `4:3`、`YouTube/Bilibili thumbnail`、`clickbait` 风格
   - 逐行给出**精确的中文标题文字**，并声明 "CRITICAL: all Chinese characters must be spelled EXACTLY as given"
   - 标题行数控制在 2 行内、每行 ≤10 字，减少文字错误率
4. **输出规格**：生成后 `ffmpeg -vf scale=1200:900` 归一化为 B站标准封面
   （生图模型输出约 1200×896，差 4px 需归一）。
5. **人工确认**：封面文字（尤其中文标题）必须由用户人工确认无误后才可替换归档；
   若 Agent 模型不支持图像输入，直接给用户路径让其打开确认。
6. **替换归档**：同步覆盖 `review/` 与 `published/` 的 `{中文标题}_cover.png`。

> ⚠️ PowerShell 中文件名含 `$`（如「告别$20订阅！」）时，字符串里必须转义为
> `` `$20 ``，否则 `$20` 会被当作变量吞掉导致文件名错误。

---

## 🔊 混音策略：100ms 串行排队

为避免声音重叠，使用严格串行排队模式：

```
句1_audio [duration] → +100ms 间隔 → 句2_audio → +100ms → ...
```

- **不做音频拉伸**（不变速）
- **不压缩原始视频帧率**
- **字幕通过 SRT 重同步** 与配音对齐
- 最终用 FFmpeg 烧录字幕并混入配音音轨

---

## ⚙️ 配置文件要点（`apps/auto-dub/config.yaml`）

### 添加新频道

```yaml
channels:
  - name: "频道显示名"
    url: "https://www.youtube.com/@channel_handle"
```

### 添加新播放列表（直接导入）

通过 `yt-dlp` 手动下载播放列表元数据后，将视频记录插入 `tracking.db`：

```sql
-- 查看当前待处理视频
SELECT video_id, title, status FROM videos WHERE status = 'pending';

-- 查看整体状态分布
SELECT status, COUNT(*) FROM videos GROUP BY status;
```

### 调整筛选规则

```yaml
filters:
  min_duration_seconds: 180    # 最短 3 分钟
  max_duration_seconds: 1200   # 最长 20 分钟
  max_age_days: 30             # 仅处理最近 30 天
  exclude_languages: ["zh"]    # 排除已是中文的视频
```

### 术语表维护

```yaml
glossary:
  keep_english:     # 这些词保留英文，不翻译
    - "YourTool"
  translations:     # 这些词固定翻译
    "your term": "你的翻译"
```

### 说话人分离与逐句对齐（多人视频 / 原句字幕）

```yaml
pipeline:
  diarize: auto                  # auto=全量跑说话人分离按结果分档（多人/单人）；off=跳过（单人为主省时间）
  human_review: auto             # 说话人审校分流：auto=说话人>=2 强制人审，单人自动通过留档；required=所有视频（含单人）强制人审
  alignment:
    merge_gap_seconds: 0.5       # 原句合并：相邻转录段最大时间间隙
    max_utterance_seconds: 15.0  # 原句合并：单句上限，超限不硬并
    chunk_max_chars: 40          # 原句切合成子块（Chunk）的最大字符数
    tempo_budget: 0.05           # 逐句变速预算 ±5%（保音高）
    tolerance: 0.15              # 对齐容差 ±15%（验收达标率）
    inherently_long_seconds: 1.0 # 物理不可达句阈值（原句 < 1s，允许超容差且不计入达标率）
    queue_gap_seconds: 0.10      # 排队间隔 100ms（变速目标 = 原句时长 − 排队间隔）
    allow_slowdown: true         # 是否允许放慢语速对齐时间槽（铁律 A 补充，2026-08-17）：true=允许 duration_factor/atempo 拉长配音贴合原句（默认）；false=只禁放慢、允许加快（听感自然）。优先级 video.metadata.allow_slowdown > config。改此配置后必须清空 assets/audio 并删 assets/edit/compose/publish checkpoint 再重跑，否则旧 WAV 被复用不生效。
```

- **转录后按原句（Utterance）合并**：字幕与时长对齐锚点为原句，不再出现碎句；SRT 每条 = 一个原句。
- **多人视频自动分音色**：`diarize: auto` 时 pyannote 分离说话人，按 speaker 从原视频切声纹，每句按说话人选音色；单人/未分离回退单声纹（零回归）。
- **说话人审校闸门**（`human_review`，ticket #10）：转录后按说话人数分流——多人（>=2）或 `required` 时生成 `speaker_review.md`（音色概览 + 每音色逐句 + 修正指令区），script checkpoint 置 `awaiting_human`，`process` 停在闸门并把 DB 状态标为 `awaiting_review`（非失败），`run-heavy`/`render-assets` 会被前置检查拒绝；单人（auto 模式）自动通过并留档。
- **人审修正**：编辑 `projects/auto-dub/auto-dub-{video_id}/speaker_review.md`，语法：
  - `# 合并 SPEAKER_03 -> SPEAKER_02`：把某音色所有话归给另一音色（删除 = 合并到他人）
  - `# u10 -> SPEAKER_02`：把某一句改给另一音色
  改完运行 `python bin/auto_dub.py approve-review --video-id {video_id}`：解析修正 → 回写 `transcript.json`（utterances + speaker_turns）→ 同步 `script.json` sections 的 speaker（**不重翻**，译文文本 per-utterance 独立）→ script checkpoint 置 `completed` 放行。
- **翻译审校闸门**（ticket #9）：与说话人审校同分流（`human_review`）——多人/`required` 时同时生成 `translation_review.md`（全量逐句中英对照：每句 `### [u0] (…) [SPEAKER]` + `- EN:` 原文 + `- ZH:` 译文）。
- **译文人审修正**：直接编辑 `translation_review.md` 中各句 `- ZH:` 行内容（其余行勿动），运行 `approve-review`：解析 `ZH:` 行 → 回写 `script.json` sections 的 `delivery_cues.provider_text`（仅应用有改动的句子，**不重翻**）→ script checkpoint 置 `completed` 放行。`approve-review` 会应用实际存在的 speaker/translation 审校文档。
- **逐句对齐**：合成 → 实测时长 → 逐句 atempo（±5%）→ 校验；变速不可达句单次缩短重翻；`segment_timings.json`/`alignment_report.json` 输出 ±15% 达标率、碎句率、物理不可达句数。
- **合成失败重试**（ticket #11）：TTS 子块合成失败（返回 False / 服务异常 / 产出静音伪文件 `rms < 100`）时重试，上限 `synth_retry_max`（默认 2，重试换 seed）。单人重试耗尽 → 静音兜底继续（容忍少数静音句）；**多人视频 0 次重试** → 生成 `synthesis_review.md`（失败清单：id/文本/原因/目标时长），assets checkpoint 置 `awaiting_human`，DB 状态 `awaiting_review`，`run-heavy`/`render-assets` 前置拒绝。
- **合成失败人审**：编辑 `synthesis_review.md` 填 `# 重试 u3`（该句重新合成）或留空（接受静音兜底）。运行 `approve-review`：有重试句 → 清空其 wav、assets checkpoint 置 `in_progress`（重跑 run-heavy 重新合成）；无重试句 → 直接放行（render-video）。
- 需 GPU 的端到端验收（TikTok 双人分音色、F3lL98Pj90o 漂移复跑）在无 GPU 会话中**不可执行**，须派发 Compute Worker（`render-assets` / `run-heavy`）。

---

## 🗣️ 用户自然语言指令 → 操作映射

当用户说以下内容时，执行对应操作：

| 用户说 | 对应操作 |
|--------|---------|
| "开始处理" / "启动配音" / "跑一下 auto-dub" | `python bin/auto_dub.py run`（轻任务：scan+filter+process） |
| "扫描新视频" / "更新候选池" | `python bin/auto_dub.py scan` |
| "处理待处理队列" / "推进流水线" | `python bin/auto_dub.py process`（轻任务，重算力另派 Worker） |
| "查看进度" / "现在处理到哪了" | `python bin/auto_dub.py status` |
| "处理视频 {video_id}" | 先 `process`（轻任务），就绪后**派发子 Agent** 执行 `run-heavy` |
| "合成音频/配音" / "跑 TTS" | `render-assets --video-id {video_id}`（重算力，**必须派发子 Agent**） |
| "压制视频/出片" | `render-video --video-id {video_id}`（重算力，**必须派发子 Agent**） |
| "一口气跑完 {video_id}" | `run-heavy --video-id {video_id}`（重算力，**必须派发子 Agent**） |
| "标记 {video_id} 已发布" | `python bin/auto_dub.py mark-done {video_id}` |
| "有哪些视频还没完成" | 查询 `tracking.db` 中非 `published` 状态的视频 |
| "添加频道/播放列表" | 修改 `config.yaml` 中的 `channels` 列表 |
| "处理这个视频 {YouTube URL}"（单个 URL） | 见下方「单个视频 URL 入库流程」 |

### 单个视频 URL 入库流程（CLI 无 add 命令，2026-08-26 验证）

`scan` 只扫 config 里的频道，单个 URL 需手动入库：

1. `yt-dlp --skip-download --print "%(id)s|%(title)s|%(channel)s|%(duration)s|%(language)s|%(upload_date)s" <URL>` 获取元数据
2. 人工核对筛选规则（时长 180-1200s、非中文、时效），符合则插入 `tracking.db`：
   ```sql
   INSERT INTO videos (video_id,url,title,channel,channel_url,duration_seconds,published_at,language,status,discovered_at)
   VALUES (<id>,<url>,<title>,<channel>,<channel_url>,<dur>,<date>,<lang>,'pending',datetime('now'))
   ```
3. **关键**：`process` 只取 `status='queued'` 的视频（不是 `pending`！）→ 手动 `UPDATE videos SET status='queued' WHERE video_id=<id>`
4. `python bin/auto_dub.py process`（轻任务：下载→转录→翻译→script+scene_plan）
5. 按输出提示派发 Compute Worker 执行 `run-heavy --video-id <id> --json`

⚠️ 库中可能有历史遗留的 `processing` 状态视频（中断产物），`process` 不会碰它们，无需处理。

---

## 🤝 子 Agent 汇报契约（Log Barrier）

**重算力命令必须由 Compute Worker 子 Agent 执行，且回报使用 `--json`。**

- Worker 会话中可以看到完整的 `[AutoDub]` 心跳进度流（进度/耗时/ETA），这些**只留在 Worker 自己的窗口/日志**。
- 向主 Agent 回报时，只允许粘贴**单行 JSON 摘要**。禁止粘贴整个 stdout。

示例（`render-assets --json` 的末行输出）：

```json
{"project_id":"auto-dub-abc123","stage":"assets","success":true,"output_path":"projects/auto-dub/review/abc123.mp4","drift_seconds":0.42,"verification_notes":["零重叠校验通过：所有相邻音频分段间隔均大于等于 100ms"],"warnings":[],"error":null}
```

字段说明：

| 字段 | 含义 |
|------|------|
| `project_id` | 项目 ID（`auto-dub-{video_id}`） |
| `stage` | 刚完成的阶段（assets / video / heavy） |
| `success` | 是否成功 |
| `output_path` | 成品相对路径 |
| `drift_seconds` | 配音相对原视频的漂移秒数 |
| `verification_notes` | 通过的核心校验项 |
| `warnings` | 警告列表（零重叠失败等） |
| `error` | 失败原因（无则 null） |

> 主 Agent 收到 JSON 摘要后，用 `python bin/auto_dub.py status` 复核数据库状态即可，
> 无需重复查看 Worker 的完整日志。

---

## 📁 成品文件位置（按 频道/视频 分目录）

成品按视频的 channel 分频道子文件夹，频道下再按视频标题分独立文件夹（每个视频的所有产物放一起）。

```
projects/auto-dub/review/<频道>/<视频标题>/      # 待人工审核的成品（生成后只进这里）
├── {中文标题}.mp4                    # 中文配音成品视频
├── {中文标题}_cover.png              # 4:3 封面图
├── {中文标题}_meta.json              # 元数据（video_id、标题、简介等）
└── {中文标题}_简介.txt                # B站简介（开头含「中文标题: ...」与「原视频: ...」）

projects/auto-dub/published/<频道>/<视频标题>/   # 已确认发布的归档（人工确认后才归档）
└── (同上，审核通过后归档一份)
```

**review 与 published 的流转：**
- 生成后成品**只进 review/**（待审），不再自动复制到 published/
- 你审核确认后，运行 `python bin/auto_dub.py confirm-video {video_id}`
  → 把 review/ 下该视频文件夹归档到 published/<频道>/<视频标题>/（按频道/视频分目录）
  → review/ 保留已确认的副本，DB 状态标记为 published

**简介（_简介.txt）内容：**
- 开头固定两行：`中文标题: {翻译后的中文标题}` 和 `原视频: {英文原标题}`
- 末尾固定一行：`#AI #人工智能 #中文配音`
- 中间为翻译后的 B站简介（保留代码/URL/专有名词）
- 原视频无简介时，仅生成标题两行 + 标签

**CLI 命令：**
```bash
# 审核确认：review → published 归档（按频道/视频分目录，review 保留副本）
python bin/auto_dub.py confirm-video {video_id}
```

---

## 🐞 常见问题排查

### 1. VoxCPM 静音问题

**症状**：视频某段没有声音，或配音时间明显不够  
**原因**：VoxCPM 对某些句子生成了静音 WAV  
**修复**：

```bash
# 扫描并清理静音文件，然后重新 process
python bin/auto_dub.py process
```

### 2. 混音后声音重叠

**症状**：两段配音同时播放  
**原因**：配音时间戳计算错误，未使用串行排队  
**修复**：检查 `batch/batch_runner.py` 中的混音逻辑，确认使用 100ms 串行间隔

### 3. 字幕与配音不同步

**症状**：字幕比说话早或晚  
**原因**：SRT 时间戳未重同步  
**修复**：触发 SRT 重同步步骤，将字幕时间戳对齐至实际配音时间

### 4. yt-dlp 下载失败

**症状**：视频卡在 `downloading` 状态  
**原因**：网络问题或视频受地区限制  
**修复**：手动运行 `yt-dlp {url}` 测试，检查代理设置

### 5. 成品时间戳跳变（播放中途长时间定格/黑屏）

**症状**：视频播放到约 2/3 处画面定格数分钟（画面冻结、无声音），
文件时长明显大于「原视频 + 片尾」之和（如 670s 原片 + 3s 片尾却得到 808s）。
上传 B 站审核/播放器会报「时间戳跳变」。

**原因**（2026-08-03 定位）：`concat demuxer + stream copy` 拼接主视频与片尾时，
当两者的 `time_base` 不同（例如 main 为 25fps 的 1/12800、outro 为 30fps 的 1/15360），
concat 对第二个文件的时间戳偏移计算错误，把 3s 片尾偏移到数百秒之后，
产生超长空档（表现为单个包的 duration 高达 100+ 秒）。

**修复**：已改为 `concat filter` 重建时间戳（`pipeline_automator.py` 的
compose 拼接段，`[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1` + libx264 CRF 18 重编码）。
**禁止回退为 concat demuxer + `-c copy`。**

**排查命令**（检测跳变，阈值 1.5s）：

```powershell
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 final.mp4 |
  ForEach-Object { [double]$_ } |
  ForEach-Object { $prev=$null } { if ($prev -ne $null -and ($_-$prev) -gt 1.5) {
    Write-Output ("JUMP at {0:N2}s -> {1:N2}s" -f $prev, $_) }; $prev = $_ }
```

**重压替换流程**（修复后对已损坏成品）：用修复后的拼接命令重压
`renders/final.mp4` → 校验时长 = 原视频 + 片尾、零跳变 →
同步覆盖 `review/` 与 `published/` 下的 `{中文标题}.mp4`（删除旧错误文件）。

### 6. 片尾末句没说完（最后一句截断）

**症状**：成品最后一句只说一半，或根本没声音
**排查**：按 `skills/pipelines/localization-dub/lessons-learned.md → 片尾末句防截断三层核验`
逐层查：转录丢尾（末词无标点/end 与片尾差 > 0.5s）→ 译文半句收尾 →
末句 WAV 静音（rms < 100，删文件重跑 `run-heavy` 补合成）→ 成品时长/片尾音频峰值/SRT 末条。
派 Worker 时把末句中英文原文 + 时间戳写死在 prompt 里当比对基准，核验数值进 JSON `checks` 字段。

---

## 🔗 相关技能文档

| 技能 | 路径 | 用途 |
|------|------|------|
| VoxCPM TTS | `.agents/skills/voxcpm-tts/SKILL.md` | 本地 GPU 语音合成详细用法 |
| FFmpeg | `.agents/skills/ffmpeg/SKILL.md` | 视频处理、混音、字幕烧录 |
| video-edit | `.agents/skills/video-edit/SKILL.md` | 视频剪辑操作 |
| video-download | `.agents/skills/video-download/SKILL.md` | yt-dlp 下载 YouTube 视频 |

---

## ✅ 新会话快速启动清单

在新会话开始时，完成以下步骤：

1. **确认项目根目录**：`e:/YifuAIForge/OpenMontage`
2. **查看当前状态**：`python bin/auto_dub.py status`
3. **查看成品**：`ls projects/auto-dub/review/*.mp4`
4. **按用户指令执行**：使用上方的「用户指令映射表」

> 💡 **任何新 AI 工具（OpenClaw, Cursor, Windsurf 等）** 读取本 Skill 后，
> 即可无缝接手 Auto-Dub 任务，无需用户重复解释项目背景。
