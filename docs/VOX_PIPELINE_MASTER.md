# VOX 纸质拼贴管线总纲（2026-10 现状版）

> **本文定位**：把「VOX 拼贴」体系的两条执行路线、共享视觉 DNA、生图/配音/合成/字幕全链路规范整理成单一索引。
> 细则是唯一事实源（各 spec / skill 原文）；本文与原文冲突时以原文为准，并回写本文。
> 相关文档：`docs/VOX_PAPER_COLLAGE_HELP.md`（自然语言使用指南）、`docs/VOX_PAPER_COLLAGE_SESSION_GUIDE.md`（复现手册）、`docs/adr/ADR-002-vox-paper-collage-playbook-alignment.md`（治理决策）、`apps/vox-collage/specs/`（路线 A 四件套规范）。

---

## 0. 两条路线总览

本仓库的 VOX 拼贴有**两条并行的执行路线**，共享视觉 DNA 与提示词资产，2026-10 起生图统一为 **Qwen-Image 2.1**。

> ⚠️ **路线 B 已于 2026-10-04 冻结，不要再向它投入维护。**
> 实测：路线 B 29 文件 / 6216 行，占本视觉风格总量的 **59.5%**，却**从未被执行过一次**（0 checkpoint）；
> 实际出片全部走路线 A（21 文件 / 4226 行）。改一组节奏参数会牵动 10 个文件（`f454040` 实证）。
> 冻结标记：`pipeline_defs/vox-paper-collage.yaml` → `metadata.frozen: true`。
> 处置决策与分阶段计划：`docs/optimization-charters/vox-pipeline-simplification.md`。

| 维度 | 路线 A：CLI 全自动线 | 路线 B：原生 8 阶段线 |
|---|---|---|
| 入口 | `python bin/vox_collage.py <cmd>` | `bin/omo.py` 状态机 + EP 编排；用户用自然语言驱动 agent |
| 代码/规范 | `bin/vox_collage.py` + `apps/vox-collage/` + `.agents/skills/vox-collage/SKILL.md`（**已入库**，见 `a42ce30`） | `pipeline_defs/vox-paper-collage.yaml` + `skills/pipelines/vox-paper-collage/` + `styles/vox-paper-collage*.yaml`（**已冻结**） |
| 编排方式 | 命令串行，script 单人审闸门；重命令派 Compute Worker | EP（executive-producer）串行驱动 8 阶段，多个人审闸门 |
| 生图 | Qwen21-txt2img（AI 幕）+ wf_edit（真实照片重绘） | Qwen21-txt2img + Qwen21-edit（单参考净化版）+ wf_edit（双参考备用） |
| 视频动效 | MiniMax H3 核心幕图层组装 + HyperFrames 2% slow drift | HyperFrames 确定性动画（build-on/living-poster，无 H3） |
| 配音 | IndexTTS 2.5 桥接（回退 Edge-TTS） | tts_selector → indextts_tts |
| 字幕 | FFmpeg + ASS 3D 挤出立体字幕（后烧） | 无独立字幕阶段（如需硬字幕另行补充） |
| 音乐 | 暂无 BGM 步骤（旁白 + ASMR） | pixabay_music / 素材库（Egyptian trailer 系）|
| 缩略图 | 暂无 | publish 阶段 3 张 Thumbnail DNA |
| 适合 | 本地一键生产、中文视频现役主产线、90 秒~10 分钟 | 需要多闸门治理、素材库/数据真实性管线的通用 agent 流程 |

---

## 1. 共享视觉 DNA

### 1.1 核心铁律

1. **真实素材入画**：真车/真装备/企业 Logo/历史人物/工厂赛道必须用真实摄影素材（Wikimedia Commons 等），拒绝 AI 臆造；AI 只做「风格化重绘」。
2. **基准图锚定**：立项先定 Master Sheet（如 `archival-red`）；色板、排版、图注规则从母版抽取。
3. **色彩克制**：红色仅作最高层级强调（描边/下划线/箭头/连线/图章/数据英雄），**严禁大面积铺底**；芥末黄/辅助色极度克制。
4. **动静混编**：核心幕跑图层组装视频；叙事幕用高清静帧 + **2% 呼吸慢漂移**，杜绝 PPT 感。
5. **母版与字幕解耦**：HyperFrames 只渲染**无字幕纯净母版**；字幕由 FFmpeg + ASS 后烧（改错别字不重渲染）。

### 1.2 调色板与四主题（路线 A `apps/vox-collage/presets/`；路线 B 见 styles）

