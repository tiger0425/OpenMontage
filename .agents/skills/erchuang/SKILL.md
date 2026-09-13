---
name: erchuang
description: >
  Auto-Dub 下游的抖音横屏二创编排（ErChuang）：把 auto-dub 中文成品/原片 二次创作成
  抖音节奏片——去原作头像与广告、按你的音色配音、逐句克隆原片情感、以车辆性能和设计思路为纲、
  完整单集（不拆集不限长）、重点提示 overlay、
  出抖音成品包（封面/简介/meta）并按 auto-dub 协议确认归档。首批 Nissan B_PnlpsVtnw 验证通过。
  触发词：二创、抖音二创、erchuang、把视频做成抖音版、去原作头像配音、拆集连载、换我的音色做解说、
  复用二创管线、日产那种二创。
metadata:
  tags: "erchuang, douyin, remix, emo-ref, indextts, hyperframes-overlay, localization-dub"
---

# ErChuang — 抖音横屏二创编排（auto-dub 下游）

> 2026-09-03 由 Nissan B_PnlpsVtnw P1+P2（用户验收 → review → confirm-video → published）验证固化。
> 任何 Agent 在新会话接手"二创/抖音版"任务，先读本 SKILL。

## 定位与边界

- 输入：auto-dub 已处理过的视频（`projects/auto-dub/auto-dub-<video_id>/` 内有
  `source.mp4`、`assets/vocals.wav`、`assets/no_vocals.wav`、`transcript.json`）。
  缺则先跑 `python bin/auto_dub.py process` 生成。
- 输出：抖音 16:9 横屏成片（你的音色 + 原片逐句情感 + 无原作头像/广告素材 + 重点卡），
  及抖音成品包归档。
- 重算力（GPU TTS/ffmpeg render/hyperframes render）须派 Compute Worker，回报 `--json`/一行摘要
  （见 AGENT_GUIDE Multi-Agent Delegation 与 auto-dub SKILL 的 Log Barrier）。

## 用户资产（音色等）

- 声纹参考：`D:/index-tts/my_voice.wav`（24000Hz PCM，13.6s）。音色 = 用户本人。
- IndexTTS 运行环境：模型 `D:/index-tts`，venv `D:/index-tts/.venv/Scripts/python.exe`，
  权重 `D:/index-tts/checkpoints`（2.5）。情感参考从原片 `assets/vocals.wav` 切。

## CLI 与文件

- 编排 CLI：`bin/erchuang.py`（zones / synth / montage / mux，轻量无 DB，对齐 auto_subtitle）
- 人脸模型：`apps/erchuang/models/{yunet,sface}.onnx`
- 示例 manifest：`apps/erchuang/examples/nissan_p1.manifest.json`
- 桥（合成规范入口）：`apps/indextts-bridge/client.py`；协议字段 `emo_audio_prompt`
  （音色 voice_ref 与情感音频分离；emo_audio 优先于 emo_vector；缺省纯净克隆）已支持，勿直调模型绕过桥。

## 六步流程

1. **禁区标注**：`python bin/erchuang.py zones --video-id <id> --ref-sec <原作头像秒> --out-dir <proj>`
   → `zones.json`（SFace 余弦≥0.35，±5s 并簇；片尾引流段另记）。ref-sec 先抽帧 contact sheet 让用户指认原作头像。
2. **文案（爆款剧作与深度下潜）**：严禁说明书式参数罗列与编年史流水账！必须严格遵守
   `apps/erchuang/specs/STORYTELLING.md` 剧作规范：
   - **黄金 2 秒爆点**：前 2 秒强制三选一（荒谬漏洞 / 生理极限代价 / 降维反杀）；严禁圈内黑话/赛事缩写（IMSA/WSC）、严禁年份时代起手、严禁报菜名、严禁前 3 秒提前报车名自毁悬念。
   - **五步戏剧弧线**：0~5s 悬念核爆 → 5~25s 资本/规则绝境高墙 → 25~60s 致命工程代偿（三层下潜） → 60~90s 赛道命运过山车 → 90s+ 哲学反思与评论区争议。
   - **三层下潜深度剖析**：拒绝报参数（What），讲透工程上的致命代偿与技术赌博（Trade-off），揭露背后的资本与权力围剿真相（Why & Power）。
   - **未闭合悬念链（Open Loops）**：全片主悬念贯穿，每 25~30 秒埋入推翻预期的次级危机，消灭注意力断崖。
   - **质检门禁**：文案写成 `manifest.json` 后，必须运行 `python bin/erchuang.py check-manifest --manifest <path>`，PASS 清零 error 方可进入下一步；同时过 `humanizer-bilibili`（单句≤28字，年份一律汉字）。

