---
name: wrc-pipeline
description: >
  WRC 拉力 YouTube 视频 → 中文抖音竖屏流水线（bin/wrc.py）的完整操作指南。
  输入一个 YouTube 拉力视频 URL，产出：1~3 集 9:16 竖屏中文配音解说视频 + 成品包（标题/封面/简介）。
  触发词：跑WRC管线、wrc管线、wrc.py、处理拉力视频、搬运WRC视频、拉力视频转中文竖屏。
metadata:
  tags: "wrc, rally, youtube, douyin, 搬运, 中文配音, hyperframes, indextts"
---

# WRC 拉力视频 → 中文抖音竖屏流水线

## 一句话

**「跑 WRC 管线 + YouTube URL」** → 下载 → 转录 → LLM 脚本（脚本闸门人审）→ IndexTTS 配音（情绪 0.325）→ 抽帧/截片 → hyperframes 合成渲染 → BGM 混音 → 成品包（视频+封面+标题+简介）→ 人工上传抖音。

## 入口

- CLI：`python bin/wrc.py`（唯一执行入口，禁止 ad-hoc 脚本）
- 详细规格：`apps/wrc/specs/`（script-prompt / frame-selection-spec / pipeline-cli-spec / package-spec / background-library-spec / LESSONS）
- **跑管线前必读**：`apps/wrc/specs/LESSONS.md`（实战踩坑，含年份读法/白卡审计/验收清单）
- 分幕 JSON schema：`schemas/artifacts/wrc_episode.schema.json`
- 模板生成器：`apps/wrc/template/generate_composition.py` + `README.md`
- 背景库：`background_library/wrc/`（README 含入库流程，用户发 URL 直接入库）

## 会话内执行流

| 步骤 | 命令/动作 | 谁执行 |
|---|---|---|
| 1. 建项目+下载 | `python bin/wrc.py new <url>` | 主 Agent（轻）|
| 2. 转录+脚本 | `python bin/wrc.py script <id>` → 读 transcript.json → 按 `apps/wrc/specs/script-prompt.md` 生成 `artifacts/episodes/<n>.json`（含 display 块）+ `artifacts/frames/frames.json` + contact sheet | 主 Agent + LLM（轻）|
| 3. **人审闸门** | 用户审/改 episodes JSON + contact sheet（或口述，agent 代改）| **用户** |
| 4. 放行 | `python bin/wrc.py approve-script <id>` | 主 Agent（轻）|
| 5. 重算力 | `render-assets <id> --json` → `render-video <id> --json` → `package <id>` | **Compute Worker / 后台 job**（重，`danger-full-access`）|
| 6. 交付 | 打开 `package/<n>/video.mp4` + cover.jpg 验收；改 → 定位重跑对应阶段 | 主 Agent |
| 7. 发布 | **先问平台**：抖音=手动上传（给标题/简介/封面包）；YouTube=`python bin/youtube.py upload`（CLI 直传，建议先 unlisted）| 主 Agent / 用户 |

## 硬纪律（AGENTS.md 红线）

- **主 Agent 不跑重命令**（render-assets/render-video/run-heavy）：派 Compute Worker，回报用 `--json` 单行，禁止粘贴完整 stdout。
- **沙箱**：IndexTTS 生成、hyperframes 渲染、npm 命令必须 `danger-full-access`；npm 前设 `$env:npm_config_cache="E:\YifuAIForge\OpenMontage\.npm-cache"`。
- **GPU 锁**：CLI 内部用 `lib/gpu_lock.py`，勿并行两个 render-assets。
- **脚本闸门是人的环节**：钩子密度/文案/配图用户确认后才进配音，不得跳过。

## CLI 速查

```bash
python bin/wrc.py new <url>                     # 下载
python bin/wrc.py script <id>                   # 转录 → 停闸门
python bin/wrc.py status                        # 队列
python bin/wrc.py approve-script <id>           # 人审后放行
python bin/wrc.py render-assets <id> --json     # 重：配音+抽帧（Worker）
python bin/wrc.py render-video <id> --json      # 重：合成+渲染+BGM（Worker）
python bin/wrc.py package <id>                  # 成品包
python bin/wrc.py run <url>                     # 轻全流程（停闸门）
python bin/wrc.py run-heavy <id> --json         # 重全流程（Worker）
```

## 关键参数（已定，勿改）

- TTS：IndexTTS-2.5，`use_emo_text=True` + `emo_alpha=0.325` + seed 42 + `INDEXTTS_USE_QWEN_EMO=1` + 声纹 `D:/index-tts/my_voice.wav`
- 脚本：8 类钩子硬规则（s0=open_conflict、每幕≥1、末幕=follow）；每幕 12~20s/60~110 字；逐集生成
- 合成：3 布局（split/center/ending）；玻璃卡 flex:1 到底；**extra_img 必须 ≠ 媒体区图**（生成器查重）
- BGM：`bgm_epic.mp3` 0.25 音量 + 1.5s 淡入淡出
- 背景：一个系列共用一条 loop（背景库），`background` 字段指定

## 内容生产要点（LESSONS 摘要）

- **年份读法**：文案里年份一律写"数字+年"（"2003年"），无"年"的列表 IndexTTS 读错
- **品牌名中文读法**：配音文案里品牌/人名用中文（Citroën→雪铁龙、Xsara→赛纳、Loeb→勒布），屏幕文字保留英文
- **白卡审计**：白底图文卡占比 >50% 警惕、>90% 弃用；技术幕可留白卡但同款 ≤3 次，用动态片段调剂
- **重复度**：合并分集时每张图出现次数 ≤3
- **快速迭代**：改模板先用 3-6s 最小 composition 渲染验证，再全量（30-40 分钟）
- **语音验证闭环**：重配某段后 Whisper 回听（读 `sN_transcript.json`），通过后再全量渲染
- **交付验收**：卡片不压玻璃卡线、无残留帧、片段播开头不播尾巴、年份朗读对、音轨 -20~-30dB、package 齐全
