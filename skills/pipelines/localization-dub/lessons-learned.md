# Localization-Dub Pipeline — 实战避坑与最佳实践指南 (Lessons Learned)

> **适用范围**：使用 `localization-dub` 管线时，所有 Agent **必须在执行任何阶段前强制阅读本文档**。
> 本文档包含从真实项目中反复迭代总结的硬性规则，违反任何一条都会导致成品质量严重下降。

---

## 🚨 两条铁律 (Iron Rules)

### 铁律 A：变速策略分三级 (Tempo Strategy — 2026-08-09 修订)

**变速必须保听感，不能变怪（最高优先级约束）**。变速只是"贴合时长"的手段，任何变速若让声音变怪（语速突兀、机械感、音调失真），宁可溢出推挤或缩短译文，**绝不强行变速**。这是当初设"禁止 atempo"铁律的根本原因，修订后依然成立。

变速按以下三级策略，**从第一级开始，能用低级别就不用高级别**：

| 级别 | 手段 | 触发条件 | 幅度（听感已验证） |
|------|------|---------|---------|
| **1. 翻译预算控制（首选）** | 翻译 prompt 注入秒数硬约束 + 短句缩放下限 + 确定性截断兜底 | 转录后翻译时 | — |
| **2. 逐句 atempo** | 单句 `atempo`（保音高，`_atempo_wav`） | 合成后实测偏离目标 | **±5%（默认 tempo_budget，听感自然，已真机验证）** |
| **3. 全局 atempo 兜底** | 整段 `atempo`（`_apply_global_atempo`） | 漂移 > drift_budget(1.5s) 且 ≤ max_drift | ±4%（max_speed_factor 默认 1.04，听感可接受） |

**⚠️ 未验证上限（勿默认使用）**：代码里 `clamp_tempo_factor` 支持 `max_ratio=1.15`（15% 变速，来自 tachidubb 参数），但 **±5% 之外的中文听感未真机验证**，默认不应触发。只有明确确认听感仍自然时才可放宽。

**禁止**：
- ❌ 漂移 ≤ 1.5s 时仍全局变速（应由逐句对齐 + 溢出推挤吸收）
- ❌ 超出已验证听感的变速幅度（默认 5%，逐句；4%，全局）
- ❌ 变速后声音变怪仍强行使用（**宁可溢出推挤或缩短译文**）
- ❌ 截断超长音频尾部（句子说不完）——宁可溢出推挤或缩短译文
- ❌ 不同段落用不同变速倍率（除逐句对齐外）

**核心经验**：旧"完全禁止 atempo"导致超长句只能溢出推挤，访谈类视频累积漂移 5-13s。本次真机（tt-test）验证：**翻译预算打折（首要）+ 逐句 ±5% 变速 + 全局兜底**能把漂移压到 ~1.5s 内，主视频时长 = 原视频，且 ±5% 内听感自然。**变速幅度严格限制在听感已验证的范围内，是修订后铁律 A 的底线。**

### 铁律 A 补充：禁放慢 (No-Slowdown / allow_slowdown) — 2026-08-17 修订

**背景**：用户反馈"有时配音语速明显被拉慢，拖沓，放慢是没有必要的"。根因是**对齐策略**：流水线为让配音时长贴合英文原句时间槽，用 IndexTTS 2.5 的 `duration_factor`（双次合成）或逐句 atempo 把"自然合成短于原句"的句子**拉长减速**。对翻译后很短的句子（尤其 1~2s 短句），拉长幅度可达 1.2~3.4×，听感明显拖沓。

**判断标准**：放慢只服务于"音画同步"这个验收指标，但**用户感知的听感优先于对齐达标率**。对齐的收益（字幕/画面/配音同步）不值得用"读得怪"换。

