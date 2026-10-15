# console-remake 实战经验（LESSONS）

> 来源：console-remake 管线 v1 全流程实战（Agent Harness 中文版：样片 → 40 幕全片 → 三轮设计迭代 → 归档，2026-09-15）。
> 用途：任何 agent 改动本管线（生成器/运行时/样式/封面/流程）前必读。踩过的坑不再踩第二遍。

---

## 0. 全流程事实基线（用于估时/估成本）

> 两轮实测对照。第二轮（console-local-multimodal-rag，2026-10-09）含吉祥物零件与多规格封面，
> 是当前**最新的口径**（估时请用它）。

| 环节 | 第一轮（v1 精讲片） | **第二轮（含角色 + 多规格封面）** | 备注 |
|---|---|---|---|
| 单集规模 | 40 幕 / 121 句 / 234 零件 | **29 幕 / 112 句 / 217 零件** | 分 3 批写入 episode.json |
| 中文旁白字数 | 2285 字 | **2454 字** | 数字汉字化后偏长 |
| 配音音频 | 481.2 s | **471.2 s**（112 句） | 语速 ≈ **5.2 字/秒**（术语多时更快，4.6~5.7 波动） |
| 成片时长 | 565 s（9:25） | **540.8 s（9:01）** | 音频 + 句间/幕间呼吸 ≈ 70 s |
| **GPU 配音** | 121 句 ≈ 12.7 min | **112 句 = 648 s ≈ 10.8 min** | 含模型冷启动；seed 42；GPU 锁串行 |
| **词级对齐 align** | ≈3 min | **255 s ≈ 4.3 min** | 产出 line_words.json（`at` 锚定依据） |
| **渲染 1080P** | 565 s ≈ 8.5~10 min | **540.8 s → 1239 s ≈ 20.7 min** | 0.44× 实时；元素数/吉祥物会显著拉长 |
| 子集渲染（2 幕） | — | **≈4 min**（271 s 时间轴） | 快速迭代用，见 SKILL §7 |
| snapshot 抽帧 | 秒级/批 | **≈1 min/10 帧**（含字体编译） | 一批 ≤10 个时间戳 |
| 封面（7 规格） | AI 底稿 2 张 + 排版 | **PIL 程序化合成，< 5 s / 7 张** | 零生图 |
| package / archive | < 10 s | < 10 s | 纯本地拷贝 |
| 空屏扫描 | 20 组帧差分 | **58 帧特征色/墨迹统计** | 见 §16 |

**成本**：TTS / 渲染 / 封面**全部本地免费**。第二轮 AI 生图只用了 3 张**已弃用**的封面底稿
（≈$0.015）；最终封面为程序化合成，**API 成本 0 元**。

**估时公式（下预算用）**：`成片秒数 ≈ 字数 / 5.2`；`渲染秒数 ≈ 成片秒数 × 2.3`（元素密、含角色时取 2.3~2.5）。

---

## 1. 架构铁律（HyperFrames 官方 modular / sub-compositions）

- **每幕一个 HTML**：`hyperframes/compositions/<scene>.html`，`<template>` 即传输容器——
  `<style>`/`<script>`/主标记**全部必须在 `<template>` 内**，`<head>` 里的东西一律被丢弃。
- **宿主只做编排**：`index.html` = 槽位（`data-composition-src`）+ 音频（root 直子）+ 宿主 UI（字幕条 + HUD 框架）+「薄」根时间轴（`__timelines["main"]`）。
- **三键一致**：宿主槽位 `data-composition-id` == 幕文件内根节点 `data-composition-id` == `window.__timelines["<id>"]`。不一致 → 渲染日志 `Sub-composition timelines not registered`，45s/幕 超时后出静帧。
- **视觉幕统一 `data-track-index="1"`**（顺序排布）；音频用高位轨：旁白 10、BGM 11。
- **子合成根不要用 class 定样式**（lint error `subcomposition_root_styled_by_class`）：
  渲染时子合成 CSS 会被作用域化为 `[data-composition-id="xxx"] <selector>`，
  根节点自己的 class 选择器永远匹配不到根自身 → 幕"裸奔"。**根样式一律内联**。
- **共享 CSS/JS 放宿主**（`assets/console.css`、`assets/console.js` 外部引用）：
  宿主是 standalone 组合，外链正常加载；挂载后的幕内容继承宿主全局样式。
  幕文件因此保持 ~30 行（lint warning `composition_file_too_large` 也不会触发）。
- **`gsap` 全局**：宿主先加载 gsap，幕脚本后执行 → 幕里可直接用 `gsap`。
- **时间归幕**：幕内 timeline 一律**幕内相对时间**（= 全局时间 - 幕起点）；
  字幕/音频淡出/HUD 等宿主级动画才用全局时间。
- **`--scenes` 子集模式**：时间轴整体前移归零；样片即全片片段，先样片再全片不浪费。

## 2. 箭头（连接线）的坑（已修复，勿回退）

- **挂载先于布局**：子合成脚本执行时，克隆内容可能尚未参与布局，`getBoundingClientRect()` 全 0
  → 箭头几何塌缩到原点、完全不可见。
- **正确姿势**（console.js 现行实现）：
  1. 构建时先测一次；`root.getBoundingClientRect()` 宽高为 0 视为未就绪；
  2. 未就绪 → `gsap.ticker.add(retry)` + `tl.eventCallback('onUpdate', retry)`，就绪后重测并自移除；
  3. 绘制动画用 **proxy + onUpdate**（`paintArrow` 按「当前几何」逐帧写 dasharray/dashoffset），
     **不要**把 `getTotalLength()` 的结果烧死在 tween 里——重测后长度会变。
  4. 初始 `stroke-dasharray/offset = 99999` 兜底，防止未绘制时闪整线。

## 3. GSAP / seek 坑

- **`fromTo` 的 immediateRender**：from 值在**构建时立即应用**。所有入场元素
  必须 `from {opacity:0}`；箭头容器尤其不能 `from {opacity:1}`（否则整条箭头提前显形）。
- 包装类元素（text/bignum/seal）：**外层 `.p` 控制 opacity，内层控制 transform**——
  不要把 `p` 类加在内层（内层会被 CSS `opacity:0` 锁死，外层动画无效）。
- `tl.set()`/`tl.to()` 在时间点上生效；查询选择器只在**本幕**内使用（全局 id 会撞车；元素 id 已带幕前缀）。
- **HUD 章节翻页用 `tl.call`**（宿主时间轴，全局时间）；进度轨用
  `fromTo(fill,{scaleX:0},{scaleX:1,duration:total,ease:'none'})` + 游标
  `fromTo(head,{x:0},{x:1908,...})`——固定像素位移，seek-safe。
- 元素初始不可见依赖 CSS `.p{opacity:0}`；任何新零件都必须挂在 `.p` 基类下。

## 4. 世界实现坑

