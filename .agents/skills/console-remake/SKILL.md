---
name: console-remake
description: >
  深色开发者控制台（console / HUD）设计复刻管线（bin/console_remake.py）的操作指南。
  输入一条参考视频（YouTube URL / 本地文件），把它的控制台设计语言拆成九种零件
  （空心描边框/数据格阵/等宽胶囊/发丝线/巨型数字/连接箭头/刻度槽/米白纸面板/通知 toast），
  以「结构借鉴 + 独立重写」产出中文版：IndexTTS2 克隆配音 + HyperFrames 1920×1080 合成 +
  内嵌设计文字 + console 字幕条；零 AI 生图（封面除外），真实人物/实物/界面一律采集
  真实素材（image/footage 零件）并登记出处；动笔前必做 HyperFrames 能力侦察（catalog/docs）。
  触发词：控制台复刻 / console-remake / 深色控制台 / 跑控制台管线 / 把这条视频做成控制台版中文 / 控制台设计复刻。
---

# 深色控制台设计复刻管线操作指南（console-remake）

## 1. 概述

`console-remake` 是针对**讲解型视频**的设计复刻管线（CSS 世界负责"讲解"，真实素材负责"作证"）。
参考片分析已固化为世界宪法 `apps/console-remake/specs/design-system.md`（console-v1 → v2 → v2.1/v2.2）。

**两条世界级纪律（v2.2 新增，违反=返工）**：

1. **能力面纪律**：动笔写分幕之前，先侦察 HyperFrames 能力面（注册表积木/调色/关键帧/转场）。
   "能用的能力没用上"按缺陷处理——教训来源：第一版全片把 HyperFrames 当渲染器用，被用户判定
   「你并没有把 HyperFrames 的能力发挥出来」。见 §8。
2. **素材真实纪律**：真实存在的人物/实物/项目/界面 **必须采集真实素材**（`image` 图片 /
   `footage` 录屏）并登记出处与许可；CSS 只负责抽象概念、结构与数据。禁止 CSS 假扮真实实体，
   禁止 AI 生图编造真人/真实产品（封面除外）。见 §9。

**世界观三律（v1 沿用）**：仪表律（元素必须"测量什么"）· 留白律（敢空，单帧可 40%~90% 纯黑）· 呼应律（同色跨空间、发丝线分区、箭头串联）。

- **九种零件** + 三种辅助原语（panel/text/source/seal）+ **三类连接件**（引线 leader / 括线 bracket / 端刻度 tick）+ **动作动效库**（travel/push/shift/erase/leak/stack/grow + 划线），全部由 `console.css / console.js` 实现。
- **色彩语义**：红=问题·成本 ｜ 琥珀=占用 ｜ 蓝=模型·查询 ｜ 青=结果；v2 主强调色改橙。
- **常驻 HUD 框架**：顶栏品牌 + 章节翻页（CH xx/09）、底部进度轨（红填充+游标+章节刻痕）、全幅画框 + 颗粒层——观众永远知道"讲到哪"。
- **禁用清单**：圆角实心卡片+投影（工具界面零件除外）、全屏标题卡、渐变/玻璃拟态、emoji、花哨转场。

与既有管线的区别：ref-remake 是竖屏+AI 生图+人物锚点；wrc/erchuang 是实拍搬运；
**console-remake 是横屏 + HTML/CSS 零件 + 真实素材采集 + 零生图（封面除外）**。

## 2. CLI 速查（`bin/console_remake.py`）

