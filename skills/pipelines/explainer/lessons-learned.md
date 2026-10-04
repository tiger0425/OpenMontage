# Animated-Explainer Pipeline — 实战避坑与最佳实践（DSH 试播集经验沉淀）

> **适用范围**：使用 `animated-explainer` 管线做全生成讲解视频时，所有 Agent 应参考本文档。
> 来源：地图 #52「DSH 插件系统视频教程试播集」→ 项目 `dsh-pilot-short`（§1 组合模型 × 短平快 101.5s，全 HyperFrames 生成，IndexTTS 配音，$0 成本）。本片 5 轮渲染迭代，以下每条都是真实踩坑后沉淀。

---

## 🚨 铁律（任何后续视频违反必翻车）

### 铁律 A：HyperFrames 场景必须手写组合，不要用 scaffold 默认模板

`video_compose` 的 `composition_mode="templated"` + `render_runtime="hyperframes"` 路径，scaffold 生成的模板**只把 `cut.text` 渲染成默认文字卡**，不实现 scene_plan 的定制视觉（插件块、光环、分层动画等），且**配色错误**（text-card 的 `h1` 是浅底 `rgba(250,246,246,0.90)` + 浅色字 `--color-fg:#F5F5F5` = 白底白字）。**第一版成片因此被用户否决（"大部分页面空屏，白底白字看不清"）。**

**正确做法**：渲染前直接重写 `projects/<name>/hyperframes/` 工作区：
- `index.html`：定义正确的 CSS 变量（深底 #0F172A + 紫/粉 accent）、挂载 sub-composition、放 audio 元素。
- `compositions/cut-N.html`：手写每个场景的 HTML/CSS/GSAP（见铁律 B 视觉配方）。
- 改完必须 `npx hyperframes check` 全过再渲染（lint + runtime + layout + motion + contrast）。

**关键契约**（hyperframes-core）：
- sub-composition 的 `<style>`/`<script>` 必须在 `<template>` **内**（外头会被丢弃）。
- host 的 `data-composition-id` == 内部 template 的 `data-composition-id` == `window.__timelines` key，三者必须一致。
- 根元素用 `#root` 样式选择器，**不要**给根元素加 class 再按 class 选（CSS scoping 会丢弃）。
- 背景填在 full-bleed child（`position:absolute; inset:0`），不要填在 composition 根上（帧合成会掉成黑）。
- 每条 composition 只注册**一条** `gsap.timeline({ paused: true })`。
- 动画只用 GSAP transform 别名（x/y/scale/rotation）+ opacity/color/backgroundColor/borderRadius；**禁止** tween `width/height/top/left/letterSpacing`（letterSpacing 会 snap 整数像素，seek 引擎卡顿，lint 报 `gsap_non_transform_motion`）。
- 无 `repeat:-1`、无 `Math.random`、无 `Date.now`——呼吸动画用 bounded onUpdate 读 `tl.time()`（见 `ambient-glow-bloom` 规则）。
- 每个元素 `id` 全局唯一；sub-composition 内 id 加前缀（`<id>-hero`）。

### 铁律 B：视觉配方（吸睛度 = 层次 + 发光 + 动效节奏）

用户否决"太简陋"后升级的配方（视觉模型评价"吸睛度高，符合 B 站高端审美标准"），每个动效场景至少包含：

| 层 | 做法 | 参数 |
|---|---|---|
| **背景渐变** | `radial-gradient` 深紫蓝（#1E1B4B → #0F172A → #020617） | 中心偏上/偏侧，别正中央 |
| **呼吸光晕** | `.bg-glow` radial-gradient + bounded sine breathe（onUpdate 读 phase） | peak opacity ≤ 0.45，OPACITY_AMP 0.04-0.05，SCALE_AMP 0.02 |
| **网格纹理** | 双层 linear-gradient 细线（1px，低透明度） | rgba(99,102,241,0.05~0.07)，80px 格 |
| **漂浮装饰** | 2-3 个模糊圆点（blur 2-3px）fade+y 入场 | 半透明紫/粉/青 |
| **大字发光** | `text-shadow: 0 0 60px rgba(124,58,237,0.55)` + 渐变文字（background-clip:text） | 渐变用 `-webkit-background-clip: text` |
| **卡片质感** | `linear-gradient(145deg, light, dark)` + 内高光 `inset 0 1px 0 rgba(255,255,255,0.25)` + 投影 | border 1px rgba(255,255,255,0.12) |
| **slam 入场** | `ease: "back.out(2.2)"` scale 0.6→1 + y 偏移 | 大字/卡片/块 |
| **扫光** | 单次 traveling sweep（x 从一侧穿到另一侧，clip 到表面） | 见 `ambient-glow-bloom` 的 Form B |

### 铁律 C′：旁白分段粒度 = 场景窗口（一句一对画），全系列执行

> 来源：DSH 系列 Day2（`dsh-plugins-day2` §2 双平面）grilling——用户明确要求：**一段旁白 = 一个 scene_plan 场景窗口**，段落粒度不允许大于场景，因为「若都在一个大段，画面和内容会漂移/脱节」。这是铁律 C 的**最严形式**，并定为全系列规格。
>
> **执行**：script 的 `sections[]` 数 = scene_plan 的 `scenes[]` 数（Day2 详解：12 场景 = 12 段旁白）。每段旁白只在其对应场景窗口内播放（占该窗口 85-90%，段尾留 3-5s 呼吸，铁律 H）。配音段 = 场景段 = 编辑 cut 段 = 同一切分。
>
> **不要**：把旁白按「叙事大段落」（d1-d7 语义段）切——那会让一段旁白跨多个视觉场景，叙事长句跟画面 cut 脱节（Day1 详解『长段跟画面脱节』的复发根因）。语义段落是内容组织（six-act），旁白分段是编辑粒度（场景），两者不同轴。
>
> 生产顺序：先定 scene_plan 场景窗口 → 再按窗口写逐段旁白脚本 → 每段短、独立、好对齐；配音子代理更适合小而独立的任务块（Day2 遇 GPU 锁：分段够小也便于定位失败点/避锁重试）。

### 铁律 C：旁白按场景粒度切，一句不跨画面

用户否决"一句太长和画面对不上"：**旁白必须按 scene/beat 粒度切分**，每段朗读时长 ≤ 对应场景窗口。实测标定：IndexTTS 中文约 4.7 字/秒（另一口径 measured_wps 2.98 词/秒）。

本片 11 段旁白（82s）对 8 场景，每段 4-9s，全 ≤ 窗口。**script.sections 的 start/end 必须与 scene_plan 场景窗口一致**（第一版 script 5 段 vs scene_plan 8 场景错位，是最初音画脱节的根因）。

### 铁律 D：节奏 = 旁白占比 75-85%，别留大空档

用户否决"节奏慢，中间停顿太多"：第一版 180s 视频旁白仅 82s（45%），场景间大量空档（最长 19s）。压缩到 101.5s（旁白占 81%），每段后只留 1.5-2s 呼吸。**总时长应约 = 旁白总时长 × 1.25，不是随手定 180s。**

