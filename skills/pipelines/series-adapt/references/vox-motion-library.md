# Vox Motion Library — 动效层参考库（series-adapt）

动效词表与 GSAP 实现清单：为 series-adapt 单集的 HyperFrames/GSAP 动效提供可执行规范。
与 `vox-story-library.md`（叙事层）、`vox-look-library.md`（视觉层）配套使用。
由 `scene-director.md`（camera_move 选型）与 `compose-director.md`（GSAP 实现）引用。

> 来源：提炼自 vox-director（Alisa0808/vox-director, MIT）的 `references/beat-layer.md` 与
> `references/local-engine.md`。其本地关键帧引擎（逐元素飞入组装）与我们 HyperFrames 路线
> 同构，经验直接翻译为 GSAP 写法；其 AI 视频模型 5 轴提示结构不采用。

## 0. 核心原则

> **动效的能量来自元素运动（element_motion），不是相机运动。**
> 一个静止大图配 1.07× 推近是"移动的 PPT"；多个纸片同时动才是"活的拼贴"。

- 相机与元素是两个独立轴：一个相机运动（camera_move）+ 尽可能多的元素运动。
- **刚性纸片边界**：剪贴片只能 slide / flap / pivot / scatter——禁止 morph / warp /
  vortex / explode 等有机形变（实测唯一会翻车的三种写法）。
- 相邻场景运动族必须轮换（scale ↔ translate ↔ opacity），`static` 只留给高光/收尾节拍。

## 1. camera_move 硬约束词表（每场景选 1 个）

词表 = 整图在场景持续期内的运动。**相邻场景不得重复；`static` 保留给高光节拍**。

| ✅ safe（token） | GSAP 实现 | 用途 |
|---|---|---|
| `static` | 无整图 transform，仅元素微浮动 | 让引语/数据落地 |
| `push_in` | `gsap.to(img, {scale:1.07, duration:scene_dur, ease:'power1.out'})` | 张力/聚焦 |
| `pull_out` | `gsap.from(img, {scale:1.1}, ...)` 反向 | 揭示全貌/收尾 |
| `pan` | `translateX` 于超宽图 | 读时间线/列表 |
| `tilt` | `translateY` | 揭示规模/计数 |
| `parallax` | 前景/中景/背景层不同速度 | "活纸"签名动作 |
| `element` | 整图静止，单元素滑入/铰链入 | 引入/强调单个物件 |

**🚫 banned**（破坏 flat 纸感，与场景窗口/字幕锁定冲突）：`orbit` `dolly_zoom` `roll` `whip` `handheld` `fast_zoom`。
GSAP 物理上能做这些，但它们是"3D 感"运动，违背拼贴的平直语言；需要强冲击时用"快切"而非"甩镜"。

**时间线弧的移动方向规则**（叙事层 `timeline` 弧配套）：
同方向连续平移 = 时间流动感（如每段地图场景都向右 pan）；转折点用 `push_in`；收尾感悟用 `pull_out`。

## 2. element_motion 能量引擎（每场景必填，≥2 元素同时动）

元素运动 = 场景内各剪贴片各自的运动。**这是动效能量的真正来源，禁止只动一个元素。**

| 规则 | 说明 |
|---|---|
| 数量 | **每场景 ≥2 个元素同时运动**（多元素漂移/摆动/散落/脉冲） |
| 安全动词 | drift · sway · ripple · flutter · slide · pivot（刚性）· bob · pulse · shimmer · settle · 层间 parallax |
| 禁止动词 | morph · warp · vortex · explode（有机融化、body-horror） |
| 景别门控 | WIDE → 多元素同时动；CLOSE/DETAIL → 该单一元素强动（其余微动） |
| 文字保护 | 内嵌标签所在的纸片只能整体平移/缩放，禁止逐字或弯曲变形 |
| 落地即停 | 元素 settle 后静止，只保留微呼吸（paper corner lift、halftone shimmer）——"stop-motion 定格"是纸拼贴的节奏感 |

