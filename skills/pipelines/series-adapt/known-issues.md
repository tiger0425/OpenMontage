# Known Issues & Fixes — series-adapt Pipeline

**遇到问题先查这里。** 按症状查找 → 找到根因 → 按修复流程执行 → 在关联规范处确认已回写。
每个 director skill 的 `When to Use` 都引用本文件；review 阶段（lessons-protocol）要求新问题必须登记到这里。

---

## 症状索引（按现象快速定位）

| # | 症状 | 跳到 |
|---|---|---|
| K-01 | 语音"没说完"画面就切走了 / 切点落在句子中间 | [K-01 语音边界](#k-01-分镜窗口没有跟随语音句边界) |
| K-02 | 语音出来晚（画面先出几秒没声音） | [K-02 TTS 前导静音](#k-02-tts-wav-自带前导静音导致语音晚出) |
| K-03 | 分镜画面全是同一个/大量重复 | [K-03 分镜图片重复](#k-03-分镜图片重复或视觉雷同) |
| K-04 | 人脸被图钉/红线/标签遮挡 | [K-04 人脸被装饰元素覆盖](#k-04-人脸被装饰元素覆盖) |
| K-05 | 合并后某些片段内容丢失（被裁掉） | [K-05 盲目裁头](#k-05-合并时盲目裁头切掉真实内容) |
| K-06 | 结尾语音被 fade 压掉/没听完 | [K-06 结尾余量不足](#k-06-结尾语音被截断或余量不足) |
| K-07 | 片头标题/集数被纸卡挡住 | [K-07 片头 z-index 层级](#k-07-片头元素被遮挡) |
| K-08 | 分镜之间有长空白/不连贯 | [K-08 GSAP 时间偏移遗漏](#k-08-gsap-时间偏移遗漏导致空白) |
| K-09 | 渲染失败 audio.aac 缺失（12fps） | [K-09 12fps 渲染音频 bug](#k-09-12fps-渲染音频提取失败) |
| K-10 | 生图批次互相覆盖丢失 | [K-10 批量生图非幂等](#k-10-批量生图脚本互相覆盖) |
| K-11 | 画面判定"空白"误报/漏报 | [K-11 用错验证指标](#k-11-画面内容验证用错指标) |
| K-12 | scene_plan 重做后时长回到旧值 | [K-12 重做 scene_plan 丢音频校正](#k-12-重做-scene_plan-丢失音频时长校正) |
| K-13 | 视频画质低/模糊（图片分辨率不足） | [K-13 生图分辨率不足](#k-13-生图分辨率不足) |

---

## K-01 分镜窗口没有跟随语音句边界

**症状**：语音"没说完"画面就切走；切点落在句子中间；节奏感差。
**根因**：sub-shot 窗口用 `词数 ÷ 语速` 均分生成，未对 TTS 音频做 whisper 转写（EP.02 实测 s01 均分 8.4s/窗 vs 语音句 7.04/9.80/12.64s 不均匀，多处切在句中）。
**修复流程**：
1. TTS 生成后先**裁前导静音**（见 K-02）
2. 用 whisper（medium, cuda）转写 clean WAV，取 seg 起止为窗口锚点
3. 用 L-009 连续窗口公式：`start_i = max(prev_end - 0.5, voice_start_i - 0.4)`，`end_i = voice_end_i + 0.6`（幕末 +1.0）
4. 窗口数=seg 数；图片按窗口数循环复用（同幕内容一致）
**标准工具（唯一合法路径）**：`tools/gen_voice_windows.py <episode_dir>`（转写+窗口+design 一步生成）。禁止手工词数均分。
**关联**：L-049 · scene-director `Step 2b` · tools/gen_voice_windows.py 模式
**验证**：转写 seg 边界 ≈ 画面切点（±0.2s）；无"切在句中"

---

## K-02 TTS WAV 自带前导静音导致语音晚出

**症状**：画面先出 1-7 秒没声音；每句"出来晚"；感知"没说完"。
**根因**：IndexTTS2 合成 WAV 自带 1.2-7.2s 前导静音（EP.02 实测 s09 7.17s、s06 4.2s、s08 4.3s），即使 vo data-start 正确，语音内容也要等静音过完才出声。
**修复流程**：
1. `ffmpeg -i s.wav -af silencedetect=noise=-50dB:d=0.15 -f null -` 检测前导静音
2. 裁掉 `lead - 0.15s`（保留缓冲）：`ffmpeg -ss <cut> -i s.wav -c copy s_clean.wav`
3. 用 clean WAV 重新转写、重算窗口、组装 workspace
4. 验证 clean WAV 前导 ≤0.2s
**标准工具**：`tools/trim_audio_lead.py <episode_dir>`（检测+裁剪+报告一步完成，幂等）。
**关联**：L-050 · asset-director `Transcribe the final narration` / `VOICE-AUDIO PIPELINE`

---

## K-03 分镜图片重复或视觉雷同

**症状**：大量分镜画面相同；"一个分镜不停重复"；同主体同参考帧。
**根因**（三层）：
1. 每幕只生成 1 张 hero 图复制到所有分镜（L-035）
2. 全部图用同一参考帧+同一主语 img2img（L-036）——MD5 不同但视觉雷同
3. 构成族按幕分配而非按分镜分配（左图右文系列重复）
**修复流程**：
1. 每个 sub-shot 用**不同参考帧**（分散帧库）+ **不同画面主体**描述
2. 人物图用脸保护版 style（见 K-04）
3. 构成族**按分镜轮换**（相邻不同）；生成器强制校验（fams 数≠分镜数报错）
4. 唯一性验证：MD5 + 视觉抽查相邻分镜主体不同
**关联**：L-035 · L-036 · asset-director `EVERY SUB-SHOT GETS ITS OWN IMAGE` / `DISTINCT REFERENCES` · compose-director `SUB-SHOT LEVEL variety`
**验证**：抽查帧 MD5 全不同 + 视觉模型确认相邻分镜主体不同

---

## K-04 人脸被装饰元素覆盖

**症状**：人脸上有红线/图钉/标签文字；模型幻觉人名（如把祝榆生写成 "Dr. Zhao Tianlin"）。
**根因**：
1. prompt 里 label 指令 → 模型把文字画在图上随机位置（压脸）
2. 共享 style block 含 "red string and brass pins"（yaml 里 4 种措辞）→ 模型把装饰画到脸上
**修复流程**：
1. **人物图 prompt 禁止 label**（L-037），label 由 HTML 叠加
2. 人物图用**脸保护 style**（L-038）：剥离全部 red-string/brass-pin 措辞 + 追加 "The face of any person must be completely clear and unobstructed: no lines, no pins, no string, no text..."
3. 身上/背景装饰可保留，只有脸必须干净
**关联**：L-037 · L-038 · asset-director `NO LABEL TEXT IN PERSON IMAGES` / `FACE-PROTECTED STYLE`
**验证**：视觉模型确认人脸无元素横穿

---

## K-05 合并时盲目裁头切掉真实内容

**症状**：合并后某些片段内容丢失；开头内容突然中断。
**根因**：EP.01 分段带 2.6s 前导空白所以裁头；新集若没有空白（scene 从 0 起）照抄裁头逻辑 = 切掉真实内容（EP.02 曾丢 23s）。
**修复流程**：
1. 裁头前**验证**每段前 3s 是否真的空白（volumedetect）
2. 统一方案（L-048）：scene-1 从 2.6 起 + vo=3.0 + 合并裁 2.6s；或 scene-1 从 0 起 + vo=0.4 + 不裁——**二选一，禁止混用**
3. 合并后核对总时长 = Σ(各幕时长) - 裁剪量
**关联**：L-040 · L-048 · compose-director `Merge: verify head-trim before applying`
**验证**：合并后每幕开头 0.5s 有画面+语音

---

## K-06 结尾语音被截断或余量不足

**症状**：最后一句没听完就结束；fade 压掉尾音。
**根因**：outro 时长 = 语音时长（无余量）或 fade 从 total-1s 开始压在语音上；没算 vo 前置（0.4s）吃掉了 hold。
**修复流程**：
1. outro 时长 = vo前置 + 净语音 + **≥2s 空屏停留**（EP.01 s10: 27.7s 视频 vs 13.1s 语音）
2. 结尾 fade ≤0.5s，且从 `total - 0.5` 开始
3. 验证：`语音结束时间 < 视频结束时间 - 1.5s`
**关联**：L-041 · scene-director `Step 2: Assign scene types and durations` · merge fade 参数
**验证**：结尾最后 1s 近静音（空屏停留），最后一句完整

---

## K-07 片头元素被遮挡

**症状**：片头 IRON DRAGON 标题/EP.NN stamp 看不见或被纸卡盖住。
**根因**：`.paper-cut { z-index: 4 }` 盖住无 z-index 的 headline/stamp（EP.01 无此 z-index，靠 DOM 顺序）。
**修复流程**：
1. paper-cut/paper-card **不设 z-index**（DOM 顺序决定层级）
2. headline/stamp 显式 `z-index: 8`
3. 组装后 lint + 视觉确认片头元素可见
**关联**：L-044 · tools/assemble_episode.py `CSS`
**验证**：片头帧含 IRON DRAGON + EP.NN

---

## K-08 GSAP 时间偏移遗漏导致空白

**症状**：加片头/偏移后分镜间出现 1-3s 空白；board 淡出提前。
**根因**：时间偏移正则只匹配 `tl.fromTo`（两组 vars），`tl.to`/`tl.set`（一组 vars）未偏移。
**修复流程**：
1. 偏移脚本必须匹配两种模式：fromTo（两组 `{..},{..}`）+ to/set（一组 `{..}`）
2. 偏移后验证：每个 board 淡出结束 ≈ 下一 scene 淡入开始（gap ≤0.2s）
3. 片头偏移脚本要幂等（检测 scene-1 已偏移则跳过）
**关联**：L-043 · tools/build_episode_parts.py `JS generation`
**验证**：逐 scene 检查 board fade 时间链

---

## K-09 12fps 渲染音频提取失败

**症状**：`hyperframes render -f 12` 报 audio.aac 缺失/打不开。
**根因**：hyperframes CLI 12fps 渲染的音频提取 bug（已验证）。
**修复流程**：**一律 30fps 渲染**；Vox 12fps 签名用 stepped keyframes / 停顿 2-3 帧实现（L-028），不是渲染帧率。
**关联**：L-045 · compose-director `Step 4: Render`
**验证**：渲染成功且含音频流

---

## K-10 批量生图脚本互相覆盖

**症状**：分批跑生图后前面批次图片丢失。
**根因**：脚本里有"清空输出目录"步骤，分批运行时每批先删光再生成。
**修复流程**：
1. 生图脚本**只生成缺失文件**（幂等）
2. 清空仅通过显式 env（`CLEAN_FIRST=1`），且一次全量跑完
**关联**：L-046 · asset-director `Idempotent batch generation`
**验证**：图片数 = 计划分镜数，无缺失

---

## K-11 画面内容验证用错指标

**症状**：浅色纸面背景画面被判"空白"（std 低），或真空白漏检。
**根因**：用 luminance std 判断内容有无——浅米黄纸面 std≈9 但内容占 92-99%。
**修复流程**：用**非背景像素占比**（dominant color + distinct color 数）：非背景 <50% 或颜色数 <500 才算空白。
**关联**：L-047 · lessons-protocol `QA verification`
**验证**：抽查帧非背景像素 90%+ 且颜色数 >2000

---

## K-12 重做 scene_plan 丢失音频时长校正

**症状**：某幕语音截断；scene 时长回到词数预算而非实际音频。
**根因**：scene_plan 因构成族/布局重做时重新生成，时长按词数算，丢了"音频时长+hold"校正（EP.02 曾 7 幕截断，最严重 19.4s）。
**修复流程**：**任何 scene_plan 重新生成后**必须重跑音频校正：`scene时长 = ffprobe(clean_wav) + hold(0.6/1.0s)`，并验证每幕 plan ≥ 音频。
**关联**：L-039 · asset-director `DURATION CHECK` · 生成器流程
**验证**：每幕 plan 时长 ≥ 音频时长

---

## K-13 生图分辨率不足

**症状**：画面模糊/放大后糊；图片尺寸非 1920×1080。
**根因**：google_imagen 输出 1365-1376×768（请求 1920×1080 但模型降级）。
**修复流程**：
1. 生图后**验证尺寸**（PIL），不足则放大或重生成
2. HyperFrames `object-fit: cover` 会放大 768→1080（约 1.4x）导致模糊——优先保证出图分辨率
**关联**：asset-director `Consistency rules`
**验证**：全部图片 ≥1920×1080

---

## 登记新问题（规则）

review 阶段发现新问题（lessons-protocol 第 4 条）时：
1. 在 `final_review.json` 加 lesson（L-NNN）
2. **同步登记到本文件**：按症状加一行到索引表 + 写完整条目（症状/根因/修复流程/关联/验证）
3. 在对应 director skill 回写规则
4. 三处缺一不可——lessons 是记录，本文件是检索，director 是执行
