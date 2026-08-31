# setup-video 管线 CLI 规格（bin/setup_video.py）

> 决策来源：`.scratch/setup-video-pipeline/issues/03-pipeline-orchestration.md`（grilling 定稿）
> 模板契约：`projects/setup-video-template/TEMPLATE.md` v0.2
> 先例：`bin/wrc.py`（结构模板）、`bin/auto_dub.py`（队列/预算护栏）

## 形态

独立 CLI，不走 `pipeline_defs/` + omo.py。状态机 SQLite：`projects/setup-video/tracking.db`。

## 轻重拆分硬红线

- **轻命令**（主 Agent 会话内跑）：`scan / fetch / extract / review / approve-review / script / approve-script / status / retry / package-meta`
- **重命令**（必须派 Compute Worker，`--json` 单行回报，`danger-full-access`）：`assets / render`
- 主 Agent 禁止内联跑重命令；Worker 禁止回贴原始 stdout/stderr。

## 状态流

```
pending → downloading → extracting → awaiting_review → scripted
        → assets → rendering → qa → packaged
任何阶段可 → failed（记 failed_stage + last_error，retry 从该阶段续跑）
```

## 每视频产物目录

`projects/<游戏名称-slug>/<视频slug>/`（游戏名取元数据/OCR 清洗；slug = 车名+赛道 kebab-case）：

```
assets/original.mp4        源视频（HD 梯度下载）
assets/s1..s6.wav          IndexTTS 配音（fixed calm 克隆，2026-08-29 定案）
assets/s1_drive.mp4        第一幕行驶片段（crop+慢放，静止图兜底见降级）
assets/bg_loop.mp4         ping-pong 循环背景（blur 由模板 CSS 做）
assets/bgm.mp3             纯环境声 BGM（highpass55+loudnorm I=-15+aloop）
assets/badges/<brand>.png  品牌徽章（assets/brand_logos/ 映射）
assets/shot_*.png          配置图截屏（只准配置界面，禁标题卡/示意图）
artifacts/frames/          extract 阶段采样帧
artifacts/ocr.json         OCR 数值提取结果（MiniMax-M3，票 02 方案）
artifacts/transcript.json  Whisper 解说转写
artifacts/review.html      前 3 条数值对照表（人核用）
artifacts/episode.json     集 JSON（agent 按 script-prompt.md 写，schema 校验）
artifacts/tts_manifest.json  TTS 缓存指纹（G1 防复发：段 narration md5 + TTS 参数签名 ↔ wav）
artifacts/qa/              render 阶段抽的 QA 帧 + 基础校验报告
compose/                   实例化后的 HyperFrames 项目（index.html + assets）
renders/final.mp4          成片
package/                   video.mp4 + title.txt + desc.txt + cover_s1.jpg + cover_s6.jpg
```

## 命令规格

| 命令 | 重/轻 | 做什么 | 停在哪 |
|---|---|---|---|
| `scan <list.txt>` | 轻 | 逐行解析 URL（`URL 备注` 可选）→ 建库行 pending | - |
| `fetch <id>\|--all` | 轻 | yt-dlp HD 梯度 `-f "bv*[height>=1080]+ba/bv*[height>=720]+ba/b"`，2 并发，同 ID 去重 | downloading→pending-extract |
| `extract <id>` | 轻 | **画面稳定性采样**（每秒 1 帧 → 哈希分组 → 相邻帧变化>10 即切段；**所有段尾帧保留**——页面可能只闪现 1-2s）→ **模糊签名聚类**（32x18 高斯模糊 aHash，576bit，阈值 120；同页面聚成一簇，代表帧=簇内最后一帧=落定值——"取最后页"规则，2026-08-28 用户定）→ 每簇一次 MiniMax-M3 读数（kind+页面名+数值，JSON 直出）→ 有参数即 config。同类别连续 config 折叠只留最后一张 | awaiting_review |
| `review <id>` | 轻 | 重新生成/打开 review.html（Invoke-Item）。**对账工具**：`apps/setup-video/scripts/contact_sheet.py <id>` 把代表帧拼带时间戳网格图，可整图交 M3 审计"哪些格子是设置界面"与提取结果对账（2026-08-28 实测定位采样/读数问题关键手段） | - |
| `approve-review <id> [--fix k=v ...]` | 轻 | 修正值写回 ocr.json（标记 human_fixed）→ 放行 scripted | scripted |
| `script <id>` | 轻 | Whisper 转录 → transcript.json + 脚本工单（agent 按 script-prompt.md 写 episode.json） | awaiting_script |
| `approve-script <id>` | 轻 | schema 校验 + 违禁词扫描 + 预算检查（58–65s 规划值）→ 放行 assets | scripted→ready |
| `assets <id> --json` | **重** | IndexTTS 6 段配音（GPU 锁；**wav 缓存按 tts_manifest.json 文本指纹+参数签名校验，改口播无需手动删 wav**，G1 防复发）+ 行驶片段 + ping-pong 背景 + BGM 提取 + 徽章映射 + 配置图截屏 + 聚焦裁剪（G7 矩形组） | assets→ready-render |
| `render <id> --json` | **重** | instantiate_template.py 实例化 → hyperframes 渲染 → 基础 QA → QA 帧采样 → 封面两张 → 成品包 | qa→packaged |
| `status [--json]` | 轻 | 队列状态汇总 | - |
| `retry <id>` | 轻 | 清 failed 标记，从 failed_stage 续跑 | - |

