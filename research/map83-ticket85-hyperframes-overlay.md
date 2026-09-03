# Ticket #85 findings — hyperframes 横屏重点提示 overlay 可行方式

- Map: #83 抖音二创管线（横屏去广告 / 换音 / 抖音节奏重剪）
- Ticket: #85 hyperframes 横屏重点提示 overlay 可行方式
- Skill 基线：`hyperframes`（入口路由）、`graphic-overlays`、`hyperframes-core`、`hyperframes-media`、`hyperframes-cli`；只读 skill，未写代码、未渲染
- CLI 版本（只读确认，2026-09-03）：`hyperframes 0.8.27`，`upgrade --check` 显示已最新；`skills check` 仅 `hyperframes-cli` 一项 skill 快照 outdated，不影响本结论
- 核心约束（来自 skill，四个形式通用）：HyperFrames 是"在已有视频上叠加合成"，**不剪辑原片本身**（不改 timing / 颜色 / 构图 / 音频）；原片全程照常播放，提示层是定时 HTML 卡片经 GSAP 主时间轴合成后 render 成 MP4

## 渲染链路（四个形式共用同一条链，进的环相同）

1. `ffprobe` 取宽/高/时长/fps + `ffmpeg` 提 `audio.mp3`
2. `npx hyperframes transcribe audio.mp3 --json --model <对应语言>`（本地 Whisper，无 key；注意默认 `small.en` 会把非英文静默翻译，必须显式传 model；字级数组 `[{text,start,end}]`，尾词可能超出片长，需 clamp 到片长）
3. 读 transcript 定 card 时间轴（`storyboard.json`，agent 内部规划物，无 CLI 消费；字段 `id/intent/startSec/endSec/accentIndex/zone/contentHints`）
4. 原片重编码为密关键帧版（`ffmpeg -g <fps> -keyint_min <fps>`），否则 seek 会冻帧
5. 写 `public/cards/card-XX.html`（单根 `.card`、scoped CSS、无 `<script>`、无外链、用 `data-anim-*` 声明动画）
6. 组装 `public/index.html`：`#video-wrap`（`<video>` 必须是 host root 直接子节点，framework 接管播放）+ 每个 card 一个 `card-host clip`（`data-start/data-duration/data-track-index`，bounds 按 zone 解析）+ 单条 paused GSAP 主时间轴注册到 `window.__timelines`
7. `lint` → `validate` → `inspect` → `snapshot --at <各卡中点>` 目检 → `render --quality draft` 迭代 → `high` 交付

横屏（1920×1080）布局配方：`split→side-panel`、`stack→lower-third`、`pip→fullscreen`、`overlay→video-overlay`；另有 `whiteboard-area`（稠密数据）、`fullscreen`（hero/金句）可单卡变体。`data-anim` 可用：`fade-in/out`、`slide-in`、`kinetic-chars`、`typewriter`、`count-up`、`draw-path`、`grow-x/y`、`scale-pop`、`blur-in`、`mask-reveal`、`morph-to`。

## 形式一：关键词描边 / 高亮

- 做法：`video-overlay` / `lower-third` zone 的透明卡，用 `kinetic-chars`（逐字 pop）或 `typewriter` 做关键词，描边用 `-webkit-text-stroke` / 多重 `text-shadow`，高亮用 `mask-reveal` 色块或 `grow-x` 下划线；相对卡片 `startSec` 的 `data-anim-at` 偏移对齐关键词说出时刻
- 进链路哪一环：第 5 步单卡 HTML + 第 6 步 GSAP 时间轴（`card.startSec + anim-at` 量化到 1/fps）；不新增链路节点
- 大致工时：单样式模板约 0.5 天（含 snapshot 目检）；整条片多处复用约 +0.5 天调参
- 风险：低。注意两条硬规则——描边字需留标题安全边距（≥80px padding）以免贴边；`transform/scale` 对 inline `span` 无效，逐字 `char` 必须 `inline-block` 且有尺寸，否则隐形（lint 不报，属静默 bug）

## 形式二：数据卡

