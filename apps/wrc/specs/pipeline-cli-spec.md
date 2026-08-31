# WRC 管线落地形态规范（CLI v1）

> 所属地图：[wayfinder:map - WRC拉力视频→中文抖音竖屏流水线](https://github.com/tiger0425/OpenMontage/issues/58)
> 决议来源：[grilling: 管线落地形态（独立 CLI bin/wrc.py）](https://github.com/tiger0425/OpenMontage/issues/66)（2026-08-23 定稿）
> 参考先例：`bin/markhasara.py`（MarkHasara 独立 CLI）、`bin/auto_dub.py`（auto-dub 内核/轻重拆分/GPU 锁）
> 各环节规格引用：#61 脚本规范（script-prompt.md / wrc_episode.schema.json）、#64 抽帧规范（frame-selection-spec.md）、#65 模板生成器（template/）、#59+#60 TTS 情绪配置

## 形态总则

- **独立 CLI `bin/wrc.py`**：不扩 auto-dub（输出形态不同：抖音竖屏 vs B 站横屏）、不进 pipeline_defs（搬运管线非生成管线）。
- **URL 驱动**（非频道发现）：用户粘贴 YouTube URL → 一条系列。
- **独立 DB** `projects/wrc/tracking.db` + **独立项目目录** `projects/wrc-<video_id>/`。
- **轻重拆分硬红线**：主 Agent 只跑轻命令；重命令只能由 Compute Worker 执行并以 `--json` 单行回报。

## CLI 子命令集

| 命令 | 重量 | 职责 |
|---|---|---|
| `new <url> [--title]` | 轻 | 建项目 + yt-dlp 下载 → `assets/original.mp4` → 状态 `downloading→transcribed-ready` |
| `script <id>` | 轻 | Whisper 转录（带时间戳）→ LLM 按 `script-prompt.md` 逐集生成 `artifacts/episodes/<n>.json`（含 display 块）+ contact sheet → **`awaiting_script_review` 挂起** |
| `approve-script <id>` | 轻 | 校验人审后的集 JSON（wrc_episode.schema.json）→ 通过进入 `tts` |
| `render-assets <id>` | **重** | ① IndexTTS-2.5 配音（`use_emo_text=True` + `emo_alpha=0.325` + seed 42 + `INDEXTTS_USE_QWEN_EMO=1`）→ `assets/sN.wav`；② 按 `frame-selection-spec.md` 抽帧/截片（LLM 提案 → ffmpeg → minimax 核验 → 兜底）→ `assets/scene*.jpg/mp4` |
| `render-video <id>` | **重** | ③ `template/generate_composition.py` 生成 `index.html`；④ hyperframes 渲染（pin 0.7.109，danger-full-access + npm cache 指工作区）；⑤ ffmpeg BGM 混音（`bgm_epic.mp3` 0.25 音量 + 1.5s 淡入淡出）→ `renders/final.mp4` |
| `package <id>` | 轻 | 成品包：标题/封面/简介（规格由 #67 定稿后实现） |
| `run <url>` / `run-heavy <id>` | 轻/重 | 全流程：轻 = new→script 停在闸门；重 = 闸门通过后 render-assets→render-video→package |
| `status` | 轻 | 队列状态统计（DB 按状态分组） |

## 状态机与 DB

`projects/wrc/tracking.db` → `videos` 表（MarkHasara 同款独立 DB）：

```
pending → downloading → transcribing → scripting → awaiting_script_review
       → tts → frames → composing → rendering → review → packaged → published
```

- 脚本闸门 = `awaiting_script_review`（人审挂起，非失败）：等待 `approve-script`。
- 每集独立 JSON（`artifacts/episodes/`），逐集人审。

## 脚本闸门交互（Q5 定稿）

- **人直接改集 JSON 文件**（`artifacts/episodes/<n>.json`）：文案、钩子、visuals 说明都改文件；contact sheet 图（`artifacts/contact-sheet-<n>.png`）同目录供核对抽帧/截片。
- 改完 `approve-script <id>` 放行（校验 schema + 钩子密度规则）。
- 与上/中/下三集工作方式一致：用户口述问题 → agent 改文件。

## 复用内核边界（Q6 定稿）

**复用**：yt-dlp 下载、Whisper 转录、`lib/gpu_lock.py`（IndexTTS 占 8-16GB VRAM，锁文件 `%LOCALAPPDATA%/openmontage/.gpu.lock`）、ffmpeg 工具函数、checkpoint 机制（auto-dub 的 `lib/checkpoint.py` 模式）。
**不复用**：频道 discovery（URL 驱动）、VoxCPM TTS（用 IndexTTS-2.5 + 情绪 0.325，见 #59/#60）、发布层（人工上传抖音，自动发布已证伪）。

## 项目目录结构

```
projects/wrc-<video_id>/
├── artifacts/
│   ├── transcript.json        # Whisper 转录稿（带时间戳）
│   ├── episodes/1.json ...    # 集脚本（wrc_episode.schema.json 契约）
│   └── contact-sheet-<n>.png  # 每集抽帧总览
├── assets/
│   ├── original.mp4           # 下载的源视频
│   ├── s0.wav ... sN.wav      # IndexTTS 配音（情绪 0.325）
│   ├── scene*.jpg / .mp4      # 抽帧/截片产物
│   ├── <background>.mp4       # 背景库选中 loop
│   └── bgm_epic.mp3           # BGM
├── index.html                 # 模板生成器产物
└── renders/final.mp4          # 定版（含 BGM）
```

## 实现注意（环境坑，复用地图 Notes）

- IndexTTS 生成 / hyperframes 渲染 / npm：必须 `danger-full-access` + `$env:npm_config_cache` 指工作区 `.npm-cache`
- 视觉核验：`PYTHONIOENCODING=utf-8` 落盘，控制台 GBK 乱码
- ffmpeg 直路 `C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe`

## 后续

- `package` 命令依赖 #67（成品包规格）定稿后实现。
- `bin/wrc.py` 本身是实现任务——地图决策全部完成后（#67 关票）新开 task 票落地。
