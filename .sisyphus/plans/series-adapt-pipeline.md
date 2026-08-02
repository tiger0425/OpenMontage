# Series-Adapt 管线实施计划

## 摘要

设计并实现一个名为 `series-adapt` 的 OpenMontage 生产管线，用于将任意非英语系列视频（播放列表）通过"独立知识重写 + 全新视觉语言 + 用户母语配音"的方式，重建为英语纪录片频道。首个落地项目为 YouTube 频道 @toby5906（人畜无害小托比）的【99追忆】系列（ZTZ-99 中国坦克开发史，100 集已完结），输出为 Vox 风格的英文 HyperFrames 纪录片，旁白使用 IndexTTS2 本地克隆的用户音色。

## 背景

### 源头频道

- **频道**：@toby5906「人畜无害小托比」
- **内容**：中文军事评论，订阅 ~1.76 万
- **组织结构**：多系列并行，包括【内核】（技术评论型）、【俄方回忆录】（叙事型）、【99追忆】（历史回忆录型）、多个影视剧情解说系列
- **字幕情况**：部分视频仅有中文字幕（自动生成），无英文版本，无其他语言翻译版本
- **YouTube/B 站/全网**：未发现该频道内容的任何翻译或搬运版本

### 为何不做翻译搬运

直接下载原视频翻译配音再发布（Auto-Dub 模式）存在不可接受的版权风险。该频道视频画面大量使用了第三方新闻素材、军事示意图等，素材链上的版权无法清理。解决方案是将频道作为"选题灵感库 + 观点来源"，Agent 独立重写英文稿，弃用原画面，用 AI 生成的全新视觉素材替代。

## 目标

1. **管线复用性**：`series-adapt` 不是为 99 坦克史定制的，而是为"任意外语系列 → 新语言纪录片"设计的通用管线
2. **内容再创作**：Agent 理解源视频观点后，用目标语言独立撰写文案（非翻译），保留事实但不复制表达
3. **视觉品牌**：Vox 风格——AI 静态插图 + 动态信息图表 + 动态排版 + 地图推演，全部在 HyperFrames HTML/GSAP 中实现
4. **声音品牌**：用户自己的声音通过 IndexTTS2 本地零样本克隆，100 集保持一致的品牌声线
5. **生产可管理**：100 集通过 tracking.db 状态机跟踪，OMO harness 管理单集 9 阶段流水线

## 范围

### 包含

| 组件 | 说明 |
|---|---|
| `pipeline_defs/series-adapt.yaml` | 管线声明文件（YAML，~120 行） |
| `skills/pipelines/series-adapt/` | 7 个阶段导演技能文件（Markdown） |
| `apps/series-adapt/` | 系列管理应用：`config.yaml` + `series_runner.py` + `db.py` |
| `bin/series_adapt.py` | CLI 入口（从 `auto_dub.py` 改编） |
| IndexTTS2 注册 | 将 IndexTTS2 注册为 OpenMontage TTS 工具 |
| HyperFrames 自检协议 | 每次会话开始时执行能力刷新 |
| 术语发音表 | `glossary.yaml`：~20 个坦克军事型号的英语/IndexTTS2 自定义读音 |

### 不包含

- 不做原视频的 1:1 翻译（版权原因）
- 不实现 VoxCPM2 的英文 TTS 适配（已确定为中文引擎，英文质量不够）
- 不做 ElevenLabs API 集成（已选 IndexTTS2 本地方案，零边际成本）
- 首版不支持视频素材（原版画面不在复用范围之内）

## 技术决策

以下为 grilling 会话中逐一确认的全部架构决策：