### 铁律 E：`composition_mode="atelier"` 是 Remotion 专属，hyperframes 不可用

`video_compose` 的 `_render_via_atelier` **只走 Remotion**（要求 `bespoke.entry` 是 .tsx）。`render_runtime="hyperframes"` + `composition_mode="atelier"` 会被 atelier 分支抢先捕获并尝试 Remotion（node_modules 未装则失败）。**HyperFrames 的自定义视觉 = 手写工作区组合（铁律 A），不是 composition_mode。** 已在 decision_log 记录修正。

---

## 音频链路（IndexTTS）

- **调用**：走 `apps/indextts-bridge/client.py` 的 `IndexTTSSession`（统一处理 UTF-8 编码、情感纯净、GPU 锁、超时）。**不要**用 PowerShell 管道传中文（GBK 变乱码）；用 Python subprocess + `encoding="utf-8"`。
- **参数**：2.5 版**只传 `use_emo_text: false`、不传 `emo_vector`**（传 calm emo_vector 会触发情感-音色混合 → 男声变女声）。repo-to-video 的 asset-director/config.yaml 是旧文档，**以 `apps/indextts-bridge/CALLING.md` 为准**。
- **样音门**：先合成最敏感段（如核心句）给用户听样，批准后再批量。本片样音 11.2s，用户听样通过。
- **GPU 锁**：工具层已内置 `GpuLockHandle`（`%LOCALAPPDATA%/openmontage/.gpu.lock`），经工具/客户端调用无需手动加锁；常驻服务整个生命周期持锁。
- **前导静音**：IndexTTS 输出带 1.2-7.2s 前导静音，合成后需 `silencedetect` 裁剪再测时长/转写。
- **验证**：`faster_whisper` 转录确认清晰中文（无 "Maze Maze" 类伪音 = 权重错位）。**控制台输出中文乱码是 GBK 显示问题，不是音频问题**——用 `PYTHONIOENCODING=utf-8` 重新输出即可。
- **成本**：本地 GPU 免费（`estimate_cost()=0`），2-5 分钟旁白纯推理约 25-62s（RTF 0.206），冷加载数分钟。

---

## 资产生成（0 美元路线）

| 工具 | 行为 | 坑 |
|---|---|---|
| `code_snippet` | 纯本地 Pygments+Pillow，**静态**语法高亮 PNG | 产静态图非动画；逐行高亮/打字动画需在 HyperFrames HTML 层手写（本片 scene-5 就用 HTML 代码窗口替代了 PNG） |
| `diagram_gen` | Mermaid 渲染 | **中文字体未嵌入 → 方块乱码**：节点标签用英文（或补字体）；且返回 `method:text_card` 时可能是代码文本卡而非渲染图，务必 vision 验证 |
| `image_selector` | 本机无本地图像生成，仅 google_imagen(付费)/pexels | **避开**：代码/图示/排版主题用 code_snippet+diagram_gen+HyperFrames 原生承载即可 0 美元 |
| `tts_selector` | IndexTTS(VOX)/VoxCPM/Piper/Google 池 | 用 `preferred_provider="indextts"` 直选 |

---

## 校验与门禁

- **渲染前**：`npx hyperframes check` 必须全过（lint/runtime/layout/motion/contrast）。`validate` 是 deprecated 别名，用 `check`。
- **常见 check 拦截**：
  - `content_overlap`（布局重叠）→ 挪位置，或**有意的叠层**加 `data-layout-allow-overlap`。
  - contrast < 阈值 → 换亮色（本片 Profile 蓝 #4F46E5→#818CF8、hint 灰 #818CF8→#C7D2FE）。warning 不阻断渲染，但视觉模型确认可读性才算数。
  - `font_family_without_font_face` → 每个 font-family 加 `@font-face { src: local('...') }` 声明（中文用 Microsoft YaHei local）。
- **渲染后自审**（compose-director 强制 6a-6e）：
  1. ffprobe：视频流+音频流都存在（本片曾遇无音轨隐患，必须在）。
  2. 抽帧 + **视觉模型审**（`minimax-m3-vision`）：无空屏/白屏/黑屏、文字清晰、无乱码/重叠/白底白字、场景与 scene_plan 对应。
  3. whisper 转写成片音频：字数 ≈ 脚本字数（本片 425/425），头尾完整。
  4. 每段旁白时长 ≤ 场景窗口（音画同步）。

---

## 视觉自审清单（每次渲染后逐条过）

- [ ] 背景是深色渐变（非纯平底色、非白）
- [ ] 无空屏/白屏/黑屏帧
- [ ] 文字清晰、无乱码/方块/重叠/白底白字
- [ ] 每个场景内容与 scene_plan 对应（尤其检查**容器 opacity 陷阱**：父容器 `opacity:0` + 子元素动画到 1 → 内容被父容器遮住不可见，本片三词卡就栽在这——容器要 `opacity:1`，显隐交给子元素/退场动画）
- [ ] 代码窗口内容完整（无底部裁切——本片 13 行代码超窗口，减字号/行距/加高窗口解决）
- [ ] 音画同步（旁白段落在对应场景内）

---

## 项目结构速查（后续视频直接抄）

```
projects/<name>/
├── artifacts/            # 各 stage 的 JSON（research_brief/proposal_packet/script/...）
├── assets/
│   ├── audio/            # sc-N.wav（每段旁白）+ sample 样音
│   ├── images/           # code_snippet PNG（如用）
│   └── music/background_music.mp3   # 从 music_library 复制
├── hyperframes/          # ★ 手写组合（index.html + compositions/cut-N.html + assets/）
├── renders/final.mp4     # 成片
└── exports/              # B 站发布包（export_bundle）
```

**asset_manifest 的 path 是仓库根相对**（`projects/<name>/assets/...`），不是项目相对——提交时 Harness 按 PROJECT_ROOT 解析，写错了会报 physical file does not exist。

---

## 本轮数据（供后续对照）

| 指标 | 值 |
|---|---|
| 时长 | 101.5s（旁白 82s，占 81%） |
| 分辨率/编码 | 1920x1080 h264+aac，30fps |
| 渲染迭代 | 5 轮（模板否决→配色→门禁→节奏→视觉/三词卡） |
| 成本 | $0.00 |
| 音色 | IndexTTS2 纯净克隆（D:/index-tts/my_voice.wav） |
| BGM | music_library/ep01_bgm.mp3（93.5s loop） |

---

## 🚨 铁律 F：封面与标题必须专门生成，不能从成片抽帧

发布包的封面和标题是**门面**，用户明确要求「在流程里做好」——不要用 ffmpeg 抽帧当封面（抽帧=视频某一秒的画面，没有专门的信息层级，不吸睛）。

### 封面：专门设计的 HyperFrames 封面组合

在 `projects/<name>/hyperframes-cover/index.html` 写一个**独立封面组合**（1920x1080，data-duration ~2s），视觉语言与视频一致，但信息层级为封面优化：

