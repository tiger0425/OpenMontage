# Generate Director — Pipeline Forge

## 职责

按 blueprint 把 style_dna 落成三件套文件。产出 `pipeline_package`。这是机械生成阶段（无审批），但**模板文本必须与 style_dna 逐字一致**——validate 阶段会复核。

## 产物结构

```
pipeline_defs/<slug>.yaml                  # 管线 manifest
styles/<slug>.yaml                         # 结构化 playbook（过 playbook schema）
skills/pipelines/<slug>/
├── executive-producer.md                  # EP 技能（参照 forge 自身的）
├── <stage>-director.md                    # 每个 manifest 阶段的 director skill
└── templates/
    ├── style_block.md                     # 图像风格块（verbatim）
    ├── closer.md                          # 图像结尾块（verbatim）
    ├── video_prompt.md                    # 通用视频提示词（verbatim）
    ├── thumbnail_dna.md                   # 缩略图规则（如有）
    └── music_prompt.md                    # 音乐提示词（verbatim，多变体并列）
```

## 生成规则

### 1. Manifest（pipeline_defs/<slug>.yaml）

- 参照 `pipeline_defs/animation.yaml` 结构：name/version/description/category/stability/orchestration/extensions/required_skills/compatible_playbooks/stages
- `category: custom`（schema 枚举值）
- `default_checkpoint_policy: manual_all`（硬性，前期全人工）
- `budget_default_usd` 用 blueprint 值
- stages 按 blueprint 的 stage_map；每个阶段含 skill、produces、tools_available、checkpoint_required、human_approval_default、review_focus、success_criteria
- 引擎特有规则（Fern DNA、节拍规则、缩略图 DNA）写入对应阶段的 review_focus 引用（如 "Template blocks must be used verbatim from templates/ — see extract red line"）
- **YAML 陷阱**：review_focus/success_criteria 是字符串数组，元素内不能出现 `冒号+空格`（会被解析成字典）；用括号或破折号替代

### 2. Playbook（styles/<slug>.yaml）

- 必须过 `schemas/styles/playbook.schema.json`：identity / visual_language / typography / motion / audio / asset_generation / quality_rules 必填
- 从 style_dna 映射：identity 抄角色定位；visual_language 填风格描述与调色板；motion 填引擎的运动规则（如"锁定镜头、0-7s 逐层组装、7-10s 微动效"）；audio 填音乐与音效计划；asset_generation 填模板引用路径（templates/ 文件）；quality_rules 填引擎的禁止项（no watermarks、no text beyond label 等）

### 3. Director skills（skills/pipelines/<slug>/）

- 每个 manifest 阶段一个 `<stage>-director.md`，结构参照 forge 自身技能（职责/流程/质量要求/成功标准）
- **脚本阶段**：写入引擎的脚本规则（字数表、句子/节拍规则、结尾模式）为可执行指令
- **scene_plan 阶段**：写入节拍/句子拆分规则（2.5 wps 累计时间码、每节拍一个视觉想法）
- **assets 阶段**：明确"每节拍/每句一张图，提示词 = scene 描述 + style_block + closer（从 templates/ 读取，逐字拼接）"；TTS 用 tts_selector（参考音色约定写入）；音乐/音效用绑定工具
- **compose 阶段**：明确 HyperFrames（或 blueprint 锁定的 render_runtime）10s/图动画结构：0-7s 分层揭示、7-10s 微动效、锁定镜头；混音 = 旁白 + 音乐 + ASMR
- **publish 阶段**（若有缩略图）：写入缩略图 DNA

### 4. Templates（templates/*.md）

- 从 style_dna 的 verbatim 块原样写入，一个文件一块
- 文件头注明 `<!-- verbatim from <source_ref>, hash <source_hash> -->`（注释不进入提示词拼接）

## 质量要求

- 生成后自检：文件落盘、非空、manifest 能被 `lib.pipeline_loader.load_pipeline` 加载
- 模板文件与 style_dna 的 verbatim 文本逐字一致（先做一次 md5 对比自检）
- 新管线 manifest 的 `required_skills` 必须引用刚生成的全部 director skill 路径

## 成功标准

- `pipeline_package` 列出全部生成文件路径
- 所有文件存在且非空
- 自检通过（loader 可加载）
