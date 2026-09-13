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
| 剧作重构（2026-09-06 重大升级） | **严格执行 STORYTELLING.md 五步戏剧张力与三层下潜**：彻底告别编年流水账与参数说明书。开篇黄金 2 秒强制三选一（荒谬漏洞/生理极限/降维反杀），严禁赛事缩写、年份起手、报菜名与提前揭秘车名。中段每 25~30 秒埋入未闭合悬念（Open Loop）。强制过 `check-manifest` 门禁 | 用户 2026-09-06：故事太平淡、2秒跳出率太高、完播率低、偏描述型缺乏深度分析 |
| 车辆性能深度剖析 | **三层下潜法则**：表象数据(What) → 工程致命代偿(Trade-off，讲透极端性能背后的残酷代价与赌博) → 底层博弈(Why & Power，讲清规则修改背后的资本围剿与权力死斗)。拒绝干瘪配置单 | 用户 2026-09-06：没有对问题的深入分析 |
| 黄金 2 秒爆点 | 前 2 秒造生理级认知冲突（违背直觉的荒谬行为 + 不可思议后果）；严禁以 IMSA/WSC/Group C 圈内黑话起手 | 2秒跳出率大盘优化 |
| 单句与节奏 | 单句 ≤28 字，善用短句，呼吸感标点；年份一律汉字（"一九九四年"）；过 humanizer | humanizer §36–38 |
| 事实核查 | 戏剧化不等于造谣：所有性能数据、赛事转折必须与转录严格对位；删存疑细节比写错强 | Eagle / 日产 P2R 复验 |
| 结尾争议钩子 | 结尾上升到工业与规则伦理反思，抛出让评论区对立争论的问题（"你说这算天才的胜利还是规则的耻辱？"），禁鸡汤平淡收尾 | 完播率与互动率双考核 |


## 4. 素材/出镜禁区（两次都踩）

- **作者出镜常超出 zones ±5s 并簇边界 2–5 秒**：Nissan zones 到 475 但作者出到 478；到 645 但出到 648。
  → **定稿前必须用 1s 步长 SFace 把成片所用窗口逐秒复核一遍**（复用 denselocate 思路，阈值 0.25 起）。
