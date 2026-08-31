# short-rewrap 竖屏短视频「四段式」二创 · 使用与经验文档

> 面向想用 OpenMontage 把一条**已有的竖屏高光视频**重包装成"竞猜钩子 → 揭晓 → 资料卡 → 结尾关注"成片的制作。
> 只做**画面叠加图层**（原视频原样播放、保留原音轨），用 HyperFrames 组合渲染，输出 1080×1920 竖屏 MP4。

---

## 0. 定位与适用

- **适用**：任何有高光瞬间的竖屏短（赛车腾空、魔术、烹饪、游戏操作、探店名场面等），需要"悬念+信息+引导关注"。
- **不适用**（走别的流程）：
  - 制作**全新合成**视频 → Universal Harness `bin/omo.py`（AGENTS.md 红线：禁止手动 ad-hoc 生成资产）。
  - 只加字幕/配音 → `chinese-subtitle` / `auto-dub`。
  - 纯剪辑/转场/压缩 → `video-edit` + ffmpeg。
  - 生成全新 AI 视频 → `ai-video-gen` / `avatar-video`。

> ⚠️ 本 skill 针对**已有文件、纯 overlay 叠加**，是编辑性组合，不替代生成管线。

---

## 1. 四段式核心结构（约 17s）

| 段 | 建议时间 | 作用 | 赛车例 |
|----|---------|------|--------|
| 1. 钩子 Hook | 0–4s | 悬念留人 + 倒计时 3·2·1 | 竞猜时间 / 来的是什么？/ 它能突破地心引力？ |
| 2. 揭晓 Reveal | ~4.8–8s | **velocity 残影动画**打出"答案" | 答案是—— / TOYOTA / GR YARIS / RALLY1 |
| 3. 信息卡 Info | ~9–14s | 叠数据卡 | 赛车档案（车型/车队/车手/组别/动力） |
| 4. 结尾 CTA | ~14.5–17s | 上半屏引导关注 | 你猜对了吗？/ 这胎会飞的 GR Yaris / 下次看它的过弯神技！ |

---

## 2. 增强层（信息增量 + 叙事感）——均已内置模板

1. **揭晓 velocity 速度残影动画（标准揭晓动效）**：答案词沿运动向量擦入 + 模糊强调色残影尾迹先超前滑再收敛 + 停稳 loom 推近。配方见 §4。
2. **揭晓性能副注 `#reveal-note`**：高光词下方一行"懂原理"（`腾空的秘密：轻量化 + 涡轮爆发`），把"看腾空"升级为"懂原理"。
3. **副注层 `#note-chip`**：半透明赛道/动作信息 3–5s 自动淡出（`WRC 芬兰站 · 经典飞跳 ｜ 落差 3 米`）。
4. **过渡 `#transition-line`**：揭晓→资料卡桥接句（`腾空的秘密，藏在这台车里`），平滑衔接。
5. **信息卡数字动效 `#hp-count`**：动力等数值 GSAP 0→N（N 依赛季核实值）。
6. **CTA 呼应开头 + 埋伏笔**：`你猜对了吗？/ 这台能飞的 X / 下次看它的Y！`（有始有终 + 系列感，引导关注）。

---

## 3. ⚠️ 两条你必须遵守的红线

### 红线 A —— 事实准确性（最高优先）

所有写进画面的数据（车型、车队、车手、赛季、动力/混动、赛段、战绩）**必须是可信来源（官方优先）证实**的，禁止凭印象硬编。

