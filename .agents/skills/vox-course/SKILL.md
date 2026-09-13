---
name: vox-course
description: >
  VOX 科技与硬核课程自动化生产独立管线（bin/course.py）的操作指南。
  输入课程大纲、文章或文本要点，自动化产出符合 VOX 工业纸张剪贴风格的
  1080P FHD / 4K UHD HEVC 视频、IndexTTS2 纯净克隆语音、100% 咬合的视觉卡片与动态同步字幕。
  触发词：做课程视频、课程视频、vox-course、跑课程管线、技术课程视频、课程内容生成视频、录课程视频。
---

# VOX 科技/硬核课程生产管线操作指南 (vox-course)

## 1. 概述与核心能力

`vox-course` 是 OpenMontage 内置的工业级科技/技术课程视频自动化生产管线。
旨在解决传统技术视频三大痛点：
1. **AI 腔严重、书面语晦涩**：内置 38 条去AI化文案规范与口播 3 条铁律，强制粉碎长句，年份/数字全汉字化；
2. **音色发飘、合成机械**：内置 IndexTTS2 纯净克隆模式，锁定稳态采样参数；
3. **音画脱节、无字幕无留白**：画面卡片与台词 100% 咬合，标配 VOX 全屏毫秒级高对比度字幕条，片尾强制留白 4 秒。

---

## 2. 核心 CLI 命令速查 (`bin/course.py`)

| 阶段 | 命令 | 说明 | 属性 |
|---|---|---|---|
| **初始化** | `python bin/course.py new <topic> [--script-file <path>]` | 创建目录并初始化音效与 BGM | 轻 |
| **生成剧本** | `python bin/course.py script <id>` | 生成 7 幕剧本并**停在人审闸门** | 轻 |
| **放行剧本** | `python bin/course.py approve-script <id>` | 校验去AI化与年份汉字化 | 轻 |
| **语音合成** | `python bin/course.py synth <id> [--json]` | IndexTTS2 纯净克隆与字幕对齐 | 重 (GPU) |
| **装配模板** | `python bin/course.py compose <id>` | 生成 HyperFrames `index.html` | 轻 |
| **成片渲染** | `python bin/course.py render <id> [--json] [--4k]` | 渲染 1080P FHD 并压制 4K HEVC | 重 (CPU/GPU) |
| **组装成品包** | `python bin/course.py package <id>` | 提取封面、生成双标题与简介 | 轻 |
| **轻量一键流** | `python bin/course.py run <topic> [--script-file <path>]` | `new` + `script` 直达人审闸门 | 轻 |
| **重量一键流** | `python bin/course.py run-heavy <id> [--json] [--4k]` | 人审后一键完成配音、合成与压制 | 重 |
| **状态查询** | `python bin/course.py status` | 查看所有项目流转状态 | 轻 |

---

## 3. 标准会话执行流程 (Workflow)

```
用户给出：“把这段 Agent Harness 课程做成视频”
  │
  ├─ 1. 轻量启动：python bin/course.py run "Agent Harness" --script-file lesson.md
  │     └─ 产出 artifacts/course_episode.json，进入 awaiting_script_review 状态
  │
  ├─ 2. 检查与润色：检查文案（去AI化、短句、年份汉字化、音画词汇咬合、末幕钩子）
  │
  ├─ 3. 人审放行：python bin/course.py approve-script course-agent-harness
  │
  ├─ 4. 重量全量执行：python bin/course.py run-heavy course-agent-harness --4k
  │     ├─ synth: IndexTTS2 纯净克隆逐幕配音
  │     ├─ compose: 模板生成器产出 hyperframes/index.html
  │     ├─ render: 渲染 1080P 并 Lanczos 压制 4K HEVC
  │     └─ package: 产出 package/ 完整交付包
  │
  └─ 5. 交付用户：展示 1080P/4K 成片路径、封面图、推荐双标题与简介。
```

---

## 4. 五大绝对红线 (Red Lines)

1. **绝对禁止书面废话与假深刻**：严禁出现“从本质上讲”、“决定到底”，年份必须写“二零二五年”，金额必须写“三百亿美金”。
2. **严禁音画脱离**：卡片大标题、终端代码行、官方印章必须直击台词中的专业术语。
3. **严禁台词念完立刻黑屏**：最后一幕必须有下集预告，且台词完结后必须留出 3.5 ~ 4.0 秒定格，BGM 渐弱淡出。
4. **必须尊重脚本闸门**：剧本未通过 `approve-script` 校验前，严禁调用 `synth` 浪费算力。
5. **成品包必须单文档交付与全比例覆盖**：严禁将标题、简介、标签拆散为多个文件，必须统一输出单个一键复制文档 `package/bilibili.txt`；封面必须自动覆盖 16:9、4:3、1:1、3:4、9:16 五种标准比例。