- 做法：`side-panel`（split）或 `whiteboard-area` zone 的半幅/内嵌卡，标题 + 大数字（`count-up`，`format=.0f/.1f/,d`）+ 1~2 条明细；长持卡（>15s）做多步 stagger 展开；数字必须在 author 时 bake 进 HTML（render 期禁网络、无实时拉数）
- 进链路哪一环：第 3 步 storyboard 定"哪句出哪张卡" + 第 5 步卡片 HTML；`count-up` 的 from/to 写死在 `data-anim` 属性里
- 大致工时：首张数据卡约 0.5~1 天（含设计 token：10 style × frame 矩阵选型）；同片复用每张 +1~2h
- 风险：低~中。数字与口播对不上是最常见翻车（转录纠错必须做）；稠密数据卡在小字号下横屏可读性差，需按 style 参考放大约 1.3 倍思路的反方向——横屏基线标题 64~96px、正文 24~30px，低于此易糊；`--strict-variables` 下未声明变量会 fail，需过 lint

## 形式三：箭头与框选

- 做法：`video-overlay` zone 的全画布透明卡，SVG 箭头用 `draw-path`（元素须是 `<path>`），框用 `mask-reveal` / `scale-pop` + `morph-to`；位置是手写绝对定位（百分比/bounds），指向画面固定区域；如原片该区域有运动，只能"估平均位"跟随，不能真跟踪
- 进链路哪一环：第 5 步透明卡（`.root` 必须透明，否则盖住视频）+ 第 6 步 GSAP tween；无额外 CLI 步骤
- 大致工时：固定位置框选约 0.5 天；多处箭头 + 路径微调约 1 天
- 风险：**中，这是四种里风险最高的**。HyperFrames 无目标跟踪、无抠像跟随：被指物一旦在画面内移动/切镜，箭头即错位；只能用于"位置稳定的 UI/车辆/固定机位"；跨运镜需按切镜拆卡，每镜一张，卡数膨胀。误用会出现全片箭头指空

## 形式四：侧栏小结

- 做法：`split` 布局标准配方：`#video-wrap` GSAP tween 收至右半 `{left:960,top:0,width:960,height:1080}`，左半 `side-panel` 放小结卡（kicker + 标题 + 3 条以内要点，`slide-in`/`fade-in` stagger）；`object-fit:cover` 下视频会被裁，需把 tween 矩形对齐源宽高比或接受裁边
- 进链路哪一环：第 6 步组装（video-wrap 位移动画是按卡写 GSAP tween，schema 不存单卡 video bounds）+ 第 7 步 snapshot 重点目检左右比例
- 大致工时：首版 split 模板约 1 天（含 video 位移 + 卡片设计）；后续复用每条片约 +2~4h（换文案 + 微调 tween）
- 风险：低~中。主要风险是裁剪观感：横屏源在半幅下 `cover` 会裁掉左右或上下；人物访谈建议 `stack`（上视频下卡）替代 `split`；`video-overlay` 全幅玻璃卡透传路径（`透传完整路径`类比：此处指卡片透明、视频全幅保留）更稳但信息密度低

## 另注：motion-graphics 透明 overlay 路线（备选，不推荐作主链）

- 单个短促下三分之一/标注可用 `/motion-graphics` 输出透明 overlay（alpha WebM/MOV），再用 ffmpeg 叠回原片；适合"只要一个框、不要整片包装"的轻需求。但二创管线要的是全片多卡节奏包装，主链仍应走 `graphic-overlays` 整片合成，避免两套渲染链并存。

## 给管线的选用建议

- 优先级：侧栏小结（信息承载）+ 关键词高亮（节奏）作默认组合；数据卡按"有数字才上"触发；箭头/框选仅限固定机位镜头，写进规格时加前置判断（镜头是否运动/是否切镜）。
- 规格里必须锁：canvas 固定 1920×1080 landscape；布局四选一事先定（默认 `stack` 最稳，访谈/数据再用 `split`）；card 节奏按片长基线（60s~3min 取 8~12s/卡，信息密度 ×0.7/×1.0/×1.5）自动估卡数， floor 5 卡。
- 工时基线（单条 1~3min 成片，复用模板后）：转录纠错 + storyboard 约 0.5 天；卡片 HTML + 组装约 0.5~1 天；lint/validate/snapshot/render 迭代约 0.5 天；合计约 1.5~2 天/条，模板稳定后可压到约 1 天/条。
