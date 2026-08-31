# setup-video v0.3 批量重做执行清单（2026-08-29，8 条）

> 前置：MC / Wales 两条现代已按 v0.3 验收（fixed calm 配音 + 钩子金句 + 裁剪截图 + 提速 s1）。本条列用于其余 8 条 packaged 视频批量重做。

## 涉及视频（8 条，video_id / slug）

| video_id | slug | 品牌 | 赛道 |
|---|---|---|---|
| (查库) | fabia-rs-rally2-wales | Skoda | Wales |
| (查库) | fabia-rs-rally2-greece | Skoda | Greece |
| (查库) | fabia-rs-rally2-greece-2 | Skoda | Greece |
| (查库) | 208-rally4-wales | Peugeot | Wales |
| (查库) | 208-rally4-alsace | Peugeot | Alsace |
| (查库) | delta-hf-integrale-wales | Lancia | Wales |
| (查库) | delta-hf-integrale-alsace | Lancia | Alsace |
| (查库) | impreza-s3-monte-carlo | Subaru | Monte Carlo |

## 每条改动（顺序执行）

1. **episode.json**：
   - `video.hook`：金句"<赛段痛点解决> · <收益>"（12 字内，从各条 badge/renhua/package.title 提炼）
   - `video.promise`：可省略（默认"全参数片尾定格 · 长按保存"）
   - `narration.s1`：提速句式"<赛道痛点>别乱调，片尾全参数直接抄。"（20-28 字，痛点从 badge/package.title 提炼；避开违禁词"最"）
2. `approve-script <id>`（预算/违禁词/引用完整性）
3. `assets <id> --json`（Worker）：**TTS 缓存指纹已内建（G1 代码化）——改口播后直接跑 assets 自动重录变更段，无需手动删 wav**；fixed calm 全 6 段 + 行驶片段（外部追车探针，无则车内，C5 顺序）+ 背景 + **BGM（非静音校验已内建 G4）** + 徽标 + 截图全帧 + **聚焦裁剪（2026-08-29 内建 assets 第 7 步，G7 矩形自动套用）**
5. `render <id> --json`（Worker）：实例化 v0.3 → 渲染 → QA → package（title/desc/**publish.txt 标题+简介+标签**）

## 批次节奏

- assets 每批 2-3 条串行（GPU 锁）；批间主代理裁截图；render 每批 2-3 条串行
- 每条总耗时 ~25-30 分钟；8 条全程 ~3.5-4.5 小时，分 3 批汇报
- 每批完成后主代理 M3 抽检 1 条（qa 帧），批间暂停汇报等用户放行（批次节奏定案）

## 已知边界

- fabia-turini (xp_sOYhv7QI, ready 未渲染) 用户定跳过，勿碰
- 只做 ACR；EA WRC 搁置（F1）
- 徽标：Skoda/Peugeot/Lancia/Subaru 用模板已验证徽章（F4/F6）；白色版只现代需要
- BGM fallback 属正常降级（G4）；音量 0.22 定案