**解决方案**：新增配置 `pipeline.alignment.allow_slowdown`（`apps/auto-dub/config.yaml`，默认 `true` 保持既有行为）：
- `true`：允许 `duration_factor`/atempo 拉长配音贴合原句（追求音画同步，现状）
- `false`：**只禁放慢、允许加快**——合成 `factor>1` 时保留自然语速版本不重合成；逐句/全局 atempo 因子下限钳到 `1.0`
- **优先级**：`video.metadata.allow_slowdown` > `config.pipeline.alignment.allow_slowdown`（单视频可用 DB metadata 覆盖，不影响全局）

**代码落点**（`apps/auto-dub/batch/pipeline_automator.py`）：
1. `_synthesize_indextts`：`factor > 1.0` 且禁放慢 → 直接复制自然合成版本，不做第二次拉长重合成
2. `compute_utterance_tempo` / `clamp_tempo_factor`：新增 `allow_slowdown` 参数，`lo` 钳到 `1.0`
3. 全局 atempo 兜底：`min_speed = max(min_speed, 1.0)`，禁止整体放慢

**真机验证**（`auto-dub-5vEEBhbfUWw`，2026-08-17）：
- 放慢最明显的长句 u43（35 字译文）：禁放慢前被拉长到 **10.47s ≈ 3.3 字/秒** → 禁放慢后 **6.69s ≈ 5.2 字/秒**，恢复自然语速
- 全片变速副本均为 `_t10xx.wav`（因子 ≥1.0），无任何减速副本
- 配音总时长仍对齐 606.3s（0 漂移，SRT 0ms）：多数句子自然语速本就够长，只有少数被拉长的短句问题被消除
- **注意**：极短句（如「全部。」3 字）`out_of_budget` 的慢是 TTS 短句固有起步开销（真实 cps 3.1~4.2），不是对齐放慢，`allow_slowdown=false` 不改变它

**复盘教训**：
- 分析"是否被放慢"不要用"中文字数/4.1cps"的估算（短句真实 cps 远低于校准值，会误判超长句为放慢）；应直接对比新旧两版同句 `actual` 时长，或检查变速副本文件名的因子
- 音频复用风险：改 `allow_slowdown` 后必须**清空 `assets/audio/`** 并删除 `assets/edit/compose/publish` checkpoint 再重跑，否则旧的"放慢版" WAV 被 `is_valid_existing` 复用，改动不生效

---

### 铁律 B：串行排队混音算法 (Serial Queue Mix)

所有配音段落在主音轨上按**串行排队**方式放置，保证每段语音 **100% 完整播放、0% 重叠**。

#### 算法规则：

```
对于第 i 段配音：
  ideal_start = 原始英文时间戳（秒）
  actual_start = max(ideal_start, previous_end + 0.10)   ← 100ms 最小停顿
  actual_end   = actual_start + len(tts_audio) / sample_rate
  previous_end = actual_end
```

#### 关键约束：

| 约束项 | 值 | 说明 |
|--------|-----|------|
| 最小段落间隔 | **100ms** | 相邻段落物理隔离，杜绝重叠 |
| 段尾淡出 | **15ms** | 消除截断爆音与边缘噪声 |
| 段首淡入 | **15ms** | 消除起始爆音 |
| 截断 | **禁止** | 每段 TTS 音频必须完整放入，不允许裁剪尾部 |
| 变速 | **禁止** | 见铁律 A |

#### 字幕动态重同步：

SRT 字幕的时间戳**必须**根据混音后各段的 `actual_start` 和 `actual_end` 重新生成，**严禁**沿用原始英文时间戳。

---

## 📋 各阶段执行要点

### Script 阶段（翻译）
- **尽量简炼**：用地道凝练的中文口语表达，避免不必要的长句
- **严禁过度砍删**：不为了机械匹配时间而删除有意义的内容
- 极短段落（`< 0.8s`）可精简为 2~4 个字

### Assets 阶段（TTS 合成）
- 全局锚点文件 `voice_reference.wav`（5~10 秒纯净人声）必须存在
- 每次 TTS 调用必须传入 `reference_wav_path`，保证多段音色 100% 一致
- 保持 `seed=42`、`cfg_value=3.0` 参数稳定