**hero 飞行元素**（全片能量峰值）：
- 一个跨全场飞行的 hero 元素（纸鸟/炮弹/徽章/箭头），落在叙事层的"高光节拍"上
- **规则：全片 ≤2 处，且只出现在高光节拍**——每帧都飞会读作公式
- GSAP 实现：`gsap.fromTo(el, {x:-300, rotate:-15}, {x:600, rotate:10, duration:2.5, ease:'power1.inOut'})`，飞行轨迹略弧线（叠加 y 正弦），落地后 `power3.out` 微过冲

## 3. GSAP 纸感动效清单（入场/落地，来自 local-engine 翻译）

vox-director 本地关键帧引擎的四个入场手感 + 两个防翻车经验，直接翻译为 GSAP：

| 手感 | GSAP 实现 | 备注 |
|---|---|---|
| `fly_in`（屏外飞入+过冲） | `gsap.from(el, {x:-600, rotation:-12, ease:'back.out(1.7)', duration:0.9})` | 纸片飞入落地时的"啪"感 |
| `slap`（放大→硬拍） | `gsap.from(el, {scale:1.3, ease:'power3.in', duration:0.25})` | 印章/标签拍上纸面 |
| `drop`（下落+弹跳） | `gsap.from(el, {y:-260, ease:'bounce.out', duration:1.1})` | 物件坠到台面 |
| `pop_settle`（原地聚焦） | `gsap.from(el, {scale:1.35, autoAlpha:0, ease:'power3.out', duration:0.7})` | **原地放大落位，无屏外行程**——唯一不产生 ghost 重影的"出现"方式 |
| `stamp-appear`（顺序盖章） | 多个元素 `scale:1.25→1 + autoAlpha` 顺序 stagger 0.08s | 标题卡/数据卡 |

**防 ghost 重影经验**（local-engine 实测）：
1. 元素飞入前，其落位区域在背景上会露出"副本"——**对该区域施加高斯模糊**（`filter: blur(6px)` 的占位块），元素飞入落地后模糊块隐藏。模糊保留亮度与颜色，不会像压暗/提亮那样露出补丁。
2. `back` 缓动在 scale 上会过冲低于 1.0 露出副本——**scale 落位一律用 `power3.out` 或 `back.out` 时目标必须 ≥ 当前值且无背景副本**。
3. 组装结果必须还原原海报：元素落回**原始位置**（bbox 中心 × 画布缩放），画布宽高比与海报一致——"组装后的画面 == 原海报"是验收线。

## 4. 反单调规则（质量最大杠杆）

- 相邻场景 camera_move 不重复（§1 词表轮换）
- 相邻场景入场动效族不重复：scale 族（scale-in/slap/pop_settle）↔ translate 族（drop-in/fly_in/poster-rise）↔ opacity 族（stamp-appear/vignette-in）轮换
- `static` + `pop_settle` 的组合保留给高光/收尾节拍——动效骤停本身是"这里就是重点"的信号
- 每 4–7s 至少一个视觉事件（元素入场/图表更新/子镜头切换）——长场景内部也要有节奏，不能全场景只推一次

## 5. 与既有 compose 规范的衔接

- 本库补充 `compose-director.md` 的 Step 2 动画调色板：场景的 `animation_type` 决定入场手感（§3），
  新增 `camera_move`（§1）与 `element_motion`（§2）字段进入 scene_plan
- `highlight: true` 场景获得 hero 飞行元素与动效峰值配额（全片 ≤2）
- 既有规则不变：cross-dissolve 过渡、场景窗口跟随 voice boundaries、paper SFX 落位触发、字幕 karaoke 锁定

## 6. 词表（copy-paste）

```
MOVES: static push_in pull_out pan tilt parallax element   (BANNED: orbit dolly_zoom roll whip handheld fast_zoom)
ELEM:  drift sway ripple flutter slide pivot bob pulse shimmer settle parallax   (BANNED: morph warp vortex explode)
ENTRY: fly_in slap drop pop_settle stamp-appear
RULE:  ≥2 元素同动 · 相邻不重复 · static 留给高光 · hero 飞行 ≤2 处 · 落地即停 · 刚性纸片
```