## 批次节奏

10 条/批。每批跑完打印汇总（成功/失败/待核/待抽检）**暂停等用户放行**。M3 视觉抽检：第 4 条起每 10 条抽 1，抽中条 render 完成后由 agent 用 `minimax-m3-vision` 对 `artifacts/qa/` 帧核验。

## QA

- **基础（每条，render 内建）**：渲染退出码、成片时长 ∈ [55, 67]s、silencedetect(n=-38dB) 找解说洞、BGM 轨 astats 非静音。
- **视觉（抽检）**：数字卡终值 = OCR 值；s5 chips 逐条出现；全部截图为配置界面（禁标题卡/零件示意，模板硬规则）。

## TTS 参数（固定，2026-08-29 用户定：去 auto 情绪）

```python
TTS = dict(use_emo_text=False, emo_alpha=1.0, seed=42, speed=1.0,
           spk_audio_prompt="D:/index-tts/my_voice.wav")
# use_emo_text=False → fixed calm 情绪向量（段间语气一致、无拖腔；s1 实测 3.94→4.7 字/s）
# 注意：统一客户端 IndexTTSSession 的 emotion="auto" 硬编码与定案不符 → 走 IndexTTS2TTS 工具路径
```

## 质量护栏（2026-08-28 用户追问"如何保证批量不出错"后确立）

> 原则：视觉 LLM 读任意视频**不可能零错误**（票 02 的 96.9% 是人工挑的干净截图）。保证结构 = 错误**有界、自动可测、修复廉价**，绝不静默传播。

1. **覆盖确定性**：稳定采样全分辨率读数，每个稳定画面必读——漏页在机制上不可能（读得对错另说）。
2. **自动召回审计**（`extract` 内建）：全帧网格图 → 1 次 M3 数"哪些秒是设置界面" → 与提取结果对账 → 缺秒自动定点补读（全分辨率，一次一调用）→ 仍缺记 `ocr.needs_review`，review.html 顶部红横幅警示，**绝不静默通过**。
3. **引用完整性**（`approve-script`）：episode 的 table/points 里每个数字必须能在 ocr.json（含 human_fixed）找到出处；孤儿数字拒绝放行。
4. **人闸**：前 3 条 B 式人核 + 每 10 条抽 1 + 批间暂停汇报（票 03 D3/D13）。
5. **校准即定法**：批量前 3 条 = 方法校准（本会话 EA WRC 暴露的 320px 缩略图、模型格式冲突、折叠过并 3 类根因均已修复并内建审计），定法后不逐条重演。

## 降级路径

- **徽标硬规则（2026-08-28 用户定）**：s1 车标**必须是图形徽标（圆形/飞箭/盾形等），禁止纯文字字标**。映射优先级：`episode.video.brand_badge` 显式指定 > `projects/setup-video-template/assets/logos/<brand>_badge.*`（模板验证过的徽标）> 模板 logos `<brand>.*` > `assets/brand_logos/<brand>*.png`（部分为字标，慎用）。品牌库中纯文字字标（如 skoda.png 的 ŠKODA 字样）不得上屏。

- 行驶片段不可用 → 静止大图兜底（episode.json `drive.fallback_image`，TEMPLATE.md 规则）。
- BGM 提不出干净段 → 复制公共备用 `projects/setup-video-template/assets/bgm.mp3`，成片标记 `bgm_fallback: true`。
- OCR 低置信度 → 票 02 规则（规则区间校验 + 双引擎交叉 + 抽检）。