- step=5 的 zones 只是初筛；0.35 阈值漏小脸/侧脸。宁可复核多花 2 分钟。
- 不同脸命中（车手老照片）不是禁区——SFace 同脸比对已自动排除（Eagle 的 1:55/2:20/7:20/9:15）。
- emo ref 从 vocals 切，与画面禁区**无关**（情感参考可以取作者说话段）。
- **素材必须与内容相符（2026-09-05）**：纪录片转录时间轴≈画面内容轴。按文案主题抽帧（每8s，拼 contact sheet），逐格验"画面内容是否对题 + 有无作者"，建**对照表（文案段→画面区间→状态）**再写 cuts。E1R 对照：2:04进气喇叭口→引擎段，测试场→底盘段，Monza实战→战绩段。**素材不符就改文案**，不硬配：E1R c8"Goodwood现存"无对应画面，改为"九台赛车三场胜利"配颁奖台。
- **工作目录/脚本输出一律 ASCII**：cv2.imwrite 中文路径静默失败（返回 False 不报错），sheet 白跑。教训：验货目录用英文名；控制台 GBK 看中文全是问号，核验用 unicode_escape 或 read 工具。

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
- **TTS 坏块定位法（2026-09-05，H-vvv P2）**：chunk1（41字） deterministic 输出 27s——首句后20s空+后句丢失+尾部乱码，重跑完全一致。定位流程：① seg 时长异常（同等字数 3 倍时长）即告警；② 切片转录验内容；③ 单句/组合对照实验（tA 单句1✓/tB 单句2✓/tC 改写组合✓/tE 原文单独✗/tF hook+原文✗）→锁定"原文双句组合"触发（疑似 ACO+Jost 双拉丁 token 长上下文，机制未定）。绕行：**拆成已验证的单句 chunk**（tA+tB），文字不变，重合后 9 段全 <15s、全文转录验收。教训：新 manifest 全片转录验收（数字/关键词）后再进 overlay。

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
- **rename/ glob 转义坑（2026-09-05）**：PowerShell 传进 python 的 `\\` 与 `\` 肉眼难辨，一次 rename 改错了目录（后恢复，有惊无险）。教训：rename 前先打印确认目标；目录枚举用 os.listdir + startswith 过滤，别拼转义字符串；中文目录在 GBK 控制台下显示为问号，repr 同样不可读。
- montage 音频分支旧写法 `atrim=start=start=` 双前缀 bug → 已修。
- `--bed-volume` 只影响 montage 中间件；mux 的 loudnorm 会重算 bed，勿依赖它调成品音量。

## 8. 成品包与发布

- 抖音规格：视频 16:9；标题 ≤55 字钩子+关键词；封面 16:9 大字 + 上下集角标；简介首行
  `中文标题:`、次行 `原视频:`、末行话题标签。
- DB 注册 `review` → 用户确认 → `confirm-video` → published（review 留副本）。
## 9. 复验清单（新视频上线前逐项过）

- [ ] **开场 0~2 秒声画核爆**：严禁慢动作与远景，必须为“濒死级疯狂驾驶”第一视角/特写；战歌 0 秒强音落地（禁淡入）+ 纯净引擎声浪 + 原声惊呼
- [ ] **语音按标点符号单句生成**：严禁复合长段喂给 TTS。以句号/感叹号/问号为绝对边界独立生成，确保单句内语气连贯不乱喘，句间 gap_ms 控制换气
- [ ] **字幕即说即显 + 单句聚焦**：严禁一次性展示多行剧透整段话。说到哪句显示哪句（单行居中），每句重点冲突词用 `<span class="highlight">` 金黄/亮色高亮
- [ ] **封面 100% 纯净无污染**：底图必须提取自纯净母本（严禁从带字幕/带HUD卡片的成片中截取）；标题收束在顶部独立渐变安全区，绝不遮挡赛车主体
- [ ] **片尾双阵营对决钩子**：抛出具象、对立的阵营投票（如“A vs B”），激发评论区站队点火，严禁鸡汤平淡收尾
- [ ] zones 已按用户指认的 ref-sec 生成，且**成片窗口 1s 步长复核零作者脸**
- [ ] 中插广告（转录口播段）整段已剔除
- [ ] 文案符合 `STORYTELLING.md`：黄金2秒爆点3选1、五步戏剧张力、三层工程与博弈深度下潜、未闭合悬念链
- [ ] 运行 `python bin/erchuang.py check-manifest --manifest <path>` 结果为 **PASS（0 错误）**
- [ ] 文案过 humanizer-bilibili；单句≤28字；年份一律汉字；被干趴/击败对象经转录事实核对
- [ ] narration = 你的音色 + 逐句 emo-ref；bed loudnorm -25 混音可闻
- [ ] hyperframes check 0 error 且 runtime 0 warnings；card 卡点 = 配音 timings.json
- [ ] 成品包含 mp4+封面+meta+简介；review → confirm → published

## 10. 历史发布记录与状态
- 2026-09-06 首批单集验证：`6yPcEkQVnAI_E1`（《8.0L卡车自吸干趴欧洲超跑？道奇毒蛇远征欧洲传奇》）。
- 2026-09-07 现象级爆款验证：`KK4TueysI14_E1`（《被重罚8分钟后，他反手在同一场比赛里赢了两次！》· 阿里·瓦塔宁 1985 蒙特卡洛拉力赛）。

## 11. 爆款视听与交付演进（2026-09-08 瓦塔宁蒙特卡洛实战复盘）

### 11.1 开场 0~2 秒“声画核爆定律”（拉住用户的绝对核心）
- **核心结论**：抖音用户停留决策在 **0.5 ~ 1.5 秒** 内完成，前 2 秒是压制跳出率的生死线。
- **画面铁律**：严禁静态车模、远景匀速巡航或发车台慢动作；必须挑出全片最惊险的**主观视角“濒死级疯狂驾驶”**（如贴石墙 200 码狂飙、冰雪悬崖大角度横滑）。
- **音频铁律**：开局 0 秒**绝对禁止淡入（fade-in）**，史诗战歌重拍直接炸响 + 赛车高转速狂暴声浪 + 领航员/车手真实惊叫原声（如 `"Dear god..."`）。
- **动效配合**：0 秒同步闪烁 HyperFrames 危险脉冲红光与时速 HUD，制造本能的生理级肾上腺素冲击。

### 11.2 语音合成“标点单句闭环法则”（彻底杜绝 AI 碎断与乱喘）
- **痛点根因**：以往将包含 2~3 个复合句的大段落（15~18秒）作为一个 chunk 喂给 TTS。模型遇到超长文本会在逗号处强行换气降调，把一句连贯完整的话切得支离破碎。
- **强制标准**：
  1. **严格以句号（。）、感叹号（！）、问号（？）为绝对边界建立单句生成单元**，严禁多句合并生成；
  2. 每一句话必须完整一口气读完，保证单句内语调和情绪起伏一气呵成；
  3. 句与句之间的停顿呼吸通过拼接参数 `gap_ms`（180~250ms）由编排控制，绝不让模型自行在半句中乱断。

### 11.3 字幕呈现“单句即说即显 + 重点高亮法则”
- **痛点根因**：以往在 HyperFrames 中偷懒使用 15 秒大段落字幕，将 2~3 行文本同屏显示，导致声音刚念第一小句，后续台词和结局悬念已被观众提前看完，破坏观影沉浸感。
- **强制标准**：
  1. **说到哪句显示哪句**：字幕轨时间轴必须精准对齐单句（通常 8~16 字，单行大字居中）；
  2. **严禁多行剧透**：当前句说完立刻切下一句，全屏始终保持单行聚焦；
  3. **重点词高亮**：每句话的核心冲突或极限参数用 `<span class="highlight">` 金黄/亮色高亮，增强视觉抓手。

### 11.4 封面设计“纯净底图与通栏大字法则”
- **痛点根因**：误从压制好特效与字幕的成片中截帧，导致片中字幕、HUD 卡片与封面标题多层重叠互踩。
- **强制标准**：
  1. **底图 100% 纯净**：必须从无字幕、无卡片的纯净母本视频（`visuals_clean_base.mp4`）中截取冲击力强的正面冲刺或动作瞬间；
  2. **安全区排版**：标题大字统一收束在顶部（或底部）独立半透渐变安全区，与赛车主体保持物理区隔，绝不遮挡车辆与驾驶员；
  3. **文字层级**：顶部小标签（赛事背景/悬念定位） + 双行或单行高对比爆款大字（黄/白黑描边）。

### 11.5 片尾“双阵营对决投票钩子”（评论区点火法则）
- **核心结论**：结尾绝不说教，不写鸡汤；
- **强制标准**：必须以极具争议与站队属性的**“A 阵营 vs B 阵营争议投票”**作为收口（如“开后驱硬斩四驱的罗尔 vs 怀疑物理定律的麦克雷”），引导评论区留评打卡，触发抖音推荐算法二度推荐。