| # | 决策项 | 结论 | 理由 |
|---|---|---|---|
| 1 | 内容模式 | **独立重写**——Agent 阅读源视频转录稿，提取核心观点后用英文重新组织表达 | 版权安全 + 内容质量更高 |
| 2 | 首季系列 | **【99追忆】**——ZTZ-99 坦克总师回忆录，100 集已完结，叙事完整 | 有头有尾；历史 > 时事；英文军事史受众成熟 |
| 3 | 视觉风格 | **Vox 风格**——AI 坦克插图 + 动态信息图表 + 排版动效 + 地图推演 | 绕过 AI 视频一致性难题；动态图表天然适合技术纪录片 |
| 4 | 组合引擎 | **HyperFrames**——HTML/CSS/GSAP，动态排版和信息图是它的绝对主场 | Vox 风格的核心竞争力就是排版和图表 |
| 5 | HyperFrames 版本 | **每次会话自检协议**——`npx hyperframes --version && --help && catalog --json` | `npx --yes` 总是拉最新版，但 Agent 需要用自检结果更新上下文 |
| 6 | 管线命名 | **`series-adapt`**——描述"系列→新语言→新视觉"的通用再创作模式 | 不绑定单个项目，未来【内核】【俄方回忆录】都能复用 |
| 7 | 调度架构 | **混合**——系列管理（tracking.db + CLI）用独立 `bin/series_adapt.py`，单集生产（9 阶段）走 OMO harness | Auto-Dub 批处理逻辑 + OpenMontage 创意审查流程 |
| 8 | 工具复用 | **全部复用**——8 个所需工具已在 registry 中，0 行代码需写 | `video_downloader`、`transcriber`、`tts_selector`、`image_selector`、`hyperframes_compose`、`video_compose`、`audio_mixer`、`export_bundle` |
| 9 | TTS 引擎 | **IndexTTS2**——本地部署，零样本声音克隆，FP16 模式，运行在 3090 GPU | 唯一同时满足"本地 + 克隆 + 好英文 + 情绪控制 + 免费"的方案 |
| 10 | Kokoro | 否决——不支持声音克隆，架构设计就不包含此能力 | 只能使用预置声线，无法使用用户自己的声音 |
| 11 | VoxCPM2 | 否决——英文质量差，主要训练语言为中文 | 适合中文配音，不适合英文纪录片 |
| 12 | ElevenLabs | 备选——如果需要，可替代 IndexTTS2，但 1000 分钟旁白 ~$100-200 | IndexTTS2 满足需求且免费，ElevenLabs 作为 fallback |
| 13 | 本地 TTS 检索 | **IndexTTS2**（B 站 Index Team, 22.3k stars, arXiv 2506.21619） | 开源 + 零样本克隆 + 情绪解耦 + 精确时长控制 + FP16 8-12GB VRAM |
| 14 | 管线创建量 | ~10 个文件，<2000 行声明代码 + Markdown | YAML 管线 + 导演技能 + 改编 auto-dub 的 CLI/追踪库 |

### VRAM/性能评估（IndexTTS2 on 3090）

| 指标 | 数值 |
|---|---|
| 模型文件数 | `gpt.pth` (~3-5GB) + `s2mel.pth` (~1-2GB) + 辅助文件 |
| FP16 模式 VRAM | ~8-12 GB（3090 24GB 轻松承载，剩余 12GB+） |
| FP32 模式 VRAM | ~16-22 GB（紧但可跑） |
| 实时率（RTF） | 10-30×（每秒 GPU 时间生成 10-30 秒音频） |
| 单集 10 分钟旁白 | ~20-60 秒合成时间 |
| 100 集全量 | ~30-100 分钟 GPU 总耗时 |
| 声音克隆 | 零样本——1 段参考音频即可，无需训练 |

## 管线设计

### 架构概览

```
┌──────────────────────────────────────────────────┐
│              bin/series_adapt.py                  │
│  run / status / import / process / mark-done      │
└──────────────┬───────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  apps/series-adapt/ │
    │  config.yaml        │  ← 系列配置、源播放列表、目标语言、视觉风格
    │  series_runner.py   │  ← 状态推进 + 调用 OMO harness
    │  db.py              │  ← tracking.db CRUD
    └──────────┬──────────┘
               │ 每集调用
    ┌──────────▼──────────┐
    │  bin/omo.py         │
    │  start-stage /       │  ← OpenMontage 统一 harness
    │  submit-artifact     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────────────────────────────┐
    │  pipeline_defs/series-adapt.yaml             │
    │                                              │
    │  fetch → brief → rewrite → scene_plan →     │
    │  assets → compose → render → review → publish │
    └──────────────────────────────────────────────┘
```