| 主题 | 适用题材 | 基底纸色 | 油墨 | 主强调 | 二级辅助 | 暗纹 |
|---|---|---|---|---|---|---|
| `archival-red`（基准） | 历史、调查、地缘 | `#C9BB9C` 档案棕 | `#1A1A1A` | `#B62E1F` 热红 | `#D9A441` 芥末黄 | 老地图等高线 |
| `racing-orange` | 汽车、WRC/F1、重工 | `#1E2024` 沥青深灰 | `#FFFFFF` | `#FF5500` 竞速橙 | `#FFD200` 赛道黄 | 赛道/转速表 |
| `tech-cyan` | 半导体、AI、芯片 | `#16181D` 极客冷黑 | `#E0E6ED` | `#00D2FF` 荧光青 | `#FF5F1F` 警示橙 | 电路/晶圆栅格 |
| `finance-green` | 商业、股市、资本 | `#EDE6D6` 浅牛皮 | `#1F2421` | `#2E7D32` 美钞绿 | `#C59B27` 黄铜金 | 财报网格/K线 |

> 路线 B 另有 `vox-paper-collage.yaml`（旧报纸）与 `vox-paper-collage-guofeng.yaml`（国风：宣纸+朱印）两套播放本，色板独立维护。
> 注意：设置主题时旧主题 master sheet 缺失会按调色板**动态生成**主题母版（`build_theme_master_sheet`），禁止静默串色回退。

### 1.3 标准零件库（6 类）

1. **主体抠图**：rembg 去底 + 粗糙纸质白边（3-6px）+ 错位强调描边（4-8px，偏移 4px）+ 投影 `drop-shadow(0 15px 25px rgba(0,0,0,.35))`。
2. **撕裂便签底衬**：毛边纤维白/淡色纸条，垫大标题或作分割线。
3. **地图定位标**：双层倒水滴大头针，红白嵌套。
4. **数据标签徽章**：剪纸胶囊/方框，白底红字或红底白字，带半调网点（承载 `$123B`、`420HP`、`85%`）。
5. **档案老相纸**：真实照片嵌复古相纸白框，**必须 -4°~+4° 微倾斜**。
6. **芥末黄便签条**：斜贴相纸边角，承载打字机图注。

### 1.4 六大微场景构图范式（严禁连续两幕同型）

| 范式 | 构图 | 适用 |
|---|---|---|
| A 数据流向 (`stat_hero`) | 左主体 → 红箭头 → 巨型数据徽章 → 红箭头 → 右主体 | 资金流向、指标对比 |
| B 地图时空 (`map_pin`) | 半调老地图全屏 + 红定位标 + 引线打字机便签 | 历史地点、赛段、供应链 |
| C 档案相纸散落 (`archival_mat`) | 1-2 张微倾斜相纸 + 黄色便签 + 旧报纸头条底 | 历史回溯、人物引言 |
| D 技术爆炸拆解 (`exploded_blueprint`) | 居中透视图 + 放射红细线 → 3 个局部卡片 | 发动机、芯片、机械内胆 |
| E 双阵营对抗 (`versus_clash`) | 左右两主体 + 中间红色对峙箭头/百分比天平 | 市场份额、新旧技术 |
| F 局部网点特写 (`macro_halftone`) | 高对比黑白半调极致放大 + 一行断言 | 情绪转折、章节过渡 |

### 1.5 排版

| 层级 | 字体（英 / 中） | 特征 |
|---|---|---|
| H1 Headline | Impact / Bebas Neue ｜ 微软雅黑粗体 (msyhbd)、方正黑体 | 全大写/紧凑、厚重、手绘下划线 |
| Stat Hero | Oswald Bold / DIN Condensed ｜ 站酷高端黑、思源黑体 Heavy | 占画面高 15%~25%，强调色 |
| Annotation | Courier Prime / Typewriter ｜ SimSun、打字机等宽 | `Fig. N - 描述` |
| Body | Helvetica / Inter ｜ 思源黑体 Regular | 不抢焦点 |

> **CJK 红线**：中文字体必须用 `msyhbd.ttc` / `simhei.ttf` 等本地 CJK 字体，防豆腐块；HTML 端字体栈用 miSans/Noto Sans SC/PingFang SC/微软雅黑。

### 1.6 动效法则（路线 A）

- **绝不静止**：每幕常驻 `scale 1.0→1.02` 或 `x -1%→+1%` 呼吸漂移。
- **超调回弹**：抠图弹入用 `back.out(1.7)`，模拟纸片拍桌微震。
- **数字翻滚**：Stat Hero 入场 0.5s 内滚动递增。
- **笔刷刷入**：下划线/箭头 0.35s 从左向右遮罩刷入。
- **幕间硬切**：0 帧硬切，禁淡入淡出（路线 A）；路线 B 采用 0.5s 交叉溶解（奇偶 track 交替，fade out 结束于边界前 ≥0.1s）。

