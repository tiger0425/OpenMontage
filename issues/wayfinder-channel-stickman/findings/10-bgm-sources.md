# 调研 10：BGM 音源来源评估（channel-stickman，约 2 分钟中文心理学解说）

> 只读调研。预检已知事实：`music_generation` 能力 0/3 配置（elevenlabs / minimax / suno 均无 key）。

## 一、music_library/ 目录清点

目录**存在**，含 1 个曲目文件：

| 文件名 | 大小 | 时长（ffprobe 实测） |
|--------|------|---------------------|
| `ep01_bgm.mp3` | 3,745,876 字节（约 3.6 MB） | 93.5 秒 |

关键结论：

- 文件名 `ep01_bgm` 表明这是第 1 集用过的 BGM，**可直接复用**（若该集风格延续）。
- **93.5 秒 < 约 2 分钟目标时长**，直接使用需做循环拼接 + 尾部淡出（FFmpeg `audio_processing` 本地能力即可完成），或另补一首更长的曲目。
- 该工具族对应 `music_library` 工具（`tools/audio/music_library.py`，capability=`music_library`，runtime=LOCAL，无任何依赖），支持 `MUSIC_LIBRARY_DIR` 环境变量覆盖库路径；支持扩展名：mp3/wav/m4a/aac/flac/ogg/opus/aiff。

## 二、music_generation 族工具清单

通过 grep `tools/` 源码确认，capability=`music_generation` 的工具有 **3 个**，全部为 API 运行时、依赖单个环境变量：

| 工具 | 源文件 | provider | runtime | 所需 env var |
|------|--------|----------|---------|--------------|
| `music_gen` | `tools/audio/music_gen.py` | elevenlabs | API | `ELEVENLABS_API_KEY` |
| `minimax_music` | `tools/audio/minimax_music.py` | minimax | API | `MINIMAX_API_KEY` |
| `suno_music` | `tools/audio/suno_music.py` | suno | API | `SUNO_API_KEY` |

各工具特性要点：

- **music_gen（ElevenLabs Music）**：背景音乐 + SFX；duration 3–600 秒可精确指定（适配 2 分钟视频）；SYNC。
- **minimax_music（MiniMax）**：纯音乐/带词歌曲；**固定时长槽位仅 30 / 60 / 120 秒**（120s 恰好匹配 2 分钟视频，但无法精确到实际成片长度）；ASYNC。
- **suno_music（Suno via sunoapi.org）**：完整歌曲/器乐，最长约 8 分钟；每次请求产出 2 首默认取第 1 首；BETA。

相邻但不属于 `music_generation` 能力族的音源工具（grep 同步发现，供走廊 A 参考）：

- `freesound_music`（capability=`music_search`，API，env=`FREESOUND_API_KEY`——官网免费申请）：按 mood/genre 标签搜 CC 授权音频并下载。
- `pixabay_music`（capability=`music_search`，API 爬虫实现，**无需任何 key**）：Pixabay 免版权音乐搜索下载；稳定性一般（站点改版即失效）。

## 三、三条走廊评估与推荐排序

### 推荐 A（首选）：库存 / 用户自备曲导入 music_library/

- **现状**：库里已有 `ep01_bgm.mp3`（93.5s）。复用它只需 FFmpeg 循环+淡出，**零成本、零 key、立即可执行**。
- **补充来源**：YouTube Audio Library、Jamendo、Freesound、Pixabay Music 等免版权渠道人工下载后放入 `music_library/`；其中 Freesound/Pixabay 还有现成工具（`freesound_music` 需免费 key；`pixabay_music` 无 key）可代为检索下载。
- **适用场景**：风格延续型系列（如 ep01 已定调）、预算为零、希望提案阶段就锁定确定性音源（AGENT_GUIDE 要求 proposal 阶段呈现 music plan，库存曲是唯一"看得见摸得着"的选项）。
- **代价**：需要人工挑选与版权自查（确认 royalty-free / CC 许可条款允许商用与二次创作）；情绪定制精度低于生成式 API；当前单曲偏短需循环处理。

### 推荐 B（次选）：配 key 解锁 API 生成

key → 工具解锁关系：

| 配置的 env var | 解锁的音乐工具 | 附带解锁 |
|---------------|---------------|---------|
| `ELEVENLABS_API_KEY` | `music_gen` | `elevenlabs_tts` 等 ElevenLabs 族 |
| `MINIMAX_API_KEY` | `minimax_music` | `minimax_tts`、`minimax_image`、`minimax_video_direct` 等 MiniMax 族 |
| `SUNO_API_KEY` | `suno_music` | 仅音乐 |

- 成本：**需查官网**（本调研不引用任何具体价格）。
- 适用场景：想要与解说文案情绪精确对齐的定制曲（如指定"温暖钢琴+弦乐渐强"）、系列长期量产希望每集曲风差异化、且愿意承担注册与付费成本。
- 代价：注册流程 + API 计费 + 网络依赖；生成结果随机需试听筛选；`minimax_music` 时长槽位固定（120s 槽最接近本需求）；单配一个 key 即可满足音乐需求，无需三个都配。

### 推荐 C（兜底）：无 BGM 仅人声

- **适用场景**：极简冷静风（部分心理学内容刻意去配乐以突出"临床感/可信感"）、人声质量极高且节奏自足、或 A/B 均不可行时的兜底。
- **代价**：零成本零风险零额外工序；但 2 分钟解说全程无人声衬底会显得干涩，情绪引导、段落转场感和完播率通常受损，抖音竖屏生态下尤其吃亏。

### 综合排序理由

**A > B > C**。A 是唯一当前即可落地且有现成资产的路径，符合"先盘点再花钱"的原则；B 的价值在于定制化与量产差异化，但被 0/3 key 的事实阻塞，属于"一分钟配置决策"而非技术障碍；C 仅在用户明确偏好无配乐美学时才应主动选择，否则作为兜底而非首选。

## 四、心理学解说类短视频 BGM 情绪基调建议（3 个方向）

1. **温暖钢琴 + 轻弦乐**（warm piano, soft strings, gentle swell）
   共情、安抚基调。适合认知偏差、情绪调节、亲密关系等"贴近生活痛点"选题；让解说显得温和不说教。
2. **极简 ambient pad / lo-fi 底色**（minimal ambient, calm pads, subtle texture）
   中性、冷静、克制。适合脑机制、实验研究、数据结论等"硬知识"段落；低存在感不抢注意力，长循环不易疲劳，最适合 2 分钟信息密度高的解说。
3. **轻快原声 pluck / curious acoustic**
   微妙的好奇感与推进感。适合"为什么我们会……"式 hook 开场的选题，前 5 秒抓人后回落为底色。

**通用约束**（无论哪个方向）：

- 纯器乐、**无人声**（避免与人声解说频段冲突）；
- 低至中强度，避免强鼓点、大起大落与突然转调；
- 混音时 BGM 音量压在人声之下并做人声段 ducking；
- 选循环友好型曲目（当前 `ep01_bgm.mp3` 93.5s 循环拼接时注意首尾相位衔接 + 尾部淡出）。
