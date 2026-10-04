---
name: vox-collage
description: >
  VOX 纸质拼贴科普与纪录片全自动生产管线（bin/vox_collage.py）。
  支持 16:9 横屏 (1920x1080) 与 9:16 竖屏 (1080x1920)，时长覆盖 90 秒短解说到 10 分钟中长专题片。
  核心铁律：真实素材入画（真车/真Logo/工厂/历史照，拒绝 AI 臆造）；基准图母版（Master Sheet）前置风格锚定；
  多主题预设库（archival-red / racing-orange / tech-cyan / finance-green）；
  6 类微场景构图范式轮转与动静混编策略（hero_motion + 2% slow drift）；
  读 WAV 头精确毫秒排布时间轴，母版无字幕 + FFmpeg ASS 3D 挤出立体字幕快速烧录。
  触发词：VOX拼贴 / 纸片拼贴 / 纪录片拼贴 / vox-collage / 跑拼贴管线 / 拼贴科普视频 / 纸质纪录片 / 9:16拼贴 / 16:9拼贴。
---

# VOX Collage 纸质拼贴科普/纪录片管线 (vox-collage)

一条**高度工业化、可复现、防审美疲劳**的音视频独立生产线：
将文字选题或参考素材，全流程自动化生产为具备顶级调查纪录片质感、真实素材入画、纸质剪贴报刊风格、动静结合的 16:9 横屏或 9:16 竖屏成片（90秒~10分钟）。

---

## 一、 核心铁律与系统特色

1. **真实素材铁律 (True Photography Only)**：
   * 严禁依靠 AI 文生图臆造车型、企业工厂或历史人物。
   * 通过 Wikimedia Commons 自动抓取真实照片入画，并完整记录 CC 许可清单（`manifest.json`）。
2. **基准图前置锚定 (Master Sheet as Anchor)**：
   * 立项必须先确定一张 Master Sheet（如经典的 `archival-red` 或 `racing-orange`）。
   * 调色板 HEX、排版比例、打字机图注均从母版抽取；
   * Qwen-Image-Edit 2.1 风格化严格锁定以本项目的 `master_sheet.png` 作为 `<image_2>`，风格 100% 稳固。
3. **题材驱动换肤 + 单片构图防单调体系**：
   * **多主题换肤**：`archival-red`（历史/调查）、`racing-orange`（汽车/机械）、`tech-cyan`（科技/芯片）、`finance-green`（商业/金融）。
   * **单片构图轮转**：单片内必须在 6 类范式中交替轮转（Stat Hero / Map Pin / Archival Mat / Exploded Blueprint / Versus Clash / Macro Halftone），严禁连续两幕构图雷同。
4. **90 秒 ~ 10 分钟跨度与动静混编 (Hybrid Motion)**：
   * **核心高潮幕 (Hero Motion)**：跑 ComfyUI MiniMax H3 图层组装视频（4 步 Turbo 采样）；
   * **叙事铺垫幕 (Drift Only)**：由 HyperFrames 前端渲染高清静帧 + `2% Slow Drift`（呼吸慢推拉），画质达 4K 且免去 GPU 冗长等待。
5. **配音优先与字幕母版解耦**：
   * 读 WAV 头精确秒数驱动槽位：`slot = lead(0.3s) + vo + tail(0.25s)`；
   * 母版纯净无字幕，由 FFmpeg + ASS 快速烧录 3D 挤出立体字幕，改错别字无需重渲染整片。

---

## 二、 完整 CLI 指令集 (`bin/vox_collage.py`)

### 1. 轻量策划与素材阶段（人审闸门前）
```bash
# 创建项目（支持 16:9 横屏与 9:16 竖屏，指定时长与主题预设）
python bin/vox_collage.py new "福特重回WRC" --ratio 16:9 --theme racing-orange --duration 5m

# 抓取 Wikimedia Commons 真实参考素材并生成许可清单
python bin/vox_collage.py refs ford-wrc

# 生成 SCRIPT.md 剧本，触发人工审查闸门
python bin/vox_collage.py script ford-wrc

# 审查文案（检查有无破折号、去 AI 化），批准放行
python bin/vox_collage.py approve-script ford-wrc
```

### 2. 算力生产阶段（重型 / GPU）
```bash
# IndexTTS 2.5 配音，读取真实 WAV 毫秒秒数
python bin/vox_collage.py synth ford-wrc [--json]

# 基于主题色板与构图范式生成 16:9 或 9:16 资料图
python bin/vox_collage.py dataliao ford-wrc [--only "01,02"]

# ComfyUI Qwen-Image-Edit 2.1 风格化出静帧（锚定 master_sheet）
python bin/vox_collage.py stills ford-wrc [--only "01,02"] [--json]

# ComfyUI MiniMax H3 生成核心幕的 4 步图层动效视频
python bin/vox_collage.py motion ford-wrc [--only "01,02"] [--json]
```

### 3. 时间线装配与成片交付
```bash
# 生成 HyperFrames index.html（自动计算 lead/tail 槽位与 2% slow drift）
python bin/vox_collage.py compose ford-wrc

# 渲染无字幕纯净母版（HyperFrames 0.8.105 锁版）
python bin/vox_collage.py render ford-wrc [--json]

# FFmpeg 烧录 3D 挤出立体字幕交付成片
python bin/vox_collage.py subtitle ford-wrc
```

### 4. 宏命令与状态查询
```bash
# 轻量直达闸门：new + refs + script
python bin/vox_collage.py run "选题名称" --ratio 16:9 --theme tech-cyan

# 重型算力流：synth + dataliao + stills + motion + compose + render + subtitle
python bin/vox_collage.py run-heavy <id> [--json]

# 查看项目数据库跟踪状态
python bin/vox_collage.py status
```

---

## 三、 实战踩坑速查 (Quick Checklist)

1. **PowerShell 引号**：多参数过滤必须加双引号，如 `--only "02,03,04"`，否则会被抹去前导零。
2. **破折号禁令**：文案绝对禁止出现 `——` 或 `-`，IndexTTS 会念成“减减”，停顿一律改逗号或句号。
3. **字体选择**：中文字体必须使用 `msyhbd.ttc`（微软雅黑粗体）或 `simhei.ttf`，防止变豆腐块。
4. **H3 首帧黑场**：提示词声明首帧全亮，或时间线利用 `data-media-start="1.0"` 裁掉暗头。
5. **显存释放**：在 H3 之前若显存过紧，向 ComfyUI 发送 `POST http://127.0.0.1:8188/free` 释放显存。
