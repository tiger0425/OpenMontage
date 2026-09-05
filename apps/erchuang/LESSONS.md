# ErChuang（抖音二创）经验沉淀 LESSONS.md

> 2026-09-03 两条视频复验沉淀：Nissan B_PnlpsVtnw（拆两集 P1/P2，用户验收）+
> Toyota Eagle 0fHBKr8h5JM（广告整段剔除 + 单集 128s，复验后归档）。
> 本文是**全量经验真相源**；SKILL.md 只做路由与速查，细节以本文件为准。

## 1. 定位

把 auto-dub 成品/原片（`projects/auto-dub/auto-dub-<id>/` 有 source.mp4、assets/vocals.wav、
assets/no_vocals.wav、transcript.json）二次创作为抖音横屏片：去原作头像/广告 → 拆集连载或单集 →
你的音色 + 逐句原片情感配音 → 干净素材蒙太奇 + 重点卡 → 成品包（auto-dub review/published 协议）。

CLI：`bin/erchuang.py`（zones/synth/montage/mux）；合成走 `apps/indextts-bridge/client.py`；
文案必须过 `.agents/skills/humanizer-bilibili/SKILL.md`。

## 2. 六步流程（已跑通三遍（日产原版/Eagle/日产重做））

1. **zones 禁区**：`erchuang.py zones --ref-sec <原作头像秒>`（SFace 指纹，±5s 并簇）。
   ref-sec 来自用户指认：先抽 contact sheet（全片人脸命中簇 16 格）让用户指出原作头像所在格。
2. **拆集/文案**：见 §3；文案过 humanizer-bilibili。
3. **synth**：manifest 逐段合成（voice_ref=你的音色 + `emo_audio: "vocal@<s>:<len>"` 自动从原片
   vocals 切情感参考 + 呼吸 gap + tempo）。产出 narration.wav + timings.json（overlay 卡点轴）。
4. **montage**：`--cuts "a-b;c-d;…"`（禁区外干净段，避免含作者/广告/语义错位），`--bed no_vocals` 出引擎声床。
   重做压缩版可**复用老 input-video/bed**：新旁白更短时直接复用（新窗口是老窗口子集，无新增禁区风险），composition duration=新 narration； bed 超长无碍（mux 内置 `amix duration=first + -shortest`）。前提：故事半区对齐（P1R 用 P1 蒙太奇，P2R 用 P2 蒙太奇），禁区子集结论要如实告诉用户（1s 步长复核做可选项）。
5. **overlay**：手写 `public/index.html`（hyperframes 契约；卡片时间轴 = timings.json = 配音轴，
   不是原片转录轴）→ `hyperframes check` → `render -q high` → visuals.mp4（无声）。
   - 封面抽帧前先**像素级验黑边**（PIL 读左右边缘列（均值 <30 即黑边）），别信播放器肉眼：日产母带 `source.mp4` 全片自带 4:3 pillarbox（content x≈246–1672）， montage/render/cover 逐级继承，**不是管线 bug**。母带属性且老片已如此验收时，新版与老片 parity、不另起重切；R14 零黑边指包装不引入新黑边。
   - overlay 里 GSAP timeline 的选择器必须对应真实 id：卡片容器要写 `id="card-0X"`，否则 `#card-0X .detail/.sub` 类选择器报 `GSAP target not found`。 check 0 error 不够，**runtime 也要 0 warnings**（contrast 类 warning 沿用老设计可接受）。
6. **mux + 成品包**：narration + bed 混音（§5.1）→ review/<channel>/<标题>/（mp4+封面+meta+简介）
   → DB 注册 `<源id>_P1/P2/E1` → `confirm-video` 归档 published。
- **重做一律新 ID 后缀 R**（如 `B_PnlpsVtnw_P1R/_P2R`），老片保留对照；确认后 published 并存，不覆盖。
- 成品包文件名对齐 published 惯例：`<标题>.mp4` + `<标题>_cover_16_9.png` + `<标题>_meta.json` + `<标题>_简介.txt`（review 裸名 cover.png/meta.json 在 confirm 前改名，避免 confirm-video 认不到）。

## 3. 拆集与文案决策

| 决策 | 结论 | 依据 |
|---|---|---|
| 1 集还是 2 集 | 按**内容体量**定，不是按原片时长：日产 12.7min 拆 2（两幕都够一个钩子弧）；Eagle 广告剔除后主线单一 → 用户拍板合 1 集 128s | 用户 2026-09-03：两集合计才 200s 就别拆 |
| 合集追问（2026-09-04） | 用户看 P1R 73s+P2R 67s 合计 140s 问"合成一集？"→用 R7（45–90s）+ R8（超 90s 必须拆集）+ 完播压力三选项回答，用户选"保持两集"。**结论：合计 <200s 不是合集理由**，单集超 90s 就拆；两幕各够钩子弧更要拆 | 日产重做 P1R/P2R |
| 断点 | 叙事转折（日产=守江山 u50；Eagle=广告中插即天然分幕） | — |
| 钩子 | 结果前置 + 价值承诺（#84 R1–R3），0–2s 出爆点关键词 | research/douyin-retention-rules |
| 单句 | ≤28 字；长句拆 | humanizer §36–38 |
| 年份读法 | TTS 会把"1964"读"一千九百六十四" → 文案一律"一九六四年" | 用户反馈（Eagle 复验） |
| 事实核查 | 被干趴对象必须对位剧情年代：Eagle hook 原写"保时捷"被砍——1991–93 Eagle 对位是日产/捷豹，保时捷 962 是 80 年代末 | 用户反馈（Eagle 复验） |
| 事实核查2 | 日产 1992 Daytona 是 LM **组别冠军 + 总成绩第二**（输 Jost），不是总冠军。压缩版直接删掉该细节避错——**删存疑细节比写错强** | 日产重做 P2R（老 P2 卡片"总冠军"有误，新版已删） |
| 中插广告 | 转录 u19–u30 整段口播即广告区间，整段剔除、不补配音 | Eagle Flexi-Spot 193–316s |
| 结尾钩子 | **每集（含单集/终集）结尾必留钩子**：连载中间集=下集悬念；单集/终集=关注钩子（"下一台更疯，关注别错过"）或反常识反问（"你说它到底值不值？评论区聊"）。**禁止无钩子干收尾** | 用户 2026-09-03（日产 P2、Eagle 终集均漏钩） |