- **paper 普通行必须 `innerHTML` 赋值**（曾经漏写导致"只显示高亮行"）。
- **`**词**` 行内强调与 `highlight` 可重叠**：先 `mdBold()` 再在结果 HTML 里定位 `esc(highlight)` 插高亮框。
- **巨数字 count-up**：val 与 suffix 是分离节点，onUpdate 只写数字本体（曾出现 `15××`）。
- **坐标 8 倍数**只是提示（warning），不阻塞；但字幕条占底部 104px、HUD 进度轨在 y≈962，
  内容区应落在 **y ∈ [96, 940]** 之间（顶部让给 HUD 顶栏）。
- **格阵 divider** 只在「部分填充」时出现（整行填满时 col=0 跳过，属预期）。
- **刻度槽颜色**支持 red/amber/cyan/blue 四色 tick（blue 是后补的，CSS 里必须有）。

## 5. 背景与框架（"太单调"与"不知道讲到哪"的解法，2026-09-15 沉淀）

- **背景层次**（`#root::before`，自上而下检测顺序）：320px 大格 → 64px 小格 → 320px 交点节点 →
  暗角 → 左下红/左上蓝微光（放最上层，避免被暗角吃掉）。
- **颗粒**：单独 `#grain` div（z 140），256px 确定性噪声图（`random.Random(42)` 生成，构建时重建），
  opacity 0.05、`image-rendering: pixelated`；位于内容之上、字幕条（z 200）之下。
- **HUD 框架**（宿主级，40 幕常驻）：顶栏品牌 + `CH xx / 09 · 章名`（tl.call 翻页）；
  底部进度轨（暗轨 + 红填充 + 游标 + 每章刻痕）；16px 内缩画框 + 四角框标。
- **改动背景/HUD 后必须全片重渲**（它们进每一帧；不能只重渲片段）。
- 教训：**观众需要空间定位**——没有章节指示与进度，40 幕长片会"迷路"；这两件是常驻刚需，不是装饰。

## 5b. 关系与动作（"元素孤立"与"只有显形"的解法，2026-09-15 沉淀）

- **元素不许孤立漂浮**：凡有归属/指向/分组关系的元素，必须用连接件系住——
  `leader` 引线（标签→被标注物，默认带端刻度）、`bracket` 括线（把一组元素括起）、
  尺寸线式 `hairline`（`tick:true` 两端刻度）、`arrow`（因果/流程）。
  每幕至少一处"联系"（同色呼应/引线/括线/箭头/发丝线，四选一以上）。
- **动词要演出来，不能只显形**：台词里出现跑/塞/挪/删/漏/叠等动词时，用 motion 家族——
  `travel`（行进）、`push`（塞入目标并缩小消失）、`shift`（位移）、`erase`（压扁擦除）、
  `leak`（底部渗落小方块）、`stack`（层叠落定）、`grow`（生长）。
  动作必须落在"台词说到该动词"的 0.5s 窗口内。
- **删除线改动画**：`strike` 文本不再用 CSS text-decoration，改为 `p-strike-line` 红线
  从左划到右（`strike_at` 控制划出时刻）——"打不开/跑不了"是动作，不是样式。
- 实测样例：s04 四条虚线引线把 HARNESS 与 4 个术语胶囊接成接线图；
  s14 三枚胶囊被"塞"进 MODEL 框（push）；s20 旧办法框"漏"出红块（leak）；
  s23 "就能删文件"胶囊被"删"掉（erase）；s29 模型/外壳被"拉"到一起（travel）；
  s37 三层工程框"叠"上来（stack）；s34 读 30 次用 `stagger:0.028` 放慢扫填让观众数得清。

## 5c. 语音驱动（根问题，2026-09-15 确立为最高纪律）

- **症状**：画面"看起来还行"，但用户看片觉得"看到和听到不在一条线上、割裂"——
  因为元素只是"在台词开始后出现"，而不是"演这句台词的意思"。
- **机制**：
  1. `align` 阶段（whisper，逐句 wav，word_timestamps）→ `artifacts/line_words.json`（121 句 ≈3 分钟）；
  2. episode 元素用 `"at": "某个词"` 锚定；装配器 `_resolve_at` 用字符游标映射到词级时间戳
     （找不到时按字符比例退化）；
  3. 动作 = 把台词的小句语义**演出来**：三次"打不开"就是三次真实的"冲刺→弹回→坠落"（motion: reject）；
     "发回去。一遍，又一遍"就是同一块「整段对话」真的再发两趟（travel + travel_fade）。
- **自检**：逐幕问两个问题——「这一句在演什么动作？」「这个动作对应哪个词？」
  答案不清 = 偷懒，返工。
- 这一条优先级高于所有视觉规范：宁可元素简单，不可音画脱钩。

## 6. 封面（两步法，勿退回"截帧+标题"）——**已被 §16.4/16.5 取代，看新法**

> ⚠️ 本节是 v2.2 时代的"AI 无字底稿 + 排版叠字"两步法，**已降级为备用路径**。
> 2026-10-09（v3）确立的主路径是 **PIL 程序化多规格合成**（`make_cover_series.py`，一次 7 个规格、
> 含吉祥物姿态、零生图）——见 `design-system.md` §11.3 与本文件 §16.4/§16.5。除非需要照片级底图，
> 否则不要走本节。AI 底稿若用，必须先用视觉模型确认<u>无伪文字</u>（§15.6）。

1. **无字底稿**：`image_selector` 生成（prompt 明确 "absolutely no text/letters/numbers/glyphs/logos/watermarks"，
   构图预留左侧暗部）；**16:9 与 4:3 各出 2 张候选择优**。
   - 路由事实：minimax 尊重 `aspect_ratio`（4:3/16:9 都准）；**google_imagen 会忽略 aspect_ratio 返回 1408×768**，
     且会丢弃 seed——要精确比例就用 minimax 或生成后裁剪。
2. **排版叠字**：`python apps/console-remake/template/make_cover.py --bg ... --size 1920x1080 ...`
   （左侧+底部渐变遮罩 → 红条 → 标题/副题/标签；4:3 用 `--size 1440x1080 --bias 0.62`）。
3. **封面不可被覆盖**：`package` 阶段检测 `cover_16x9.png` 已存在则跳过截帧兜底（勿回退此保护）。

## 7. 文案与发布

- **publish_copy 用单文档 txt**（`publish_copy.txt`），json 只作内部数据源；章节时间轴并入简介段。
- 章节（`episode.chapters`，6-10 个为宜）用 `scene` 字段锚定起始幕；
  txt 的章节时间戳从 timings 实时换算（mm:ss），不要手写。
- 红线纪律照旧：结构借鉴+独立重写；术语保留（Harness/token/Agent）；数字汉字化；AI 声明必填。

## 8. 流程/工程坑

