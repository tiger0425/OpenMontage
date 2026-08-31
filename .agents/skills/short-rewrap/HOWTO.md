# HOWTO — 用 short-rewrap 四段式做一条二创竖屏短视频

从拿到视频到出成片的完整分步流程。基线打磨自 `videos/wrc-hook-recut/`，增强层（副注/过渡/数字动效/呼应CTA）在 `videos/rewrap-test-v2/` 验证。

---

## 0. 前提

- ffmpeg / ffprobe（若 `hyperframes` 找不到，用 **环境变量指定真实 bin**，见 §5）。
- HyperFrames 已装：`npx hyperframes doctor` 可用，`FFmpeg/FFprobe` 打勾 ✓。
- 竖屏源视频（1080×1920 最佳；若不是，先裁剪/缩放到竖屏）。
- 能看图：建议有视觉模型（minimax-m3-vision 脚本，或当前模型支持读图）。

---

## 1. 拿视频

```bash
# YouTube
yt-dlp "URL" -o "input_orig.mp4" --merge-output-format mp4
# 或用户给本地路径：cp 源视频 videos/<项目>/
```

## 2. 分析关键帧 + 定位落点

```bash
# 规格
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of json 源视频.mp4
# 按 0.5–1s 采样几帧，用视觉模型看
ffmpeg -y -ss <t> -i 源视频.mp4 -vframes 1 frames/<t>.png
```

**要定位/确认：**
- **高光瞬间**（放揭晓 Reveal 用）：本片=赛车腾空顶峰。用视觉模型逐帧看：`仅腾空顶峰在 t=6.75s`。
- **钩子前段是否"空/无主体"**（放钩子字）：本片前 3s 是赛道静态画面，钩子叠上方干净。
- **字幕/水印/赞助商/主体位置**：叠字要避让；本片车身有 DENSO/TAMADIC/TOYOTA GAZOO 等，箭头或揭晓字要避开。
- **⚠️ 赛季/身份事实**（决定动力/混动/车手写不写）：**赛季以官方/权威发布为准**，画面贴纸只是弱证据、可能误导——本片贴纸写 `NIEULA FOREST 2024`，官方视频实为 **2026 赛季** → **无混动·纯内燃**。没核准就**只写组别 WRC Rally1**，别写死动力/混动/马力数字。车身事实以**画面能证实的**为准（本片车牌 OC-4491、赞助商 DENSO/TAMADIC/CCI/FORUM8/Panasonic、TOYOTA GAZOO Racing）；**车手经确认 = Takamoto Katsuta**（2026 厂队名单内），填资料卡；换视频/换人必须重新核实，勿照搬。

## 3. 建工作目录 + 套模板

```bash
mkdir -p videos/<项目>/public/fonts videos/<项目>/public/vendor
```

把 `references/template-4act.html` 复制为 `public/index.html`，然后按项目填：
- `data-duration` = 视频实际时长（秒）。
- 主四段的 `data-start` / `data-duration`（钩子 0 / 揭晓 ~4.8 / 信息卡 ~9.2 / CTA ~14.5）。
- 副注层 `note-chip` 与过渡 `transition-line` 的 `data-start`/`data-duration`（见模板注释）。
- 各卡文案（见 `copywriting.md`），**动力/混动等数值按 §2 核实的赛季填**。
- 若赛车题材：替换成 `rally-skin.md` 提供的配色变量 + 资料卡行；若通用题材：改颜色/文案即可。
> ⚠️ **改文案/复制卡片后，务必保持 GSAP 选择器与元素 id 前缀一致**（card-host `id="hook-card"` → JS `#hook-card #c3`）。改错会**面板静默失效**（倒计时不递减、velocity 残影不出现、且不报错）。详见 `rally-skin.md §5` 红线。

**增强三层（信息增量/叙事感）改法**（`references/template-4act.html` 已内含，按需删改）：
- `#reveal-note`：揭晓段"性能副注"，把高光绑定原理（`腾空的秘密：轻量化 + 涡轮爆发`）；⚠️ 动力机制按官方确认的赛季写（本片 2026 → 无混动，勿写"混动爆发"）。
- `#note-chip`：副注层，半透明一行赛道/动作信息，`data-duration` 设 3–5s 自然淡出。
- `#transition-line`：揭晓→信息卡桥接句，1.5–2s。
- `#hp-count`：信息卡数字动效，GSAP 0→N；**N 按官方赛季核实的值填**（本片官方确认 2026 → 纯内燃约 380 匹，勿按旧混动填 500，标注"待官方规格确认"）。
- CTA：`你猜对了吗？/ 这台能飞的 X / 下次看它的Y !`（呼应开头+埋伏笔）。

## 4. 配字体

把源视频复制/重编码为 `public/input-video.mp4`（密集关键帧，保证 seek 精确）：

```bash
ffmpeg -y -i 源视频.mp4 -c:v libx264 -crf 18 -g 30 -keyint_min 30 -pix_fmt yuv420p -movflags +faststart -c:a aac public/input-video.mp4
```

**字体加载（重要）— 用项目共享字体库，别自己转 woff2 塞 public/fonts/：**

