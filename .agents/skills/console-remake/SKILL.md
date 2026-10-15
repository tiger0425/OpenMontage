---
name: console-remake
description: >
  深色开发者控制台（console / HUD）设计复刻管线（bin/console_remake.py）的操作指南。
  输入一条参考视频（YouTube URL / 本地文件），把它的控制台设计语言拆成零件
  （空心描边框/数据格阵/等宽胶囊/发丝线/巨型数字/连接箭头/刻度槽/米白纸面板/通知 toast
  + v2 界面零件 + 三类连接件 + 划线标注 + v2.3 吉祥物零件），
  以「结构借鉴 + 独立重写」产出中文版：IndexTTS2 克隆配音 + HyperFrames 1920×1080 合成 +
  内嵌设计文字 + console 字幕条；**全程零 AI 生图**——真实人物/实物/界面采集真实素材并登记出处，
  封面走 PIL 程序化多规格合成（一次出 7 个尺寸），出镜角色用系列吉祥物「小挽」的 6 姿态透明底图。
  v2.3 两条硬纪律：**主角尺度律**（每幕视觉主角 ≥ 200px）与**角色贯穿**（每集 8~13 次、视线朝内容）。
  动笔前必做 HyperFrames 能力侦察（catalog/docs）。
  触发词：控制台复刻 / console-remake / 深色控制台 / 跑控制台管线 / 把这条视频做成控制台版中文 /
  控制台设计复刻 / 加吉祥物 / 做封面多规格。
---

# 深色控制台设计复刻管线操作指南（console-remake）

## 1. 概述

`console-remake` 是针对**讲解型视频**的设计复刻管线（CSS 世界负责"讲解"，真实素材负责"作证"）。
参考片分析已固化为世界宪法 `apps/console-remake/specs/design-system.md`（console-v1 → v2 → v2.1/v2.2 → **v2.3**）。

**四条世界级纪律（违反=返工）**：

1. **能力面纪律（v2.2）**：动笔写分幕之前，先侦察 HyperFrames 能力面（注册表积木/调色/关键帧/转场）。
   "能用的能力没用上"按缺陷处理——教训来源：第一版全片把 HyperFrames 当渲染器用，被用户判定
   「你并没有把 HyperFrames 的能力发挥出来」。见 §8。
2. **素材真实纪律（v2.2）**：真实存在的人物/实物/项目/界面 **必须采集真实素材**（`image` 图片 /
   `footage` 录屏）并登记出处与许可；CSS 只负责抽象概念、结构与数据。禁止 CSS 假扮真实实体，
   禁止 AI 生图编造真人/真实产品。见 §9。
3. **主角尺度律（v2.3）**：**每幕必须有 1 个视觉主角，视觉高度 ≥ 200px**；禁止"整幕最大元素 ≤ 72px"
   的清单幕。留白律只允许"少而大"，不允许"多而小"。教训来源：用户评审「前面画面中的视觉元素都很小，
   不吸引人看下去」。见 `design-system.md` §11.1。
4. **角色贯穿（v2.3）**：每集 **8~13 次**吉祥物 beat，相邻机位/姿态必须不同、**视线必须朝向内容**。
   教训来源：用户评审「怎么没有放吉祥物」。角色是**系列资产**（「小挽」，见 §6 与 §10）。见 §11.2。

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
14. **主角尺度律**：每幕必须有 1 个视觉主角，视觉高度 **≥ 200px**；禁止"整幕最大元素 ≤ 72px"。
    `bignum` 放宽到 180~420px；`sm` 胶囊只能当句内次级标签。自检：缩到 480×270 时第一眼能不能说出这幕在讲什么。
15. **角色贯穿**：每集 8~13 次吉祥物 beat（开场/章转场/数字揭晓/静默失败/结论），相邻两次**机位与姿态必须不同**；
    3/4-朝左的姿态放右侧、`point` 放左侧或镜像——**不许指画外**。角色是"实物"，**不参与语义色编码**。
16. **归档/发布字段禁止硬编码**：署名、来源、AI 声明、素材出处一律从**本项目的
    `artifacts/publish_copy.json` / `episode.source`** 取，缺失才回落到通用句式。
    硬编码会把上个项目的署名带进本项目归档（已发生过：把 Kai《Agent Harness》写进了别的片子）。
17. **成片抽帧验收，不接受快照放行**：注册表槽位视频、连接件、吉祥物零件都有"快照正常≠成片正常"；
    改完必须整片 render 后抽帧验证（小改动可用子集 `compose --scenes sNN` + `render` 快速迭代，见 §7）。