| 元素 | 做法 | 本片实例 |
|---|---|---|
| 系列标识 | 顶部 eyebrow（小字 + 大字距） | 「DeepSeek Harness 插件系统」 |
| 主标题 | 超大字号（150px+）+ 渐变 accent + 强发光 | 「改能力 = **改组合**」 |
| 副标题 | 时长承诺 + 内容点 | 「**3 分钟** 讲透 DSH 插件组合模型」 |
| 装饰 | 复用视频的插件块/光环/渐变/网格 | Profile/Bundle/Patch 三色块 + 「能力」光环 |
| 系列条 | 底部系列归属 | 「DSH 插件系统 · 组合模型 · 第 1 节」 |

生成：`cd projects/<name>/hyperframes-cover && npx hyperframes snapshot --at 1.8` → `snapshots/frame-00-at-1.8s.png`（1.8s 时所有元素已入场）。**必须用视觉模型审封面**（文字清晰/无裁切/层次/吸睛度）。

### 标题：B 站 hook 公式（地图 #56）

【分区】好奇钩子 + 细节 + 情感锚。给 2-3 个候选让用户选，推荐一个：

| 模式 | 模板 | 本片实例 |
|---|---|---|
| 反直觉钩子（推荐） | 「[反直觉断言]？[核心结论]，[时长]讲透[主题]」 | 「【编程】DSH 没有配置文件？改能力 = 改组合，3 分钟讲透插件组合模型」 |
| 悬念钩子 | 「打开[文件]，里面是[意外]——不是[常见误解]」 | 「打开 DSH 的 cordis.yml，里面是空的——不是你没配好」 |
| 求知钩子 | 「[主题]：为什么[反直觉结论]」 | 「DeepSeek Harness 插件系统：为什么「改能力」等于「改组合」」 |

### 流程落位

publish 阶段**必须**产出：① 设计封面 PNG（hyperframes-cover snapshot）；② 标题候选 + 定稿；③ 两者进 `export_bundle`（`thumbnail_path` = 设计封面，`title` = 定稿标题）。成片抽帧只作内部参考，不进发布包。

### 🔧 自动化（后续视频直接调，不用手写）

```bash
# 标题：hook 公式三候选（反直觉/悬念/求知）
python bin/make_title.py --topic "<主题>" --claim "<结论>" --duration "<时长>" --partition "编程" [...]

# 封面：模板渲染 → hyperframes snapshot → PNG
# 详解版用 --light（浅底单红 + 3 彩色概念 pill + 能力环，与 Day1/Day2 详解版一脉相承）
python bin/make_cover.py --project <name> --light --series "<系列>" --topic "<主题>" \
    --episode "第 N 节" --title-main "<主标题>" --title-accent "<accent>" \
    --duration "<时长>" --subtitle "<副标题>" [--plugs "A,B,C"] [--ring "能力"]

# 短平快/预告用默认深底紫（flat-motion-graphics 系，不加 --light）
python bin/make_cover.py --project <name> --series "<系列>" --topic "<主题>" \
    --episode "第 N 节" --title-main "<主标题>" --title-accent "<accent>" \
    --duration "<时长>" --subtitle "<副标题>" [--plugs "A,B,C"] [--ring "能力"]

# 封面视觉审（必做）：minimax-m3-vision
python .agents/skills/minimax-m3-vision/scripts/analyze_media.py projects/<name>/renders/cover_design.png -p "..."
```

- 工具：`bin/make_title.py`、`bin/make_cover.py`（读 `templates/hyperframes-cover/index.template.html`（深底紫）或 `index.light.template.html`（浅底单红详解版）渲染，`--light` 选详解版）
- **详解版封面必须 `--light`**：DSH 系列 Day2 实测——默认模板是深底紫系列风，第一次跑出 Day2 封面与成片的浅底单红视觉不符、也跟 Day1 详解版封面不统一。详解版（8-15 分钟那种）封面应和正片同视觉（浅底单红 + 3 彩色 pill + 能力环），用 `--light`。
- 模板变量：`{{SERIES_NAME}} {{TITLE_MAIN}} {{TITLE_ACCENT}} {{DURATION_LABEL}} {{SUBTITLE}} {{PLUG_1..3}} {{RING_LABEL}} {{SERIES_TOPIC}} {{EPISODE_LABEL}}`（两个模板共用同一套变量）
- 本片实测：make_cover 全链路跑通（渲染→snapshot→PNG），视觉模型确认「无乱码/无裁切/吸睛」
- **🚨 封面全比例矩阵铁律（绝对禁止 PIL crop 居中硬切）**：
  - 严禁用 16:9 横版封面直接居中裁切输出 1:1、3:4 或 9:16，否则标题文字、能力胶囊与环形图表必被切断！
  - 必须针对 16:9 (1920x1080)、4:3 (1440x1080)、1:1 (1080x1080)、3:4 (1080x1440)、9:16 (1080x1920) 分别定义自适应 HTML 布局，并用 `hyperframes snapshot` 独立渲染原生 1:1 像素高清快照。例如 1:1 使用双行标题+居中并列，9:16 采用竖屏满血布局+清单补充卡，确保全平台内容 100% 完整。

---

## 🚨 铁律 G：交付包 = 一个独立文件夹，4 件套全在顶层

用户要求「视频、封面、文案最终成品全部放在一个独立文件夹下，不要到处找」。**每个项目必须产出 `projects/<name>/deliverables/`，且只有 4 个文件、全部在顶层（不分子文件夹）：**

```
projects/<name>/deliverables/
├── final.mp4          ← 成片
├── cover.png          ← 设计封面
├── 发布文案.txt        ← 标题 + 简介 + 章节 + 标签，一份搞定
└── README.md          ← 交付清单 + 后续指引
```

### 硬规则

1. **不分子文件夹**——成片也直接放顶层（用户明确要求，video/ 子目录被否决）。
2. **文案合成一个「发布文案.txt」**——标题/简介/章节/标签四段用 `━━━` 分隔，**不要**拆成 title.txt/description.txt/chapters.txt/tags.txt 多个文件（用户明确否决拆分）。
3. **UTF-8 中文**——文件内容必须 UTF-8；PowerShell 控制台显示乱码是 GBK 假象，用 `PYTHONIOENCODING=utf-8` 或 Python 读取验证。
4. **README.md 自解释**——内容清单 + 定稿文案速览 + 生成方式 + 后续指引，让用户打开文件夹就懂。

### 🔧 自动生成（publish 阶段收尾必调）

```bash
python bin/make_deliverables.py --project <name> \
    --title "<B 站标题>" \
    --description "<简介全文>" \
    --chapters "0:00 标题,0:10 标题,..." \
    --tags "标签1,标签2,..." \
    [--series "系列名"] [--episode "第 N 节"] \
    [--cost "0.00"] [--duration "101.5s"]
```

- 工具：`bin/make_deliverables.py`（自动 copy 成片/封面 + 生成发布文案.txt + README.md）
- 默认取 `renders/final.mp4` 和 `renders/cover_design.png`（make_cover 产物）
- 本片实测：全链路跑通，`发布文案.txt` 四段内容验证正确（标题/简介/章节/标签）

---