| 阶段 | 命令 | 说明 | 属性 |
|---|---|---|---|
| 新建+抓取 | `python bin/console_remake.py new <slug> --ref-url <url>`（或 `--ref-file <path>`） | 建项目 + 下载/拷贝 + 转录 + 抽帧 | 轻 |
| 脚本闸门 | `python bin/console_remake.py script console-<slug>` | 校验 episode.json + 红线扫描 → 停闸门 | 轻 |
| 放行 | `python bin/console_remake.py approve-script console-<slug>` | 人审放行 | 轻 |
| 配音 | `python bin/console_remake.py synth console-<slug> [--json]` | IndexTTS 2.5 逐句克隆 + 实测时长 | **重·GPU** |
| 装配 | `python bin/console_remake.py compose console-<slug> [--scenes s01,s02] [--no-audio]` | 时间轴 + 烘焙音频 + index.html | 轻 |
| 渲染 | `python bin/console_remake.py render console-<slug> [--json] [--4k]` | HyperFrames 渲染 1080P | **重·CPU** |
| 成品包 | `python bin/console_remake.py package console-<slug>` | 封面（截帧兜底）+ 文案 txt + README | 轻 |
| 归档 | `python bin/console_remake.py archive console-<slug>` | 归入 `exports/<id>/`（成片/封面/文案/章节/档案） | 轻 |
| 一键轻 | `python bin/console_remake.py run <slug> --ref-url <url>` | new + 闸门 | 轻 |
| 一键重 | `python bin/console_remake.py run-heavy console-<slug> [--json] [--scenes ...]` | synth+compose+render+package | **重** |
| 状态 | `python bin/console_remake.py status` | 所有 console 项目状态 | 轻 |

## 3. 标准会话执行流

```
用户给出：「把这条视频用控制台世界做中文版」
  │
  ├─ 1. 侦察：读参考片转录（fetch 产物）+ 设计分析 → 定差异点
  ├─ 2. 轻量启动：new（下载/转录/抽帧）
  ├─ 3. **能力与素材侦察（强制，动笔前必做）**：
  │      ├─ HyperFrames 能力面：npx hyperframes catalog / docs / media-treatment --capabilities
  │      │   → 写 artifacts/capability_recon.json（积木↔分幕映射 + 调色/转场候选），见 §8
  │      └─ 真实素材面：列全片真实实体清单（人/产品/项目/界面/地点）→ 按 §9 路由表
  │          搜寻 + 登记 provenance；找不到才允许降级（记录原因）
  ├─ 4. 撰写创作契约 artifacts/episode.json（Agent 亲自写，见 script-spec.md）
  │      ├─ 真实实体用 image/footage 零件 + provenance（§9）；抽象概念才用 CSS 零件
  │      ├─ 先出 2-3 幕样片验收「世界」（可复用为全片片段，不浪费）
  │      └─ 全片：逐幕铺开，控制台零件必须"发话即出"
  ├─ 5. script → 【人审闸门】（脚本 + 红线 + 时长估算；输出 capability_recon 与 real_assets 摘要）
  ├─ 6. approve-script 放行
  ├─ 7. 派 Compute Worker：run-heavy（TTS + 渲染 + 成品包）→ --json 单行回报
  └─ 8. 呈现成片 + 封面 + 文案（含【素材来源】credits）；用户验收后手动上传（平台勾选 AI 声明）
```

## 4. 绝对红线（Red Lines）

1. **脚本是结构借鉴 + 独立重写**：禁止逐句翻译；术语保留（Harness/Agent/token/上下文窗口/Prompt）；数字汉字化（"四到十五倍"）。
2. **素材真实纪律（v2，取代旧「零实拍」）**：画面分两层——
   ① **讲道理**（抽象概念/结构/数据/结论）→ 九种零件 CSS；
   ② **看真东西**（真实存在的人物/产品/项目/界面/地点）→ **必须采集真实素材**：
   `image` 零件引用真实图片（放 `assets/images/`）、`footage` 引用真实录屏，并登记
   `provenance`（url + license；自产填 `url:"self"`、`license:"自有素材"`）。
   - 禁止 CSS 假扮真实实体（元素标 `real:true` 却无真实素材 = 校验错误）；
   - 禁止 AI 生图编造真人/真实产品（封面除外，见封面两步法）；
   - 找不到真实素材时允许降级为 CSS 抽象，但必须在幕 `label` 写明原因。