## 5. 目录与文件

```
apps/console-remake/
├── specs/design-system.md          # 世界宪法（必读；§11 = 主角尺度律 / 角色贯穿 / 封面制度）
├── specs/script-spec.md            # 中文脚本与分幕规范
├── specs/LESSONS.md                # 实战经验（改管线前必读）
├── specs/console_episode.schema.json
├── template/
│   ├── console.css                 # 零件 CSS → 拷贝为宿主 assets/console.css
│   ├── console.js                  # 运行时（buildScene 每幕 / buildHost 宿主）→ 宿主 assets/console.js
│   ├── generate_composition.py     # 装配器：episode+tts → timings + 宿主 + 每幕独立 HTML + 音频烘焙
│   ├── make_cover_series.py        # **封面主路径**：程序化多规格合成（7 规格，含吉祥物姿态）
│   ├── make_cover.py               # 旧：AI 底稿 + 排版叠字（仅备用，见「封面」节）
│   └── fonts/                      # 系列字体：NotoSansSC-Black.ttf + CascadiaMono.ttf（跨项目复用）
└── tools/capture/
    ├── capture_screens.mjs         # Playwright 真机网页截图（双次导航 + 结算等待 + 内容断言）
    ├── fetch_logos.mjs             # Simple Icons(CC0) → 256px PNG 品牌标识
    └── diag_host.mjs               # 宿主页诊断：起静态服务 + 抓 console/pageerror

projects/console-<slug>/
├── artifacts/  fetch_report.json, capability_recon.json, episode.json, redline_scan.json,
│               tts_results.json, timings.json, line_words.json, publish_copy.json(可选)
├── assets/source/  ref.mp4, transcript.json, frames/
├── assets/images/  真实图片素材（image 零件；文件名写进 episode.src）
│                   + 吉祥物姿态 mascot_{land,idle,point,inspect,gate,wave}.png（系列资产）
├── assets/footage/ 真实录屏素材（footage；片段时长 ≥ 幕时长，见 LESSONS §11）
├── assets/sfx/     音效（episode.sfx；tick/whoosh/thud/ping…）
├── assets/audio/   <line_id>.wav（逐句）
├── hyperframes/    index.html（薄宿主：槽位+音频+字幕条）
│                   ├── compositions/s01.html …（每幕独立子合成）
│                   └── assets/ (gsap.min.js, console.css, console.js, audio/, images/, footage/)
├── renders/        final.mp4 (+ final_4k.mp4)
└── package/        final.mp4, cover_*.png（7 规格）, cover_specs.json, publish_copy.txt(含【素材来源】), README.txt
```

**渲染架构（HyperFrames 官方 modular / sub-compositions 铁律）**：
- 每幕一个 `compositions/<id>.html`（`<template>` 载体，脚本在模板内，timeline 键 = 幕 id，幕内相对时间）；
- 宿主 `index.html` 只做编排：槽位 + 音频（root 直子；旁白 track 10 / BGM track 11）+ 字幕条；
- 共享 CSS/JS 放宿主 `assets/`；子合成根样式必须内联（class 定样式会被作用域化失效）；
- 细节与坑见 `apps/console-remake/specs/LESSONS.md`。

## 封面（主路径：程序化多规格合成）

> **不要再走"AI 底稿"**。实测 AI 生图在"控制台/HUD 场景"里极易画出**伪文字**（4/4 张都有），
> 需要逐张用视觉模型验证才敢用；而系列真做法是 **PIL 程序化合成**——零生图、零方框、可批量出规格。

```bash
python apps/console-remake/template/make_cover_series.py \
  --out-dir projects/<slug>/package \
  --mascot projects/<slug>/assets/images/mascot_gate.png \
  --hero "一个模型" --sub1 "吃下文字、代码、图片、视频、音频" \
  --sub2 "EmbeddingGemma 2 拆解 · 现在能本地跑" --sub2-accent "本地跑" \
  --kicker-head "B · " --kicker-tail "控制台译制 #01" \
  --url "huggingface.co/google/embeddinggemma-2" \
  --meta "Apache 2.0 · 768 维共享空间 · 7.4 亿参数 · 控制台拆解"
```

**一次出 7 个规格**（`--specs` 可裁剪）：