- Windows 下 `npx` 是 `.cmd`：subprocess 调用前必须 `shutil.which()` 解析（CLI `sh()` 已内置）。
- 渲染前 `hyperframes lint` 必须 0 error；宿主根要有 `data-start="0"`。
- **快照先行**：`npx hyperframes snapshot <dir> --at a,b,c --describe false` 秒级验证构图，
  再跑全片渲染（10 分钟级）；改动样式后先快照 QA 再派 Worker。
- TTS 复用：行文本未变时 `synth --only-missing` 跳过已有 wav；改文案会换 id，不必刻意重命名。
- `synth` 内置逐句时长校验（<0.2s 报错，防静音/杂音）；
  配音出现"男声变女声/杂音"先查 `apps/indextts-bridge/CALLING.md`（纯净克隆禁 emo_vector）。
- 重命令（synth/render/run-heavy）一律派 Compute Worker，`--json` 单行回报。
- **周期复盘**：设计类反馈（背景单调/缺框架）应提炼为世界级规格（写入 design-system.md）
  而不是单集补丁——同一条反馈只改一次。

---

## 9. console-v2 实战（AI LABS 8-repo 样片，2026-09-15）

- **连接件端点必须用分幕坐标解析，不能只靠 DOM 测量**：
  子合成脚本执行时布局常为 0，`getBoundingClientRect()` 塌缩 → 箭头/引线在**渲染器里整条消失**
  （浏览器预览正常、成片没有，最难查的一类 bug）。
  现行做法：`buildScene` 给每个节点挂 `node._spec = e`；`_endpoint()` 优先用 spec 的 x/y/w/h
  （确定几何），仅当零件没有 w/h（text/bignum 等）才回退 DOM 测量并挂 ticker 重试。
- **`p-arrow--*` 颜色类要同时设 `color`**：path 的 stroke 是 `currentColor`，
  只写 `stroke: var(--x)` 在 `<svg>` 层不生效（渲染成白色）。
- **`at` 锚定可与 `enter_offset` 叠加**（装配器已支持）：同一词起多个元素时用递增
  `enter_offset` 做错峰（8 卡阵 = 0.12s/张）。
- **空拍自检**：锚词靠近句末会出现 3~4 秒空屏（样例：8 卡阵锚「八个」→ 前 4 秒全黑）。
  锚词取句子的前中段，或分阶段锚（先「这些」出卡、后「立起来」画圈）。
- **样片 QA 流程**：compose（带音频）→ render → `ffmpeg -ss <锚词时刻±0.5>` 抽帧核对
  「动作是否落在词上」；连接件/标注类元素要在成片里抽帧验证（预览正常≠成片正常）。
- **console-v2 零件速记**：`win`（窗口 chrome，内容元素另叠其上）/`term`（逐字+输出行）/
  `rows`（状态点逐条点亮）/`repocard`（仓库卡）/`mark`（hl/ul/ring/cross 跟随标注）/
  `bars`（对比条）/`shape`（prim 分 stage 构建）。主色橙 `--accent`，绿 `--green`=通过。
- **语义要复述台词的本意，不能只做字面动作**（用户反馈实录）：
  「很平」不等于「空缺」——画面必须是"东西在、但它是平面的"，不是"没有"；
  「生成立体模型」必须真的立体——平面演示会被判定为"没理解内容"。
  经验：动手前把台词拆成"主体 + 状态"（有什么 / 它处于什么状态），画面只演这个状态。
- **`shape` 支持真 CSS 3D**：`stage3d:true`（`preserve-3d` + 六面体 prims：`x,y,z` + `rx/ry/rz`），
  `rot_x` 俯仰 + `spin_from/spin_to/spin_dur` 旋转；用于"图片→3D 模型"这类必须立体的演示。
  六面体 = 前/后/左/右/顶/底 六张面（背面 `ry:180`、右面 `ry:90`、顶面 `rx:90`），
  明暗靠面底色区分（前亮/右侧暗/顶中）。旋转要在比对/标注前收住（spin 提前结束），
  否则 2D 红圈/绿圈对不上 3D 面上的镜组位置。

## 10. 第一纪律：先理解，再画面（用户确立，2026-09-15）

> 用户原话：「要先理解内容再去生成画面，要保证画面和内容的一致性。」

**工作流（每句必走）**：读台词 → 拆出 **主体 / 状态 / 关系** → 选零件演这三样 → 自查三问。

**自查三问**：
1. 这句的主体是什么？我画的是它吗？
2. 它的状态是什么？画面能看出这个状态吗（而不是它的反面）？
3. 拿掉这个元素/动作，意思会变吗？不会变 = 装饰，删掉。

**已踩的坑（典型反面教材）**：
- 「很平」→ 画成"空缺框"：错，应为"东西在，但它是平面的"（静态图 + 不能转不能动）。
- 「生成立体模型」→ 平面示意：错，必须真立体（CSS 3D + 透视 + 旋转）。
- 「打不开仓库」→ 胶囊撞一下：错，应为"引线被切断/被门挡住"（状态语义，不是拟物碰撞）。

**验收方式**：抽帧对齐旁白词（`align` 词级时间戳 ±0.5s 抽帧），逐帧问"这一帧在演哪句话的什么状态"。

## 11. 混合真实素材（footage，2026-09-15 用户确立）

> 用户反馈：「差太多了，完全不是一个档次的」——原片 60% 是真实录屏，纯 CSS 抽象界面到不了那个观感。

**采集工具链**（全部本地、可重跑）：
- 网页录屏：`playwright`（node，`executablePath` 指系统 Chrome，`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` 装包）
  → 预热导航（第一次不录）避免开头白屏 → `recordVideo` → ffmpeg 转 mp4 → **自动裁白屏头**
  （1fps 缩略图找首个"非白像素 >2%"的帧，从该时刻 -0.2s 起切）。
- 终端录屏：`wt --pos 0,0 --size 118,37 powershell -File rec.ps1` 定位窗口 + `ffmpeg -f gdigrab
  -offset_x/-offset_y/-video_size -i desktop` 录区域。**坑**：Windows 11 默认 Windows Terminal，
  控制台窗口标题/`MoveWindow` 都不可靠，必须用 `wt --pos`；`.ps1` 必须带 **UTF-8 BOM**（PowerShell 5.1
  会把无 BOM 的 UTF-8 当 GBK，中文全乱）。
- WebGL/three.js 录屏：**Playwright 的 recordVideo 对 WebGL 会黑屏** → 改用逐帧截图
  （`page.screenshot` × N + ffmpeg 合成），并可程序化驱动旋转/推近来导演动作。

**footage 零件（装配器内置）**：
- 分幕里写 `"footage": {"src","x","y","w","h","radius","dim","focus"}`；
- 装配器把 `<video muted playsinline id="<scene>-footage" data-start="0" data-duration="<幕长>"
  data-track-index="2">` 放进**子合成内部**（HyperFrames 官方支持：子合成媒体按祖先偏移重定基）；