---

## 2. 生图系统（2026-10 全 Qwen 口径）

### 2.1 工作流与调用参数

| 用途 | 工作流文件 | output_node | 提示词节点 | 参考图 |
|---|---|---|---|---|
| 文生图（蓝图 / beat 完整图 / 独立元素） | `tools/_comfyui/workflows/Qwen21-txt2img.json` | `10` | `5` 正向 / `6` 负向（`8` seed/steps/cfg；`7` 宽高） | 无 |
| 图生图（单参考重绘/风格化：真实照片、matplotlib 数据图） | `tools/_comfyui/workflows/Qwen21-edit.json` | `461` | `459:474` prompt/negative（`459:458` seed；`459:456` 宽高） | `470`（`<UPLOADED_IMAGE>`） |
| 双参考图编辑（蓝图锚点 + 当前状态；备用，先用先测） | `apps/vox-collage/template/comfyui/wf_edit.json` | `461` | `459:474` prompt | `470` + `475`（`<UPLOADED_IMAGE_1/2>`） |
| H3 视频（路线 A 核心幕） | `apps/vox-collage/template/comfyui/wf_vid.json` | 按输出扫描 | 提示词节点 `138` | `137` 参考图 |

> ⚠️ `comfyui_image` 工具契约：自定义工作流调用**必须带顶层 `"prompt"` 字段**（构建返回值时直接取用；缺省会在生成完成后报 KeyError）。`<UPLOADED_IMAGE>` 占位符由工具自动替换为上传后的文件名；**加载槽位必须显式覆盖**，否则会静默使用工作流模板里的旧参考图。

### 2.2 提示词资产（verbatim 模板）

- **STYLE BLOCK**：`skills/pipelines/vox-paper-collage/templates/style_block.md`（hand-cut documentary paper collage … soft cutout drop shadows）。
- **CLOSER**：`templates/closer.md`（… NOT digital illustration, NOT cartoon, NOT 3D render … Premium documentary collage aesthetic, 16:9, ultra-detailed, 8K）。
- **UNIVERSAL VIDEO PROMPT**：`templates/video_prompt.md`（锁定镜头 + build-on 0→70% + living poster 70→100% + 纯纸 ASMR）。
- **缩略图 DNA**：`templates/thumbnail_dna.md`（CLOSER 调整版：`no text beyond the specified thumbnail words`）。
- **音乐提示词**：`templates/music_prompt.md`。
- 以上模板文件头带 `<!-- verbatim ... -->` 注释，拼接时剔除注释行；**禁止改写/缩写/合并**。

### 2.3 中文文字政策（2026-10 修订，`bilingual-spec.md §10`）

1. **中文数量内容驱动、不设上限**：标题、标签、地名、年份、印章、图注……需要几处写几处；Qwen 直出。
2. **辅助元素不要全部留白**（画面会空、模型也会乱填）：按内容需要填 **中文短标**（已售/证物/机密）、**英文短语**（FILE / ARCHIVE / NO. 03）或**图标**（箭头/索引圆点/条形码/无字图章）。
3. **必须显式写出各元素文案**：未指定处模型会自创伪文字（假英文/鬼画符 CJK）；负向词带乱码护栏（`no fake or corrupted characters / no garbled caption text`）。
4. **质检红线**：所有生成文字（中文+英文）逐张放大目检（或 OCR 比对），错字/乱码/伪词重掷；照片重绘路线（edit）伪文字风险更高，额外抽查。
5. 关键小字（必须 100% 正确）可回退 CSS / PIL 叠加兜底。

### 2.4 尺寸与模型栈

- **16:9 = `1664×928`（Qwen 原生尺寸）**；9:16 = `928×1664`。勿用 1280×720 等非原生尺寸（背景出纹理伪影）。
- 模型栈：`qwen_image_2.1_int8_convrot`（UNET）+ `qwen3vl_8b_int8_convrot`（CLIP，`type: qwen_image`，**4096 维锁定**，勿换 Qwen2.5-VL 系）+ `qwen_image_2.1_vae_bf16`（VAE）。
- 重阶段切换前向 ComfyUI 发送 `POST http://127.0.0.1:8188/free`（`unload_models + free_memory`），防显存击穿（0xC0000409）。

### 2.5 生图实测教训（合并两线）

