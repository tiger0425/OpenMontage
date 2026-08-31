# short-rewrap — 竖屏短视频"四段式"二创/重包装 Skill

把一条**已有竖屏短视频**（精彩瞬间、值得留人的画面）重包装成"竞猜钩子 → 揭晓答案 → 信息/资料卡 → 结尾关注"四段式成片。
只做**画面叠加图层**（视频原样播放、保留原音轨），用 HyperFrames 组合渲染，输出 1080×1920 竖屏 MP4。

> 适用：任何有高光瞬间的竖屏视频（赛车腾空、魔术、烹饪、游戏操作、探店名场面等）。
> 附带一个"赛车皮肤"（可选垂直模板）：WRC 官方红黑配色 + 车型/车手资料卡。
> **触发方式：显式调用** —— 用户在消息里明确说"用 short-rewrap skill / 做成四段式二创"之类才启用。

---

## 什么时候用 / 什么时候不用

**用（匹配）：**
- "这条视频做成竞猜式二创 / 加钩子和资料卡 / 加结尾关注"
- 给一条已有视频叠加"悬念 + 揭晓 + 信息卡 + CTA"，保留原画面和原音轨
- 用户说"用 short-rewrap skill"或"四段式重包装"

**不用（改走其他 skill/流程）：**
- 制作全新合成的视频（→ 走 Universal Harness `bin/omo.py`，尤其 **AGENTS.md 红线**：禁止手动 ad-hoc 生成资产，必须走 `start-stage`/`submit-artifact`）
- 只加字幕/配音（→ `chinese-subtitle` / `auto-dub`）
- 纯剪辑/转场/压缩（→ `video-edit` + ffmpeg）
- 生成 AI 视频/av 头像（→ `ai-video-gen` / `avatar-video` / `create-video`）

> ⚠️ **红线提醒**：本 skill 针对**已有文件、纯 overlay 叠加**，不替代 Universal Harness 的生成管线。AGENTS.md 第 4 条"NO SINGLE-SHOT HTML GENERATION"针对的是 HyperFrames **从零创作**视频；本 skill 是**给已有成品视频加图层文案**，属于编辑性组合。但若目标是"生成全新视频"，一律先走 `bin/omo.py`。

---

## 四段式模板（理解核心）

一条 17s 左右的竖屏短视频，切四段：

| 段 | 建议时间 | 作用 | 本片实例（赛车） |
|----|---------|------|----------------|
| **1. 钩子 Hook** | 0–4s | 悬念留人：短句 + 倒计时 | 竞猜时间 / 来的是什么？/ 🎯它会飞 / 3·2·1 |
| **2. 揭晓 Reveal** | ~4.8–8s | 高光时刻打出"答案" | 答案是—— / TOYOTA / GR YARIS / RALLY1 |
| **3. 信息卡 Info Card** | ~8–13.5s | 叠一张数据卡 | 赛车档案（车型/车队/车手/组别/动力） |
| **4. 结尾 CTA** | ~14–17s | 引导关注/互动 | 你猜对了吗？/ 后期更精彩 / 请关注 XX! |

- 时间轴通常取**视频后半段有稳定画面**时叠信息卡，**结尾**叠 CTA（放上半屏，避开抖音底部操作栏）。
- 若视频更长/更短，可按比例伸缩，但**信息卡和 CTA 至少各占 1.5–2s**，钩子覆盖前 20–25%。

---

## 使用流程（简短版，详见 `HOWTO.md`）

1. **拿到视频** → `youtube`/本地文件 → 用 `video-download` skill（yt-dlp）或用户提供路径。
2. **分析关键帧**（决定钩子/揭晓/信息卡/CTA 的落点和字幕避让位置）：
   - `ffprobe` 拿规格（分辨率/时长/fps）；
   - `ffmpeg` 按 0.5–1s 采样几帧；
   - 用视觉模型（如 minimax-m3-vision / 当前模型能看图时直接看）定位"高光瞬间"（本片=腾空顶峰）和中文字幕/水印/赞助商文字位置。
3. **建工作目录** `videos/<项目名>/`，把源视频放进去。
4. **套四段式 HTML 模板**（`references/template-4act.html`）→ 填你的文案、落点、颜色。
   - 若做赛车题材，套用 `references/rally-skin.md` 的配色 + 资料卡结构（WRC 红黑、Ver 车型卡）。
5. **配合 HyperFrames 渲染器跑**：
   - 复制模板到 `public/`，字体放 `public/fonts/`，把源视频重编码为密集关键帧版 `input-video.mp4`；
   - `npx hyperframes lint public`（0 error 通过）；
   - `npx hyperframes snapshot public --at <t>` 逐段预览；
   - `npx hyperframes render public ... -o output.mp4 --fps 30`。
6. **视觉 QA**（`references/qa-checks.md`）：逐段抽帧复核，文字可读、无遮挡、位置对。

---

## 关键规范（务必遵守）

