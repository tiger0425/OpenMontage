# VOX Collage 实战避坑与工程铁律 (LESSONS.md)

本文档汇整了在 RTX 3090 24GB、ComfyUI、IndexTTS 2.5、HyperFrames 与 FFmpeg 全流程实战中踩过的所有深坑与最佳应对策略。跑管线前必读！

---

## 一、 命令行与脚本执行陷阱

### 1. PowerShell 数组吞前导零
* **现象**：执行 `--only 02,03,04` 时，只有最后一场 `04` 被执行，甚至报 `File not found: scene-2.png`。
* **原因**：PowerShell 解析未加引号的逗号分隔字符串时，会将其视为数值数组 `[2, 3, 4]`，自动抹去字符串前导零。
* **铁律**：**所有多参数列表必须加英文双引号**，如 `--only "02,03,04"`。

### 2. 输出文件名编码与残留
* **现象**：渲染文件带有中文名称时，经常残留 `.hf-transaction` 或 0 字节损坏文件。
* **原因**：Windows 下 Node.js 与 Chromium 管道通信对中文字符集转义异常。
* **铁律**：时间线项目名与渲染输出一律采用 ASCII 拼音或英文小写短横线（如 `ford-wrc-ep01`），成片交付打包时再用 Python 改为带中文的发布名称。

---

## 二、 旁白与 TTS（IndexTTS 2.5）避坑

### 1. 破折号灾难
* **现象**：配音中莫名出现“减减”两个怪音（如“福特回归——为了重振辉煌”变成“福特回归减减为了重振辉煌”）。
* **原因**：IndexTTS 将中文破折号 `——` 或长连字符当作减号 `-` 连续朗读。
* **铁律**：**文案中绝对禁止使用破折号 `——` 或连字符 `-`**！停顿一律使用逗号 `，` 或句号 `。`。

### 2. 时长必须“读 WAV 头真实秒数”，严禁依赖估算
* **现象**：画面切走或黑屏了，旁白还在继续说；或者旁白说完了画面空挂 3 秒。
* **原因**：用中文字数估算朗读秒数（如 1 秒 3.5 字）误差可达 ±25%。
* **铁律**：TTS 合成完成后，**必须用 `wave.open()` 读出真实 sample frames 并计算浮点秒数**，存入 `voice-manifest.json`。时间线槽位公式为：
  `slot_duration = lead(0.3s) + wav_exact_seconds + tail(0.25s)`。

### 3. Whisper 质检模型选择
* **现象**：跑完 Whisper 自动核对，经常假报警说年份念错（如 2024 年报错为 2020 年）。
* **原因**：`faster-whisper-small` 对中文数字和年份的音频转录精度不足，容易产生幻觉。
* **铁律**：自动质检必须使用 `faster-whisper-medium`（或本地 GPU `medium` 模式），CPU 上跑 10 条语音仅需几秒，但准确率接近 100%。

---

## 三、 视觉与 ComfyUI 编辑/生成避坑

### 1. Qwen-Image-Edit 2.1 风格参考图污染
* **现象**：生成的静帧画面角落莫名出现了风格参考图上的色板色块、示例文字（如 `THE DEAL`）或示例数字（`$123`）。
* **原因**：给大模型输入 `<image_2>` 风格图时，模型把参考图里的排版内容误认为是用户想要的内容。
* **铁律**：Prompt 模板必须声明以下负向约束：
  > *"DO NOT include any of the actual content, words, color swatches, or sample numbers present in <image2>. Only borrow the artistic style, paper texture, rough keylines, and halftone rendering."*

### 2. MiniMax H3 视频首帧黑场（Fade In）
* **现象**：H3 生成的图层动画开头有 0.5~1.0 秒是黑屏渐入，硬切播放时每幕开头都闪一下黑。
* **原因**：文生视频/图生视频模型在未指定初始光照时，默认带有从全黑渐显的电影镜头习惯。
* **铁律（双重保险）**：
  1. Prompt 显式锁定：`The FIRST FRAME already shows the fully lit paper background; there is NO fade from black.`
  2. 时间线利用 `data-media-start="1.0"` 跳过视频开头组装与黑场余量，让硬切直接落在已经展开完毕的明亮画面上。

### 3. 显存抢占与 0xC0000409 崩溃
* **现象**：跑完静帧去跑 H3 视频，或者跑完视频去渲染视频时，进程直接崩溃报错 `0xC0000409`（STATUS_STACK_BUFFER_OVERRUN）。
* **原因**：RTX 3090 24GB 显存被 ComfyUI 的 Qwen 模型常驻占用（占用约 18GB），H3 模型动态载入时显存击穿。
* **铁律**：进入下一个重阶段前，必须向 ComfyUI 发送请求强制回收：
  `POST http://127.0.0.1:8188/free`，参数：`{"unload_models": true, "free_memory": true}`。

### 4. Windows 字体缺失导致排版“豆腐块”
* **现象**：资料图和图注渲染出白色乱码方块 `□□□`。
* **原因**：排版代码默认使用了不支持 CJK 的英文系统字体（如 Arial、Impact 渲染中文）。
* **铁律**：排版引擎中文字体必须按优先级使用本地安装的字体：
  `C:\Windows\Fonts\msyhbd.ttc`（微软雅黑粗体）或 `simhei.ttf`（黑体）。

---

## 四、 90 秒 ~ 10 分钟中长视频渲染性能治理

### 1. 动静混编策略（Hybrid Motion）
* **痛点**：一条 8 分钟的深度纪录片包含 60 幕。如果全部跑 H3 图层视频：
  - 生成时间需要 4~6 小时；
  - 观众长时间注视高频图层动效容易产生视觉疲劳。
* **工程解法**：
  - **核心幕 (Hero Scenes, 占比约 30%~40%)**：跑 H3 图层组装视频（开场钩子、关键赛车/装备、核心转折、高潮）；
  - **叙事幕 (Drift Scenes, 占比约 60%~70%)**：直接由 HyperFrames 前端加载高清静帧，应用 `2% slow drift`（慢速缓动推拉）+ 弹性弹入动效。
  - **效果**：渲染速度提升 3 倍以上，画面清晰度达 4K 级别，全片张弛有度。

### 2. 长时间 Chromium 内存泄漏防护
* **痛点**：HyperFrames 渲染超过 5 分钟的单条长视频时，Chromium 容易在第 8000 帧左右发生内存溢出崩溃。
* **工程解法**：
  - 超过 3 分钟的视频，管线自动按**章节（Chapter）**切分为独立的子合成；
  - 分别渲染每个 Chapter 的无损 MP4；
  - 最后调用 FFmpeg concat demuxer（`ffmpeg -f concat -safe 0 -i list.txt -c copy`）瞬间无损合并为完整母版。

### 3. 母版与立体字幕解耦
* **铁律**：永远不要把文字字幕写进 HyperFrames 页面中随整片一起耗时渲染！
  - HyperFrames 只渲染**无字幕的纯净画面母版**（母版可永久复用、可发不同语言版本）；
  - 字幕由 FFmpeg 读取 ASS 字幕文件极速烧录（10 分钟视频仅需十几秒）。
  - 若用户需要微调错别字或调整字幕位置，只需修改字幕文本重新烧录，无需耗费一小时重渲染母版。
