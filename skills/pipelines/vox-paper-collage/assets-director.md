# Assets Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 5（配音）、STATE 7（每节拍一张拼贴图）+ 音乐 + 纸 ASMR：为每个节拍生成一张"旧报纸档案拼贴"图（agent 直调 `image_selector`，不产 .txt 手动喂），用 IndexTTS2 生成旁白，用 Pixabay 搜音乐、Freesound 搜纸 ASMR。产出 `asset_manifest`。

## 输入

- scene_plan（节拍表 + 每节拍视觉想法）
- script（旁白全文）

## 流程

### 0. TTS + whisper（VOICE-LED 时间戳，2026-08 修订）

**本阶段第一步**：先执行 TTS 全段合成 + whisper 时间戳提取，再生成图像。这是 scene_plan 字数估算的验证步骤。

```
script 定稿
  → scene_plan（已完成，时间戳 = 字数估算 4.7 字/秒）
  → assets 阶段：
      0. TTS 全段合成（IndexTTS2，20-25s 批次）
      1. whisper 提取词级/句级时间戳（timestamps JSON）
      2. 对比 scene_plan 估算时间戳：若偏差 >5% → 回到 scene_plan 重排分镜
      3. 生成图像（element mega-grid + bg textures + composed-scene ref + thumbnails）
  → edit
  → compose
```

**字数估算 vs 实测对比**：
- 若所有段落偏差 ≤5% → 直接用估算时间戳继续，无需重排
- 若某段偏差 >5% → 回到 scene_plan，把该段估算时间戳替换为 whisper 真实时间戳，重排该段分镜

### 1. 图像（每节拍一张，STATE 7）

对每个节拍，转换成一个完整自足的拼贴图提示词：

**思考过程（不输出）**：对每个节拍找到核心想法，而非字面词。选择最强的纪录片视觉：物体、文件、地图、时间线片段、半色调人物、地点。选择一个英雄元素，至多 2-3 个支撑元素，以及服务故事的背景。绝不逐词插图。可视化 IDEA。

**提示词结构**（一个自然散文块）：

1. **SCENE**：本节拍的具体构图。一个英雄元素（主导，约 70% 视觉权重），至多 2-3 个支撑元素，大量负空间。若节拍带有日期/名字/数字，可作为一个 1-4 词的短标签出现在纸条或印章上。否则无文字。
2. **STYLE BLOCK**：每个提示词必须 verbatim 包含 `templates/style_block.md` 全文（剔除文件头注释）。
3. **CLOSER**：每个提示词以 `templates/closer.md` 全文精确结尾（剔除文件头注释）。

提示词 = SCENE 描述 + STYLE BLOCK + CLOSER，三者拼成一个块，经 `image_selector` 调用。

**语言红线（`bilingual-spec.md §10`，硬性）**：

- 生图 prompt **一律英文**，无论 narration_language（STYLE BLOCK / CLOSER 本来就是英文模板）
- **中文字符绝不进生图 prompt**（AI 生图中文字必错，零例外）——中文标题/标签/图章全部走 CSS 渲染
- Recurring Subject Rule（§9）：同一主体跨拍复现时 prompt 中描述措辞逐字一致

**工具**：`image_selector`（首选 google_imagen；若风格遵循不达标，升级 FLUX 需 FAL_KEY——先告知 EP）。调用前必须阅读 Layer 3 技能（`google-gemini-image` / `flux-best-practices` 等，查工具 agent_skills 字段）。

### 2. 旁白（STATE 5，脚本批准后）