- 未指定文案的辅助纸片 → 模型填满伪文字；**文案/图标显式写进 prompt**。
- 模板自带 `image_2` 槽位残留旧图 → 污染画面；**单参考生产必须用无 image_2 的 `Qwen21-edit.json`**。
- 风格参考图（master sheet）直接作为图生图输入 → 把母版里的色卡/示例文字抄进画面（`THE DEAL`/`$123` 污染事件）；参考图污染必须用负向约束压制。
- H3 首帧黑场：prompt 声明首帧全亮 + 时间线 `data-media-start` 裁暗头，双保险。
- 小装饰（<5% 画面）不适合图生图提取，走 CSS/素材库 decal。

---

## 3. 路线 A：CLI 全自动线（`bin/vox_collage.py`）

### 3.1 项目结构

```
projects/vox-collage/<id>/
├── episode.json          # 分幕契约（scenes/chapters/refs_manifest）
├── tokens.json           # 主题色板
├── master_sheet.png      # 主题母版
├── SCRIPT.md             # 人审稿（script 闸门）
├── index.html            # HyperFrames 合成页
├── .media/
│   ├── refs/             # Wikimedia 真实素材 + 许可清单
│   ├── dataliao/         # 程序化资料图（PIL 排版）
│   ├── assets/           # gen-scene-*.png 风格化静帧
│   ├── video/            # gen-scene-*.mp4（H3）+ asmr-*.m4a
│   ├── audio/voice/      # voice_*.wav
│   └── voice-manifest.json  # 读 WAV 头的真实秒数
└── renders/              # 母版 + 字幕成片
```

跟踪库：`projects/vox-collage/tracking.db`（sqlite）。

### 3.2 命令全表

| 命令 | 作用 | 产物/状态 |
|---|---|---|
| `new "<选题>" [--ratio] [--theme] [--duration] [--scenes N]` | 建项目：幕数（90s=10/3m=20/5m=35/10m=65）、6 范式轮转、章节划分、hero_motion 分配（第 1 幕 + 每 3 幕） | `episode.json` pending |
| `refs <id>` | 抓 Wikimedia 真实素材（`ref_query_map` 检索词；topic 6 张/其余 4 张） | refs_done |
| `script <id>` | 由 `episode.json` 渲染 `SCRIPT.md`，暂停等审 | awaiting_script_review |
| `approve-script <id>` | 红线检查（`——`/`--` 即拒）后放行 | script_approved |
| `synth <id> [--json]` | IndexTTS 2.5 合成（参考音色 `D:/index-tts/my_voice.wav`，calm；失败回退 Edge-TTS `zh-CN-YunxiNeural`）；读 WAV 头真实秒数 | voice-manifest.json / tts_done |
| `dataliao <id> [--only]` | 程序化资料图（PIL：标题/图注/裁切，字体 msyhbd/simhei） | dataliao_done |
| `stills <id> [--only] [--json]` | 风格化静帧：真实素材→`wf_edit`（Qwen-Image-Edit）；AI 幕→`Qwen21-txt2img`；1664×928→1920×1080 | stills_done |
| `motion <id> [--only] [--json]` | 核心幕 H3 图层组装（4 步 Turbo；gen_sec = min(15, max(5.2, span+media_start+0.4))；1024×576 / 576×1024）；抽 ASMR 音轨 | motion_done |
| `compose <id> [--only]` | 生成 `index.html`：slot = lead(0.3)+vo+tail(0.25)，2% slow drift，asmr 铺底，`--only` 章节预览 | composed |
| `render <id> [--json]` | HyperFrames lint 闸门 → 渲染低内存母版（`npx hyperframes@latest`） | rendered |
| `subtitle <id>` | ASS 3D 挤出字幕 + FFmpeg 烧录（取最新母版） | subtitled |
| `run "<选题>" ...` | 轻量宏：new + refs + script（直达闸门） | — |
| `run-heavy <id> [--json]` | 重算宏：synth+dataliao+stills+motion+compose+render+subtitle | — |
| `status` | 项目跟踪表（sqlite） | — |

状态机：`pending → awaiting_script_review → script_approved → refs_done → tts_done → dataliao_done → stills_done → motion_done → composed → rendered → subtitled → packaged`（`packaged` 为保留态）。

### 3.3 关键机制

- **静帧路线分流**：`visual.asset_source == "real"` 走图生图（真实照片→VOX 重绘）；否则纯 AI 象征图直出。
- **时间槽契约**：`slot = 0.3s + wav_exact + 0.25s`；H3 视频用 `data-media-start` 裁掉黑场余量，落到「已搭建完」画面。
- **动静混编**：hero_motion 约 30-40%，drift_only 60-70%；渲染速度与观感兼得。
- **章节切分**：>3 分钟先按章节渲染子合成，再 FFmpeg concat 无损合并（规避 Chromium 长渲染 OOM）。
- **字幕参数**（`subtitle_burner.py`）：16:9 = 字号 46 / 每行 ≤26 字 / y=960 / 挤出 (12,8,4)；9:16 = 字号 56 / 每行 ≤15 字 / y=1600 / 挤出 (18,12,6)；SimHei 白字 + 深色 3D 底；CJK 标点智能断行，禁孤字。
- **执行规范**：重命令（synth/stills/motion/render）派 Compute Worker，`--json` 单行回报；TTS 遵守 GPU 文件锁（`lib/gpu_lock.py`）。

