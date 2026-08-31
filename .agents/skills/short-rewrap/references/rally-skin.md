# 可选"赛车皮肤" (Rally / Racing Skin)

通用四段式增强模板之上，叠加这层，即可做出赛车/拉力题材专属的效果。
WRC 官方主色：**红 `#E0283D` + 黑 + 白 + 黄 `#FFD200`**。

---

## ⚠️ 准确性红线（必读，先于一切文案）

1. **先确认赛季/车型代际，再写动力/组别/混动值。** 动力数字、混动与否是**按赛季变化**的事实，不是恒定规格：

   | 赛季 | WRC Rally1 动力形态 | 混动？ |
   |------|--------------------|--------|
   | 2022–2024 | 混动，额定 ~500 匹（综合） | **混动** |
   | 2025 起 | 纯内燃（混动已移除） | **无** |
   | 2027 起 | 全新规则 / 新代际赛车 | — |

   ⚠️ 本参考片经**官方视频确认属于 2026 赛季** → **无混动·纯内燃**。不要再写"混动/500"。具体马力数值以权威规格表为准，没核实就别写死数字。

2. **赛季来源以"官方/权威"为准，画面贴纸只能作弱证据，甚至可能误导。** 本片尾帧有 `NIEULA FOREST 2024` 贴纸，曾据此推断 2024 → 被官方视频推翻（实为 2026）。**装饰/致敬性贴纸并不能代表车型年份**。判断赛季优先看：官方发布、次看一致性较强的画面线索，贴纸存疑时**必须由官方确认**。

3. **车手/车队/车型若无法证实，不要硬填。** 本参考片画面能证实的是：车牌 `OC-4491`、车号在尘土/近景下**多次读图结果不一致(曾读到 17/18/13)**、赞助商贴纸 DENSO/TAMADIC/CCI/FORUM8/Panasonic Automotive、TOYOTA GAZOO Racing。**2026 丰田厂队名单 = Solberg/Ogier/Evans/Katsuta/Pajari**；本片车手经用户确认为 **Takamoto Katsuta(胜田贵元)** → 按此填。换任何视频/换人不经确认不得照搬，必须重新核实。

> 判断依据：**画面能证实的写，推测的一律不写**。宁可信息少一条，绝不写一条错的。

---

## 1. 配色（覆盖 `:root`）

```css
:root {
  --accent: #E0283D;   /* WRC 标志红 */
  --accent2: #FFD200;  /* 拉力黄 */
  --panel: rgba(23,8,11,.92);  /* 红黑深色卡片 */
}
```

- 主标题/车型名/资料卡边框/结尾"拉力虎"＝ 红 `#E0283D`
- 倒计时数字、揭晓 RALLY1、资料卡标签＝ 黄 `#FFD200`
- 白字 + 黑描边 + 深投影 保证可读（**不用 `-webkit-text-stroke`**，用 `NotoSansSC-Black`(900) + 多层投影 + 强调色塑形）

## 1b. 中文字体用极粗黑体（推荐）

中文标题要够"冲/赛博感"，用项目字库的 `NotoSansSC-Black`（思源黑体 Black，900）：

```css
@font-face { font-family: 'NotoSansSC'; src: url('assets/shared_library/fonts/NotoSansSC-Black.ttf'); font-weight: 900; font-display: block; }
```

再配合 `transform: scaleX(0.78)` 横向压扁，得到接近英文 `Archivo Black` 的"浓缩粗体"观感。
（路径根相对 `assets/...`，不要用 `../`。⚠️ 若仅在 `public/` 内渲染而字库在仓库根 `assets/shared_library/`，必须从**仓库根**跑 hyperframes，否则该字体加载失败——见 HOWTO。）

## 2. 车型揭晓（Reveal）——可选加"性能副注"

腾空/高光时刻打出车辆身份，用 `Archivo Black` 冲击字：
```
答案是 ——
TOYOTA
GR YARIS        ← 常用红 (.sub)
RALLY1          ← 黄 (class)
腾空的秘密：轻量化车身 + 涡轮爆发   ← 性能副注 (#reveal-note)，"看腾空→懂原理"
```
- **性能副注**把高光时刻绑定"懂背后原理"，是本皮肤推荐的叙事增强（见 copywriting §2）。
- **动力机制表述依赛季核对**：2022–2024 写"混动"，2025 起写"纯内燃·轻量化"。本参考片官方确认 2026 → 写"涡轮爆发"，**别写混动爆发**。
- 车型名要**避开车身赞助商文字/水印**（DENSO、TAMADIC、TOYOTA GAZOO 贴纸）。揭晓字集中放画面中下部的干净区（路面/尘雾），别盖住车身。