3. **合成配音**：`synth` 逐段 IndexTTSSession（voice_ref=my_voice + emo_audio_prompt=原片对位句切片），
   emo_alpha 0.6；manifest `emo_audio` 用 `"vocal@<startSec>:<lenSec>"` 自动切 vocals。
   呼吸 gap：hook 后 300–350ms、段间 150–250ms、收尾 400–700ms；tempo 局部 1.0–1.07。
   产出 `narration.wav` + `timings.json`（overlay 卡点基准）。`--dry-run` 先看计划。
4. **素材蒙太奇**：`montage --cuts "a-b;c-d;..."`（全部取自 zones 禁区之外、画面无语义错位），
   `--bed no_vocals.wav` 同 cuts 出引擎声床（旧 0.15 预乘已弃用——见混音经验）。
5. **overlay + 渲染**（作者环节，未 CLI 化）：手写 `public/index.html`（hyperframes 数据契约），
   卡片时间轴 = narration `timings.json`，**不是**原片转录。卡片样式走
   `.config/opencode/skills/talking-head-recut` 的三处改造版（卡点跟中文配音轴；输入为裁剪后 input-video；
   简体字形 local()）。`npx hyperframes check` 清零 error → `snapshot --at` 自检 → `render -q high` 出 visuals.mp4。
6. **压片 + 成品包 + 确认**：
   `mux --video visuals.mp4 --narration narration.wav --bed bed.wav --out Px.mp4`
   → 按 auto-dub 协议落 `projects/auto-dub/review/<channel>/<中文标题>/`（{标题}.mp4 + 16:9封面 +
   meta.json + 简介txt），DB `tracking.db` 注册新行（video_id 用 `<源id>_P1/_P2`，status=review）
   → 用户确认后 `python bin/auto_dub.py confirm-video <新id>` 归档 published（review 留副本）。

## 混音经验（2026-09-03 用户反馈修）

- `no_vocals` 平均约 -31dB 偏静；mux 里 bed 走 `loudnorm=I=-25:TP=-2:LRA=13` 再与旁白
  `amix=inputs=2:normalize=0`（**不要 normalize=1 默认除 N**）+ `alimiter=limit=0.95`。
  老版 vol0.15 混出 bed ≈ -47dB 等于没声（日产 P1/P2、Eagle 均踩过，已全部重混修正）。
- montage 的 `--bed-volume` 参数仅影响未走 loudnorm 的 montage bed 中间件；最终 mux 会重算，勿依赖。

## 素材禁区经验（2026-09-03 Eagle 复验）

- 出镜常超出 zones 并簇边界 2–5s（Eagle 源 475–478 / 645–648 均漏在 ±5 并簇外）。
  **成片定稿前用 1s 步长 SFace 复核一次成片所用窗口**（脚本循环帧检测，见上），别信 step5 的 zones 一次到位。
- 中插广告常见整段口播出镜（Eagle 193–316s Flexi-Spot），转录 u19–u30 全文可直接当广告区间切。
- 年份数字 TTS 会读"一千九百六十四"，文案一律写"一九六四年"逼标准年份读法（用户 2026-09-03 反馈）。

## 关键规格（用户已验收）

> 全量经验真相源见 `apps/erchuang/LESSONS.md`（决策/踩坑/复验清单）；下表为速查。