### 目录结构

```
OpenMontage/
├── pipeline_defs/
│   └── series-adapt.yaml                    # 新：管线声明（~120 行 YAML）
├── skills/pipelines/series-adapt/
│   ├── fetch-director.md                    # 新：下载 + Whisper 转写
│   ├── brief-director.md                    # 新：提取观点 + 事实梳理
│   ├── rewrite-director.md                  # 新：重写英文稿 + 视觉提示
│   ├── scene-director.md                    # 新：场景拆分 + 画面方向
│   ├── asset-director.md                    # 新：TTS + AI 图片生成
│   ├── compose-director.md                  # 新：HyperFrames HTML 组合
│   └── publish-director.md                  # 新：SEO 元数据 + YouTube 上传包
├── apps/series-adapt/
│   ├── config.yaml                          # 新：系列配置
│   └── series_runner.py                     # 新：改编自 auto-dub/batch_runner
├── bin/
│   └── series_adapt.py                      # 新：改编自 auto_dub.py
├── tools/audio/
│   └── indextts_tts.py                      # 新：IndexTTS2 工具注册
└── projects/series-adapt-99/
    ├── tracking.db                           # 新：100 集状态机
    └── ep-{NN}-{slug}/                       # 每集独立工作目录
        ├── assets/
        │   ├── images/                       # AI 生成的坦克/图表/地图
        │   ├── audio/                        # IndexTTS2 旁白分段 WAV
        │   ├── source/                       # 源视频 + 中文字幕/转录
        │   └── brief.json                    # 本集观点提取结果
        ├── edit_decisions.json               # 场景组合决策
        └── hyperframes/                      # HyperFrames 工作空间
            ├── index.html
            ├── hyperframes.json
            ├── DESIGN.md
            └── renders/
                └── final.mp4
```

### 单集 9 阶段流水线

| 阶段 | 名称 | 导演技能 | 输入 | 输出 | 人工审查 | 核心工具 |
|---|---|---|---|---|---|---|
| 1 | `fetch` | `fetch-director.md` | 源 YouTube URL | 源视频文件 + Whisper 中文转录稿 | 否 | `video_downloader`、`transcriber` |
| 2 | `brief` | `brief-director.md` | 中文转录稿 | `brief.json`——核心论点、关键技术事实、时间线节点、术语表 | 否 | Agent 分析能力 |
| 3 | `rewrite` | `rewrite-director.md` | `brief.json` | `script.json`——英文旁白全文 + 每段配图方向 | **是** | Agent 写作能力 |
| 4 | `scene_plan` | `scene-director.md` | `script.json` | `scene_plan.json`——场景序列（插图/图表/地图/文字卡类型 + 时长 + 动效类型） | 否 | Agent 规划能力 |
| 5 | `assets` | `asset-director.md` | `scene_plan.json` + `script.json` | `asset_manifest.json`——AI 图片文件 + TTS 旁白分段 WAV | 否 | `tts_selector`→IndexTTS2、`image_selector`→FLUX/ComfyUI |
| 6 | `compose` | `compose-director.md` | `asset_manifest.json` + `scene_plan.json` | `index.html`（Vox 风格 HyperFrames 组合） | 否 | `hyperframes_compose` |
| 7 | `render` | —（无独立技能文件，走 compose-director 末尾步骤） | `index.html` | `final.mp4` | 否 | `hyperframes_compose`（lint → validate → render） |
| 8 | `review` | —（走 meta/reviewer.md） | `final.mp4` | `final_review.json` | **是** | `ffprobe` 检测 |
| 9 | `publish` | `publish-director.md` | `final.mp4` + `final_review.json` | YouTube 上传包（视频 + 元数据 + 缩略图概念） | **是** | `export_bundle` |

### 状态机（tracking.db → episodes 表）