## 4. 素材/出镜禁区（两次都踩）

- **作者出镜常超出 zones ±5s 并簇边界 2–5 秒**：Nissan zones 到 475 但作者出到 478；到 645 但出到 648。
  → **定稿前必须用 1s 步长 SFace 把成片所用窗口逐秒复核一遍**（复用 denselocate 思路，阈值 0.25 起）。
- step=5 的 zones 只是初筛；0.35 阈值漏小脸/侧脸。宁可复核多花 2 分钟。
- 不同脸命中（车手老照片）不是禁区——SFace 同脸比对已自动排除（Eagle 的 1:55/2:20/7:20/9:15）。
- emo ref 从 vocals 切，与画面禁区**无关**（情感参考可以取作者说话段）。

## 5. 音频/合成经验

### 5.1 bed 静音（重要）
- no_vocals 平均约 -31dB，旧 montage 预乘 0.15 → 成品 bed ≈ -47dB = 用户听不到背景音。
- 修法（`mux` 已内置）：bed 过 `loudnorm=I=-25:TP=-2:LRA=13`；`amix=inputs=2:normalize=0`
  （默认 normalize=1 会把两路再除 2，双双 -6dB）；最后 `alimiter=limit=0.95`。
- 生效范围：日产 P1/P2 与 Eagle 都已用新混音重混并同步替换 review/published。

### 5.2 emo-ref 情感
- calm 太淡、use_emo_text(auto) 太演 → **逐句原片 emo_audio_prompt**（0.6，0.35 弱档）用户认可。
- bridge/server+client 已加 `emo_audio_prompt`（emo_audio 优先于 emo_vector；缺省纯净克隆不变）。
  **勿绕桥直调模型**：合成一律 `IndexTTSSession.synthesize(..., emo_audio_prompt=…)`。

### 5.3 呼吸感
- 句间 gap 不要统一 100ms：hook 后 300–350、段间 150–250、收尾 400–700；tempo 局部 1.0–1.07 做起伏。

## 6. 封面 / 渲染踩坑

- drawtext 中文：filter 内 Windows 路径要 `C\:/…` 正斜杠 + 单引号整值；坐标用 `main_h/main_w`
  （drawtext 无 `ih`）；字体 `msyhbd.ttc`。
- hyperframes index.html：简体中文不能裸用自带 WenKaiTC(latin 子集) →
  `@font-face{font-family:"Microsoft YaHei";src:local("Microsoft YaHei")}`，否则 lint
  `font_family_without_font_face` / 豆腐块。
- `hyperframes check` 传**目录**；render 的 mp4 **无声**（video muted）→ 音频一律 mux 补。
- 卡片/动画禁 `<script>` 做动效；用 data-* + GSAP paused timeline 注册 `window.__timelines[id]`。

## 7. CLI/代码经验

- `erchuang.py` 顶部须把 ROOT 注入 sys.path（client.py 依赖 `lib.gpu_lock`）。
- montage 音频分支旧写法 `atrim=start=start=` 双前缀 bug → 已修。
- `--bed-volume` 只影响 montage 中间件；mux 的 loudnorm 会重算 bed，勿依赖它调成品音量。

## 8. 成品包与发布

- 抖音规格：视频 16:9；标题 ≤55 字钩子+关键词；封面 16:9 大字 + 上下集角标；简介首行
  `中文标题:`、次行 `原视频:`、末行话题标签。
- DB 注册 `review` → 用户确认 → `confirm-video` → published（review 留副本）。
- **注意：成品包必须含 16:9 封面图**。Eagle 归档时漏了封面（0fHBKr8h5JM_E1 待补）。

## 9. 复验清单（新视频上线前逐项过）

- [ ] zones 已按用户指认的 ref-sec 生成，且**成片窗口 1s 步长复核零作者脸**
- [ ] 中插广告（转录口播段）整段已剔除
- [ ] 文案过 humanizer-bilibili；年份一律汉字；被干趴/击败对象经转录事实核对
- [ ] 结尾留钩子（单集/终集=关注钩子或反问，非空收尾；连载中间集=下集悬念）
- [ ] narration = 你的音色 + 逐句 emo-ref；bed loudnorm -25 混音可闻
- [ ] hyperframes check 0 error 且 runtime 0 warnings；card 卡点 = 配音 timings.json
- [ ] 成品包含 mp4+封面+meta+简介；review → confirm → published

## 10. 当前状态与未决（2026-09-03）

- published：日产上/下（B_PnlpsVtnw_P1/_P2）、Eagle 单集（0fHBKr8h5JM_E1，**封面待补**）。2026-09-04 重做版 P1R（73.2s）/P2R（67.5s）已 published（新 ID，老片保留；丰田 Eagle 未动）。
- 首批剩 2 条（mEYUjkU3nAk、H-vvv--Eq6M）未二创；另 19 条待排；RixZZNV2NxE 原片曾机器人验证。
- 平台数据未验：#90（2 秒跳出 / 5 秒完播≥50% / 整体≥20%）。
- map：#83 追踪，#87 规则已近定稿待收，#88 剩 3 条标注待跑。