- 渲染器默认自带(bundled)：`Noto Sans JP`（中文）、`Archivo Black`（英文冲击）、`Oswald`/`Roboto`/`Lato`/`Playfair Display` 等。
- 想要更粗/更风格化的**中文字体**（如超粗黑体、书法体），用项目字库 `assets/shared_library/fonts/` 里的 ttf（如 `NotoSansSC-Black.ttf` 思源黑体 Black / `MaShanZheng.ttf` 书法 / `NotoSerifSC-Bold.ttf` 宋体粗）。加载法——**`@font-face` 用根相对路径（无 `../`）**，因为组合以项目根为基准：

```css
@font-face { font-family: 'NotoSansSC'; src: url('assets/shared_library/fonts/NotoSansSC-Black.ttf'); font-weight: 900; font-display: block; }
/* 用法 */
#hook-main { font-family: "NotoSansSC", sans-serif; font-weight: 900; }
```

> ⚠️ 不要写 `url('../.../fonts/...')`（会 lint 报 `invalid_parent_traversal_in_asset_path`）。路径必须**根相对** `assets/shared_library/fonts/...`。
> ⚠️ **如果字库在仓库根、你的组合在 `videos/<项目>/public/`，就必须从仓库根跑 hyperframes**（`cd <仓库根>` 再 `npx hyperframes ... videos/<项目>/public`），否则该 `@font-face` 解析不到而加载失败（日志 `Fonts FAILED: NotoSansSC` → 中文回退成系统书法字/楷体）。我已踩过：从 `public/` 内部跑会失败，从仓库根跑即成功。
> ⚠️ 中文粗细受字体限制：bundled 的 Noto Sans JP 最高 700；要更粗就用 `NotoSansSC-Black`(900)。可用 `transform: scaleX(0.78)` 横向压扁模拟"浓缩粗体"。

## 5. Lint → Preview → Render

从**仓库根**跑（这样 `@font-face` 根相对路径能解析到字库）：

```bash
cd <OpenMontage 仓库根>
ffbin="C:\Users\<u>\scoop\apps\ffmpeg\<ver>\bin"
$env:HYPERFRAMES_FFMPEG_PATH  = "$ffbin\ffmpeg.exe"
$env:HYPERFRAMES_FFPROBE_PATH = "$ffbin\ffprobe.exe"

npx hyperframes lint videos/<项目>/public          # 0 error 再继续
npx hyperframes snapshot videos/<项目>/public --at 6   # 单帧预览；逐段(dashboard)逐个 time 跑
npx hyperframes render videos/<项目>/public --skill short-rewrap -o videos/<项目>/output.mp4 --fps 30
```

> ⚠️ **`--at` 一次只传一个时间再逐个跑**，多个 `--at` 可能被去重只出最后一个（我踩过：传 5 个只出了末帧）。逐段抽帧建议：2.5 / 5.0(副注) / 6(揭晓) / 8.6(过渡) / 10.5+12(信息卡) / 16(CTA)。
> ⚠️ **`FFmpeg not found` 通常是文件沙箱拦截 spawn，不是 PATH 问题**：`render`（比 snapshot 多一步编码）要在更宽沙箱权限下重跑同一条命令；同时设好上面两个 `HYPERFRAMES_*_PATH` 指向真实 ffmpeg bin。用 `npx hyperframes doctor` 确认 `FFmpeg/FFprobe` 打勾 ✓ 后再 render。

## 6. 视觉 QA

逐段抽帧 + 视觉模型复核：`references/qa-checks.md`。不通过就改字号/颜色/位置，`snapshot` 再看，直到 PASS 再最终 render。**QA 同时要复核"赛季/动力/混动"等事实是否与画面一致**（见 §2）。

---

## 常见坑（本次踩过的）

| 问题 | 原因 | 修复 |
|------|------|------|
| **写错"混动/动力/车手"等事实** | 没先核赛季就写死；或凭印象填 | **先逐帧找赛事贴纸/年份/赛段名/车牌/车号**，只写"画面能证实的"；未核赛季→只写组别(见 §2, rally-skin 红线) |
| 中文字显示成毛笔/楷体 | 自定义 woff2/ttf 渲染器不加载 → 回退系统字体 | 用项目字库 `@font-face` 根相对指向 `assets/shared_library/fonts/...ttf`，并从**仓库根**跑 hyperframes(见 §4/§5) |
| `FFmpeg not found` / 渲染失败 | 文件沙箱拦截 ffmpeg spawn(不是 PATH) | 设 `HYPERFRAMES_FFMPEG_PATH/FFPROBE_PATH` + 更宽沙箱重跑同一条命令(见 §5, qa-checks) |
| 多个 `--at` 只出最后一帧 | snapshot 对多时间点去重 | 一次只传一个 `--at`，逐个跑(见 §5) |
| 单字金色、其他字变色 | `-webkit-background-clip:text` 配合逐字 span 会只生效第一个字 | 去掉 clip 渐变，用纯色填充 + 描边 |
| CTA 被抖音底部 UI 挡 | `bottom` 定位在屏幕下方 | 改 `top:12%` 放上半屏 |
| 字幕缺水印/赞助商文字 | 没做画面分析 | 第 2 步先用视觉定位避让区 |
| 没声音 | 忘加原始音轨 | `<audio id="source-audio" src="input-video.mp4">` |
| 结尾文字"少字/乱" | 字体缺字形 | 中文一律 `Noto Sans JP` |

---

## 交付

- 成品：`videos/<项目>/output.mp4`（或改名放 `projects/`）。
- 关键帧截图自留：`qa_frames/`。
- 若需发布：另用 `youtube-upload` / 平台自行上传。
