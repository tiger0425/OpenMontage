# 06 管线 manifest 与阶段设计（提案 v1，待人审）

> 工单《管线 manifest 与阶段设计》产出。阻塞项 01/02/03/04 均已定案，本文为设计定案提案；manifest/schema 落文件属执行期工作。

## 1. 阶段划分（七阶段 + 双闸门）

```
ingest → brand-kit(一次性) → select-split【闸门A】 → script【闸门B】
       → assets → compose → package(人工发布, 不自动上传)
```

| # | 阶段 | produces（canonical artifact） | 关键字段 | human_approval_default |
|---|---|---|---|---|
| 1 | `ingest` 频道摄取 | `channel_manifest.json` | videos[]: {video_id, url, title, duration_s, lang} | false |
| 2 | `brand-kit` 资产包 | `brand_kit.json` + logo.png / banner.png / seo_tags.json（抖音+小红书两套） | tag_sets{douyin[], xiaohongshu[]}；图走无字底稿模板（findings/05） | true（一次性品牌拍板） |
| 3 | `select-split` 选片分集 | `episode_plan.json` + `split_review.md` | episodes[]: {ep_no, source_span[t0,t1], hook_summary, target_duration_s}；切点算法按 findings/03 | **true（闸门A）** |
| 4 | `script` 脚本改写 | `script.json` + `similarity_report.json` | scenes[]: {narration_zh, emotion, clip(动捕名), prop, caption}；红线扫描按 findings/04（0.75红/0.45黄） | **true（闸门B·脚本闸门）** |
| 5 | `assets` 场景资产 | `asset_manifest.json` | narration WAV 列表(tts_selector)；背景图(image_selector：minimax_image 主 / google_imagen 备)；InkPuppet clip 选择表 | false |
| 6 | `compose` 合成 | `composition/index.html`（HyperFrames 单 paused timeline） | InkPuppet choreograph 表情层 RIG 数据；字幕轨；AI 标识角标（强制） | false |
| 7 | `package` 包装渲染 | `review/{标题}.mp4` + 封面 + `_meta.json` + 简介.txt | 标题 `{钩子}｜第N集`；封面角标 EP.N 排版层叠加 | true（成片终审；发布永远手动） |

## 2. required_tools / fallback_tools（依 findings/01 填实）

| 能力 | 主 | 备 | 说明 |
|---|---|---|---|
| 下载 | yt-dlp（经 auto-dub CLI 同源能力） | video-download skill | 禁 ad-hoc 直调 |
| 转录 | whisper（transcriber） | elevenlabs-scribe | 带时间戳 JSON |
| LLM 改写 | pipeline_automator 内置 LLM | 无 | 术语表沿用 config glossary 模式 |
| TTS | `tts_selector` → voxcpm_tts / indextts（本地 GPU） | minimax_tts | 重算力派 Compute Worker，--json 回报 |
| 生图 | `image_selector` → **minimax_image**（image-01，seed 支持） | google_imagen（gemini-3.1-flash-image） | 全部无字底稿 |
| 角色动画 | ink-theater InkPuppet（CMU 动捕 clips.js） | add-motion.mjs 扩展 | 禁手调 transform |
| 合成 | hyperframes_compose | 手写 index.html 按 mocap-figure 范例 | 单 paused GSAP timeline |
| 混音/压制 | audio_mixer + ffmpeg（concat filter） | — | 禁 concat demuxer -c copy |
| 升级走廊 | minimax_video_direct 图生视频 | — | 仅当试点判定伪动效不足（map 已记备选） |

## 3. 与既有协议对齐

- **checkpoint/reviewer**：对齐 auto-dub 的 `awaiting_review` 语义——闸门A/B/终审挂起时状态置 `awaiting_human`（非失败），重命令前置拒绝；`approve-review` 式回写。
- **轻/重拆分**：阶段 1–4 为轻任务（主会话可跑）；5–7 重算力必须派 Compute Worker，回报单行 JSON（success/output_path/error），心跳流留 Worker 会话。
- **断点续跑**：每阶段产物落盘即 checkpoint；重跑从最后完成阶段续，与仓库 omo.py 状态机同构（执行期落 `pipeline_defs/channel-stickman.yaml`）。

## 4. 待确认 ⚖

1. 七阶段划分与双闸门（A 分集 / B 脚本）是否成立？
2. brand-kit 设为一次性人审阶段是否同意？