```sql
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_num INTEGER NOT NULL,           -- 01~100
    source_video_id TEXT NOT NULL,          -- YouTube video ID
    source_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'imported', -- 状态流转
    title_zh TEXT,                           -- 原中文标题
    title_en TEXT,                           -- 重写后英文标题
    slug TEXT,                               -- URL 友好标识
    work_dir TEXT,                           -- 工作目录路径
    error_msg TEXT,                          -- 错误信息
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

状态流转：`imported` → `fetched` → `briefed` → `rewritten` → `scene_planned` → `assets_ready` → `composed` → `rendered` → `reviewed` → `published`

### config.yaml 结构

```yaml
series:
  name: "ZTZ-99: The Iron Dragon"
  source_playlist: "https://www.youtube.com/playlist?list=PL1cW_x46fy4TTDUk_5nrKZToywGMI9aVR"
  target_language: "en"
  episode_count: 100
  episode_duration_target: 600  # 秒（10 分钟）

tts:
  provider: "indextts_tts"
  voice_reference: "my_voice.wav"   # 用户录音参考文件路径
  emotion: "calm"                    # 纪录片风格：平静
  fp16: true                         # 3090 推荐 FP16

visual:
  style: "vox-documentary"           # Vox 风格动态图表/排版
  image_provider: "image_selector"   # 自动选择可用图片生成器
  color_scheme: "military-green"     # 军绿/沙色/深蓝 + 重点红/橙
  diagram_style: "flat-vector"       # 扁平矢量风格坦克插图

composition:
  runtime: "hyperframes"
  hyperframes_version_check: true    # 每次会话执行自检协议

glossary:
  path: "apps/series-adapt/glossary.yaml"

output:
  youtube_category: "Science & Technology"
  default_tags: ["tanks", "military history", "Chinese defense", "ZTZ-99", "MBT", "armored warfare"]
  disclosure: "This video features AI-generated visuals and synthetic voice narration."
```

### HyperFrames 自检协议（每会话）

```bash
# 每次生产会话开始时执行：
npx hyperframes --version              # 当前版本
npx hyperframes --help                 # 当前 CLI 命令列表
npx hyperframes catalog --json         # 当前可用的 registry blocks

# Agent 用以上输出更新本会话的能力上下文，与新功能/弃用标记对齐
```

### 术语发音表（glossary.yaml 骨架）

```yaml
# 坦克型号 → IndexTTS2 自定义英文读音
terms:
  ZTZ-99:    "zee tee zee ninety nine"
  ZTZ-96:    "zee tee zee ninety six"
  T-62:      "tee sixty two"
  T-72:      "tee seventy two"
  M1A2:      "em one ay two"
  MBT-70:    "em bee tee seventy"
  WZ-122:    "double-u zee one twenty two"
  L7:        "el seven"
  VT-4:      "vee tee four"
  59式:      "type fifty nine"
  69式:      "type sixty nine"
  79式:      "type seventy nine"
  99式:      "type ninety nine"
  # ... 按需扩展，一次建立，100 集复用