| 文件 | 尺寸 | 用途 |
|---|---|---|
| `cover_16x9.png` | 1920×1080 | B站 / YouTube 横版主封面 |
| `cover_16x9_1280.png` | 1280×720 | 小尺寸横版 |
| `cover_bili_1146x717.png` | 1146×717 | B站后台上传推荐尺寸 |
| `cover_4x3.png` | 1440×1080 | 4:3 |
| `cover_1x1.png` | 1080×1080 | 方版（分享卡 / 动态） |
| `cover_3x4.png` | 1080×1440 | 图文位（小红书等） |
| `cover_9x16.png` | 1080×1920 | 竖版（抖音 / 视频号 / Shorts） |

**四条硬纪律（都是实测踩出来的）**：
1. **中西混排必须逐段换字体**：Cascadia Mono 无 CJK 字形，整行用等宽画中文 = 整片方框
   （脚本内 `draw_mixed/fit_mixed` 已内置；URL/meta 行最容易漏）。
2. **竖向推进用「墨迹底边」不用「墨迹高度」**：PIL 的 `draw.text` 原点在 ascender，
   墨迹底边 = `bbox[3]`、**不等于** `bbox[3]-bbox[1]`；用高度推进 → 下一行压进上一行下缘（"压字"）。
3. **吉祥物定位分模式**：`H/W ≥ 1.2` 走竖版（文字块下方，需给页脚让位）；其余走**右列通高**
   （只受右列宽与边距约束）。混用会把 1146×717 的吉祥物夹成 65px。
4. **背景必须有可见纹理**：网格 7% + 交点 12.5% + 扫描线 2.8% + 巨型底纹数字（0.52H / 8.5% 亮度）
   + 双侧微光；**暗角只压边缘**（整幅 composite 会把近黑底连网格一起压掉 → "全黑封面"）。

**验收**：视觉模型逐规格读一遍，要求「零方框 + 零出框 + 文字互不压 + 吉祥物 ≥ 45% 画面高 +
背景 textured」。**已存在的封面不被 `package` 覆盖**；`archive` 归档全部 `cover*.png`。

> 备用（降级）：`make_cover.py --bg <底稿> --size 1920x1080 --title …` 走"AI 无字底稿 + 排版叠字"；
> 仅在需要照片级底图时用，且**底稿必须先用视觉模型确认无伪文字**。

## 6. 零件字段速查（episode.json elements）

`frame / grid / pill / hairline / bignum / arrow / slot / paper / toast / panel / text / source / seal`
`win / term / rows / repocard / mark / bars / shape / image / mascot`（v2 界面零件见 design-system §10）

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
- **`mascot`（v2.3 吉祥物「小挽」）**：`pose: land|idle|point|inspect|gate|wave`、
  `x` 或 `right`、`y`、`h`（240~380）、`flip`、`bob`、`bob_period`、`ground`、`at`。
  - 素材固定名 `assets/images/mascot_<pose>.png`（装配器自动拷入，无需写 `src`）；
  - 宽高在 JS 里按姿态表**写死像素**（`MASCOT_ASPECT`），**不要用百分比/auto**——子合成里会解析成整只错位；
  - `flip` 的镜像加在**外层 wrapper**；写在 `img` 上会被 GSAP 的 transform 覆盖而静默失效；
  - `land` 自动走跃入落地四段 + 全部姿态带有限次 yoyo 呼吸待机（seek-safe）。

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
  **一次不要传超过 10 个时间戳**——实测 58 个一批会**静默输出全黑帧**（不报错）；
  且 `--output` 目录每批会被清空 → 分批要写各自子目录。遇到"全黑帧"先拿已渲染成功的老项目做对照实验；
- **快速迭代循环（省 20 分钟）**：小改动先 `compose console-<slug> --scenes s05,s19` → `render`（子集只渲这几幕，
  数分钟级）→ 抽帧确认，**确认后再 `compose`（不带 --scenes）恢复全片 + 全片 render**。
  注意子集模式下场景保留**原绝对时间**（`data-start` 不复位），所以抽帧时间仍按全片时间算；
- 静音/异常音频：`synth` 已内置逐句时长校验（<0.2s 直接报错）；
- **registry 组件时长适配（装配器自动）**：组件内部 timed 元素的 data-duration 会把可见窗口截断
  （实测 >声明值后整幕空白），装配器 compose 时自动对齐槽位时长；手改组件勿删 `duration-adapter` 标记；
- **`data-color-grading` 禁用**：v0.7/v0.8 实测会让页面加载挂死（snapshot/render 全挂），
  本管线不使用运行时调色——素材融入靠窗口框与画面设计，勿再加 `grading` 字段；