| 项 | 值 |
|---|---|
| 时长 | **不限**，内容说清为主（2026-09-05 起不拆集；范例 268.6s 完整单集） |
| 音色 | `D:/index-tts/my_voice.wav` |
| 情感 | 逐句原片 emo_audio_prompt（0.6；0.35 弱档）——calm 太淡、auto(use_emo_text) 太演 |
| 禁区 | SFace 指纹≥0.35 命中 ±5s 并簇 + 片尾引流；全部素材绕行 |
| 文案 | 严格遵循 STORYTELLING.md；黄金2秒爆点3选1；五步戏剧弧线；三层深度下潜；check-manifest 门禁 PASS |
| overlay | 底部数据条/居中 hero/右侧语录卡；卡点=配音时间轴 |
| 完播目标 | 整体≥20%、5 秒完播≥50%、2秒跳出率从40%压降至20%以下（#84） |
| 开局核爆 | 0~2秒：第一视角/近距离“濒死级疯狂驾驶” + 战歌0秒重拍炸响（禁淡入） + 纯净引擎高转声浪 + 原声惊呼 |
| 语音生成 | 严格以标点（。！？）为边界单句生成，禁复合长段；单句一气呵成不乱喘，句间 gap_ms 控制换气 |
| 字幕规范 | 单句即说即显（单行居中，说到哪句显示哪句，禁多行剧透整段）；关键词 `<span class="highlight">` 金黄高亮 |
| 封面规范 | 必须取自无字幕无卡片纯净母本；顶部独立渐变安全区通栏大字，严禁遮挡车辆主体 |
| 片尾收口 | A 阵营 vs B 阵营争议投票强钩子（评论区点火，禁鸡汤平淡收尾） |


## 成品包（抖音规格）

- 标题 ≤55 字、钩子+关键词且与内容相符；封面大字短句（单集不再加"上下集"角标）。
- 封面 16:9：**必须截取纯净原片母本（严禁从带字幕/带HUD卡片的成片中截取）**；标题收束在顶部渐变区，不遮挡主体。
- 简介 txt 首行 `中文标题: <抖音标题>`、次行 `原视频: <英文原题>`、中段 2–3 句梗概、互动投票话题、末行话题标签。

## 已踩坑速查

- **语音断句碎断乱喘**：把复合长段塞给 TTS 会导致模型在内部 token 截断或逗号处随机降调换气。**铁律：严格按标点符号分割单句生成**。
- **字幕多行剧透**：偷懒复用长 chunk 时间轴会导致 2~3 行文本同屏挂 15 秒，剧透后文破坏悬念。**铁律：说到哪句显示哪句，单行聚焦**。
- **封面被字幕/卡片污染**：误从成片压制后的 mp4 截帧会导致片中字幕与 HUD 卡片和封面文字打架。**铁律：封面只从 visuals_clean_base.mp4 纯净母本截帧**。
- drawtext 中文：filter 内 Windows 路径必须 `C\:/...`（正斜杠）+ 整值单引号；坐标用 `main_h`（无 `ih`）。
- hyperframes index.html 中文字体：`@font-face { font-family:"Microsoft YaHei"; src:local("Microsoft YaHei") }`
  （否则 lint `font_family_without_font_face`）。卡片内每类规则前缀 `.card[data-card-id=...]`；禁 `<script>`/外部URL。
- hyperframes `check` 传目录不传文件；`render` 的 mp4 无音轨（video muted）→ 用 mux 加 narration+bed。
- `confirm-video` 只认 DB 行 + `review/<channel>/<标题>/` 目录与标题一致。
- 原片下载失败/机器人验证：过会儿重试或用 `--cookies-from-browser`。

## 当前状态（2026-09-05）

- 首批 4 条全部 published：日产 P1/P2、日产重做 P1R/P2R、Eagle E1、mEYU E1、H-vvv P1/P2、
  mEYU E1R（TS010 车辆详解 85.6s）、H-vvv E1R（Dauer 完整单集 268.6s）。
- 重大转向（2026-09-05）：不再分集、不限时长、车辆性能+设计思路为纲、30 秒一钩、句子写全。
- 待办：#83 map → #88 另 3 条标注、#90 抖音实测数据门槛、其余 19 条复用。`RixZZNV2NxE` 原片曾机器人验证。
- 二次复跑新视频时：先跑第 1 步 zones（需用户指认 ref-sec），再走 2–6。

## 新会话 Quick Start

1. 读本 SKILL（+ auto-dub SKILL、humanizer-bilibili）。
2. `python bin/auto_dub.py status` 看库存；确认目标 `auto-dub-<id>/` 资产齐。
3. 问用户：做哪条视频 / 抖音还是 B 站；原作头像在几秒（或抽 contact sheet 让用户指）。
4. 按"六步流程"跑（不再拆集、不限时长，性能+设计思路为纲），每步产出行注释；TTS/渲染重活派 Worker。
5. 出片后走 review→confirm→published，更新 #83/#90 落账。