- **⚠️ 事实准确性红线（最高优先）**：所有写入视频的字幕/资料卡数据（车型、车队、车手、服役赛季、动力、混动与否、赛段/站名、战绩）**必须是你能从可信来源（官方为准）证实的**，禁止凭印象硬编。**赛季判断以官方/权威发布为准，画面贴纸只能当弱证据、甚至可能误导**（本参考片贴纸写着 2024，官方视频实为 2026）。动力机制按赛季：**WRC Rally1 2022–2024 混动 ~500hp；2025 起已移除混动、回归纯内燃**（本参考片官方确认 2026 → 无混动）。没核准的数值就**别写死数字**，只写"组别 WRC Rally1/纯内燃"或标"待核"。宁可信息少一条，绝不写错一条。（详细判据见 `references/rally-skin.md` §准确性红线 + `references/qa-checks.md`）
- **字体**：见 `HOWTO.md §4`。默认用 bundled 字体（中文 `Noto Sans JP`、英文冲击 `Archivo Black`、压缩 `Oswald`）。要更粗的中文就**用项目字库 `assets/shared_library/fonts/` 的 ttf**（如 `NotoSansSC-Black.ttf` 思源黑体 Black），`@font-face` 用**根相对路径** `url('assets/shared_library/fonts/...ttf')`（别用 `../`，必从**仓库根**跑 hyperframes，否则该字体加载失败）。配合 `scaleX(0.78)` 压扁可得 Archivo 式浓缩粗体。
- **保留原音轨**：`<video>` muted + 单独 `<audio id="source-audio">` 引同一源文件（见模板），保证配音不动原片声音。若需加 TTS，另加 `<audio>` 轨。
- **⚠️ GSAP 选择器一致性（改模板必查）**：card-host 元素 `id`（如 `hook-card`）与 JS 里子元素选择器必须同前缀（`#hook-card #c3`）。若 HTML 用 `hook-card`、JS 却写 `#card-hook`，GSAP 找不到元素 → 该段**动画静默失效且不报错**（倒计时不递减、velocity 残影不出）。**每次新增/复制卡片都对一遍 id**（详见 `rally-skin.md §5` 顶部的红线）。
- **CTA 放上半屏**：`top:12%` 起步，避开抖音/短视频底部操作栏。
- **竖屏**：`1080×1920`，`data-width/height`、`fps=30`。
- **避让**：字幕/水印/赞助商文字、主体画面——叠字别压住关键信息。
- **可读性**：大字号 + 深色描边/投影，尤其画面偏亮时（绿树/天空/尘雾）。

## 增强层（信息增量 + 叙事感，`template-4act.html` 已内含）

- **揭晓 velocity 速度残影动画（标准揭晓动效）**：车型名/答案词沿运动向量擦入 + 模糊强调色残影尾迹先超前滑再收敛 + 停稳 loom 推近（`template-4act.html` 已内置；配方见 `rally-skin.md §5`）。
- **揭晓性能副注 `#reveal-note`**：高光时刻下方一行"懂原理"副注（`腾空的秘密：轻量化 + 涡轮爆发`），把"看高能"升级为"懂原理"。⚠️ 动力机制按赛季核实（本片官方确认 2026 → 无混动·纯内燃约380匹，勿写"混动爆发"）。
- **副注层 `#note-chip`**：半透明赛道/动作信息，3–5s 淡出，不遮主体。
- **过渡 `#transition-line`**：揭晓→信息卡的桥接句（`腾空的秘密，藏在这台车里`）。
- **信息卡数字动效 `#hp-count`**：动力等数值 GSAP 0→N（N 依赛季核对）。
- **CTA 呼应+埋伏笔**：`你猜对了吗？/ 这台能飞的 X / 下次看它的Y!`（有始有终 + 系列感）。
- 以上数值、文案仍受 **事实准确性红线** 约束，改文案前先核画面。

---

## 交付物（本 skill 目录）

- `SKILL.md` — 本文件（主指南）
- `HOWTO.md` — 完整 step-by-step 操作流程 + 命令
- `references/template-4act.html` — 可复用的通用四段式组合 HTML
- `references/rally-skin.md` — 可选赛车皮肤（配色 + 资料卡填充 + 车型信息）
- `references/copywriting.md` — 钩子/CTA 文案规范 + 抖音标题/简介模式
- `references/qa-checks.md` — 视觉 QA 检查清单 + 常见坑

---

## 参考案例（本次落地的完整实例）

- 工作项目一（基线四段式）：`videos/wrc-hook-recut/`；成品 `WRC_拉力虎_车型揭晓资料卡.mp4`。
- 工作项目二（增强层版：副注/过渡/数字动效/呼应CTA，已验证 render PASS）：`videos/rewrap-test-v2/`；成品 `output_enhanced_v2.mp4`。
- 事实核验示例：本片经**官方确认属 2026 赛季** → 无混动·纯内燃约 380 匹（勿按画面贴纸写成 2024 混动 ~500hp）。马力标"待官方规格确认"。
```