## 🚨 铁律 H：长片（8-15 分钟）时长 = Σ(旁白 + 呼吸)，不是按章节骨架随手定时间

> 来源：项目 `dsh-pilot-deep`（§1 组合模型 × 深度详解，12m40s，全 HyperFrames 手写 + IndexTTS 1.45× + $0）。**第一版按 B1-B9 章节骨架的"预期时长"设了 900s/15 分钟，但旁白只有 693s，留下大量静音空档——用户否决"节奏慢，中间有很多静音段"。** 这是短平快铁律 D 在长片上的重演，第一次没防住。

**根因**：proposal/script 阶段沿用章节骨架的 `end_seconds`（B1-B9 各 60/90/120s）当场景窗口，但实际配音时长远短于这些窗口（s13 旁白 83s 却给了 120s 窗口 → 段内 37s 静音）。

**正确公式（长片同样适用）**：
1. 先定旁白字数 → IndexTTS 实测语速算出每段旁白时长。
2. 每段场景窗口 = 该段旁白时长 + 呼吸（短平快 1.5-2s；**深度讲解 3-5s**，给画面/字幕/BGM 消化）。
3. 总时长 = Σ(旁白 + 呼吸)。成片后旁白占比：短平快 81%，**深度讲解 85-95%**（信息密度高、观众要跟，比短平快略满可接受；不是 75%）。
4. **proposal 阶段的 target_duration_seconds 只是粗估**，scene_plan 与 edit_decisions 必须按"实际旁白时长 + 呼吸"重排，绝不沿用章节骨架的宽窗口。

本片数字：14 段旁白 693s；每段呼吸 5s（末段 2s）→ 窗口总长 760s（12m40s），旁白占比 91%。**收紧后渲染转写头尾完整（'想给…加一个能力'→'……下期见'），无截断。**

### 长片配套坑（本次实测）

1. **IndexTTS `duration_factor` 的方向陷阱**：它是"输出时长倍率"，**越大越慢/越长**（`target_lengths = S × 1.72 × duration_factor`）。口语自然 ~6.3 字/s；要沉静讲解（~4.5 字/s）用 **`duration_factor ≈ 1.4-1.5`**。不要下意识把"放慢"传成 0.7——那会变快（第一版 0.72 → 更快，反而压缩时长）。校正方法：先合一段，ffprobe 实测语速，反推 factor = 目标语速 / 实测语速。

2. **`index.html` 的 root `data-duration` 决定渲染总长**（Render 帧数 = root duration × fps）。收紧时若只改了 host/audio 的 start/duration、漏改 root `data-duration`，**渲染会静默按旧时长出片**（本片 root 漏改 900 → 渲染假报 15m0.0s）。**每次重排时间线后必须 `grep data-duration index.html` 核对 root 与末段 host 对齐**，再渲染。

3. **`npx hyperframes check` 偶发 `request_failed: net::ERR_NO_BUFFER_SPACE`（GSAP CDN 瞬时加载失败）+ `gsap is not defined`**：是环境/网络瞬时问题，不是代码 bug——**直接重跑 check 即可**（同代码第二次通过）。若反复失败，把 GSAP 下载到 `assets/` 本地引用（更可复现）。

4. **`content_overlap`（check error）对"覆盖/叠压"类场景是"故意的"**：如 B5"patch 整块盖住 config 行"、B2"空根升格叠压"，本就该叠上去。收敛写法 = 给覆盖元素加 **`data-layout-allow-overlap`**，不要因此改成分开布局（会破坏"替换整行"的视觉语义）。

5. **收紧时间线是纯 HTML 重排，不必重配音**：`edit_decisions` 的 cut/narration 时间 + `index.html` 的 host/audio `data-start` 一起改即可；**各 cut 的 GSAP 动画时间轴是"场景内相对秒"，场景窗口收紧后只要动画末点 ≤ 新窗口长就无需改 sub-composition 动画**（本片全部动画都在场景前 40s 内播完，窗口 40-88s，零修改）。

6. **长片封面/章节/文案时长必须与收紧后成片同步**：封面"15 分钟"→"12 分钟"、发布文案章节时间戳（0:00-11:48）、README 时长全部要跟着变，否则交付包与新成片脱节。

### 长片"双形态"视觉区分（对照短平快）

| 形态 | 视觉 | 动效 | 每段呼吸 |
|---|---|---|---|
| 短平快 §1 | 深底 #0F172A + 紫/粉 + 光晕/扫光 | bouncy（back.out） | 1.5-2s |
| 深度详解 §1 | **浅底 #FAFAFA + 单红 #E94560 + 网格**（minimalist-diagram） | draw-in / fade（无 bounce） | 3-5s |

同主题短平快与深度版刻意用相反底色的视觉语言区分（用户要求的双形态）。

---

## 本轮数据（供后续对照 · 深度详解）

| 指标 | 值 |
|---|---|
| 时长 | 12m40s（760s；旁白 693s 占 91%） |
| 分辨率/编码 | 1920x1080 h264+aac，30fps |
| 渲染迭代 | 2 轮（首版 900s 静音多 → 收紧 760s） |
| 成本 | $0.00 |
| 音色 | IndexTTS2 纯净克隆 · `duration_factor 1.45`（沉静讲解 ~4.5 字/s） |
| BGM | music_library/ep01_bgm.mp3（93.5s loop, ducking volume 0.10） |
| 视觉审 | minimax-m3-vision：钩子/覆盖语义/终端/落地 4 帧 5/5 |
| 章节数 | 14 段（B1-B9 骨架展开） |

---

## 🚨 铁律 L：系列双形态时长必须「预告 ~60s / 详解 ~10min」，避开 3-5 分钟不伦不类区

> 来源：DSH 系列 Day2（§2 双平面）实测——计划 6-8min 详解，实际成片 **3m56s**（duration_factor 1.15 提速 + 文案密度压缩），用户判定「说长不长说短不短」：既没有预告的轻快，也没有详解的重量。**Day3 起硬性规格：预告片 ~60s、详解正片 ~10 分钟内容。**
>
> **执行**：
> 1. **详解要「做满内容」，不是靠放慢语速凑时长**：按 4.5-5 字/s × 600s ≈ **2700-3000 字**规划旁白；内容不够就把该节 SKILL 稿全量展开（Day3 §3 就是 apply 四铁律 + cordis 工具链 + 真跑演示全展开），绝不靠 duration_factor 放慢灌水（放慢反而回到 Day1『语速慢』的坑）。
> 2. **proposal 阶段就写死「详解 ~10 分钟」并向用户说清**：提速会使成片短于标称，内容量必须按 10min 目标反推字数，不是按语速反推时长。
> 3. **预告 ~60s**：问题式悬念，深底紫 flat 系（默认模板），不发章节地图，结尾 3 词快闪 CTA。
> 4. 时长决策在 proposal 就要锁定，scene_plan/edit 按铁律 H 用真实配音时长重排，但**内容字数要保证落回目标时长**。

---

## 本轮数据（供后续对照 · §2 双平面 深度详解 DSH 系列 Day2）