3. **禁用清单即宪法**：任何时候不得出现"圆角实心卡片+投影"（PPT 感）。
4. **元素不许孤立**：每幕至少一处"联系"（同色呼应 / 引线 / 括线 / 箭头 / 发丝线分区）；凡有归属关系必须用连接件系住。
5. **动词必须演出来**：台词出现跑/塞/挪/删/漏/叠等动词时，用 motion 家族把动作演在"说到该动词"的 0.5s 窗口内——只显形不算完成。
6. **音画咬合**：每个零件的入场时间由旁白句起点驱动（`enter_offset` 微调）；发话即出、说完即静。
7. **敢留白**：单帧内容簇 ≤2；开场/收尾允许近全空。禁止为填满而加装饰。
8. **脚本闸门是人的环节**：`approve-script` 前禁跑 `synth`。
9. **重命令派 Worker**：`synth` / `render` / `run-heavy` 由 Compute Worker 执行，`--json` 单行回报，禁止粘贴完整 stdout。
10. **GPU 锁**：IndexTTS 走 `lib/gpu_lock.py`，勿并行两个 TTS 任务。
11. **AI 标识**：成片不烧录角标；B 站发布勾选「AI 生成」声明。
12. **能力侦察是动笔前置**：未产出 `artifacts/capability_recon.json`（HyperFrames 积木↔分幕映射）不得开始撰写 episode.json；渲染前必须通过 `npx hyperframes check`（0 error）——"能力没用上"按缺陷处理（见 §8）。
13. **素材先搜后降级**：真实实体必须先按 §9 路由表搜寻真实素材；降级（CSS 抽象）须记录原因，`package` 输出的【素材来源】随发布文案一并归档。

## 5. 目录与文件

```
apps/console-remake/
├── specs/design-system.md          # 世界宪法（必读）
├── specs/script-spec.md            # 中文脚本与分幕规范
├── specs/LESSONS.md                # 实战经验（改管线前必读）
├── specs/console_episode.schema.json
└── template/
    ├── console.css                 # 九零件 CSS → 拷贝为宿主 assets/console.css
    ├── console.js                  # 运行时（buildScene 每幕 / buildHost 宿主）→ 宿主 assets/console.js
    └── generate_composition.py     # 装配器：episode+tts → timings + 宿主 + 每幕独立 HTML + 音频烘焙

projects/console-<slug>/
├── artifacts/  fetch_report.json, capability_recon.json, episode.json, redline_scan.json,
│               tts_results.json, timings.json, line_words.json, publish_copy.json(可选)
├── assets/source/  ref.mp4, transcript.json, frames/
├── assets/images/  真实图片素材（image 零件；文件名写进 episode.src）
├── assets/footage/ 真实录屏素材（footage；片段时长 ≥ 幕时长，见 LESSONS §11）
├── assets/sfx/     音效（episode.sfx；tick/whoosh/thud/ping…）
├── assets/audio/   <line_id>.wav（逐句）
├── hyperframes/    index.html（薄宿主：槽位+音频+字幕条）
│                   ├── compositions/s01.html …（每幕独立子合成）
│                   └── assets/ (gsap.min.js, console.css, console.js, audio/, images/, footage/)
├── renders/        final.mp4 (+ final_4k.mp4)
└── package/        final.mp4, cover_16x9.png, publish_copy.txt(含【素材来源】), README.txt
```

**渲染架构（HyperFrames 官方 modular / sub-compositions 铁律）**：
- 每幕一个 `compositions/<id>.html`（`<template>` 载体，脚本在模板内，timeline 键 = 幕 id，幕内相对时间）；
- 宿主 `index.html` 只做编排：槽位 + 音频（root 直子；旁白 track 10 / BGM track 11）+ 字幕条；
- 共享 CSS/JS 放宿主 `assets/`；子合成根样式必须内联（class 定样式会被作用域化失效）；
- 细节与坑见 `apps/console-remake/specs/LESSONS.md`。

## 封面两步法（AI 底稿 + 排版叠字）

1. **无字底稿**（生图）：通过 `image_selector` 生成，prompt 要求控制台/HUD 场景 +
   "absolutely no text, no letters, no numbers, glyphs, logos, watermarks"，
   构图预留左侧暗部给排版；16:9 与 4:3 **各出 2 张候选择优**（成本几分钱）。
   底稿存 `projects/<slug>/assets/covers/`。
2. **排版叠字**：`python apps/console-remake/template/make_cover.py --bg <底稿> --size 1920x1080
   --title "…" --sub "…" --tag "中文版 · 控制台译制" --out projects/<slug>/package/cover_16x9.png`
   （4:3 同法，`--size 1440x1080 --bias 0.62`）。
   导出 `cover_16x9.png` 与 `cover_4x3.png` 两份；**已存在的封面不被 `package` 覆盖**（截帧仅兜底）。

