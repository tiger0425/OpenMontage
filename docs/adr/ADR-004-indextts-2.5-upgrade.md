# ADR-004: IndexTTS-2.5 升级与原生语速控制

OpenMontage 将默认本地 GPU TTS 引擎从 IndexTTS-2 升级到 IndexTTS-2.5，采用双版本并行（2.5 默认、2 保留作 A/B 与回退），并利用 2.5 新增的原生语速控制 `duration_factor` 重构逐句对齐机制。ADR-003 的 D3 对齐闭环因此被部分取代。

- **状态**: Accepted
- **日期**: 2026-08-12
- **决策者**: 用户 + AI Agent (grill-with-docs session)
- **影响范围**: 外部 IndexTTS 仓库（`D:/index-tts`）、auto-dub / markhasara / 工具层 `indextts_tts`、4 个 config、9 个测试、相关 skill 文档

## 背景

IndexTTS-2.5（2026-08-10 发布）新增：五语种（`lang` 参数）、原生语速控制 `duration_factor`（0.5–2.0×）、推理快约 37%（RTF 0.206 vs 0.326）、情感向量保持 8 维但 `use_emo_text=True` 需要 `use_qwen_emo=True` 构造开关。本地 `D:/index-tts` 克隆仍停在 2（HEAD 2026-07-14），无 `infer_v2_5.py`。OpenMontage 现有对齐机制（cps 校准打折 + atempo ±5% + LLM 重翻回退）全部建立在「TTS 无语速参数」这一 ADR-003 前提之上，该前提对 2.5 不再成立。

## 决策

### D1: 全面采纳，两阶段落地

先做「止血」：外部仓库升级 + 桥收编 + 协议/lang 透传，现有机制原样跑在 2.5 上。通过 A/B 验收门槛后，再做「机制重写」：`duration_factor` 对齐。禁止一步到位直接重写对齐机制。

### D2: 双版本并行，配置加版本维度

- 权重布局：`checkpoints/`（2.5）、`checkpoints_2`（2，现 2 权重搬入）。
- 配置：`tts_engine` 保留（引擎族），新增 `tts_model_version`（默认 `"2.5"`，可 `"2"`）。
- 工具注册表 `model="indextts-2"` → `model="indextts-2.5"`；provenance 补记 `model_version`。
- cps 缓存按版本隔离：`indextts_cps_cache_<version>.json`，2.5 首次跑重测。
- 2 仅作 A/B 对照与故障回退，随质检通过后择机下架。

### D3: 桥收编进 OpenMontage，单桥 + `--version` 分支

`indextts_server.py` 收进仓库，启动参数 `--version 2.5|2` 分支三处差异：import（`infer_v2_5`/`infer_v2`）、精度（`use_bf16`/`use_fp16`）、权重目录（`checkpoints`/`checkpoints_2`）。GPU 锁、stdout/stderr 协议、GBK 修复沿用。收编后「`resolve_emotion_mode` 与桥双处同步」契约变为仓库内单源。

### D4: 2.5 协议字段

请求：`id / text / output_path / voice_ref / seed / emo_vector / use_emo_text / emo_alpha / lang / duration_factor / use_random`；预留 `emo_audio_prompt`（本轮不启用）。`use_random` 默认 `False`。三态情感语义保留；`use_emo_text=True` 时若进程未以 `use_qwen_emo=True` 启动，桥必须显式报错而非透传崩溃。`duration_factor` 越界（<0.5 / >2.0）时桥拒绝请求，OpenMontage 侧降级 atempo。

### D5: 语速机制 — Duration Factor 粗调 + Atempo 微调

- 对齐路径：双次合成（自然合成测量 → `factor = 目标时长/自然时长` → 用 `duration_factor` 重合成）；factor 越界或重合成仍失准，降级 atempo（Q6-C）。
- cps 校准职责收窄为仅服务翻译字数预算，不再承担对齐。
- 「为长度而重翻」的 LLM 回退保留但触发阈值大幅放宽。

### D6: 语言显式配置

逐流水线 `tts_lang`（ZH/EN/JA/ES/AR），缺省从 `target_language` 映射推断。禁逐句自动探测。

### D7: Qwen 情感机制先行、默认全关

`tts_use_qwen_emo: false` 默认；桥支持 `--use-qwen-emo` 启动分支。本轮无试点流水线，等真实样片诉求再开。

### D8: 验收门槛（阶段一/二之间）

2–3 个既有项目（含已知坑：静音伪文件、前导静音、短句 cps、男声音高锚定）跑 2 vs 2.5 对照；用户听 6–8 条样片 + 指标（WER/SS、逐句对齐命中率、cps 重测）不劣于 2 才切默认。

## 后果

- **正面**: 吃到 2.5 的加速（~37%）与五语能力；原生语速对齐比 atempo 更自然；cps 职责收窄简化预算模型；桥收编消除外部 untracked 脆弱点。
- **负面**: 双版本并行增加磁盘（5–8GB）与配置复杂度；对齐双次合成使对齐关键 Chunk 推理次数翻倍（2.5 速度收益部分抵消）；`duration_factor` 线性命中时长是经验假设，需实测确认。
- **风险**: 2.5 是否仍产前导静音/静音伪文件未知，决定 `trim_audio_lead.py` 与静音检测去留；`duration_factor` 命中精度不足时对齐质量依赖 atempo 兜底（±5% 限制仍在）。

## 被取代/关联

- 部分取代：ADR-003 D3（对齐闭环）。
- 后续若 `duration_factor` 精度实测满足对齐目标，可考虑将 atempo 与重翻回退整体退役（新 ADR）。
