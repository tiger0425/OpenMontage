# Skill: chinese-subtitle

# Chinese-Subtitle — 给原视频加中文字幕（不配音、不替换音轨）

## 📌 系统概述

Chinese-Subtitle 是内置于 OpenMontage 的轻量字幕工具，
从 **auto-dub** 精简而来，去掉了配音/混音/封面/片尾等全部重算力环节：
只做 **下载 → 转录 → 翻译 → SRT → 烧录**，**保留原音轨**，不生成任何语音。

**适用场景：**
- 给 YouTube 视频或本地视频加中文字幕（硬字幕烧进画面）
- 需要中文字幕但**不需要**中文配音（保留原声）
- 单视频快速处理，不想引入 auto-dub 的数据库/队列/GPU 依赖

**与 auto-dub 的核心区别：**

| 维度 | auto-dub | chinese-subtitle |
|------|----------|------------------|
| 音轨 | 替换为中文配音 | **保留原音轨**（`-c:a copy`） |
| TTS 配音 | VoxCPM/IndexTTS2 本地 GPU | **无**（无需 GPU/GPU 锁） |
| 混音对齐 | 100ms 串行排队 + atempo | **无**（字幕时间轴=原句时间戳） |
| 数据库 | tracking.db 状态机 | **无**（目录即状态，单视频） |
| 封面/片尾 | HyperFrames 生成 | **无** |
| 输入 | YouTube 批量 | YouTube URL **或本地视频文件** |

**项目根目录：** `e:/YifuAIForge/OpenMontage`
**主入口 CLI：** `bin/auto_subtitle.py`
**App 源码：** `apps/auto-subtitle/subtitle_runner.py`
**输出目录：** `projects/auto-subtitle/<id>/`

---

## 🗂️ 目录结构

```
OpenMontage/
├── bin/
│   └── auto_subtitle.py        # CLI 主入口（唯一允许的执行入口）
├── apps/
│   ├── auto-subtitle/
│   │   └── subtitle_runner.py  # 核心逻辑（下载/转录/翻译/SRT/烧录）
│   └── auto-dub/               # 仅复用其 glossary / llm_client（只读）
└── projects/auto-subtitle/     # gitignored，单视频一个子目录
    └── <id>/                   # id = YouTube video_id 或本地文件 stem
        ├── source.mp4          # 源视频（URL 时 yt-dlp 下载）
        ├── transcript.json     # 转录结果（utterances + 时间戳）
        ├── script.json         # 翻译结果（sections + 中文译文）
        ├── subtitles.srt       # 中文字幕（时间轴=原句时间）
        └── renders/
            └── subtitled.mp4   # 成品（中文字幕烧录，原音轨保留）
```

---

## 🚀 CLI 命令速查

所有命令在 `e:/YifuAIForge/OpenMontage` 目录下执行：

```bash
# 给视频加中文字幕（YouTube URL 或本地视频均可）
python bin/auto_subtitle.py run --input "https://www.youtube.com/watch?v=xxxx"

# 本地视频
python bin/auto_subtitle.py run --input "E:/videos/demo.mp4"

# 只生成 SRT，不烧录到画面（侧挂字幕场景）
python bin/auto_subtitle.py run --input <url|path> --no-burn

# 指定源语言与转录模型（默认源语言自动检测、模型 large-v3）
python bin/auto_subtitle.py run --input <url|path> --lang en --model-size base

# 自定义烧录字体/字号
python bin/auto_subtitle.py run --input <url|path> --font "Microsoft YaHei" --font-size 20

# 机器可读摘要（供脚本/CI 使用）
python bin/auto_subtitle.py run --input <url|path> --json
```

### 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `--input` | 必填 | YouTube URL 或本地视频文件路径 |
| `--lang` | 自动检测 | 源语言 ISO 639-1 代码（如 en、ja） |
| `--model-size` | `large-v3` | Whisper 模型：tiny/base/small/medium/large-v2/large-v3 |
| `--font` | `Microsoft YaHei` | 烧录中文字体 |
| `--font-size` | `20` | 字幕字号 |
| `--no-burn` | 烧录 | 只输出 SRT，不烧录 |
| `--json` | 否 | 输出单行 JSON 摘要 |