## 2b. 副注层（Annotation）— 信息增量

半透明一行小字，在高光动作/赛段瞬间短暂弹出 3–5s 后淡出，不遮主体：
- 赛道：`WRC 芬兰站 · 经典飞跳 ｜ 落差 3 米`
- 动作：`重刹降挡 + 锁止差速器 · 零失误漂移过弯`
> 一句话一个信息点。赛段/站名（如"芬兰站""蒙特卡洛站"）以**画面能证实的**为准（本片=芬兰站，据芬兰国旗 + NIEULA/芬兰）。

## 2c. 过渡（Transition）— 揭晓 → 资料卡

`腾空的秘密，藏在这台车里` / `这么猛，凭什么？往下看`，1.5–2s，自然引出资料卡。

## 3. 资料卡（Info Card）

标题建议用中性词：**「赛车档案」「车辆档案」「RALLY1 档案」**。

默认行（可删改，**值依画面/官方核实**）：
| 标签(黄) | 值(白) |
|---|---|
| 车型 | Toyota GR Yaris Rally1 |
| 车队 | TOYOTA GAZOO Racing |
| 车手 | Takamoto Katsuta（胜田贵元 · 日本）|
| 赛道 | 待确认（原疑芬兰站，因贴纸/旗帜——但赛季已官方改为 2026，赛站以官方确认） |
| 组别 | WRC Rally1 |
| 动力 | 1.6L 涡轮 · 约 380 匹（纯内燃，2026 无混动；待官方规格确认） |
| 驱动 | 四驱 · 序列式变速 |

- 动力一栏可用**数字动效**：`<span id="hp-count">0</span>` 配合 GSAP 0→N 递增。⚠️ 本片官方确认 2026 → **约 380 匹**（去混动 Rally1 业内常用值），但仍标"待官方规格确认"；勿按旧混动填 500。
- 资料要**核实准确**，不确定的数据不要编；有分歧时宁缺毋滥。

### 换车时怎么填（示例占位）
车型/年款、车队/厂队、车手、组别/级别、马力、燃料/混动、部分关键成绩——**每一项都要有画面或可信来源支撑**。

## 4. 结尾 CTA（上半屏）——呼应开头 + 埋伏笔

```
你猜对了吗？
这台能飞的 <GR Yaris>
下次看它的过弯神技 !          ← 预告下集，强化系列感
```
- 第 1 行呼应开头的竞猜设定 → 单条叙事有始有终。
- 最后一行为伏笔/系列感，或用"请关注 拉力虎 !"（"拉力虎"和"!"用 WRC 红）。
- CTA 必须 **上半屏**（`top:12%` 起步），避开抖音/短视频底部 UI。

## 5. 动效基调

- 大量 **斜切 `skewX(-6°~-8°)`**（速度感）。
- 数字用 `Archivo Black` + 硬投影（冲击）；动力用 GSAP count-up（0→N）。
- **不用 `-webkit-text-stroke` 描边**：中文用 `NotoSansSC-Black`(900) + 多层投影 + 强调色（WRC 红/黄）塑形。
- 钩子/揭晓用 `back.out` 回弹入场，倒计时逐字替换。
- 副注 chip 淡入淡出 3–5s；过渡句沿运动向量滑入（`x:-40, skewX:-14`）+ 淡出。

### velocity 速度残影揭晓动效（揭晓段标准动画，已在 `template-4act.html` 内置，已验证可渲染）

把高光"大词"（车型名/答案词）沿运动向量擦入，带模糊强调色**速度残影**尾迹 + 停稳后 **loom** 推近。三段式：

> ⚠️ **选择器一致性红线**：GSAP 里所有子元素选择器必须能匹配到真实元素（`card-host` 的 `id` 与该 id 前缀一致）。若 `id="hook-card"` 却写 `#card-hook`，GSAP 找不到元素 → 该段**动画静默失效**（倒计时不会逐字递减、残影不出现），且不会报错。**这是本次踩过的坑，务必先核对 id。**
> ⚠️ 残影要精确叠在主词上，**把 `#reveal-model-echo` 放进 `#reveal-model` 内部、`inset:0`**（勿做兄弟节点定位——那会错位到片头/别处）。

