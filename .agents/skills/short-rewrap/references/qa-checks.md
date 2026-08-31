# 视觉 QA 检查清单 + 常见坑

渲染前先用 `npx hyperframes snapshot <project> --at <t>` 逐段抽帧，再用视觉模型/delegate 复核。**不要用完整 render 去发现排版问题**（一次 render 要几十秒到两分钟）。

> 我的测试经验：`snapshot`/`render` 需在「更宽沙箱权限」下跑（详见 §Windows 沙箱与 ffmpeg 检测），否则会 `spawn EPERM` 或 `FFmpeg not found`。

---

## 必查帧（对应增强四段 + 副注/过渡）

| 段 | 采样秒 | 看什么 |
|----|-------|--------|
| 钩子 | t=1.5 / 2.8 | 钩子三句是否居中、行距、倒计时是否在顶部、文字完整；**倒计时是否逐字 3→2→1 递减（非三个数字同时叠在一起——若是,多为 GSAP 选择器不匹配,见 §选择器红线）** |
| 揭晓 | t=6 | 答案名是否打在高光角色/位置、是否挡住赞助商/水印、字号够不够；性能副注是否清晰；**velocity 残影(模糊强调色尾迹)是否出现**——若无,先查 `#reveal-model-echo` 是否在模型内 `inset:0` + 选择器是否匹配 |
| 副注 chip | t=5.0 | 半透明标注是否出现、是否遮住主体/字幕 |
| 过渡 | t=8.6 | 桥接句是否滑入、是否与即将进入的信息卡重叠打架 |
| 信息卡 | t=10.5 / 12 | 标题、每行数据完整可读、不遮主体、卡片不越屏；**动力数字动效是否爬到已核实值（2026 纯内燃约380，勿按旧混动500）** |
| CTA | t=16 | 是否在上半屏（避开抖音底部 UI）、文案完整、"关注/伏笔"是否强调色 |

## 通过标准（每帧）

1. **文字完整**：逐字读，无遗漏/无乱（比如缺"是"、中文变"?/毛笔"）。
2. **可读**：不因背景太亮而看不清（投影/压暗 scrim）。
3. **无描边**：文字风格为"无 `-webkit-text-stroke`"，只靠极粗黑体 + 投影 + 强调色；不要出现紧贴笔画的黑/深描边线。
4. **不遮挡**：不压主体、赞助商、水印、字幕。
5. **位置对**：钩子居中、倒计时顶部、信息卡/CTA 在指定区、副注不遮主体。
6. **不出界**：没有越屏、被裁切。

## ⚠️ 事实核验（必须配读）

抓帧复核时同时确认**已证实/官方认可的身份与赛季事实**已正确写进素材：
- 赛季判断以**官方/权威发布**为准；画面贴纸只是弱证据可能误导（本片贴纸写 2024、官方视频实为 2026）。
- WRC Rally1：**2022–2024 混动 ~500hp；2025 起混动移除、回归纯内燃**（本片官方确认 2026 → 无混动）。写死的动力/混动必须与赛季一致；没核准数值就只写"组别 WRC Rally1/纯内燃"。
- 车手/车队/车型以**画面能证实的**为准，推测的不写。

## 常见坑（本次踩过）

| 现象 | 根因 | 修法 |
|------|------|------|
| 写错"混动/动力数字" | 没按官方确认的赛季就写死 | 以官方/权威发布的赛季为准；未核数值只写组别/动力类型，见 rally-skin 准确性红线 |
| 中文显示成毛笔/楷体 | 自转 woff2/ttf 渲染器不加载→回退系统书法字 | 用项目字库 `@font-face` 根相对指向 `assets/shared_library/fonts/...ttf`，并从**仓库根**跑 hyperframes |
| 文字带线条描边（用户不要） | 用了 `-webkit-text-stroke` + 多层投影 | 去掉 `-webkit-text-stroke`，只留投影/强调色 |
| 整行金色只第一字生效/缺字 | `-webkit-background-clip:text` + 逐字 span 冲突 | 去掉 clip 渐变，改纯色填充+投影 |
| CTA 被底下 UI 挡 | `bottom` 定位 | 改 `top:12%` |
| 结尾/揭晓盖住赞助商 | 没做画面避让分析 | 先用视觉模型标出避让区 |
| 没声音 | 漏加原始音轨 | `<audio id="source-audio" src="input-video.mp4">` |
| 箭头指错/不同步 | 箭头坐标硬编码、不追踪主体 | 用 GSAP 逐帧/关键帧追踪主体中心 |
| 数字动效不涨/涨错 | 目标值写死且没核对赛季；或 `#hp-count` 未绑定 | count-up 目标按赛季核对；确认 `getElementById` 与 GSAP onUpdate 已绑 |
| **倒计时不递减/全叠一起 / 残影不出现** | **GSAP 选择器与元素 id 不一致**（如 HTML `hook-card`、JS 写 `#card-hook`）→ 动画静默失效不报错；或残影 echo 没放进模型内 | 对齐选择器前缀（见 `rally-skin.md §5` 红线）；echo 放 `#reveal-model` 内 `inset:0` |
| 副注/过渡与信息卡重叠 | 时间轴 overlap 太密 | 主四段用 track 2、副注/过渡用 track 3，避免 track 2 元素超过 4 个 |

## Windows 沙箱提示 —— ffmpeg 检测修复（本次实测关键）

HyperFrames 的 `render`（比 `snapshot` 多一道**编码**）需要在 PATH 上找到 ffmpeg/ffprobe **并真的能 spawn 它**。两个坑：

1. **PATH 里能看到 ≠ HyperFrames 能找到**：scoop shim 可能不被其子进程解析。用 **显式环境变量** 指定真实 bin（推荐）：
   ```powershell
   $env:HYPERFRAMES_FFMPEG_PATH  = "C:\Users\<u>\scoop\apps\ffmpeg\<ver>\bin\ffmpeg.exe"
   $env:HYPERFRAMES_FFPROBE_PATH = "C:\Users\<u>\scoop\apps\ffmpeg\<ver>\bin\ffprobe.exe"
   ```
2. **spawn EPERM / FFmpeg not found = 通常是被文件沙箱拦截**：`snapshot`/`render` 要起渲染+编码子进程（piped stdio），在受限模式下会失败。在**更宽沙箱权限**下重跑**同一条命令**即可（这是我测试时 `FFmpeg not found` 的真正原因，不是 PATH 问题）。

> 验证：`npx hyperframes doctor` 各项 `FFmpeg/FFprobe` 打勾 ✓ 后再 render。