### Edit 阶段（时间轴规划）
- `edit_decisions` 必须包含 `mix_algorithm: "serial_queue"`
- `timing_drift_policy: "allow_natural_extension"` — 允许自然延伸
- 禁止输出**超出铁律 A 已验证听感**的 atempo 变速指令（逐句 ±5% / 全局 ±4%；见上「两条铁律」）

### Compose 阶段（混音渲染）
- 严格执行 Serial Queue Mix 算法
- 渲染后校验：相邻段落间隔 ≥ 100ms，无能量重叠区间
- SRT 字幕必须与实际音频位置毫秒级同步

---

## ⚠️ 反模式警示 (Anti-Patterns)

以下做法在本管线中**绝对禁止**：

1. ❌ 按原始英文时间戳硬放中文音频 → 必然重叠
2. ❌ 用 atempo 压缩音频去适配时间窗 → 语速失真（**修订：逐句 ≤1.15 与末段兜底除外**）
3. ❌ 截断超长音频的尾部 → 句子说不完
4. ❌ 字幕沿用英文原始时间戳 → 字幕脱节
5. ❌ 不同段落使用不同变速倍率 → 全片语速混乱

---

## 🎙️ 多人访谈配音 — 实战经验 (Multi-Speaker Interview Best Practices)

> 来源：`auto-dub-tt-test`（TikTok 三人访谈，重叠说话）真机迭代（2026-08-09）。

### 1. 翻译预算必须打折 (cps Discount)

**IndexTTS2 短句真实语速远低于长文本校准值**：
- 长文本校准 cps ≈ 5.8（参考文本 72 字 / 12.41s）
- 短句实测 cps ≈ **3.1~4.2**（句首静音 + 首音节拉伸的固定开销）

**正确做法**：翻译字数预算 = 实测 cps × **0.7**（`cps_safety_factor`）。否则按 5.8 给预算，译文必然过长，IndexTTS 合成超时。

### 2. 短句预算随时长缩放，不能用固定下限 (Short-Sentence Budget)

固定 `min_budget=15` 会让 1~2s 短句被逼出 15 字译文，合成必然超长。**短句下限随时长缩放**（如 1.2s → 3~4 字），只保留核心回应，靠溢出推挤吸收残余。

### 3. 翻译长度硬约束 + 确定性截断兜底 (Hard Length Constraint + Deterministic Truncation)

LLM 对"贴近 X 字"的软约束遵守度不稳定。三层保障：
1. **短句硬约束 prompt**：`该句仅 X 秒，译文必须在 X 字以内，否则超时被截断`
2. **前文上下文**：最近 4 条已译行（600 字符预算），保人名/代词/称谓一致
3. **确定性截断**：LLM 重译后仍超预算 → 按标点边界截断 + 省略号（`_truncate_to_budget`），不依赖 LLM 自觉

### 4. pyannote 说话人分裂 → 必须合并 (Cluster Merge)

**pyannote 在重叠访谈上常把 N 个真实说话人分裂成 N+1 个 cluster**（tt-test 3 人被切成 4）。
- 判定：对每个 cluster 的 voice_ref 提 speaker embedding，余弦相似度 ≥ 0.7 合并
- **必须用拼接后的 voice_ref 提 embedding**（相似度 0.839 可靠），用原始波形切片不准（0.725）
- 合并后同一真实说话人只有一个音色（修复"同一人两种音色"）

### 5. word 级说话人切分 (Word-Level Speaker Split)

同一 Whisper segment 内跨说话人的句子（主持人问"西尔维，迪诺出轨几次？"+ Sylvie 答"四次"）按 **word 时间中点归属 speaker_turn** 切分子段。

**模型边界**：pyannote 不产生说话人边界的极短插话（如 0.4s 的"四次"）切不开——**靠人工审校兜底**（见 wayfinder map）。

### 6. 一人一音轨 + 声像分离 (Per-Speaker Stems)