- `<video>` **必须有 id**，否则 lint 报 `media_missing_id`（渲染时冻结不出画）；
- 视频外套一层**无 data-\* 的** `.footage-wrap`（圆角/描边/压暗）；不能再给外层加 data-start
  （`video_nested_in_timed_element`，lint error）；幕内淡入淡出由 `.scene-inner` 统一管；
- 素材放 `assets/footage/`，装配时自动拷贝到 hyperframes；**片段时长必须 ≥ 幕时长**
  （否则后段无帧）；子集 compose 会把尾 2s 并入最后一幕，避免 `subcomposition_blanks_before_host`。

**分工纪律**：真实素材负责"演示/证据"（仓库页、终端会话、3D 演示），CSS 世界负责
"讲解/结构/结论/转场"。素材必须**真实**：命令真跑、页面真开、模型真渲染；不许拿 CSS 假扮录屏。

**验收方式**：抽帧对齐旁白词（`align` 词级时间戳 ±0.5s 抽帧），逐帧问"这一帧在演哪句话的什么状态"。

### 10.1 零件小坑

- `mark` 的 `cross`（划叉）**必须按框对角线拟合**（`len=√(w²+h²)`、`angle=atan2(h,w)`），
  固定 ±45° 会在宽扁框上溢出画面（实测 1000×96 的框会甩出 700px 的斜线）。
- 宽扁框的划叉视觉上就是"双横线划掉整行"，正好用于划代码行/长回复。

## 12. 能力侦察与真实素材（2026-09-15 用户确立，v2.2）

> 用户点破：「你并没有把 HyperFrames 的能力发挥出来」+「有些真实存在的实物和人，
> 应该去找真实的图片来做元素，你也不会」。两条均已写成管线纪律
> （SKILL.md §8/§9 + 红线 #2/#12/#13；manifest v1.1 的 script/compose review_focus）。

### 12.1 能力侦察（HyperFrames 能力面）

- 动笔（episode.json）前跑四连：`npx hyperframes catalog --json` / `docs <topic>` /
  `media-treatment --capabilities` / `skills check --json`；产出 `artifacts/capability_recon.json`
  （catalog 备选 + 积木↔分幕 mapping + 调色意向 + docs_checked）。缺它 script 闸门告警（红线 #12）。