## 6. 零件字段速查（episode.json elements）

`frame / grid / pill / hairline / bignum / arrow / slot / paper / toast / panel / text / source / seal`
`win / term / rows / repocard / mark / bars / shape / image`（v2 界面零件见 design-system §10）

- 坐标一律 1920×1080 绝对值、8 的倍数；`bignum` 用中心坐标，其余用左上角；
- 颜色只写 token 名：`red / amber / blue / cyan / ink / dim`；
- 箭头可用 `from/to`（引用元素 id，自动测量端点）或 `x1,y1,x2,y2`；
- 胶囊 `style: solid | outline | filled`；格阵 `fill:0~1` + `divider:true` 画分界发丝线；
- 每句可用 `enter_offset` 控制零件在句内进场时机。
- **`image`（v2.2 真实图片）**：`src`（`assets/images/` 文件名）、`x/y/w/h`、`fit: cover|contain`、
  `radius`、`dim`、`label`（角标文案）、`provenance`（`url`+`license` **必填**——真实图片必须可追溯）；
- **`footage`（幕级，非元素）**：`{src,x,y,w,h,radius,dim,bare,focus,cam,provenance}`（LESSONS §11）；
- **`real: true`**：标记"本元素是真实实体"（校验用）——真实实体必须用 `image` 零件承载，
  用 CSS 零件画真实实体且标 `real`、或反过来漏标，都会被复审指出。

## 7. 跨智能体派发（Compute Worker）

```
主 Agent（轻）：new / script / approve-script / compose / package / status
Compute Worker（重）：
  python bin/console_remake.py run-heavy console-<slug> --json
  → 只回报单行 JSON（含 video / package_dir / elapsed_s）
```

排障速查：
- `npx` 在 Windows 下必须由 `sh()` 经 `shutil.which` 解析（.cmd）；运行时统一 `npx --yes hyperframes@latest`；
- 渲染前 lint 必须 0 error（根元素需 `data-start="0"`）；
- 预览检查：`npx --yes hyperframes@latest snapshot <hyperframes目录> --at 1.5,8,14 --describe false`；
- 静音/异常音频：`synth` 已内置逐句时长校验（<0.2s 直接报错）；
- **registry 组件时长适配（装配器自动）**：组件内部 timed 元素的 data-duration 会把可见窗口截断
  （实测 >声明值后整幕空白），装配器 compose 时自动对齐槽位时长；手改组件勿删 `duration-adapter` 标记；
- **`data-color-grading` 禁用**：v0.7/v0.8 实测会让页面加载挂死（snapshot/render 全挂），
  本管线不使用运行时调色——素材融入靠窗口框与画面设计，勿再加 `grading` 字段。

## 8. HyperFrames 能力侦察（动笔前置，强制）

> 教训：第一版全片只用 CSS 零件、把 HyperFrames 当"渲染器"用，被用户判定「你并没有把
> HyperFrames 的能力发挥出来」。能力不会自己出现——动笔前必须把能力面摸一遍；
> 快照会漂移，`catalog/docs` 是唯一真值（技能见 `hyperframes-registry` / `hyperframes-cli`）。

**侦察四连（每次开工重跑；运行时统一 `hyperframes@latest`）**：

```bash
npx --yes hyperframes@latest catalog --json                 # 注册表全量积木（blocks/components；超时重试）
npx --yes hyperframes@latest docs <topic>                   # 语法真值：data-attributes/rendering/gsap/compositions
npx --yes hyperframes@latest media-treatment --capabilities # 调色能力目录（注意：data-color-grading 本管线禁用，见 §7）
npx --yes hyperframes@latest skills check --json            # 技能新鲜度；stale/missing → skills update
```

**产出 `artifacts/capability_recon.json`（动笔前置，缺它 = 红线 #12 未过）**，至少含：

- `catalog`：本次可用 block/component 名清单（只列备选/打算用的）；
- `mapping`：**积木 ↔ 分幕映射**——哪几幕用哪个注册表组件/调色/转场，为什么；
- `media_treatment`：调色 preset 与参数意向（footage 全片统一影调）；
- `docs_checked`：查过的 topic（防脑补语法）。