---

## 4. 路线 B：原生 8 阶段线（agent 编排）

> ⚠️ **本节描述的路线已冻结（2026-10-04），且从未执行过一次。勿据此开工，也勿再更新本节。**
> 现役主产线是 §3 路线 A（`bin/vox_collage.py`）。本节 8 阶段定义仅作历史与设计参考保留。
> 详见 `docs/optimization-charters/vox-pipeline-simplification.md`。

### 4.0 执行模型

EP（executive-producer）串行驱动：`idea → proposal → script → scene_plan → assets → edit → compose → publish`。
每阶段 → 产出 artifact → reviewer 自审 → checkpoint。人审默认：**idea / proposal / script / scene_plan / assets / publish** 需要人工批准；edit / compose 自动放行。
预算：`budget_total_usd: 3.00` 起步；方案含图像数 × $0.05 与免费路径（本地 Qwen/TTS/音乐）。

### 4.1 idea（产物 `brief`）

- 30+ 领域选项；候选选题数量**动态**：高热领域 20-30 / 中等 15-20 / 小众 10-15。
- 每选题带具体钩子（日期/人名/数字/地点）；无 clickbait、无感叹号。
- 标题句式按 `target_platform`：爆款平台→好奇心驱动；linkedin/generic→克制纪录片。
- 已发布黑名单 `data/used_ideas.json` 检查（语义重复也算）。
- brief 含 `design_system`（旧报纸基调）与 `beat_plan` 前期构图意图。

### 4.2 proposal（产物 `proposal_packet` + `decision_log`）

- **语言**：默认 `zh`（详见附录待裁定项）；**时长**按平台推荐（B 站默认 3 分钟、YouTube 5 分钟、短视频 30-60 秒）。
- **字数**：`bilingual-spec §1`（zh 4.7 字/秒；en 2.5 wps），±5%。
- **3 个概念选项**（c1 为选定深化，c2/c3 备选）；**动态段落压缩**：3/4/5/6 段式。
- **视觉方向**：按 niche 推荐（crime→旧报纸、tech→蓝图、money→账本、古文明→羊皮纸、sports→现代杂志）；可选国风等。
- **数据真实性规划**：每元素分 `real_data / real_content / creative / css`；real_data 带真实来源；real_content 必须照片参考。
- 锁定 `render_runtime = hyperframes`（双 runtime 可用时按 AGENT_GUIDE 硬规则记录 `options_considered`）。

### 4.3 script（产物 `script`）

- **Fern DNA 形式 × 6 段式内容检查清单**（Viral Hook → Quick Intro → Main Story → Turning Point → Big Picture → Powerful Ending；压缩后段落带 `paragraph_label`）。
- 冷开场：前 3-4 句（en 30-40 词 / zh 40-60 字）落在精确日期 + 具名地点 + 具体小动作。
- 悬念结尾：五模式之一；**en ≤12 词 / zh ≤15 字**。
- 标点：en 禁 em dash；zh 禁破折号/省略号（TTS 会把 `——` 读成"减减"）。
- TTS 校准回退：TTS 实测 vs 估算偏差 ≤5% → 更新 scene_plan timing；>5% → 回退 script 精简/扩充（禁变速、禁硬塞时间码）。

### 4.4 scene_plan（产物 `scene_plan`）

- **语义 scene/beat**：scene = 段落（paragraph_label），beat = 段落内语义单元（= 一个生成片段 / 一次画面切换）；**节奏口径（常规 7-10s、快闪 3-5s 例外、≤10s 硬上限、≈6 个/分钟）以 `bilingual-spec.md §2` 为单一事实源**（含术语表、档位与数量快照）。
- **每 beat 五件套**：Sentence / Core Idea / Editorial Title / Visual Metaphor / **Image Prompt**（Playbook 级完整画面描述：背景材质+氛围词 / 主体位置大小材质 / 叙事关联细节 / 排版叠压 / 负空间 / 完整负向词）。
- **每 scene 4 层**：L1 背景纹理 / L2 hero 透明抠图 / L3 语音同步元素 / L4 CSS 装饰。
- **元素规格**：`layer / kind / data_class / box / rot / z / family / micro / sfx / sync_sentence / semantic_family`。
- 段落级视觉功能：hook 强冲击、turning 对比、ending 极简留白。
- 反模式：固定 10s/beat、元素开场一股脑全出、estimated timing 直接进 edit。