- 已见即可用的样例（`Temp\opencode\omo-reg\`，建议迁入仓库当黄金样例）：
  `browser-device-stage`（录屏进浏览器框 + `swap_at` 换屏）、`code-terminal-run`（真实命令进注册表终端）、
  `media-treatment` 调色（`warm-daylight`/`deep-contrast` + vignette 0.22 + grain 0.06）、
  `cinematic-zoom`(block) / `directional-wipe` 转场。
- 坑：PowerShell 引号会吃 `--grading` 的 JSON → 用 Python subprocess 传参；
  注册表组件带自己的 token/字体（JetBrains Mono/Bebas…）→ 用 CSS variable 对齐 console-v2（橙 `--accent`），不要两套视觉语言硬拼。

### 12.2 真实素材（image 零件 + provenance）

- **真假判定**：台词主体是真实存在的实体（人/产品/项目/界面/地点）→ 必须真实素材；
  抽象概念/结构/数据 → 九零件 CSS。
- `image` 零件（console.js `buildImage` / console.css `.p-photo`，v2.2 新增）：
  `src`（放 `assets/images/`，compose 自动拷入 hyperframes）+ `x/y/w/h` + `fit/radius/dim/label`
  + `provenance{url,license}`（**必填**；自产填 `url:"self"`、`license:"自有素材"`）。
- **校验（validate_episode，硬错误）**：`image` 缺 `src` / 缺 `provenance.url|license`；
  元素 `real:true` 却不是 `image`（= CSS 假扮真实实体）。footage 带 `provenance` 时必须完整。
- **路由表（SKILL.md §9）**：界面→真机录屏；GitHub→仓库页/官方头像；真人→官方/ Wikimedia（免 key）；
  产品→press kit；地点历史→ Wikimedia/archive.org/NASA；通用配图→ pexels/pixabay；社媒→原帖截图。
- `package` 自动把 provenance 汇总为 `publish_copy.txt`【素材来源】段（`collect_credits`）；
  archive 的 metadata.json 同步带 `credits`；`script` 闸门输出 `capability_recon` + `real_assets` 摘要供人审。

## 13. Registry 组件实战与两个硬坑（2026-09-15，console-dsh-releases）

**接入姿势（已固化进装配器）**：`npx --yes hyperframes@latest add <name> --dir <项目>/hyperframes`
→ episode 幕写 `registry: {component, vars, slots}` → 装配器产出宿主槽位（`data-variable-values`
**单引号** JSON，实体转义会触发 `invalid_variable_values_json`）+ 宿主级
`<template data-slot="<comp>-<slot>">` + 素材自动拷贝；**每集同组件最多一次**（timeline 键冲突，校验会拦）。

**坑 1 · 组件时长截断（装配器已自动适配）**：组件内部 timed 元素（如 browser-device-stage 的
`.bds-clip`）带 `data-duration="5"`，运行时按它裁剪可见窗口 → 槽位再长，声明值之后整幕空白
（v0.7.109 与 v0.8.40 行为一致；且运行时挂载后 `root.dataset.duration` 恒为 undefined，
组件读不到槽位时长）。装配器 `_adapt_registry_component()` 在 compose 时把组件内所有
`data-duration` 与 `parseFloat` 默认值对齐槽位时长（幂等，带 `duration-adapter` 标记，勿手删）。

**坑 2 · `data-color-grading` 挂死页面**：手写属性与 `media-treatment --apply` 官方写法两种方式
实测，img/video 上带 `data-color-grading` 都会让 snapshot/render 的页面加载导航超时（挂死）
→ 本管线**禁用运行时调色**；素材融入深色世界靠窗口框 + 画面设计解决。

**运行时版本纪律**：统一 `npx --yes hyperframes@latest`（本片 0.8.40 验证通过；老缓存 0.7.109 行为一致，
可放心升级）。

### 13.1 元素尺寸缺省 = 静默奇观（2026-09-16 踩坑）

- **症状**：toast 的文字"一字一行"竖着排（用户报「很多幕都有一排竖着的文字」）。
- **根因**：`buildToast` 用 `px(e.w)` 设宽，episode 里 15+ 处 toast 都只给了 x/y 没给 `w` →
  `width:0px` → 中文逐字换行。**没给尺寸字段的元素不会报错，只会静默变奇观**。
- **修复**：`buildToast` 增加默认宽 560 + 右缘收口（`x+w>1800` 时收窄，最小 400）。
  新增/修改零件时必须自查：所有 `px(e.xxx)` 的关键尺寸字段在 episode 里是否都有值。
- **顺带**：`hairline` 默认竖向且用 `len`（不是 `w`）——写 `w=1700` 且没给 `orientation:"h"` 时
  渲染为 1×0 不可见（章节分隔线整批失踪，同片发现并修复：`len=1700, orientation:"h"`）。

## 14. 视觉生产质量复盘（2026-09-16，用户判定：内容 OK，画面 50 分——不达标）

> 用户原话：「视频做的太差了，内容没有问题」。以下症状经成片抽帧确认，全部是"世界级"缺陷，
> 不是单集问题；下次生产必须按新规则执行。

**症状清单**：
1. **空屏过多**：幕间 gap + 元素入场错峰，产生大量"只有 HUD+字幕"的帧（抽帧多次落在空屏，
   观众感受是"卡了/没加载出来"）。自由留白 ≠ 空屏。
2. **容器空壳**：`win` 的设计是"chrome 壳 + 内容元素另叠其上"，本片只画了壳没放内容；
   且 `win kind=browser` 只渲染 `url` 字段（`title` 被忽略）——观众看到一排排空盒子。
   `frame`/`panel` 同理：**容器类零件必须携带可见内容或"标签+数据"**。
3. **清单式排版**：rows/panel/列表堆叠 = 文档/PPT 感；缺"一幕一个视觉主角"的构图与焦点。
4. **动效贫弱**：基本只有淡入/位移，没有"演动词"的编排密度；镜头与转场单调。
5. **节奏失衡**：11 分钟持续高密度清单，没有重点差异与呼吸（重点幕缺视觉升级/华彩）。

**新规则（写入执行纪律）**：
- **先 30–60s 视觉样片定标准，再铺全片**（管线本有此规定，本片被跳过 → 直接返工 2 轮渲染）。
- 每幕开工前过"空盒三问"：① 这幕的视觉主角是什么？② 每个容器里有什么可见内容？
  ③ 把动画全部暂停后，这一帧像不像成品？
- 成片 compose 后必跑**空屏扫描**（≥1s 连续无内容帧计数），数量 > 0 不允许进 render。

## 14b. Registry 视频槽位两个新坑（2026-09-16，console-qwen-27b-stack）

**坑 3 · 槽位 `<video>` 缺 `data-start`（装配器已修复）**：注册表槽位模板里的 `<video>` 之前没有
`data-start`，`hyperframes lint` 报 `media_missing_data_start`，render 直接失败。
装配器现已统一输出 `data-start="0"`（与幕级 footage 同例）。以后新增槽位媒体类型，先跑
`compose` 看 lint，不要等 Worker render 才暴露。

**坑 4 · 槽位名必须与组件声明一致**：`browser-device-stage` 的槽位是
`browser-device-stage-screen` / `-screen-b`（见组件头注释），episode 里写 `slots: {main: …}`
会静默回落到骨架占位图——lint 不报错，snapshot 能看见。教训：`add` 装完后先读
`compositions/components/<name>.html` 头注释的 slot 清单，再写 episode 的 slots 键；
`vars` 也只传组件声明的变量（chrome/title/swap_at/accent/exit），不要自造（如 url）。

**坑 5 · 注册表槽位视频 render 不播放（快照正常、成片冻结白帧）**：`browser-device-stage-screen`
槽位挂自录 mp4，`snapshot` 抽帧正常，但 `render` 成片整幕定格在白色首帧——快照与渲染行为分叉，
snapshot 不能作为视频槽位的验收依据（与 §2 箭头塌缩同类：预览正常≠成片正常）。
已验证的替代路径：改用**幕级 `footage`**（`opencode-repos` 九幕先例，装配器原生支持
`data-start="0"` + 时长对齐），本集 s03 即此方案。结论：**footage 一律走幕级，注册表槽位只挂
静态 img**；若必须用槽位视频，验收方式是整片 render 后抽帧，不接受 snapshot 放行。

## 15. 真实素材截图 + 划线标注实战（2026-10-09，console-local-multimodal-rag）

> 本集为「技术发布解说」题材：真实实体多、依赖官方页面与基准表。用户明确要求
> 「要有项目的截屏 / 能用真实图片就用真实图片 / 最好能用划线的动态」。以下为可复用结论。

**15.1 · 真实截图采集（Playwright）**
- 采集脚本沉淀在 `apps/console-remake/tools/capture/`（`capture_screens.mjs` + `fetch_logos.mjs`；
  Windows 下必须 `executablePath` 指系统 Chrome，双次导航避开首屏白）。品牌 logo 走
  Simple Icons（CC0）→ `cdn.simpleicons.org/<slug>/white`，SVG→256px PNG；`llamacpp`/`mlx`
  等 slug 不存在，**不要用别的品牌顶替**，登记进 manifest 的 `failed` 即可。
- **截图的 provenance 必须写"实际抓到的 URL"**，不是"打算抓的 URL"：本集
  `huggingface.co/google/embeddinggemma` 实际 404，真值是 `…/embeddinggemma-300m`；
  MTEB 榜单在 `huggingface.co/spaces/mteb/leaderboard` 只是 iframe 外壳，真值是
  `mteb-leaderboard.hf.space/benchmark/MTEB(Multilingual, v2)`。发布文案的【素材来源】会照抄，
  写错等于署名造假。
- **截图别整页铺满**：官方页面在 1920×1080 里缩到 30~40% 就只是"有张图"。正确做法是
  **裁到信息区**（本轮用视觉模型先定位表格包围盒 2%~55% × 11%~86%，再用 PIL 裁 896×784），
  卡片尺寸按裁剪后的长宽比给（`cover` 才不会二次裁切）。

**15.2 · 划线标注（用户点名要的"动态划线"）**
- 可用族：`mark` 的 `ul`（下划线从左划到右，`draw_dur`）/ `hl`（高亮扫过）/ `ring`（圈选）/
  `cross`（按框对角线拟合的划叉）；`leader`/`bracket`（stroke-dashoffset 抽出）；
  `hairline tick:true`（尺寸线两端刻度）；`arrow`（抽出）；`text strike + strike_at`（红线划过）。
- 纪律不变：全部用 `at` 锚定到旁白词，**说到那个词的时候线正在画**。本轮实测：5 枚胶囊下方的
  橙色下划线、"文字查询 ↔ 一张照片"之间的大号橙色划叉、基准表的划叉，都在成片抽帧里可见。

**15.3 · `align` 的繁体/数字改写（本轮实测 + 已修）**
- Whisper 对中文常输出繁体（"剛"/"一個"）并把数字改写成阿拉伯数字，导致 `at` 锚词
  **整词匹配命中率只有 32%**（对照 `opencode-repos` 为 50%，属常态而非异常）。
- 已在装配器 `_resolve_at` 增加「最长前缀命中」回退（整词失配 → 退到 `at[:L]` 最长可匹配前缀），
  本集命中率 32% → **65%**；仍失配才落回字符比例估计（原行为不变，向后兼容）。
- 经验：写 `at` 时优先用**句中被真正念出的短语**，避免过长数字串（"七亿四千万"会被念成数字）；
  一个 `at` 若既不在 `line_text` 里、也不在 ASR 词表里（如给图片锚"官方文档"而台词只有"文档"），
  会彻底解析失败（返回 None → 立即入场）——`script` 后建议自查一遍这类锚词。

**15.4 · snapshot 批量上限（会静默出全黑帧）**
- `npx hyperframes snapshot --at` 一次传 **58 个时间戳会全部输出纯 #0C0C0C 空帧**（不报错），
  单点或 10 点一批则完全正常。**大批量 QA 必须分批（≤10/批）**，且 `--output` 目录
  **每批会被清空**，要分批写各自子目录。遇到"全黑帧"先做对照实验（拿已渲染成功的老项目跑同一
  条命令），不要急着改画面。

**15.5 · `image` 零件不支持子目录**
- 装配器按 `Path(src).name` 取**basename**、并从 `assets/images/` 平铺拷贝；`src: "logos/x.png"`
  会判为缺失（警告）且网页路径也对不上。logo 一律平铺命名（`logo_<name>.png`）。

**15.6 · AI 封面底稿要先验"无字"**
- minimax 生图很容易在"控制台/HUD 场景"里画出**伪文字**（一堆看不懂的字母与数字），
  放到封面 B 位就是硬伤。本轮用 `.agents/skills/minimax-m3-vision` 脚本读图验证，
  第一版 4 张全部有伪文字 → 改 prompt 为"**纯抽象材质面**（明确无任何面板/屏幕/标签/符号）"
  后重出的 3 张全部 NONE。**验收标准：视觉模型报 NONE 才可用**。
- `image_selector` 的 provider 偏好键是 `preferred_provider`（不是 `provider`）；不传会按发现顺序
  落到 `google_imagen`（返回 1376×768，忽略 aspect_ratio）。4:3 封面可由 16:9 底稿裁切（纯材质面
  裁切无损语义）。

## 16. 主角尺度律 + 吉祥物贯穿 + 多规格封面（2026-10-09，console-local-multimodal-rag v3）

> 用户评审：「怎么没有放吉祥物」＋「前面画面中的视觉元素都很小，不吸引人看下去」＋
> 「封面也参考 pi-agent-harness-cn」＋「要有不同规格的」。
> 四条已全部写进世界宪法（design-system §11，v2.3），这里只记**可复用操作经验**。

**16.1 · 这个世界原本没有角色，别自己造**
- `console-remake` 的规格里**从来没有吉祥物**；`brand_assets/` 里只有 gitradar 头像 banner。
- 系列角色其实在**别的项目**里并且已跨 6 次实战复用：`projects/pi-agent-harness-cn` 的
  **「小挽」迷你机械小马**（哑光深炭灰 + 荧光绿发光挽具环 + 橙发光鬃尾 + 方形屏幕眼），
  **6 姿态透明 PNG**：`mascot_{land,idle,point,inspect,gate,wave}_crop_alpha.png`。
  做法：**直接拷贝并改名**为 `mascot_<pose>.png`（去掉 `_crop_alpha` 后缀），零成本、视觉连续。
- **先验四角 alpha=0**（`visible_h_ratio` 应 = 1.000，说明已裁到内容边界）；黑底版会在强背景上
  切出一个矩形。本轮 6 张全部 1.000。
- 落地动作照 `projects/onchain-agent-promo/skills/hyperframes-arc-motion-promo.md` §三：
  **跃入(预备) → 过冲 1.06 → 压缩 0.14s → 回落 `back.out(2.2)`**，四段共约 1.04s；
  待机用**有限次 yoyo**（禁 `repeat:-1`），次数由幕长算出。
- **朝向决定机位（视线引导）**：6 姿态里除 `point` 朝右外，其余都是 3/4-朝左。
  → 3/4-朝左的姿态放**右侧**（朝左看内容）；`point` 放**左侧**，若必须放右侧就 `flip:true`。
  本轮实测抽帧确认：左侧的 point 朝右、右侧的 idle/gate 朝左，全部指向内容。
- **别信视觉模型报的尺寸**：它把 320px 的吉祥物报成"~160px"。**用特征色量像素**才对——
  按荧光绿+橙的遮罩量垂直跨度，本轮实测 306/307/346px，与设定相符。

**16.2 · `at` 锚词必须取句中前段**
- 锚在句尾 = 主角在"这句话快说完时"才出现、停留极短（本轮 s12/s17/s20/s24 全部踩到，
  抽帧看到"幕内是空的"）。**统一改成句子前中段的短语**（如"一次输入""文字输入""六十一"）。
- 顺带：`script` 只校验 `at` 是否出现在**本句台词**里；带数字的锚词（"七亿四千万"）会被 ASR
  改写而失配（详见 §15.3）。写完 `at` 建议跑一遍自查：既要在 `line_text` 里，也尽量短。

**16.3 · 主角尺度律的落地自查（可脚本化）**
- 每幕算"最大元素视觉高度"：`bignum = size*1.24`、`text = size*1.35`、`rows = 行数*row_h`、
  `bars = 行数*(bar_h+gap)`、`mascot = h`。**任何一幕 < 200px 就是"清单幕"**，本轮据此抓出
  s09/s15/s17/s20/s23/s24 六幕并逐幕补了主角（+0.2 / -13.5 / 巨型 NaN / 8 组前缀 / 1 个向量）。
- 补主角优先用**该句真正在讲的数字**（"基本没动"配 `+0.2`、"跳水"配 `-13.5`），
  而不是随便加个装饰件——否则违反 §10.6 语义一致性纪律。

**16.4 · 多规格封面（程序化合成，别再走 AI 底图）**
- 系列真做法见 `projects/pi-agent-harness-cn`：**PIL 程序化合成**（网格底 + 大字 + 小挽姿态 +
  四角角标），零生图。本轮已固化为 `apps/console-remake/template/make_cover_series.py`，
  **一次出 7 个规格**（1920×1080 / 1280×720 / 1146×717 / 1440×1080 / 1080×1080 / 1080×1440 / 1080×1920）。
- 两个必踩的坑（本轮实测）：
  1. **Cascadia Mono 画中文 = 整行方框**（LESSONS #12/#38 第三次复发）。混排行必须**逐段换字体**
     （`_runs()` 切段 → CJK 走 Noto、其余走 Cascadia）；URL/meta 行是最容易漏的地方。
  2. **竖版/方版吉祥物踩住页脚**。正确顺序：先算 URL/meta 的 `footer_top` → 吉祥物
     `my = footer_top - mh`，并把 `mh` 夹在"副题底 ~ footer_top"之间。
- 验收：**视觉模型逐规格读一遍**——要求"零方框、零出框、吉祥物不压字、主标题缩略图可读"。
  本轮第一版 7 张全部有方框（meta 行）＋2 张竖版压字，修完复验通过。
- 归档：`archive` 原本只拷 `cover_16x9/4x3/cover_frame`，已改为**归档全部 `cover*.png`**。

### 16.5 · 封面 v2 三个真坑（2026-10-09 用户二次反馈「B站模板有压字 / 吉祥物也很小 / 背景全黑」）

1. **"压字"的根因是 PIL 的绘制原点在 ascender**：`draw.text((x,y))` 的墨迹范围是
   `[y+bbox[1], y+bbox[3]]`，**`bbox[3]-bbox[1]` 是墨迹高度、不是墨迹底边**。
   用"高度"推进下一行 → 下一行会压进上一行的下半部分（Noto CJK 的 `bbox[1]` 常有 0.2em 量级，
   所以偏差正好是一两行的下缘）。**推进一律用 `ink_bottom() = bbox[3]`**，并留 3~4.4%H 行距。
   这条对任何 PIL 排版都成立，不限封面。
2. **"吉祥物很小"的根因是横版也套用了"给页脚让位"的夹取**：竖版的吉祥物在文字块下方、必须
   夹到 `footer_top` 之间；横版/方版的吉祥物在**右列通高**，只受"右列宽 + 边距"约束。
   混用会把 1146×717 的吉祥物夹成 **65px**（占画面高 6%）。
   正确做法：按 `tall = H/W >= 1.2` 分模式；横版 `mh = min(0.72H, H-2m, col_w/ar)`，
   `mx = W - m - mh*ar`；修完实测 68~80% 画面高。
3. **"背景全黑"的根因是暗角用了整幅 composite**：把近黑底连网格一起压掉了。
   改为 numpy 径向、`edge = clip((r-0.62)/0.60,0,1)**1.6` 只压边缘；同时把网格提到 7%（带一点系列绿）、
   交点 12.5%、加 4px 扫描线 2.8%、加**巨型底纹数字**（0.52H、亮度 8.5%、右下压边）。
   修完实测 mean luma 27~32、`pct>25` 33~47%（原来几乎是纯黑）。

### 16.6 · 归档 metadata 的硬编码署名（严重事实错误，已修）

- **症状**：本项目归档的 `metadata.json` 里写着
  `"credit": "改编自 Kai《Agent Harness explained in 8min..》"`——**是第一个 console 项目
  （console-agent-harness）的署名**，从没改过；`ai_disclosure` 也是那句不含吉祥物与封面的旧文案。
- **根因**：`stage_archive` 把署名/AI 声明**硬编码成了初版项目的值**，后续每个项目都会继承，
  属"署名造假"级别的问题（比画面缺陷严重：它对外声明了错误的原作者）。
- **修法**：`metadata.json` 的 `ai_disclosure` / `credit` 一律**从本项目的
  `artifacts/publish_copy.json` 读取**，缺失时才回落到由 `episode.source` 拼出的通用句式；
  同时把 `covers`（封面清单）写进 metadata。
- **纪律**：**归档/发布类字段禁止硬编码**。凡是"对外声明"的内容（署名、来源、AI 声明、素材出处）
  都必须从本项目的创作契约里取；新增归档字段时先问一句"这个值是不是上个项目的残留？"。
- 顺带：`archive` 现在归档**全部 `cover*.png`**（原来只拷 16x9/4x3/cover_frame）。

## 17. 下次开工清单（照抄即可）

### 17.1 开工（动笔前）
- [ ] 拷系列资产：小挽 6 姿态（改名 `mascot_<pose>.png`）+ `NotoSansSC-Black.ttf` / `CascadiaMono.ttf`；
      **验 `visible_h_ratio == 1.000` 且四角 alpha = 0**
- [ ] 列全片**真实实体清单**（人/产品/项目/界面/地点）→ 按 SKILL §9 路由表采集 + 登记 provenance
      （截图先定位再裁到信息区；别整页缩小成"有张图"）
- [ ] 能力侦察四连 → `artifacts/capability_recon.json`（每条 mapping 写"这幕为什么需要它"）
- [ ] 读 `projects/onchain-agent-promo/skills/hyperframes-arc-motion-promo.md`（角色贯穿 / 三层密度 / 句级时间表）

### 17.2 写作（episode.json）
- [ ] 分批写入；每幕过**空盒三问**（视觉主角是什么 / 容器里有什么 / 暂停动画后像素不像成品）
- [ ] 每幕过**主角尺度自查**（最大元素视觉高度 ≥ 200px），< 200px 的幕必须补主角
- [ ] 规划 **8~13 个角色 beat**：相邻**机位与姿态不同**；3/4-朝左放右侧、`point` 放左侧或镜像
- [ ] `at` 锚词：出现在 `line_text` 里、**取句中前段**、避开会被 ASR 改写的长数字串
- [ ] 划线标注（`mark` ul/hl/ring/cross、`leader`、`bracket`、`hairline tick`、`strike`）都挂 `at`

### 17.3 重活分工
- [ ] 派 Compute Worker：`synth --json` → `align`（单行 JSON 回报）
- [ ] 主 Agent 自己 `compose`（轻）→ `hyperframes lint` → 抽帧目检
- [ ] 小改动用**子集循环**：`compose --scenes sNN,sMM` + `render`（分钟级）验证后再全片 compose + 派 Worker render
- [ ] 再派 Worker：`render --json` → `package`

### 17.4 交付前 13 门（一门都不能跳）
1. `script` → **0 warning** 且 `redline` = pass
2. **主角尺度**：没有任何一幕的最大元素 < 200px
3. **`at` 自查**：全部命中本句 `line_text`，且无长数字串锚词
4. `capability_recon.json` 存在，mapping 逐条有理由
5. `compose` → 0 warning、`images_missing` 为空
6. `npx hyperframes lint` → **0 error 0 warning**
7. **空屏扫描**：58 帧左右采样，无"HUD + 字幕条"帧
8. **吉祥物 beat 像素验收**：特征色（荧光绿 `G>200 & B<90`）在每个 beat 都能定位到，且**朝向内容**
9. **成片抽帧**：真实截图、连接件、划线、吉祥物在 render 后都在（不信快照）
10. **音频**：逐句 ≥ 0.2s；成片 ≈ **−16 LUFS**、TP ≤ −1 dB、无 > 1.5 s 意外空档
11. **封面 7 规格**：逐张过"零方框 / 零出框 / 文字互不压 / 吉祥物 ≥ 45% 画高 / 背景 textured"
12. **metadata 署名与 AI 声明**来自本项目 `publish_copy.json`（不是上个项目的残留）
13. `archive` 完整：成片 + 全部 `cover*.png` + 4 份 metadata + 自述 README

### 17.5 复盘纪律
- 用户的设计类反馈（"元素小 / 没角色 / 封面压字"）一律**提炼进世界宪法**（design-system）
  或本文件，**不写单集补丁**；同一条反馈只改一次。
- 跨管线通病（Cascadia 画中文、layout 豁免不继承、`data-color-grading` 挂死、组件时长截断）
  修完回写到 SKILL.md + 本文件，让下一个 agent 不必重踩。

---

## 18. console-opencode-20 实战（2026-10-15）—— 五个"世界级"坑 + 一次注册表组件判否

> 本轮首次接入 `agent-cursor` / `notification-stack`，首次把 `hyperframes check` 的
> Runtime / Motion / Contrast 三段都用起来。以下每条都不是单集补丁，已修在管线/模板层。

### 18.1 `bracket` 括线的坐标字段是 `x1/y1/x2/y2`（不是 `y`）

- **症状**：`check` 的 Runtime 段报 `<path> attribute d: Expected number, "M272 undefinedL760 un…"`，画面里括线整条消失（s03/s08 各一处）。
- **根因**：`buildConnector()` 对 bracket 取 `p1={x:e.x1, y:e.y1}`、`p2={x:e.x2, y:e.y2 ?? e.y}`；只写 `y` 时 `p1.y` = undefined。
- **修法**：bracket 一律写全 `x1,y1,x2,y2`（y1===y2 即横括线）。
- **纪律**：连接件三者字段不同（arrow 用 `from/to` 或四点；bracket 必须四点；leader 用 `from/to` + `tick`）。写完跑 `check` 的 **Runtime** 段验证，不要只看 Lint。

### 18.2 `rows` 必须给 `w`，否则文字逐字竖排

- **症状**：rows 面板里"上下文用量 / 已花费 / 待办清单"等行被压成**竖条**（s17/s19/s22/s24/s25 共 7 处）。
- **根因**：`buildRows()` 用 `px(e.w)` 设宽；只给 x/y 时 `width:0` → 中文逐字换行（与 §13.1 toast 同源的"静默奇观"）。
- **修法**：rows 一律给 `w`（本轮统一 700~824）。
- **自查**：所有容器类零件（toast / rows / paper / panel / win / term）必须有宽或高。

### 18.3 `bignum` 的 `x` 决定"可用宽度"——x 太大会换行

- **症状**：`1000+` 渲染成 `1000` 一行、`+` 掉到下一行；`214K` 同理（s16/s20）。
- **根因**：bignum 用 `left:x` + `translate(-50%,-50%)` 且**无 width**；绝对定位元素 auto 宽度受"从 left 到容器右边"的约束 → 可用宽度 ≈ 1920−x。x=1408 时仅 512px，装不下 240px 字号 × 4 字符。
- **修法**：大字号 bignum 的 `x ≤ 1320`（可用 ≥600px）；估算式 `字数 × size × 0.6 + 60 ≤ 1920 − x`。
- **顺带**：`1000+` / `214K` 会被正则拆成 `val` + `suffix`（上标小字），是**预期行为**，不是 bug。

### 18.4 `frame` 是空心框，但框里必须有内容

- **症状**：s06/s15/s21 的对比框（旧 vs 新、串行 vs 脚本、Plan vs Build）全是**空盒子**（§14.2「容器空壳」复发，且 check 看不出来）。
- **修法**：每个 frame 至少配一条框内 `text`（如"关窗 = 任务终止"/"一段脚本 → 一次取回"/"只看不动 · 先讲清楚"）。
- **纪律**：凡容器（frame/panel/win/rows）必须携带可见内容；抽帧时暂停动画自问"这一帧像不像成品"。

### 18.5 `agent-cursor` 注册表组件在本管线宿主契约下不渲染（附可复用诊断）

- **症状**：s11 整幕（17s）snapshot **全程空屏**（mean_luma 14~15、bright_ratio 0.006~0.015，只有 HUD+字幕），4 个时间点（189.5/192.5/199.5/202.5s）无一帧有内容。
- **诊断三步**：① 该幕抽 4~5 个时间点；② PIL 统计 `mean_luma` 与 `bright_ratio`；③ **同批次另一个注册表组件作对照**（本轮 `notification-stack` 正常）→ 排除"幕/时间轴"问题，锁定组件。
- **根因假设**：该组件走 `tl.to(clock,…).onUpdate(render)` **手动渲染**模式，并用 `root.clientWidth` 取尺寸；在本管线的子合成宿主结构下拿不到有效尺寸/未触发 onUpdate，停在 `render(0)`（元素 opacity 0）。
- **处置**：s11 改用 console 零件（text + term + rows + toast），语义不变；`capability_recon.json` 的 `adopted` 移除该组件并写明判否理由。
- **纪律**：**注册表组件接入后必须抽帧验收**——`add` 成功、lint 通过、文档描述都不构成可用证据。已验证可用：`browser-device-stage`（s05，槽位挂真实截图 + swap）、`notification-stack`（s13）。

### 18.6 世界级小修：HUD 分隔符对比度（a11y）

- `check` 的 Contrast 段报 `#hud-brand .hb-sep` / `#hud-chapter .hb-sep`（中点 "·"）对比度 2.21:1 < WCAG AA 4.5:1（每章出现一次）。
- 修法：`template/console.css` 的 `.hb-sep` 由 `rgba(255,255,255,0.25)` → `0.5`（**已修在模板层，后续项目自动继承**）；修后 62/62 文本检查全过。
- **纪律**：`check` 的 **Runtime / Motion / Contrast 三段都要看**；"Lint 0 error"不等于"可以渲染"。