**赛季判定尤其严格**：**以官方/权威发布为准，画面贴纸只能当弱证据、甚至可能误导**。
- 反例（本 repo 真实踩坑）：素材尾帧有赛事贴纸 `NIEULA FOREST 2024`，曾被据此写成"2024 混动 ~500hp"，**官方视频实为 2026 赛季（无混动·纯内燃约380匹）**——贴纸是装饰/旧，不代表车型年份。
- 正确做法：优先用官方/权威来源定赛季；没核准的数值就只写"组别 WRC Rally1 / 纯内燃"，别写死数字。
- 动力口径：WRC Rally1 **2022–2024 混动 ~500hp**；**2025 起移除混动、纯内燃**（2026 约 380 匹，标注"待官方规格确认"）。
- 车手/车号：能证实才写；实测同一尘土帧多个视觉模型读出的车号不一致（17/18/13），**不要凭读图断**——用户/官方确认的用真实信息，否则留空。

### 红线 B —— GSAP 选择器一致性（改模板必查）

**card-host 元素 `id` 与 JS 里子元素选择器必须同前缀**。
- 反例（真实踩坑）：HTML 用 `id="hook-card"`、JS 却写 `#card-hook #c3` → GSAP 找不到元素 → **倒计时不递减（三个数字叠一起）、velocity 残影不出现，且不报错**。
- 修复：`#hook-card #c3`、`#reveal-card #reveal-model`、`#data-card #data-title`、`#cta-card #cta-q`。
- 残影定位：`#reveal-model-echo` 要**放进 `#reveal-model` 内部、`inset:0`**，才能精确叠词（兄弟节点定位会错位）。

> 每次新增/复制卡片后，**对着 id 核对一遍**，别只依赖渲染成功（它不一定报错）。

---

## 4. velocity 速度残影揭晓动画（标准配方）

三段式、已在 `references/template-4act.html` 内置并验证可渲染：

**HTML（残影内嵌 `#reveal-model`）：**
```html
<div id="reveal-model" style="margin-top:24px;">TOYOTA<br/><span class="sub">GR&nbsp;YARIS</span>
  <div id="reveal-model-echo" aria-hidden="true">TOYOTA<br/><span class="sub">GR&nbsp;YARIS</span></div>
</div>
```

**CSS：**
```css
#reveal-model { position:relative; font-family:"Archivo Black","Oswald",sans-serif; font-size:104px; color:#fff;
  transform:skewX(-6deg); filter:drop-shadow(0 5px 0 rgba(0,0,0,.55)) drop-shadow(0 12px 22px rgba(0,0,0,.55)); }
#reveal-model-echo { position:absolute; inset:0; font-family:"Archivo Black",sans-serif; font-size:104px;
  color:var(--accent); opacity:0; -webkit-text-fill-color:var(--accent);
  filter:blur(16px); transform:skewX(-6deg) translateX(-14px); pointer-events:none; }
```

**GSAP 时间线（揭晓段，选择器带 card-host id 前缀）：**
```js
// ① 主词沿运动向量擦入（x 负→0）+ 斜切回正 + 动感模糊→清晰
tl.fromTo('#reveal-card #reveal-model',
  {opacity:0, x:-160, skewX:-18, filter:"blur(14px)", transformOrigin:"left center"},
  {opacity:1, x:0, skewX:-6, filter:"blur(0px)", duration:0.55, ease:"power4.out"}, q(5.08));
// ② 残影：模糊强调色副本更超前滑（x:-260），落地时 opacity 收敛到 0
tl.fromTo('#reveal-card #reveal-model-echo',
  {opacity:0, x:-260, skewX:-22, filter:"blur(20px)"},
  {opacity:0.9, x:-30, skewX:-8, filter:"blur(14px)", duration:0.42, ease:"power2.out"}, q(5.05));
tl.to('#reveal-card #reveal-model-echo',{opacity:0, x:6, filter:"blur(2px)", duration:0.28, ease:"power2.in"}, q(5.45));
// ③ loom：停稳后 scale 1→1.06 推近放大再回正
tl.fromTo('#reveal-card #reveal-model',{scale:1},{scale:1.06,duration:0.4,ease:"power2.out"}, q(5.7));
tl.to('#reveal-card #reveal-model',{scale:1,duration:0.4,ease:"power2.inOut"}, q(6.1));
```