### 4.5 assets（产物 `asset_manifest`）

流程顺序（硬性）：**TTS 先行 + whisper 时间戳 → 校准 → 素材库检索 → 多宫格参考（用户确认）→ beat 完整拼贴图 → 独立元素 PNG → 真实照片级联 → 音乐 + ASMR**。

- **一张生成图 = 一个独立元素**；多元素构图由 HyperFrames 组装。
- Real Photo Cascade：用户上传 → 素材库 → Wikimedia → image_selector 搜图 → Bing/Google（仅参考）→ 用户批准的风格化生成；找不到的照片进 `missing_photos[]` 交用户决策，**禁止纯生成**。
- 图片 prompt = SCENE + Editorial Title + STYLE BLOCK verbatim + CLOSER verbatim + 负向词（模板红线）。
- 生成工具绑定：`comfyui_image` + Qwen21-txt2img / Qwen21-edit（见 §2）。
- 旁白：indexTTS2，calm 必须显式 `emo_vector=[0,0,0,0,0,0,0,1.0]`，20-25s 批次。

### 4.6 edit（产物 `edit_decisions`）

- 每 clip 时长 = 对应语音段时长（非固定 10s）；build-on ≈ 前 70%、living-poster ≈ 后 30%。
- 镜头完全锁定；最终帧 = 源图（FINAL RULE）。
- clip 间 0.5s 交叉溶解（奇偶 track 交替）；clip 内无音乐/旁白，仅纸 ASMR。

### 4.7 compose（产物 `render_report` + `final_review`）

- **spec-driven**：scene_plan 是唯一契约，生成器逐元素渲染 HTML + GSAP，不临场发挥。
- 三层入场节奏：hero（+0.3s）/ l3（+1.2s）/ decor（+2.0s）固定骨架；voice 内容标签跟语音（句子时间 +0.2s，可见 ≥2.5s；短场景 ≤7s 全部快速入场）。
- GSAP 只用 `fromTo`（`from` + CSS opacity:0 = 空屏）；入场 `t+时长 ≤ scene_end` clamp。
- 标签尺寸红线（竖屏）：headline ≥100px（核心数字 150-200px）、stamp ≥64px、tstrip ≥38-44px。
- 混音：旁白主线；音乐 -14dB 级别 ducking；ASMR 点缀；旁白合并单 WAV。
- 渲染闸门：`hyperframes lint` 0 错误 + validate 无 console error → 渲染 → ffprobe + 抽帧自检。

### 4.8 publish（产物 `publish_log`）

- 3 张缩略图遵循 Thumbnail DNA（更大字/更热红/更高对比/200px 可读）；真人加黑色遮眼条；单一强调装置（红圈/下划线/图章框/黄高亮，四选一）。
- 缩略图文字：en ≤2 元素×≤3 词；zh ≤2 元素×4-6 字；中文字符不进生图 prompt（CSS/后期叠加），Qwen 直出时须逐张字形质检。
- 发布包：成片 + 3 缩略图 + 元数据（标题/描述/标签）；`used_ideas.json` 更新黑名单。

---

## 5. 配音与音频

| 项 | 规范 |
|---|---|
| 引擎 | IndexTTS 2.5（路线 A：`apps/indextts-bridge` 常驻服务；路线 B：`tts_selector` → indextts_tts） |
| 参考音色 | 必须提供 `spk_audio_prompt`（无默认音色）；路线 A 用 `D:/index-tts/my_voice.wav` |
| 情感 | calm 锁定：显式 `emo_vector=[0,0,0,0,0,0,0,1.0]`（不传=自动判情感，会破坏纪录片语感） |
| 语速 | **4.7 字/秒（中文实测）**；speed=1.0 零变速；禁 speed<0.8（杂音+变调） |
| 批次 | 20-25s 一段批量合成，每批 2-5 次选最佳；冷开场批次最高优先级 |
| 质检 | Whisper medium（small 对中文数字/年份假报警）；ffprobe 每段时长硬校验 |
| 合并 | 多段旁白→合并单 WAV（ffmpeg adelay+amix），避免段间断音 |
| 音乐 | 路线 B：pixabay_music / 素材库（`music_mood` 见 styles，Egyptian trailer 系）；ducking 阈值 -14dB；音乐仅成片混音 |
| ASMR | freesound / 素材库：paper slide / tape press / stamp thud / string zip / pin click / paper tap；clip 内只留 ASMR |