**1) HTML —— 主词内嵌一个同文残影副本（`inset:0` 精确叠层）：**
```html
<div id="reveal-model" style="margin-top:24px;">TOYOTA<br/><span class="sub">GR&nbsp;YARIS</span>
  <div id="reveal-model-echo" aria-hidden="true">TOYOTA<br/><span class="sub">GR&nbsp;YARIS</span></div>
</div>
```

**2) CSS —— 主词 `position:relative`；残影绝对定位 `inset:0` 叠后、模糊强调色：**
```css
#reveal-model { position:relative; font-family:"Archivo Black","Oswald",sans-serif; font-size:104px; color:#fff;
  transform:skewX(-6deg); filter:drop-shadow(0 5px 0 rgba(0,0,0,.55)) drop-shadow(0 12px 22px rgba(0,0,0,.55)); }
#reveal-model-echo { position:absolute; inset:0; font-family:"Archivo Black",sans-serif;
  font-size:104px; color:var(--accent); opacity:0; -webkit-text-fill-color:var(--accent);
  filter:blur(16px); transform:skewX(-6deg) translateX(-14px); pointer-events:none; }
```

**3) GSAP 时间线（揭晓段）—— 选择器必须用 `#<card-host-id> #<子元素>`：**
```js
tl.from('#reveal-card #reveal-kicker',{opacity:0,y:-30,duration:0.4,ease:"power2.out"}, q(5.0));
// ① 主词沿运动向量擦入：x 负→0 + 斜切回正 + 动感模糊→清晰
tl.fromTo('#reveal-card #reveal-model',
  {opacity:0, x:-160, skewX:-18, filter:"blur(14px)", transformOrigin:"left center"},
  {opacity:1, x:0, skewX:-6, filter:"blur(0px)", duration:0.55, ease:"power4.out"}, q(5.08));
// ② 残影：模糊强调色副本更超前滑（x:-260），落地时 opacity 收敛到 0
tl.fromTo('#reveal-card #reveal-model-echo',
  {opacity:0, x:-260, skewX:-22, filter:"blur(20px)"},
  {opacity:0.9, x:-30, skewX:-8, filter:"blur(14px)", duration:0.42, ease:"power2.out"}, q(5.05));
tl.to('#reveal-card #reveal-model-echo',{opacity:0, x:6, filter:"blur(2px)", duration:0.28, ease:"power2.in"}, q(5.45));
// ③ loom：停稳后停留期 scale 1→1.06 推近放大再回正
tl.fromTo('#reveal-card #reveal-model',{scale:1},{scale:1.06,duration:0.4,ease:"power2.out"}, q(5.7));
tl.to('#reveal-card #reveal-model',{scale:1,duration:0.4,ease:"power2.inOut"}, q(6.1));
// ④ 揭晓整体淡出
tl.to('.card-host[data-card-id="card-reveal"]',{opacity:0,duration:0.18,ease:"power2.in"}, q(8.15));
tl.set('.card-host[data-card-id="card-reveal"]',{visibility:"hidden"},8.40);
```

> 要点：残影用 `.sub` 次强调色（如拉力黄）；残影只给高光"那一个词"，正文保持简洁。完整可跑实例见 `videos/template-check/index.html`（修复版：倒计时 + velocity 残影已验证）、`videos/wrc-test2/public/index.html`（Neuville 版，残影用 `top:18px` 兄弟定位的旧写法）。

## 6. 参考成品

- 项目：`videos/wrc-hook-recut/`（基线四段式）、`videos/rewrap-test-v2/`（GR Yaris 增强版：副注/过渡/数字动效/呼应CTA，已验证 render PASS）、`videos/wrc-test2/`（Neuville/Hyundai 增强版：**含 velocity 速度残影揭晓动画**，已验证 render PASS）
- 最终组合 HTML（增强版实例）：`videos/rewrap-test-v2/index.html`、`videos/wrc-test2/public/index.html`；通用模板：`references/template-4act.html`（已内置 velocity 揭晓动画）