> 残影用 `.sub` 次强调色（如拉力黄）。只给高光"那一个词"用，正文保持简洁。

---

## 5. 工作流（配合 `.agents/skills/short-rewrap/HOWTO.md`）

1. **拿视频**：`yt-dlp` 或本地路径 → `videos/<项目>/`。
2. **分析关键帧**（落点 + 避让区 + **赛季/事实核验**）：
   - `ffprobe` 拿规格；`ffmpeg` 按 0.5–1s 采样帧；视觉模型定位高光与避让区。
   - ⚠️ 找赛季依据（官方/权威优先），核车型/车队/车手/车牌，能证实的才写。
3. **套模板** `template-4act.html` → 填文案/落点/颜色/事实；套赛车皮肤看 `rally-skin.md`。
4. **配字体**：`@font-face` 根相对指向 `assets/shared_library/fonts/...ttf`；**必从仓库根跑 hyperframes**，否则字体加载失败回退。
5. **Lint → Snapshot → Render**：
   ```bash
   cd <OpenMontage 仓库根>
   $env:HYPERFRAMES_FFMPEG_PATH  = "C:\...\ffmpeg.exe"
   $env:HYPERFRAMES_FFPROBE_PATH = "C:\...\ffprobe.exe"
   npx hyperframes lint videos/<项目>/public          # 0 error
   npx hyperframes snapshot videos/<项目>/public --at 6   # 单帧预览，一次一个时间点
   npx hyperframes render videos/<项目>/public --skill short-rewrap -o videos/<项目>/output.mp4 --fps 30
   ```
6. **视觉 QA**：`references/qa-checks.md` 逐段复核（含倒计时递减、velocity 残影、事实口径）。

---

## 6. 踩过的环境坑（重要）

- **`FFmpeg not found` 常是文件沙箱拦截 spawn，不是 PATH 问题**：`render` 多一道编码，需在更宽沙箱权限下重跑；同时设好 `HYPERFRAMES_FFMPEG_PATH/FFPROBE_PATH` 指向真实 ffmpeg bin。用 `npx hyperframes doctor` 确认 `FFmpeg/FFprobe` 打勾 ✓ 后再 render。
- **`--at` 一次只传一个时间**：多个 `--at` 可能被去重只出最后一帧，逐段逐个跑。
- **从 public/ 内跑 vs 仓库根跑**：字体 `@font-face` 根相对路径 `assets/shared_library/fonts/...` 需以仓库根为 cwd 才能解析到，否则报 `Fonts FAILED: NotoSansSC` → 中文回退成楷体。

---

## 7. QA 要点（详见 `references/qa-checks.md`）

必查帧：钩子(1.5/2.8·倒计时逐字递减)、副注(5·不遮主体)、揭晓(6·velocity 残影出现)、过渡(8.6·不重叠)、信息卡(10.5/12·数字动效爬到核实值)、CTA(16·上半屏)。

通过标准：文字完整可读、无 `-webkit-text-stroke` 描边、不遮挡主体/水印、位置对、不出界、**事实口径与赛季一致**。

---

## 8. 交付物

- **通用模板**：`.agents/skills/short-rewrap/references/template-4act.html`（含四条增强层 + velocity 残影，lint 0 err / render PASS）
- **说明文档**：`SKILL.md`、`HOWTO.md`
- **参考实现**：
  - `videos/wrc-hook-recut/`（基线四段式）
  - `videos/rewrap-test-v2/`（GR Yaris · Katsuta 2026，增强版）
  - `videos/wrc-test2/`（Hyundai i20 N · Neuville，velocity 残影）
  - `videos/template-check/`（模板自检：倒计时 + velocity 残影已验证）
- **赛车皮肤**：`references/rally-skin.md`（WRC 红黑配色 + 资料卡）
- 素材：`input-video.mp4`（密集关键帧）；字体：`assets/shared_library/fonts/` 下 `NotoSansSC-Black.ttf` 等。