- 工具：`tts_selector` → indextts_tts 首选
- 参考音色约定：`spk_audio_prompt` → `INDEXTTS_VOICE_REF` 环境变量 → 仓库 `voice_reference.wav` 兜底
- 语音方向（引擎 verbatim）：calm deadpan male narrator, mid-range, mild gravitas, documentary read。语速见 `bilingual-spec.md §1/§10`（en ~155 wpm；zh ~4.7 字/秒，speed=1.0 零变速）
- 生产规则：20-25 秒批次合成避免失真；每批 2-5 次重生成取最佳；批次间节奏匹配保证接缝无缝；冷开场批次是最高优先级 take
- 语言：narration_language（en/zh），en 用英文旁白，zh 用中文旁白（同音色）
- 调用前必须阅读 Layer 3 技能（`voxcpm-tts` / `elevenlabs-tts` 等，查工具 agent_skills 字段）

### 3. 音乐（Pixabay）

- 工具：`pixabay_music`（royalty-free music search）
- 搜索词来自 `templates/music_prompt.md`（Epic Egyptian trailer score 关键词）
- 音乐仅用于成片混音，不进 clip 动画（clip 时长 = 语音段时长）

### 4. 纸 ASMR（Freesound）

- 工具：`freesound_music`
- 搜索：paper slide / cardstock tap / tape press / stamp thud / string zip / pin click / soft room tone
- 用于 clip 的环境音效层与成片音效点缀

## 质量要求

- 模板红线：STYLE BLOCK 与 CLOSER 必须 verbatim 拼接，禁止改写/缩写
- 每节拍一张图，节拍与图像一一对应
- 所有生成物记录 provenance（模型、seed、prompt 路径）
- 物理校验：所有资产文件存在且非空
- Layer 3 技能在写提示词前阅读并记录到 `layer3_skills_read`

## 成功标准

- `asset_manifest` 通过 schema 校验
- 每节拍一张图 + 旁白 + 音乐 + ASMR，文件全部存在
- `layer3_skills_read` 完整

## 冒烟片沉淀（2026-08）

### 多宫格参考图流程（2026-08 用户确认，最高优先级）

**先出"成品效果图"作为定位参照，再分解层。** 用户原话："先生成一个六分镜的多宫格图，让我知道最终的样子，然后你再拆分生成单独的元素图，组合时也按着分镜图的位置出现。"

1. **先生成 6 分镜多宫格参考图**（2×3 布局，每格 = 该分镜最终完整拼贴效果，含所有元素位置/叠压关系）
   - 提示词：6 个 panel 分别描述每个分镜的完整构图，`style_block.md` + `closer.md` verbatim
   - 竖屏项目用 9:16 比例（如 1296×2304）
2. **用户确认参考图**后，再拆分生成独立元素图
3. **组装时元素按参考图位置出现**（HyperFrames 定位依据参考图）
4. **文字类装饰（图章/标签/胶带/红线/图钉/大字）→ CSS 纯渲染零成本**，不生成图片——模型生成文字类图章必然多元素堆叠（2026-08 实测 6 个连通域），CSS 是唯一可靠方案

### 图像生成（一张图 = 一个元素）

- **关键教训（2026-08）**：模型无法可靠生成"孤立单元素"——提示词写"isolated single stamp"仍会生成多元素场景。**用连通域分析（PIL + scipy.ndimage.label）程序化验证**，元素数 >1 的弃用或改 CSS
- 每个元素**独立生成**：单物体、纯色底（#D8C7A3）、居中、提示词只描述这一个物体 + "no other objects, isolated, generous empty space"
- 生成后 PIL 抠透明（色彩距离阈值 + bbox 裁剪），得到带 alpha 的独立元素 PNG
- **真实新闻图 → img2img 风格参考生成**（2026-08 用户确认）：真实新闻图**不作为原图直接贴入**，而是作为**图像风格参考**（image_path / image_url 参数传入生成模型），结合 VOX 拼贴风格提示词（halftone 半色调/剪报/纸张纤维/撕裂边缘/单一主体），生成"保留真实内容但符合拼贴风格"的独立元素。例：Bessent 待办清单新闻照 → halftone 剪报版待办清单元素
- 抽象数据 → 直接生成 VOX 风格图；装饰 → CSS 渲染
- 提示词质量决定风格成败：明确材质（新闻纸纤维/撕裂边缘/半色调）+ 光源 + 单一主体，不要堆砌