| 指标 | 值 |
|---|---|
| 项目 | `dsh-plugins-day2`（DSH 系列 §2 双平面 · 深度详解正片） |
| 时长 | 236.1s（3m56s；12 段旁白 232s 占 ~98%，铁律 H 重排后） |
| 分辨率/编码 | 1920x1080 h264+aac，30fps |
| 渲染迭代 | 2 轮（首版 231.5s → 补 2.3 规则后重排 236.1s） |
| 成本 | $0.00 |
| 音色 | IndexTTS2 克隆 · `voice_ref_futian3.wav`（用户指定）· duration_factor≈1.15 |
| 有效做法 | 旁白 12 段 = 12 场景（铁律 C′）；例子逐条溯源真实 `cordis.patch.yml`（铁律 I） |
| check 门禁 | `npx hyperframes check` 全过（26/26 WCAG AA 对比度） |
| 成片验证 | ffprobe（v+a 流）+ whisper 转写内容完整 + 帧采样 |
| 交付 | deliverables 4 件套（final/cover/发布文案/README） |

---

## 🚨 铁律 I：例子必须真实文件溯源（DSH 系列 Day2 新增）

> 来源：DAY1 详解反馈「例子要更准确」。DSH 系列 Day2 起强制。
> **每条上屏断言必须能溯源到 `~/.dsh/...` 或 bundle 包内真实文件/命令**，脚本的 `source_ref` 标注来源路径 + 行号。`asset_manifest`/scene 的 `data_class: "real_content"` + `data_source` 指向真实文件。上屏代码卡用 `code_snippet` 读真实文件逐字渲染（行号对齐 `line_number_start`），绝不凭记忆转述。
> 反例：§2 若把 subagents 的判据背出来而不核对 `dsh-web-app/cordis.patch.yml L367-372`，就是「凭印象讲」——违规。

---

## 🚨 铁律 J：GPU 生产子代理连挂 → 根因是 `sys.path` 缺 `lib.gpu_lock`，不是工具坏了

> 来源：`dsh-plugins-day2` 配音阶段。4 个生产子代理（IndexTTS 12 段）**全部无 closing message 失败**，一度怀疑是 GPU 锁/工具坏。最终**我自己直接驱动一个后台 job 一次跑通**，才暴露根因：
> `client.py:105` 的 `from lib.gpu_lock import GpuLockHandle` 在子代理环境**找不到 `lib`**——因 `python projects/x/script.py` 把「脚本所在目录」加入 `sys.path[0]`，而非 OpenMontage 根，`lib`（在根）解析不到。**修法：脚本顶部 `sys.path.insert(0, OPENMONTAGE_ROOT)`**（或 `PYTHONPATH` 设根）。
>
> **经验**：
> 1. **子代理环境对「长驻 GPU 进程 + piped stdio」不稳定**（配音/渲染/check 这类 spawn 长进程易被杀、无 message）。**优先用「后台 job + 独立 .py 脚本」直接驱动**，比子代理可靠。
> 2. 任何调用 OpenMontage `lib/` 的脚本，首行先 `sys.path.insert(0, repo_root)`。
> 3. 别急着怪工具——先自己最小重放定位（probe 脚本直接跑），错误信息往往就在那里。

---

## 🚨 铁律 K：IndexTTS 不认 SSML `<break>` 标签，会读出来（用纯文本 + 标点）

> 来源：`dsh-plugins-day2` 首轮配音。把 `delivery_cues.provider_text`（含 `<break time="0.4s"/>`）直接喂 IndexTTS，whisper 转写出现 **"break time等于0.4秒"**——**模型把 SSML 标签当字面英文读了**。
>
> **修法**：IndexTTS 属 offline 类，**只喂纯文本 `.text`，用标点（，。；——）制造停顿，不要用 `<break>`**。CALLING.md 的「offline/basic voices: rely on punctuation」是铁律。
> 重生成后 whisper 转写干净（无 break 字样）。
>
> **通用教训**：SSML `<break>` 只在支持它的 provider（Google/ElevenLabs）里用；对本地 offline TTS，永远用纯文本 + 标点。

---

## 铁律 C′：旁白分段粒度 = 场景窗口（全系列执行，DSH 系列 Day2 确立）

> 用户明确要求：**一段旁白 = 一个 scene_plan 场景窗口**，禁止「一段旁白跨多个视觉场景」，因为大段旁白会让画面和内容漂移/脱节。
> **执行**：`script.sections[]` 数 = `scene_plan.scenes[]` 数（Day2：12 场景 = 12 段旁白）。每段旁白只在它对应场景窗口内播（占窗口 85-90%，段尾留 3-5s 呼吸，铁律 H）。配音段 = 场景段 = 编辑 cut 段 = 同一切分。
> 生产顺序：先定 scene_plan 场景窗口 → 再按窗口写逐段旁白 → 每段短、独立、好对齐；配音子代理也更适合小而独立的任务块（便于避 GPU 锁重试 / 定位失败点）。

---

## DSH 系列 Day2 · 其余实战沉淀

1. **内容驱动的真实时长远短于计划时长**：计划 6-8min 详解，因「修语速慢（duration_factor 1.15）+ 文案密度」，实际成片 **3m56s**。这是铁律 H「宁短勿注水」的正确执行（无空档、信息密度高）。但 **proposal 就该向用户说清**「提速后成片可能显著短于标称时长」，让用户决定要不要扩内容。
2. **手写 HyperFrames 工作区 = 直接抄 Day1 打通过的样板**：别从 0 猜契约。`projects/dsh-pilot-deep/hyperframes/` 的 `index.html`（root `data-composition-id="main"` + `class="clip"` 场景 host + `<audio data-start/data-duration/data-track-index>` + `window.__timelines["main"]`）和 `compositions/cut-N.html`（`<template>` 内 style/script + `#root` selector + 单条 paused gsap timeline 注册 `window.__timelines["cut-N"]`）就是权威样板，改内容即可。
3. **改旁白内容 → 必须铁律 H 整条时间线重排 + 重渲染**：给 tool-subagent-report 段补一句规则，d5 旁白 17.5s→22.1s，后续 7 个场景全部后移 4.55s，成片 231.5s→236.1s。`root data-duration`、各 cut host、各 audio data-start 三处必须同步改，再重渲染 + **重新跑 make_deliverables（时长变了，封面/文案/README 同步）**。
4. **HyperFrames check 报错处置**：`pointer-events:none` 只是 info 不阻断；真正的 **error 是 `content_overlap` + contrast**。装饰性箭头/标签别压在文本上（会触发 overlap + contrast 双错）——删掉或移到空白区。`minimax-m3-vision` 适合做最终视觉审（本模型无 image input 时用它）。
5. **whisper 转写技术中文不准是常态**：`registry`→`register`、`只贡献`→`直供线`、`跨会话`→`跨绘画`。判断「旁白内容是否到位」不要用精确子串匹配，而是看**段级转写语义完整**（如确认 s05 段含「记住这一条...只贡献...工具...registry/后端留 host」即可）。
6. **B 站标题 hook 公式已自动化**：`bin/make_title.py --topic ... --claim ... --duration ... --partition 编程` 出反直觉/悬念/求知三候选，推荐反直觉钩子；`bin/make_cover.py` + `bin/make_deliverables.py` 全链路跑通，交付 4 件套全在 `deliverables/` 顶层（铁律 G）。