```

## 验证策略

### 阶段验证（每条管线阶段内建审查关注项）

| 阶段 | 验证项 |
|---|---|
| `fetch` | 源视频成功下载（md5 校验）；Whisper 转录稿包含完整时间戳；中文文本未被截断 |
| `brief` | `brief.json` 至少包含 3 个核心论点、5 个关键事实、1 条时间线 |
| `rewrite` | 英文稿时长在目标 ±10% 范围内；不包含直接翻译的中文句式；军事术语拼写正确 |
| `scene_plan` | 每 60 秒至少有 2 次视觉变化（场景切换/动画触发）；无连续 3 个场景使用同类型 |
| `assets` | 所有图片文件存在且分辨率 ≥ 1920×1080；TTS 音频覆盖全稿；无静音段落（RMS 检查） |
| `compose` | `hyperframes lint` 通过；`hyperframes validate` 通过 |
| `render` | `final.mp4` 存在且 ffprobe 验证通过；时长在目标 ±5% 内 |
| `review` | 人工观看后批准（或标记修改意见） |
| `publish` | SEO 元数据完整；章节标记存在；缩略图概念已生成 |

### 集成测试

1. **100 集状态流转测试**：在空 tracking.db 上模拟 `import → process → review → publish` 全周期
2. **IndexTTS2 一致性测试**：用同一参考音频克隆后合成 3 段不同文本，人工听感比较音色一致性
3. **术语发音验证**：合成所有 `glossary.yaml` 术语的独立句，验证发音准确性
4. **HyperFrames 渲染稳定性**：同一集 `index.html` 连续 render 3 次，ffprobe 对比输出哈希一致性

## 执行策略

### 优先级排序

| 优先级 | 任务 | 依赖 | 预估工作量 |
|---|---|---|---|
| **P0** | IndexTTS2 安装 + 工具注册 + 音色试样 | 无 | 1 会话 |
| **P0** | 安装 espeak-ng 系统依赖 | 无 | 10 分钟 |
| **P1** | 创建 `pipeline_defs/series-adapt.yaml` | P0 | 1 会话 |
| **P1** | 创建 7 个阶段导演技能文件 | P1（管线声明） | 2 会话 |
| **P1** | 创建 `apps/series-adapt/config.yaml` + `series_runner.py` + `bin/series_adapt.py` | P0 | 1 会话 |
| **P1** | 创建 `tools/audio/indextts_tts.py` 工具注册 | P0 | 1 会话 |
| **P2** | 创建 `glossary.yaml` 术语发音表 | P0（需 IndexTTS2 可运行） | 1 会话 |
| **P2** | 试点生产 99追忆 第 01 集（全 9 阶段） | P1 全部 | 2 会话 |
| **P2** | 人工观看第 01 集成品，收集修改意见 | P2 | 1 会话 |
| **P3** | 修复第 01 集反馈，标准化为模板 | P2 | 1 会话 |
| **P3** | 导入 99追忆 全部 100 集到 tracking.db | P1（CLI 完毕） | 1 会话 |
| **P3** | 批量生产第 1 季（第 02-10 集） | P3 全部 | 5-10 会话 |
| **P4** | 建立 HyperFrames 视觉组件库（坦克卡片、地图模板、统计图表组件） | P2 | 3-5 会话 |
| **P4** | 集成测试（状态流转、TTS 一致性、HyperFrames 稳定性） | P3 | 1 会话 |

### 试点单集（99追忆 01）验证全流程

选 99追忆第 01 集作为试点，原因：
1. 它是整个系列开头，叙事上做第一集最自然
2. 验证全部 9 阶段从 fetch 到 publish 的可行性和耗时
3. 暴露 IndexTTS2 英文军事术语发音问题，提前建立术语表
4. 验证 HyperFrames Vox 风格模板，后续集可以套用

## 待办事项

### Phase 0：环境准备

- [ ] 安装 espeak-ng（Windows/Linux 系统依赖）
- [ ] 安装 `uv` 包管理器
- [ ] 克隆 IndexTTS-2 仓库并安装依赖（`uv sync --all-extras`）
- [ ] 下载 IndexTTS-2 预训练权重到本地
- [ ] 在 3090 上运行 `uv run webui.py --fp16`，验证 GPU 推理可用
- [ ] 录制一段 10-30 秒的干净英文人声音频作为参考样本
- [ ] 用参考音频合成一段 60 秒坦克史英文旁白试听，确认音色/发音满意
- [ ] 注册 `indextts_tts` 到 OpenMontage 工具注册表
- [ ] 建立 `glossary.yaml` 初始术语发音表（~20 个坦克型号）

### Phase 1：管线基础设施

- [ ] 创建 `pipeline_defs/series-adapt.yaml`
    - 定义 9 阶段 + 所需/可选工具列表
    - 配置 `human_approval_default: true` 于 `rewrite`、`review`、`publish` 阶段
    - 配置 `reference_input` 支持
- [ ] 创建 `skills/pipelines/series-adapt/fetch-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/brief-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/rewrite-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/scene-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/asset-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/compose-director.md`
- [ ] 创建 `skills/pipelines/series-adapt/publish-director.md`
- [ ] 创建 `apps/series-adapt/config.yaml`（基于上述模板）
- [ ] 创建 `apps/series-adapt/series_runner.py`（改编自 `auto-dub/batch/batch_runner.py`）
- [ ] 创建 `bin/series_adapt.py`（改编自 `auto_dub.py`）
- [ ] 创建 `tools/audio/indextts_tts.py`（BaseTool 子类，包装 IndexTTS2 调用）

### Phase 2：试点生产

- [ ] 导入 99追忆播放列表到 `projects/series-adapt-99/tracking.db`
- [ ] 选择第 01 集执行 `series-adapt process`
- [ ] `fetch` 阶段：下载源视频 + Whisper 中文转录
- [ ] `brief` 阶段：提取第 01 集的核心观点和关键事实
- [ ] `rewrite` 阶段：撰写英文稿（提交人工审查）
- [ ] `scene_plan` 阶段：拆分场景序列
- [ ] `assets` 阶段：生成 AI 坦克插图 + IndexTTS2 合成旁白
- [ ] `compose` 阶段：编写 HyperFrames index.html（Vox 风格）
- [ ] `render` 阶段：HyperFrames lint → validate → render
- [ ] `review` 阶段：人工观看 final.mp4（提交审查）
- [ ] `publish` 阶段：导出 YouTube 上传包

### Phase 3：系列扩产

- [ ] 基于第 01 集反馈标准化模板
- [ ] 建立 HyperFrames 视觉组件库（可复用的 Vox 风格场景模板）
- [ ] 导入全部 100 集到 tracking.db
- [ ] 批量推进第 1 季（第 02-10 集）
- [ ] 第 1 季完结后执行集成测试
- [ ] 第 2-10 季延用相同流程

## 风险与约束

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| **IndexTTS2 英文军事术语发音不准确** | 中 | 建立 `glossary.yaml` 术语发音表 + 音素覆写（IndexTTS2 支持自定义读音） |
| **100 集 HyperFrames 视觉疲劳** | 中 | 建立可复用组件库（模板而非每集重写）；Phase 4 专门投入 3-5 会话建立组件库 |
| **HyperFrames npm 更新打破现有 index.html** | 低 | 每会话自检协议 + `hyperframes doctor` 预检；`npx --yes` 可随时指定版本回退 |
| **IndexTTS2 FP16 精度损失影响声音克隆质量** | 低 | FP16 文档称损失极小；必要时回退到 FP32（3090 24GB 可承载） |
| **YouTube Content ID 误匹配（因军事素材相似）** | 低 | 所有画面均为 AI 生成/原创图表，不包含原视频或新闻素材片段 |
| **100 集产能（时间和人力）** | 高 | 第 01 集试点测量单集全流程耗时；Phase 3 基于实测数据进行生产规划；如单集 >2 会话则考虑缩减季规模或并行生产 |
| **YouTube 对 AI 合成语音的政策变化** | 低 | 在视频描述中添加 `disclosure` 声明；IndexTTS2 克隆的是用户自己的声音，不属于冒充 |

## 成功标准

### 管线级别

- [ ] `series-adapt` 管线定义通过 schema 验证
- [ ] 系列 CLI `bin/series_adapt.py` 支持 `import` / `status` / `process` / `mark-done` 四个子命令
- [ ] `tracking.db` 状态机支持全部 10 个状态的正向流转和错误回退
- [ ] IndexTTS2 工具通过 `registry.provider_menu_summary()` 可见并可调用
- [ ] HyperFrames 自检协议在 Agent 会话初始化时自动执行

### 试点级别（第 01 集）

- [ ] 全 9 阶段走通，无阻塞性错误
- [ ] `final.mp4` 输出可播放，时长 8-12 分钟
- [ ] 旁白音色与参考音频一致（人工耳听通过）
- [ ] Vox 风格视觉效果包含：≥ 5 张 AI 坦克插图、≥ 2 个动态图表、≥ 1 个地图推演图
- [ ] 与源视频对比：英文稿表达的观点匹配原视频核心论点，但逐句对照无直接翻译

### 系列级别（第 1 季 10 集）

- [ ] 全部 10 集完成 review → published
- [ ] 跨集视觉风格一致（配色/字体/图表风格统一）
- [ ] 跨集旁白音色一致（IndexTTS2 同一参考音频 + 同一声线预设）
- [ ] 每集生产时间随经验下降（第 10 集应明显快于第 01 集）