每个说话人独立导出 `dub_{SPEAKER_N}.wav` stem + 立体声声像分离（声像 map）。便于定位音色问题、后期独立调音量。

### 7. 男声音高锚定是反模式 (Pitch Anchor = Anti-Pattern)

旧做法用 `asetrate + aresample + atempo` 把"克隆成女声的男声"降调——**已删除**。强制降调会引入机械感/变调（用户反馈"音色不对/男声变慢变调"）。正确做法是**在源头提供更长更干净的声纹参考**（多段择优拼接至 ~30s），让克隆本身稳定。

### 8. 合成失败重试策略 (Retry Policy)

合成失败（IndexTTS 出静音/超长/报错）**重试只浪费 GPU 时间**，多次重试结果雷同。策略：
- **单人**：重试 ≤ 2 次
- **多人**：不重试，直接转人工审校

### 9. 全局调速是末段兜底，不是默认手段 (Global Tempo = Last Resort)

漂移 ≤ drift_budget(1.5s) 时由逐句对齐 + 溢出推挤吸收；只有漂移 > 1.5s 且 ≤ max_drift 才触发全局 atempo。`_should_apply_global_atempo` 是纯函数判定。

---

## 🎨 系列封面设计 — 实战经验 (Cover Series Best Practices)

> 来源：`auto-dub-gaDdrDdczO4` 封面重建（2026-08-08 验证）。

### 铁律 C：系列封面用「固定 HTML 母版」，不做图生图

- ❌ 不要用 `image_selector` 每期重新生图 → 人物、色彩、字体、构图必然漂移
- ❌ 不要让右侧每期换视频缩略图（`thumb_path` 兜底）→ 系列感破碎
- ✅ 全系列共用 `apps/auto-dub/templates/cover.html` 一个母版
- ✅ 右侧使用 HTML/CSS 绘制固定技术视觉（代码窗口/技能节点/版本徽章），不依赖任何图片
- ✅ 中文标题一律由 HTML 文本渲染，绝不交给生图模型（杜绝错别字）

### 单母图双画幅：一张 16:9 母图内嵌完整 4:3 主封面区

- 画布固定 `1920x1080`；**中央** `1440x1080`（x=240..1680）为完整 4:3 主封面区
- 左右各 `240px` 只做延展背景（延续渐变，不放任何关键信息）
- 4:3 场景直接用中央区域等比输出（1200x900），**禁止**从普通 16:9 成品临时裁图
- 只维护一张母图，两个平台画幅共用，杜绝双版本漂移

### 关键坐标（cover.html 当前基线）

| 元素 | 位置 |
|------|------|
| 4:3 主区 | x `240..1680`，y `0..1080` |
| 左侧内容列 `.content` | top `115px`、bottom `115px`、left `320px`、宽 `820px` |
| 右侧技术面板 `.tech-panel` | top `115px`、right `288px`、宽 `480px`、高 `850px` |
| 垂直对齐 | 左右两块统一 `top:115 / bottom:115`，上下对称居中 |
| 左侧垂直分布 | `.content` 用 `justify-content: space-between`，顶部与面板平齐、底部金句贴左栏底部 |

### 排版避坑

- 左侧内容若用 `justify-content: center` 会在区间内下沉，顶部与右侧面板不平齐 → 用 `space-between` 或 `flex-start`
- 底部金句 `.footer-quote` **必须放进 `.content` 容器内**（`margin-top:auto`），不能绝对定位到画布底部，否则内容区移动时它原地不动
- 左右两块要同时调 `top/bottom`，保证顶边与底边都平齐

### HyperFrames 渲染避坑

- PowerShell 直接传 `--variables '{...}'` 会吞掉双引号导致 JSON 解析失败 → 改用 `--variables-file path.json`
- 静态单帧封面在 `#root` 上补 `data-no-timeline` 可跳过 45s 的 timeline 轮询超时
- 字体 `url('/e:/...')` 绝对路径在渲染 file server 下 404，会回退系统字体；如需精确字体，放到模板同目录用相对路径