---

## 🔄 处理流程

```
输入 (URL | 本地文件)
  → 1. 下载/定位源视频 (yt-dlp 或直接复制)
  → 2. 转录 (faster-whisper, word-level timestamps, 原句合并)
  → 3. LLM 逐句翻译为中文 (复用 auto-dub 的 Glossary 术语表 + 前文上下文)
  → 4. 生成 SRT (时间轴 = 原句 start/end, 过短补齐到 0.8s)
  → 5. FFmpeg 烧录 (subtitles filter + libass, 保留原音轨 -c:a copy)
```

**关键设计：**
- **时间轴直接取原句时间戳**：没有配音就没有漂移问题，字幕天然与说话人同步。
- **翻译质量**：复用 auto-dub 的 `glossary.py`（技术术语保留英文）与
  `llm_client.py`（DeepSeek/Gemini），并注入前文上下文保证人名/称谓一致。
- **保留原音轨**：烧录用 `-c:a copy`，不重编码音频，速度最快且无损。

---

## 🗣️ 用户自然语言指令 → 操作映射

| 用户说 | 对应操作 |
|--------|---------|
| "给这个视频加中文字幕" | `python bin/auto_subtitle.py run --input <url或路径>` |
| "给 {URL} 加字幕" | `python bin/auto_subtitle.py run --input {URL}` |
| "给本地视频 {路径} 烧中文字幕" | `python bin/auto_subtitle.py run --input {路径}` |
| "只加字幕不配音" / "原声保留" | 同上（本技能默认就是保留原音轨） |
| "只生成字幕文件" | `python bin/auto_subtitle.py run --input <...> --no-burn` |

---

## 🐞 常见问题排查

### 1. 转录慢
默认 `large-v3` 最准但最慢（视频时长的数倍）。短视频/草稿可 `--model-size base` 提速。

### 2. 烧录失败：字幕显示为方块/乱码
Windows 缺中文字体或 libass 未找到。检查 `--font`（默认 Microsoft YaHei，
即 `C:/Windows/Fonts/msyh.ttc`）。确认 ffmpeg 带 libass：`ffmpeg -filters | findstr subtitles`。

### 3. SRT 里个别句缺失
转录时 VAD 过滤了无语音片段；或该句译文为空被跳过。检查 `transcript.json` 确认转录覆盖。

### 4. 字幕与语音不同步
本工具时间轴=原句时间戳，正常情况天然同步。若个别长句显示过短，
是 `_write_srt` 的 `min_display=0.8s` 兜底逻辑——超长句按原句时长显示。

### 5. 下载失败
`yt-dlp` 网络/地区限制问题。手动 `yt-dlp {url}` 测试，检查代理设置。

---

## 🔗 相关技能文档

| 技能 | 路径 | 用途 |
|------|------|------|
| auto-dub | `.agents/skills/auto-dub/SKILL.md` | 完整配音流程（本技能的精简来源） |
| video-download | `.agents/skills/video-download/SKILL.md` | yt-dlp 下载 |
| speech-to-text | `.agents/skills/speech-to-text/SKILL.md` | Whisper 转录 |
| ffmpeg | `.agents/skills/ffmpeg/SKILL.md` | 字幕烧录 |

---

## ✅ 新会话快速启动清单

1. 确认项目根目录：`e:/YifuAIForge/OpenMontage`
2. 用户给 URL → `python bin/auto_subtitle.py run --input {URL}`
3. 用户给本地文件 → `python bin/auto_subtitle.py run --input {路径}`
4. 成品在 `projects/auto-subtitle/<id>/renders/subtitled.mp4`
5. SRT 在 `projects/auto-subtitle/<id>/subtitles.srt`

> 💡 任何新 AI 工具（OpenClaw, Cursor, Windsurf 等）读取本 Skill 后，
> 即可无缝接手加中文字幕任务。本技能**不涉及 GPU/TTS/数据库**，主 Agent 可直接内联执行。