**能力清单（快照地图，真值以 `catalog` 为准）**：

| 能力面 | 入口 | 用途 |
|---|---|---|
| 注册表积木 | `npx hyperframes add <name>`（`hyperframes-registry` 技能） | 转场 block（如 cinematic-zoom）、组件（browser-device-stage 浏览器框+swap_at 换屏、code-terminal-run 注册表终端、directional-wipe、caption-kinetic-slam…） |
| 素材调色 | `npx hyperframes media-treatment --file <f> --selector <s> --grading '<json>' --apply --json` | WebGL 调色：preset（warm-daylight/deep-contrast…）+ adjust + vignette/grain；footage 统一影调（PowerShell 引号吃字，用 Python subprocess 传参） |
| 镜头语言 | `hyperframes-keyframes` 技能 + `snapshot` | 推拉摇移、punch-in/out、Ken Burns、遮罩、SVG 绘制 |
| 动画运行时 | `hyperframes-animation` 技能 | GSAP/Lottie/Three.js/WAAPI 适配、场景蓝图、转场规则 |
| 音频/字幕 | `hyperframes-media` + `media-use` | TTS/BGM/转录/去背/字幕；SFX/BGM/图标素材解析 |
| 验证/渲染 | `npx hyperframes check` → `render` | check = lint + 运行时审计；0 error 才可渲染 |

**纪律**：
1. `catalog` 里装了 ≠ 该用；`mapping` 里每条都要写"这幕为什么需要它"——**能用没规划 = 缺陷**；
2. 样片验收时一并检查"能力利用率"：footage 调色了吗？终端段为何不用 `code-terminal-run`？
   转场评估过注册表候选吗？（把这几个问题逐条答完再给用户看样片）；
3. 注册表组件自带字体/配色（JetBrains Mono/Bebas…），接入时用 CSS variable（`--accent/--brand/--accent-2`）
   对齐 console-v2 token（橙 `--accent`、Cascadia 字体纪律），必要时改组件内 token——不要两套视觉语言硬拼。

## 9. 素材来源与路由（真实实体 → 真实素材）

**判定**：这句台词的主体是真实存在的实体吗（真人/产品/项目/机构/界面/地点/事件）？
是 → 按本表采集真实素材；否（抽象概念/结构/数据）→ 九零件 CSS。

**路由表**：

| 实体类型 | 首选来源 | 工具/入口 |
|---|---|---|
| 软件界面/网页/工具页 | 真机录屏/截图 | `playwright-recording`、capture 工具链（LESSONS §11；开源工具建议迁入 `apps/console-remake/tools/capture/`） |
| GitHub 项目/仓库 | 真实仓库页录屏、owner 头像/官方 logo | capture + `media-use resolve`（icon/logo） |
| 真人（作者/演讲者） | 官方头像/官方照片、Wikimedia Commons | Wikimedia（免 key）`direct_clip_search`；`agent-reach` 检索 |
| 产品/设备/品牌 | 官方 press kit / 官网素材 | `agent-reach` 抓官方页面；`media-use` 品牌 logo |
| 地点/历史/事件 | Wikimedia Commons、archive.org、NASA | `tools/video/stock_sources/`（wikimedia/archive_org/nasa 免 key） |
| 通用配图（设备/场景） | Pexels / Pixabay | `pexels_image` / `pixabay_image`（或 `image_selector` 的 stock_image 能力） |
| 社交媒体内容 | 原帖截图（含账号名） | `agent-reach` + Playwright 截图 |

**纪律**：

1. **先搜后降级**：每处真实实体先按本表搜寻；找不到才允许降级为 CSS 抽象，并在幕 `label`
   写明原因（如"无可用授权图，改抽象示意"）；
2. **逐条登记 provenance**：`url` + `license`（自产填 `self`/`自有素材`）；CC-BY 类素材发布时
   必须署名——`package` 会自动汇总进 `publish_copy.txt`【素材来源】段；
3. **肖像与商标**：只用官方/许可素材；不 AI 生成真人图；未授权人脸禁止进封面；
4. **归档**：图片放 `assets/images/`（image 零件），录屏放 `assets/footage/`（footage），
   文件名写进 episode；素材文件随项目留存，不用临时外链。