- **`at` 锚词取句中前段**：锚在句尾 = 主角"快说完时才出现"、停留极短（抽帧会看到幕内是空的）；
  锚词必须同时出现在 `line_text` 里（否则解析失败）。
- **视觉模型是验收工具，不是尺寸尺**：它可以判"有没有压字/是否全黑/角色朝哪"，但它报的像素尺寸**不准**
  （把 320px 的吉祥物报成 160px）。要精确尺寸就用特征色/像素统计量（如小挽的荧光绿 `G>200 & B<90`）。
- **注册表组件必须抽帧验收**：`agent-cursor` 实测在本管线宿主契约下整幕不渲染（4 个时间点全空屏，只有 HUD+字幕；
  同批次 `notification-stack` 正常）——`add` 成功、lint 通过、组件文档描述**都不构成可用证据**。
  已验可用：`browser-device-stage` / `notification-stack`；诊断三步与处置见 LESSONS §18.5。
- **`check` 的 Runtime / Motion / Contrast 三段都要看**（Lint 0 error ≠ 可渲染）：
  bracket 少写 `y1/y2` → 括线整条消失（Runtime 报 `<path> attribute d: … undefined`）；
  HUD 分隔符对比度不足已修在模板 `console.css`（`.hb-sep` 0.25→0.5，LESSONS §18.1/§18.6）。
- **零件三个静默坑**（check 看不出来，必须守字段）：`rows` 必须给 `w`（否则中文逐字竖排）；
  `bignum` 的 `x ≤ 1320`（无 width + left 定位 → 可用宽度 ≈ 1920−x，太小就换行）；
  `frame` 框内必须有可见内容（否则是空盒子）。见 LESSONS §18.2/18.3/18.4。
- **snapshot 卡住先清僵尸进程**：被中断的 snapshot 会留下挂起的 node/browser，导致后续 snapshot"在跑但不出帧"；
  按启动时间筛杀（保留 OpenCode 自身进程）即恢复。见 LESSONS §18.7。
- **官网 hero 常内嵌官方产品录屏**：parse 首页 HTML 找 `<video src>` 再下载，是比截图更硬的真实素材来源
  （本轮拿到 opencode 官方 1920×1080/60fps 终端演示 36.5s）。见 LESSONS §18.8。

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

## 10. 跨项目系列知识地图（先借，不要重新发明）

本管线不是孤岛：同目录下有一整套**系列实战**。开工前先看这几处，能省掉大量试错。

| 想解决什么 | 去哪里看 |
|---|---|
| **角色贯穿 / 三层密度 / 弧线运动 / 多姿态阶梯** | `projects/onchain-agent-promo/skills/hyperframes-arc-motion-promo.md`（方法母本） |
| 该方法的第 2~6 次实战复盘（踩坑编号连续 #1→#39） | `projects/{deepseek-harness-v020-rc1-cn,hindsight-agent-memory-cn,openshell-agent-runtime-cn,pi-agent-harness-cn}/skills/hyperframes-arc-motion-lessons-*.md` |
| **系列吉祥物「小挽」的姿态资产与封面做法** | `projects/pi-agent-harness-cn/assets/images/mascot_*_crop_alpha.png`（6 姿态透明底）+ 同项目 `deliverables/cover.png` 与 `publish_log.json` 的 `cover_credit` |
| 句级 TTS 时间表 / 分块合成（根治音画不同步） | arc-motion 母本 §十三 |
| 子代理逐幕并行写作（把大 HTML 产出卸出主上下文） | 母本 §3.2 派发包必含项 + pi 复盘 §一 |

**借用纪律**：
- 系列资产（吉祥物姿态、字体 `NotoSansSC-Black.ttf`/`CascadiaMono.ttf`）**直接拷贝改名复用**，
  零成本且视觉连续；拷完先校验（姿态图 `visible_h_ratio` 应为 1.000、四角 alpha=0）。
- 母本的**方法**照抄，**视觉宪法不照抄**（那套是纯黑+荧光绿+橙的 promo 宪法；console 世界用自己的 token）。
  唯一例外是吉祥物：它是跨片系列身份，**原样使用、不重新配色**，且不参与语义色编码。
- 复盘里的坑如果已经在本管线复现过（如 `code-terminal-run` 时长截断、`layout` 豁免不继承、
  Cascadia 画中文变方框），说明是**跨管线通病**——修完请回写到本文件与 `specs/LESSONS.md`。