### 18.7 快照环境的僵尸进程（snapshot 卡住的头号原因）

- 一次 `snapshot` 被外部中断后，留下一批**挂起的 node/browser 进程**；此后所有 snapshot 表现为"命令在跑、目录为空、10+ 分钟不产帧"。
- 处置：按启动时间过滤清理（`Get-Process node | Where-Object StartTime -gt <cut> | Stop-Process -Force`，保留 OpenCode 自身进程），清理后 snapshot 立刻恢复正常。
- **纪律**：snapshot 异常先查残留进程，再怀疑画面；清理时**按启动时间**筛，不要 `-Name node` 一把梭（会杀掉 agent 自己的进程）。

### 18.8 本轮新增可复用素材路径（真实素材，零生图）

- **官方演示录像**：`opencode.ai` 首页 hero 的 `<video src="/_build/assets/opencode-min-*.mp4">`（1920×1080/60fps，36.5s）——**官网 hero 常内嵌官方产品录屏**，是比截图更硬的素材来源，值得作为通用套路（先 parse 首页 HTML 找 `<video>`，再 curl 下载）。
- **多规格封面**：`make_cover_series.py` 一次 7 规格，本轮参数备忘 —— `--hero "关窗不再终止"`、`--mascot .../mascot_gate.png --mascot-aspect 0.7357`、`--watermark "2.0"`；横版与竖版验收均通过（吉祥物占 45%~75% 画高、零方框、文字不互压）。
- **系列资产复用**：小挽 6 姿态从 `projects/pi-agent-harness-cn/assets/images/mascot_*_crop_alpha.png` 直接拷贝改名（四角 alpha=0、visible_h_ratio=1.000 全部通过），第 7 次复用。