### 元素清单来源（2026-08 用户确认）

**元素清单从语音文本中提取**——语音里提到的每个关键名词（2.4万亿、TOP2、7%、未来已来、Fable 5、日期等）自动成为元素：
- 数字/专名/情绪词 → 醒目元素（大字 headline / 图章 stamp）
- 内容主体（发布会/榜单/K线/地图）→ hero 图片元素
- 辅助信息（地点/平台/型号）→ 标签条 tstrip
- 每分镜 = hero 图（1 张）+ 关键名词元素（1-3 个）+ CSS 装饰（2-4 个）

### 中文配音（IndexTTS2 / VoxCPM）

- 语速基准：**中文 ~4.7 字/秒**（1 分钟 ≈ 230-250 字），不要按英文 2.5wps 折算
- `speed=1.0` 零变速；speed<0.8 产生 resample 杂音
- 多段合并单文件：`ffmpeg -filter_complex "[0:a]adelay=0|0[a0];...amix=inputs=N:normalize=0"` 
- 参考音色统一用同一文件（spk_audio_prompt），保证多段音色一致
- **每段时长硬校验**：ffprobe 实测每段 ≤ 分镜时长上限（如 10s 分镜 → 每段 ≤ 9.5s），超长先精简文本重生成，禁止硬塞时间码（重叠事故根因）

### 时间戳提取（语音驱动核心）

- TTS 完成后立即 whisper 转写（`word_timestamps=True`），输出词级+句级时间戳 JSON
- 句级 segments 时间戳用于 scene_plan 分镜规划
- 短语级时间 = 段内按字符比例分配（中文 1 字符 = 1 权重，拉丁/空格 ≈ 0.3-0.55）
- 时间戳 JSON 保存至 `assets/audio/timestamps_*.json`，供 scene_plan 与 compose 引用

### 真实数据元素标准流程（2026-08 用户确认，禁止 AI 编造数据）

**新闻/纪录片的数据类元素（K线/榜单/参数/涨幅）必须真实。** 完整正确流程：

```
STEP 1 获取真实数据
  - 行情：yfinance（pip install yfinance）拉取真实 OHLC，如 9988.HK
  - 参数/排名：官方发布文档 / 已核实事实（record source）
STEP 2 matplotlib 画真实数据参照图
  - 真实数据 → 报纸风格图表（白底 #F5EFDC、黑线条、等宽字体、红强调）
  - 作用：作为 img2img 的参照底图（数据真实 + 布局可控）
  - 注意：matplotlib 直出效果简陋，不能直接用，必须走 STEP 3
STEP 3 img2img VOX 风格化（关键）
  - image_selector.execute({'image_path': 参照图, 'prompt': VOX风格提示词})
  - 提示词必须含：'SOLID FLAT TAN paper background color #D8C7A3 (background must be one uniform flat color)'
    + halftone 印刷质感 + 保留原数据形状
  - ⚠️ 不加纯色底约束 → AI 生成全幅拼贴场景图 → 抠不出透明（2026-08 实测教训）
STEP 4 PIL 抠透明
  - 背景色取四角平均（生成后实测约 [210,193,158]，非纯 #D8C7A3 但接近）
  - 色彩距离阈值 + bbox 裁剪 → 透明异形 PNG
  - 校验：opaque 比例 10-50% 为合理（图表类）；>70% 说明背景没抠干净
```

### AI 幻觉红线（2026-08 用户确认）

- **模型名/数字/日期必须来自数据源**，提示词中显式写出精确值
- 反面教训：文生图"Qwen=Fable5 对比图"被 AI 幻觉成 Gemini（模型名错误）——真实内容类必须 img2img 参照或显式写死名称
- matplotlib 直出图虽真实但简陋（用户否决）——必须 img2img 重绘为 VOX 质感