---

## 6. 时间轴与字幕

- **槽位公式**：`slot = lead(0.3s) + 语音真实秒数 + tail(0.25s)`；真实秒数一律读 WAV 头（`wave` 模块），禁止字数估算当事实。
- **H3 视频**：prompt 声明首帧全亮 + `data-media-start` 裁暗头（双保险）。
- **母版无字幕原则**：HyperFrames 渲染纯净母版；字幕独立生成、可重烧。
- **ASS 3D 字幕参数表**（`subtitle_burner.py`）：

| 画幅 | 字号 | 行宽上限 | 垂直位置 | 3D 挤出 | 字体 |
|---|---|---|---|---|---|
| 16:9 (1920×1080) | 46 | 26 字 | y=960 | (12, 8, 4) | SimHei |
| 9:16 (1080×1920) | 56 | 15 字 | y=1600 | (18, 12, 6) | SimHei |

- 断行：CJK 标点智能断行；ASCII 单词不劈开；句末标点不单独成行；白字 + 深色底层挤出 + 5px 描边。
- 烧录：FFmpeg `subtitles=` 滤镜，libx264 crf18 fast，音频 copy。

---

## 7. 环境与依赖

- **ComfyUI**（本地，`COMFYUI_SERVER_URL` 默认 8188）：模型栈见 §2.4；工作流目录 `tools/_comfyui/workflows/`（Qwen21-txt2img / Qwen21-edit 已入 git；Qwen-Layered 系仅用于需要可编辑图层时；Klein 系为历史工作流）。显存治理：`POST /free`；GPU 文件锁 `lib/gpu_lock.py`（TTS 用）。
- **HyperFrames**：`npx hyperframes@latest`；lint 闸门必须过；低内存模式 `--low-memory-mode`；渲染输出避免落在 `hyperframes/renders/`（EPERM 坑），用项目 `renders/`。
- **FFmpeg**：字幕烧录、ASMR 抽取、concat、混音。
- **Node ≥22 / npx**。
- **字体**：`C:\Windows\Fonts\msyhbd.ttc` / `simhei.ttf`（PIL 与 HTML 中文）；HTML 字体栈 miSans/Noto Sans SC/PingFang SC/微软雅黑。
- **路线 A 规范四件套**（本地目录，不在 git）：`apps/vox-collage/specs/{design-system.md, script-spec.md, LESSONS.md, collage_episode.schema.json}`。

---

## 8. 质检清单（合并两线）

**生图**：□ 文字逐张质检（中文错字/英文伪词）□ 指定文案与画面一致 □ 辅助元素无未指定伪文 □ 真实素材未走样 □ final 元素无漂移。

**时间轴**：□ 槽位=WAV 实测 □ 时长 ±5% □ 画面与旁白对齐（无说完了画面空挂）。

**视频**：□ 相机锁定（无 zoom/pan）□ 最终帧=源图 □ 画面覆盖 ≥85% □ 元素有叠压 □ 入场 clamp 不截断。

**音频**：□ 旁白合并单轨 □ 音乐 ducking □ ASMR 音量克制 □ 响度旁白优先。

**交付**：□ ffprobe（分辨率/时长/音轨）□ 关键帧抽检 □ 缩略图 200px 可读 □ 3D 字幕断行无孤字。

---

## 9. 踩坑索引（top 12 → 详版见 LESSONS 与各 skill）

1. PowerShell `--only 02,03` 吞前导零 → 必须加双引号。
2. 破折号 `——` → IndexTTS 读"减减"；标点只留逗号/句号。
3. 中文渲染豆腐块 → 必用 msyhbd/simhei。
4. H3 首帧黑场 → prompt 锁首帧 + media_start 裁头。
5. 显存 0xC0000409 → 重阶段前 `/free`。
6. 估算 vs 实测时长 ±25% → 一律读 WAV 头。
7. Whisper small 误报数字 → 用 medium。
8. 长渲染 Chromium OOM → 按章节渲染 + concat。
9. 模板风格污染（THE DEAL/$123）→ 负向约束 + 单图模式。
10. GSAP `from` + CSS opacity:0 → 空屏；只用 `fromTo`。
11. `hyperframes/renders/` EPERM → 输出到项目 renders/。
12. 自定义工作流缺顶层 `prompt` → 生成完成后崩（先补字段）。

---

## 10. 最近变更（2026-10）