---

## DSH 系列 Day3 · 其余实战沉淀（§3 写作契约，预告 55s + 详解 11m45s）

### 🚨 铁律 M：封面主标题超长必溢出——`make_cover` 模板 `.main-title` 是 150px 大字

> 来源：Day3 两封面均被用户否决（"标题字超出页面了"）。模板（深底紫 + 浅底单红两个）的 `.main-title { font-size: 150px }`，**一行只放得下 ~8 个全角字**；标题 ≥10 字必然：①右边界裁切（末尾字消失）②换行掉进副标题区重叠。

**执行**：
1. **proposal/publish 阶段先算字数**：主标题（含 accent）全角字符数 × 150px ≤ 1920px 才安全；超了就缩短措辞，不要硬塞。
2. **`--title-accent` 不要带 `=`**：模板已自带 `{{TITLE_MAIN}} = <span class="accent">{{TITLE_ACCENT}}</span>`，accent 传 `= xxx` 会渲染成**双等号**（Day3 详解封面实测 `一个插件 = = apply(ctx)`）。
3. **已生成工作区的补救（不用重跑 make_cover）**：直接改 `projects/<name>/hyperframes-cover/index.html` 的 CSS（`.main-title` 字号 150px→100-112px + `padding: 0 60px` + `line-height: 1.25`，并把 `.subtitle` 的 top 下移 60px 避免重叠），然后重跑 `npx hyperframes snapshot --at 1.8` 覆盖 PNG。
4. **封面视觉审要问边界**：`minimax-m3-vision` 可能漏报溢出，必须明确问「最后一个字是否被右边界裁切 / 是否与副标题重叠」。
5. **封面修完必须同步 deliverables**：`Copy-Item renders/cover_design.png deliverables/cover.png`（铁律 G 的封面同步）。

### 🚨 铁律 N：code_snippet PNG 中文注释必乱码（方框）——含中文的代码卡必须用 HTML 内嵌

> 来源：Day3 详解 3 个代码卡场景（apply 骨架 / hello_echo / Slot UI）首轮渲染后视觉审帧发现**中文注释全是方框 □**。`code_snippet` 工具（Pygments+Pillow）渲染的 PNG **未嵌入中文字体**，任何中文（注释/标题栏）都变豆腐块。

**执行**：
1. **判断**：上屏代码含中文注释 → **不用 code_snippet PNG**，改 HTML 内嵌代码窗口（`<pre>` + CSS 高亮，字体栈 `'IBM Plex Mono','Noto Sans SC',monospace`，中文 fallback 到已 `@font-face` 声明的 Noto Sans SC）。铁律 I 的真实文件溯源照样满足（内容从真实文件读出）。
2. **纯英文代码**（无中文）→ code_snippet PNG 可用（Day2 的 cordis.patch.yml 注释是英文所以没踩）。
3. **HTML 代码窗口的 check 坑**：`font_family_without_font_face` 会拦 `Microsoft YaHei` 的小写形式——**不要**在 font-family 里写 `'Microsoft YaHei'`（check 按小写匹配找不到声明）；用已声明的 `'Noto Sans SC'`（`@font-face { src: local('Microsoft YaHei') }`）即可。
4. **渲染后必须视觉审代码帧**，问题帧抽取法：`ffmpeg -ss <t> -i final.mp4 -frames:v 1 out.png` + `minimax-m3-vision` 问「中文注释是否清晰无方框」。

### 其余实测

1. **铁律 J/K 组合拳被再次验证**：后台 job 直驱 + 脚本首行 `sys.path.insert(0, OPENMONTAGE_ROOT)` + 只喂纯文本 `.text` → **18 段配音（详解 14 + 预告 4）全部一次通过**，零失败零重试（Day2 4 连挂根因彻底修掉）。
2. **duration_factor 实测校准**：详解 `duration_factor 1.4` → 实测 ~4.7 字/s（d1: 108 字/24.7s），与 4.7 字/s 估算吻合，时间线一次排准（705s = 旁白 649s + 呼吸 56s，占 92%）。**先合 1-2 段 ffprobe 实测语速，再排全量时间线**是铁律 H 的正确姿势。
3. **`hyperframes render` 输出 flag 是 `-o`**：`--out` 是未知 flag 直接失败（`Unknown flag: --out`）。用 `npx hyperframes render -o ../renders/final.mp4`。
4. **checkpoint/artifact schema 严格性（Day3 反复被拒后总结）**：
   - `decision_log`：decisions 需 `decision_id/stage/category/subject/options_considered/selected/reason`；`options_considered` 是**对象数组**（option_id/label/score/reason）；category 有 enum（`music_selection`→`music_source`）；顶层只允许 version/project_id/decisions。
   - `proposal_packet`：`paragraph_structure.compressed_to` 只允许 3-6；`renderer_family` / `delivery_promise.promise_type` 都是 enum（预告用 `cinematic-trailer` + `motion_led`）。
   - `scene_plan`：scene `type` enum 无 `code_snippet`（代码卡场景用 `screen_recording` 或 `diagram`）；`narrative_role` enum。
   - `final_review`：`status` 是 `pass/revise/fail`（不是 `passed`）；`checks` 固定 5 键（technical_probe/visual_spotcheck/audio_spotcheck/promise_preservation/subtitle_check）；`recommended_action` 必填。
   - `publish_log`：`metadata_used.chapters` 是数组。
   - **写 checkpoint 前先 `python -c "import json; print(json.load(open('schemas/artifacts/X.schema.json'))['required'])"` 对 schema**，别凭 Day2 旧格式硬套（Day2 的 decision_log 也未必过现在的 schema）。
   - **`write_checkpoint` 的 `_merge_decision_log` 在 validate 之前执行**：写坏的 decision_log 会先落盘项目级文件，重跑前必须 `Remove-Item projects/<name>/decision_log.json`。
5. **长片 11m45s 渲染耗时 ~13min**（21150 帧 4 workers）；重渲染（修乱码后）与首次同耗时。渲染期间并行做 publish 文案/章节/封面，不空等。
6. **whisper 中文误听**（Day3 实测）：`apply`→`戴尔派`/`ApplyPly`、`真跑`→`正跑`、`ctx`→`ct`、`standingKey`→`standing key`。判断完整性看段级语义 + 头尾（「上期我们讲完…下期见」），不逐字比。

### 本轮数据（供后续对照 · §3 写作契约 DSH 系列 Day3）

