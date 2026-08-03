# Assets Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 5（配音）、STATE 7（每节拍一张拼贴图）+ 音乐 + 纸 ASMR：为每个节拍生成一张"旧报纸档案拼贴"图（agent 直调 `image_selector`，不产 .txt 手动喂），用 IndexTTS2 生成旁白，用 Pixabay 搜音乐、Freesound 搜纸 ASMR。产出 `asset_manifest`。

## 输入

- scene_plan（节拍表 + 每节拍视觉想法）
- script（旁白全文）

## 流程

### 1. 图像（每节拍一张，STATE 7）

对每个节拍，转换成一个完整自足的拼贴图提示词：

**思考过程（不输出）**：对每个节拍找到核心想法，而非字面词。选择最强的纪录片视觉：物体、文件、地图、时间线片段、半色调人物、地点。选择一个英雄元素，至多 2-3 个支撑元素，以及服务故事的背景。绝不逐词插图。可视化 IDEA。

**提示词结构**（一个自然散文块）：

1. **SCENE**：本节拍的具体构图。一个英雄元素（主导，约 70% 视觉权重），至多 2-3 个支撑元素，大量负空间。若节拍带有日期/名字/数字，可作为一个 1-4 词的短标签出现在纸条或印章上。否则无文字。
2. **STYLE BLOCK**：每个提示词必须 verbatim 包含 `templates/style_block.md` 全文（剔除文件头注释）。
3. **CLOSER**：每个提示词以 `templates/closer.md` 全文精确结尾（剔除文件头注释）。

提示词 = SCENE 描述 + STYLE BLOCK + CLOSER，三者拼成一个块，经 `image_selector` 调用。

**工具**：`image_selector`（首选 google_imagen；若风格遵循不达标，升级 FLUX 需 FAL_KEY——先告知 EP）。调用前必须阅读 Layer 3 技能（`google-gemini-image` / `flux-best-practices` 等，查工具 agent_skills 字段）。

### 2. 旁白（STATE 5，脚本批准后）

- 工具：`tts_selector` → indextts_tts 首选
- 参考音色约定：`spk_audio_prompt` → `INDEXTTS_VOICE_REF` 环境变量 → 仓库 `voice_reference.wav` 兜底
- 语音方向（引擎 verbatim）：calm deadpan male narrator, mid-range, mild gravitas, about 155 wpm, minimal emotion spikes, documentary read
- 生产规则：20-25 秒批次合成避免失真；每批 2-5 次重生成取最佳；批次间节奏匹配保证接缝无缝；冷开场批次是最高优先级 take
- 语言：narration_language（en/zh），en 用英文旁白，zh 用中文旁白（同音色）
- 调用前必须阅读 Layer 3 技能（`voxcpm-tts` / `elevenlabs-tts` 等，查工具 agent_skills 字段）

### 3. 音乐（Pixabay）

- 工具：`music_search`（pixabay_music）
- 搜索词来自 `templates/music_prompt.md`（Epic Egyptian trailer score 关键词）
- 音乐仅用于成片混音，不进 10s clip 动画

### 4. 纸 ASMR（Freesound）

- 工具：`freesound_music`
- 搜索：paper slide / cardstock tap / tape press / stamp thud / string zip / pin click / soft room tone
- 用于 10s clip 的环境音效层与成片音效点缀

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

### 图像生成（一张图 = 一个元素）
- 每个元素**独立生成**：单物体、纯色底（#D8C7A3）、居中、提示词只描述这一个物体 + "no other objects, isolated, generous empty space"
- 生成后 PIL 抠透明（色彩距离阈值 + bbox 裁剪），得到带 alpha 的独立元素 PNG
- **真实新闻图 → img2img 风格参考生成**（2026-08 用户确认）：真实新闻图**不作为原图直接贴入**，而是作为**图像风格参考**（image_path / image_url 参数传入生成模型），结合 VOX 拼贴风格提示词（halftone 半色调/剪报/纸张纤维/撕裂边缘/单一主体），生成"保留真实内容但符合拼贴风格"的独立元素。例：Bessent 待办清单新闻照 → halftone 剪报版待办清单元素
- 抽象数据 → 直接生成 VOX 风格图；装饰 → CSS 渲染
- 提示词质量决定风格成败：明确材质（新闻纸纤维/撕裂边缘/半色调）+ 光源 + 单一主体，不要堆砌

### 中文配音（IndexTTS2）
- 语速基准：**中文 ~4.7 字/秒**（1 分钟 ≈ 230-250 字），不要按英文 2.5wps 折算
- `speed=1.0` 零变速；speed<0.8 产生 resample 杂音
- 多段合并单文件：`ffmpeg -filter_complex "[0:a]adelay=0|0[a0];...amix=inputs=N:normalize=0"` 
- 参考音色统一用同一文件（spk_audio_prompt），保证多段音色一致