- **生图全线切 Qwen-Image 2.1**：新增 `Qwen21-edit.json`（单参考净化版，实测 1664×928/36s 全链路通过）；`Qwen21-txt2img.json` 入 git；Klein/「中文绝不进图」旧口径全部废除。
- **中文文字新规**：内容驱动不限数量；辅助元素显式填充（中文短标/英文/图标）；全文字逐张质检（`bilingual-spec §10`）。
- **分镜机制口径统一 + 10s 上限（2026-10）**：yaml scene_plan 审查块改回语义分镜（ADR-002 D7），清除 VOICE-LED 遗文与 2.5wps 常数残留；新增「每 beat ≤10s」硬红线（一个 beat = 一个生成片段，超长语义单元按句子边界拆分）。
- **节奏参数收敛为单一事实源（2026-10）**：`bilingual-spec §2` 重写为节奏唯一事实源（术语表 scene/beat/clip/拍/幕 + 常规 7-10s/快闪 3-5s 例外/≤10s + ≈6 个每分钟 + 数量快照）；yaml / directors / styles / EP 全部改为引用；`playbook.schema.json` 新增 `max_beat_seconds` 字段（修复校验）。
- **同步文件**：`skills/pipelines/vox-paper-collage/*`（5 件）、`pipeline_defs/vox-paper-collage.yaml`、`styles/vox-paper-collage.yaml`、`styles/vox-paper-collage-guofeng.yaml`、`.agents/skills/comfyui/SKILL.md`、`docs/VOX_PAPER_COLLAGE_SESSION_GUIDE.md`。
- **提交**：`0a72aca` feat(vox-paper-collage,comfyui)（分支 `research/douyin-retention-rules`）。

---

## 11. 文件地图

| 想找什么 | 去哪里 |
|---|---|
| 视觉宪法（色板/零件/范式/动效） | `apps/vox-collage/specs/design-system.md` |
| 剧本与去 AI 腔（路线 A） | `apps/vox-collage/specs/script-spec.md` |
| 实战避坑（路线 A） | `apps/vox-collage/specs/LESSONS.md` |
| 分幕契约 schema | `apps/vox-collage/specs/collage_episode.schema.json` |
| CLI 用法速查 | `.agents/skills/vox-collage/SKILL.md` |
| 自然语言使用指南（路线 B） | `docs/VOX_PAPER_COLLAGE_HELP.md` |
| 复现手册（路线 B） | `docs/VOX_PAPER_COLLAGE_SESSION_GUIDE.md` |
| 8 阶段定义 | `pipeline_defs/vox-paper-collage.yaml` |
| 各阶段执行细则 | `skills/pipelines/vox-paper-collage/*-director.md` |
| 中英差异层（唯一事实源） | `skills/pipelines/vox-paper-collage/bilingual-spec.md` |
| 提示词模板（verbatim） | `skills/pipelines/vox-paper-collage/templates/*.md` |
| 风格播放本 | `styles/vox-paper-collage.yaml`、`styles/vox-paper-collage-guofeng.yaml` |
| 治理决策记录 | `docs/adr/ADR-002-*.md`、`docs/optimization-charters/vox-paper-collage-playbook-alignment.md` |
| Qwen 工作流 | `tools/_comfyui/workflows/Qwen21-txt2img.json`、`Qwen21-edit.json` |

---

## 附：待裁定的口径分歧（2026-10 盘点）

以下为文档间现存不一致，**尚未有单一结论**，建议逐一确认后回写：

1. **分镜机制 —— 已裁定并修正（2026-10）**：以语义分镜为准（ADR-002 D7）；`pipeline_defs` scene_plan 审查块已同步为「语义边界 + 两遍校准 + **每 beat ≤10s 硬上限**（视频生成限制，超长语义单元按句子边界拆连续 beats）」。注：ADR-002 原文"关键 reveal 可达 15s"已被 10s 上限取代（ADR 保留为历史记录）。
2. **默认旁白语言**：`ADR-002`（Accepted）与 `proposal-director.md` 说默认 **zh**；`pipeline_defs` 第 77 行与 `docs/VOX_PAPER_COLLAGE_HELP.md` 说默认 **en**。
3. **候选选题数量**：`idea-director.md` 为**动态**（10-30 按领域）；`executive-producer.md` 门控仍写"十选题"。
4. **词数学残留**：`executive-producer.md` 仍写 `word_target = 时长 × 2.5 wps`（英文常数），未按双语规范分支。
5. **assets 人审**：yaml 标 `human_approval_default: true`；EP 协议总结中列为"自动放行"。以 yaml 为准执行，但口径需统一。

**工程观察（非文档冲突）**：

6. **路线 A 静帧疑似硬编码横屏**：`cmd_stills` 两条路径均固定 `1664×928` 并 resize `1920×1080`，未见 `ratio` 分支（dataliao / motion / subtitle 均已按 ratio 分支）——9:16 项目的静帧路径需确认或补齐。