| 指标 | 值 |
|---|---|
| 项目 | `dsh-plugins-day3`（详解 11m45s）+ `dsh-plugins-day3-trailer`（预告 55s） |
| 详解 | 705s，14 段旁白 649s 占 92%，2700-3000 字达标（2820 字），铁律 C′ 14 场景=14 段 |
| 预告 | 55s，4 段旁白 38.6s，问题式悬念（总钩→问题连发→三坑→真跑回显→3 词快闪 CTA） |
| 分辨率/编码 | 两片均 1920x1080 h264+aac，30fps |
| 渲染迭代 | 详解 2 轮（code_snippet 中文字体缺失→HTML 代码窗口修复后重渲染）；预告 1 轮 |
| 成本 | $0.00 |
| 音色 | IndexTTS2 克隆 · `voice_ref_futian3.wav` · 详解 duration_factor 1.4（~4.7 字/s）/ 预告 1.1 |
| BGM | music_library/ep01_bgm.mp3（93.5s loop，详解 volume 0.08 / 预告 0.12） |
| 视觉审 | minimax-m3-vision：详解 7 帧 + 预告 4 帧 + 两封面全过 |
| 封面 | 详解 `--light` 浅底单红（修双等号 + 112px）；预告深底紫（修 150px→104px 溢出） |
| 交付 | 两项目 deliverables 4 件套（final/cover/发布文案/README） |
| 铁律 | A-L 全量执行 + 新增 M（封面标题长度）/ N（code_snippet 中文字体） |

---

## 🚨 铁律 O：教学法——拒绝「AI 干稿」，当有经验的老师（DSH 系列 Day4+ 硬性）

> 来源：Day3 交付后用户反馈——「之前几节课内容太干，一看就是 AI 生成的；要让不懂的人有兴趣学习，要有更多技巧，语言和课件都要更丰富」。这是**创作质量门**，不是内容准确性门：机制讲对了但像文档朗读 = 不合格。

**执行（全量规格 + 自查表见 `.research/dsh/teaching-craft-spec.md`；新旧风格对照 demo 见 `.research/dsh/teaching-style-demo.md`）**：

1. **语言 10 技**（script 逐条自查）：
   - 类比先行：每个抽象概念首次出现给生活类比并全片复用（preset=工作台清单/饭店排桌、isolate=包厢、registry=总台账、standingKeyFor=上岗试岗）
   - 删书面连接词（首先/其次/此外/即/指）；换「说白了」「注意」「坑就在这」「你可能会问」
   - 先错后对（错误示范 → 顿悟）；替观众提问；每节 ≤15 字金句收尾
   - 每 45-90s 一个情绪点；开头真人困境场景结尾回收；无人称客观陈述 < 20%
2. **课件 10 技**（scene_plan 逐条自查）：隐喻画面/场景剧/对比分屏 > 文字卡；一屏正文 ≤30 字；代码卡当证据缩一角（真实文件溯源仍是铁律 I，但视觉主角是画面不是代码）；手写批注（红圈/箭头/划线）去 AI 感；渐进构建；每节至少 1 个非文字视觉；进度指示。
3. **节奏三幕**：每节 = 是什么（类比引入 20-25%）→ 为什么（场景冲突 40-50%）→ 怎么用（真实文件+口诀 25-30%）。术语首次慢讲+类比、二次快带。
4. **旁白占比放宽**：详解从 85-95% 调到 75-85%——空档给「画面讲故事」（类比动画/场景剧/对比），不是静默空白（铁律 H 反的仍是无意义空白，教学停顿是有意留白）。
5. **proposal 阶段就要声明教学法**：concept 的 visual_approach/tone 里写明类比体系（如「全片用饭店隐喻讲 preset」），script 提交时附「自查表已过」。

### 本轮数据（供后续对照 · 教学法首秀待 Day4 验证）
| 指标 | 值 |
|---|---|
| 规格文件 | `.research/dsh/teaching-craft-spec.md`（语言 10 技 + 课件 10 技 + 三幕节奏 + script/scene_plan 自查表） |
| 对照 demo | `.research/dsh/teaching-style-demo.md`（isolate 段旧/新风格逐句对照 + 开场承接示例） |
| 生效集次 | Day4 起每集（预告 + 详解） |

---

## DSH 系列 Day4 · 其余实战沉淀（§4 静态组合 · 双产物已交付）

### 🚨 铁律 P：IndexTTS2.5 客户端的 `target_duration` 是「目标秒数」，不是「语速倍率」

> 来源：Day4 详解配音。沿用 Day3 的 `synthesize_narration.py` 传 `target_duration=duration_factor`（1.4），实测语速 ~6.2 字/s（natural），比 Day3 的 ~4.9 字/s 快——排查 `apps/indextts-bridge/client.py`：2.5 走双次合成，`factor = target_duration / natural_duration`；**传 1.4 会被当作「目标 1.4 秒」，factor 出 [0.5,2.0] 范围 → 静默回退 natural 副本**（等于没放慢）。

**正确姿势**：先合一段 natural（`target_duration=None`）ffprobe 实测 → 需要沉静讲解时传 `target_duration = natural × 1.25`（实测得 ~4.9 字/s、与 Day3 音色节奏一致）；预告 energetic 直接 `target_duration=None`。**永远先 probe 一段再排全量**（铁律 H），并核对 whisper 字/s。

### 其余实测

1. **0.1.5-alpha.1 事实漂移再校正（2026-09 开拍复核）**：preset 真实行数 ≠ 旧 drift 报告（standard 252 / ptc 272 / minimal 88 / cordis 263；editing-cordis SKILL 165 行但 isolate 原话 L78、standingKeyFor L107-112 锚点未漂移）——已写入 `.research/dsh/dsh-version-drift-0.1.5.md` ⑥ 表，拍前先核真实文件。
2. **教学法首秀验收**：详解 14 场景全游戏类比（preset=配装表/isolate=副本/standingKeyFor=试炼/spawn=招队友/fork=分身）；minimax 14 帧 14/14 PASS；成片 705.4s = 旁白 649.2s + 呼吸 56s（占 92%）。
3. **代码窗表格行宽坑**：cut-12 表格 `subagent_claude_code` 曾被 `.c12-kv{white-space:nowrap;overflow:hidden}` + 窄列裁掉尾部（视觉审 d12 抓到「subagent_claude_co」缺 de）——修法：加宽表 (1320→1560px)、缩 kv 字号 (21→19px)、name 列 500→440px，重渲染后复核完整。
4. **子代理分工**：14 个 HyperFrames cut 拆 4 个写手并跑（各 ~3-4 个），再统一 `audit_cuts` 脚本校验（1 timeline / __timelines key==composition-id / 无 repeat:-1 / 无 width-height tween），全部一次过。
5. **预告独立项目链**（`dsh-plugins-day4-trailer`）：与正片同 research 数据点但独立 script/scene_plan/hyperframes（单文件深底紫 58s），5 cuts（含 CTA 定格）、4 旁白段；ffprobe + whisper 197 字 + 5 帧 5/5 验证后出 4 件套。

### 本轮数据（供后续对照 · §4 静态组合 DSH 系列 Day4）

