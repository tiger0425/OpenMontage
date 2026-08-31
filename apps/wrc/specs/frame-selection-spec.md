# 对题画面抽帧/截片自动化规范（v1）

> 所属地图：[wayfinder:map - WRC拉力视频→中文抖音竖屏流水线](https://github.com/tiger0425/OpenMontage/issues/58)
> 决议来源：[grilling: 抽帧选图自动化（对题画面）](https://github.com/tiger0425/OpenMontage/issues/64)（2026-08-23 定稿）
> 输入契约：[wrc_episode.schema.json](wrc_episode.schema.json)（#61 产物，含 `visuals[].type` image/clip）+ Whisper 转录稿（带时间戳）+ 源视频
> 消费方：hyperframes 模板生成器（#65）、管线落地（#66）

## 目标

每个 visual（`type=image` 静态帧 / `type=clip` 动态片段）从**源视频**中定位、抽取、核验出与配音内容相符的资产，产出 `frames.json` + contact sheet，供模板生成器使用。

## 术语

- **时间戳提案**：LLM 从转录稿定位匹配画面的时间点（每个 visual 1~2 个候选）
- **候选帧**：提案时间戳附近抽的帧
- **视觉核验**：minimax-m3-vision 判定帧/片是否对题（desc 相符）
- **兜底帧**：核验 2 轮仍失败的兜底——该幕配音起始时间点的中性驾驶帧（保证画面动感），contact sheet 上标黄"兜底待换"
- **contact sheet**：每集抽帧结果的网格总览图（行=幕，列=该幕各 visual），随脚本闸门给人审

## 流程（每集执行）

1. **时间戳提案**（LLM）：读该幕配音文案 → 在转录稿中定位对应英文内容 → 给每个 visual 提 1~2 个候选时间戳；`source_hint` 优先；`type=clip` 给出片段起始时间。
2. **抽取**：
   - `image`：候选时间戳 t 抽 3 帧（t-1s / t / t+1s），原分辨率 jpg（16:9 横图，`object-fit:contain` 黑底展示，不裁切）；
   - `clip`：`ffmpeg -ss t -t 8`（默认 8s，6~10s）截 mp4，16:9。
3. **视觉核验**：minimax-m3-vision 判帧内容与 desc 相符（image 判 3 帧挑最贴；clip 抽首帧+中帧判）。落盘报告用 UTF-8（`PYTHONIOENCODING=utf-8` + Out-File utf8；控制台 GBK 会乱码）。
4. **重试**：每个 visual 最多 2 轮提案（首轮 + 1 次换候选时间戳）；仍失败 → 兜底帧（标黄）。
5. **contact sheet**：每集一张网格图（行=幕，列=visuals），附在脚本闸门给用户扫一眼；不满意的标注 → 针对性重选。
6. **产出 `frames.json`**（每集一个，与场景 JSON 平行）：per scene → visual → `{type, desc, timestamp, asset_path, verdict, offset_hint?}`。

## 片段（clip）规则

- **分配**：动作/实拍幕（飞驰、跳跃、漂移、实车画面）优先 clip；规则/图表幕（规则图、认证、成本对比）纯图。
- **配比**：每幕 **0~1 段 clip + 1~2 张图**（clip 为主视觉，图为补充定帧；每幕至少 1 个静态锚点）。
- **规格**：6~10s（默认 8s）；幕内按真实时长播放，**幕长不足则截断、超出则循环**；16:9 contain 黑底，与图片统一；opacity 交叉淡入淡出切换。
- **切换时机**：默认按 visuals 顺序**等分幕长**；`offset_hint`（0~100%）可微调（如钩子句出现时切）。
- **玻璃卡附图（extra_img）必须与媒体区图片不同**（硬规则，用户 2026-08-23 验收要求）：extra_img 由抽帧阶段**单独抽一帧**（不同时间戳），不得复用 visuals 中任何一张的 asset_path；生成器检测到重复会报 ERROR 并跳过该附图。

## 资产命名与位置

- 位置：`projects/<project>/assets/`
- 命名：`scene{s}_{desc_short}.jpg` / `scene{s}_{desc_short}.mp4`（沿用 wrc2027-* 既有风格，如 `scene0_grid.jpg`）

## 环境坑（本会话实测）

- 视觉核验：`.agents/skills/minimax-m3-vision/scripts/analyze_media.py`；**必须 UTF-8**（`PYTHONIOENCODING=utf-8`），输出落盘而非控制台。
- 模型判定对同一内容会波动（观众席/赞助条幅/HUD 的"是否合格"在不同轮次可能翻转）→ 以人工 contact sheet 为准，模型只做初筛。
- 帧抽取用 `C:\Users\tiger\scoop\apps\ffmpeg\current\bin\ffmpeg.exe` 直路。