| 指标 | 值 |
|---|---|
| 项目 | `dsh-plugins-day4`（详解 524.3s / 8m44s）+ `dsh-plugins-day4-trailer`（**已按用户决定停用归档**，`ARCHIVED.md`） |
| 详解 | 524.3s，14 段旁白 475.3s，口语稿 2732 字；成片即 Day4 唯一交付物 |
| 分辨率/编码 | 1920x1080 h264+aac，30fps |
| 渲染迭代 | 详解多轮（calm×1.25 否决 → cut-12 截断修复 → 口语稿+拆句 0.8× 定稿）；预告项目停用 |
| 成本 | $0.00 |
| 音色 | IndexTTS2 克隆 futian3 · 详解 句末级拆句 + 0.8×natural + 200ms 句间呼吸 |
| 视觉审 | minimax：详解画面 14/14 PASS + 封面（浅底 `--light`）全过（音轨重配不影响画面） |
| 交付 | 详解 deliverables 4 件套（final/cover/发布文案/README） |
| 铁律 | A-N 全量 + O（教学法）+ P（target_duration 秒数语义）+ Q（整段≠拆句级）+ R（多音字规避） |

---

## 🚨 铁律 Q：IndexTTS 长段「一口气」≠ 拆越细越好——句末级拆分才是语速稳的甜点

> 来源：Day4 详解配音三轮听感迭代。**用户耳朵判定的三层体验**：
> ① 整段 200-300 字一次喂 → 语速均匀但「一口气读完、不按标点停」（IndexTTS 长段内部吞句号停顿）；
> ② 逗号级拆碎逐句合成（每句独立推理、无跨句上下文）→ 停顿有了，但**句长参差导致语速忽快忽慢**（短句被急促念完、含英文/术语长句明显放慢）；
> ③ **句末级拆（按 。！？… 断，句内逗号整句保留给模型统筹）+ 0.8×natural + 200ms 句间呼吸** → 停顿真实 + 语速稳（~5.5-5.7 字/s），用户一次通过。

**执行**：
1. 拆句函数只按句末标点切（保留「——」破折号连接与英文原话完整性），单句 >60 字才在中文逗号/分号处补一刀。
2. 每句两次合成（natural 测速 → `target_duration = natural×0.80` 提速，走 2.5 双次合成，铁律 P 语义）。
3. 句间插 200ms 静音拼接（铁律 K：不喂 SSML）。
4. **语速目标按用户耳朵校准**：整段 natural ≈7 字/s（赶）→ 拆句 natural ≈4.5 字/s（拖）→ 0.8× ≈5.6 字/s（甜点）。不同音色/内容甜点不同，先出一段样音给用户听再全量（铁律 H「先 probe」的听感版）。
5. 成片时长随语速漂移：0.8× 下详解 2732 字 → 8m44s（短于「~10min」规格但用户认可听感优先；时长规格要让位给用户验收的语速，宁短勿灌水）。

## 🚨 铁律 R：IndexTTS 不吃注音——多音字用「改写规避」，别靠 pronunciation_guides

> 来源：Day4 逐句合成暴露多音字误读（用户点名「重」「行」）。`script.schema` 的 `pronunciation_guides` 只是元数据注释，**IndexTTS 离线路径不读它**（铁律 K 只吃纯文本），拼音/注音喂进去会被当字面读。

**执行（改写规避表，先自查全文再动笔）**：

| 高风险字 | 典型误读场景 | 规避改写 |
|---|---|---|
| 重 | 重头戏(chóng?) / 重启(chóng?) | 重头戏→**重点**；重启→**重新启动** |
| 行(名词) | 身份行/工具行/两行/灰行/一行一 | 一律改 **条 / 区 / 栏**：两行→两条、一行行→一条条 |
| 数 | 数出三个(shǔ?) | **点出**三个 |
| 调 | 调不到(diào/tiáo) | 用不上 |
| 行(xíng 动词) | 并行/不行/就行 | 低风险可留（上下文明确） |

**验证闭环**：改写后全量 scan 高危字词残留 → 对拿不准的短语（如「N 行代码」量词 háng）单句合成给用户耳验 → 全量前先播 3 段代表句（开场/含原话/含列表）让用户点头。多音字靠耳朵，不靠规则表自证。

## Day4 定稿后修正（2026-09-10）

- 用户最终拍板：**Day4 只出详解正片，预告停用归档**（`dsh-plugins-day4-trailer/ARCHIVED.md`，58s 成品与流水线原样保留）。系列「双产物」规格遇用户单集取舍时，**以用户指令为最终覆盖**，同时把决策与理由写进归档标记，防后续会话误当「漏做预告」。
- 上一版本轮数据（705.4s / 双产物）为中途态，**以本段 524.3s 单详解为准**。铁律 L 的「~10min」规格在语速修正后让位于用户验收（8m44s），series 路线图同更。

---

## 🚨 铁律 S：封面严禁用成片随意抽帧，必须调用专用 HyperFrames 封面引擎（`bin/make_cover.py --light`）

> **教训来源**：Day5 交付时自动打包脚本简单使用 `ffmpeg -ss 12.0` 截取了一张视频画面作为封面，立刻遭到用户严厉批评（“你做的什么封面，就截了一张图，你看以前几集是怎么做的”）。
> 视频截帧即使再清晰，在信息流里也缺乏视觉压迫感、品牌辨识度和结构化标题，在 B 站等平台点击率暴跌。

**全系列统一封面排版规范（Light Minimalist 公式体系）**：
1. **统一模板与工具**：
   - 必须使用 `bin/make_cover.py --light`，调用 `templates/hyperframes-cover/index.light.template.html` 生成并由 HyperFrames 渲染出 1920×1080 矢量级设计封面。
2. **核心大字公式（`<核心动作> = <关键破局点>`）**：
   - Day 2：`改能力 = <span class="accent">找对平面</span>`
   - Day 3：`一个插件 = <span class="accent">apply(ctx)</span>`
   - Day 4：`改能力 = <span class="accent">改 preset</span>`
   - Day 5：`装开插件 = <span class="accent">三路径防砖</span>`
   - **字号与颜色**：150px 超大粗黑体，Accent 词统一采用警示红 `#E94560`。
3. **副标题卖点行**：
   - 结构：`<时长高亮> <痛点/反转> · <核心操作> · <价值承诺>`
   - 示例：`5 分钟 官方无市场 · 三路径安装 · 源码级防砖审计`（时长词标红加粗）。
4. **三彩色胶囊标签（`plug-row`）**：
   - 提炼本集三个最核心关键词，分别赋予红（`#E94560`）、蓝（`#6366F1`）、绿（`#34A853`）色块，具有强烈的硬件装具感。
5. **右侧高光核准光环（`ring`）**：
   - 四色渐变光环，正中 66px 黑色粗体大字印刻本集终极安全目标（如 `能力`、`验证`、`防砖`）。
6. **全平台 5 比例封面矩阵**：
   - 必须由 `cover.png` 自动衍生生成 5 款标准比例图：
     - `cover_16x9.png` (1920×1080)
     - `cover_4x3.png` (1440×1080)
     - `cover_1x1.png` (1080×1080)
     - `cover_3x4.png` (1080×1440)
     - `cover_9x16.png` (1080×1920)
   - 确保核心文字处于 1080×1080 正方形安全区内，全平台裁切永不丢字。
