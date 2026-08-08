# Auto-Dub 原句对齐与多音色改造 实施计划

> 本计划由两份计划合并而来：`auto-dub-multi-speaker.md`（多人分音色）与 2026-08-09 grilling 会话成果（逐句时长对齐与分句合并，已产出 ADR-003 与 CONTEXT.md Auto-Dub 章节）。因两者改动同一批文件、同一链路，且 script sections 结构只能重构一次，故合并执行。
> 领域术语见 `CONTEXT.md`「Auto-Dub 领域上下文」；决策记录见 `docs/adr/ADR-003-auto-dub-per-utterance-alignment.md`。

## 摘要

对 Auto-Dub 批量翻译管线做两项耦合改造：

1. **逐句时长对齐与分句合并**：Whisper 碎段按规则合并为原句（Utterance）作为字幕与对齐锚点；字幕单位（原句）与合成单位（Chunk）分离；逐句变速（±5%）使中文配音贴合原语音，超限回退 LLM 重翻；验收逐句 ±15% 容差。
2. **多人/多音色**：自动判断多人/单人，多人时转录带 speaker 标签、翻译保持说话人语气、配音按人分音色；单人零回归。

## 背景

### 问题一：分句碎 + 逐句时长不一致

- 用户观察「明明是一句却分成几句」；实测 29 项目、6734 句：超 ±15% 误差占 66.5%，超 ±30% 占 37.1%。
- 实测 67s 漂移案例 `auto-dub-F3lL98Pj90o`（原片 908.7s → 混音 976.1s）：访谈对话被 Whisper 切成大量 <1s 微段（回应词），字数预算下限 `min_budget=15` 逼出完整中文短句，TTS 读出 2~4.6 倍时长，311 段累积。全局 atempo（限 ≤1.5s 漂移）与缩短重翻（限 ≥15 字）均救不回。

### 问题二：多人视频单音色 + diarization 已损坏

| 环节 | 文件:行 | 现状 | 问题 |
|------|---------|------|------|
| 转录 | `tools/analysis/transcriber.py:214` | `_apply_diarization` 用 whisperx 旧 API | 与 pyannote 4.0.7 不兼容，一调用即崩溃 |
| 设备 | `transcriber.py:229,243` | 硬编码 `device="cpu"` | 未用 RTX 3090 |
| 转录调用 | `pipeline_automator.py:324` | 未传 `diarize` | 默认 False，永不分离说话人 |
| 翻译 | `pipeline_automator.py:403` `_translate_segments` | 逐段翻译，无 speaker 上下文 | 多人语气/称谓无法保持 |
| script | `pipeline_automator.py:357` | sections 无 `speaker` 字段 | 下游无法按人分音色 |
| 声纹 | `pipeline_automator.py:926` `_extract_voice_ref` | 取最长一段人声作为唯一 ref | 单说话人假设 |
| TTS | `pipeline_automator.py:647-720` | 所有行同一 `external_voice_ref` | 多人视频所有句子同一音色 |
| 混音/压制 | — | 100ms 串行排队 | 保留不动 |

### 已验证的前置事实（2026-08-08 实测）

1. **模型授权**：`pyannote/speaker-diarization-3.1`、`pyannote/segmentation-3.0`、`pyannote/speaker-diarization-community-1` 三个 gated 模型均已接受协议；共约 62.6 MB，本地推理零费用。
2. **模型本地化**：4 个 pyannote 模型已复制进项目 `models/hf_cache/`（标准 HF 结构，符号链接解引用），阻断网络可纯离线加载，传假 token 即可。
3. **pyannote 4.x 正确用法**（TikTok 83s 双人访谈实测通过）：
   - `Pipeline.from_pretrained(..., token=...).to('cuda')`
   - 音频用 `whisperx.load_audio()`（librosa），绕开 torchcodec（当前 DLL 缺失）
   - 结果 `out.serialize()['diarization']` 取 `{start, end, speaker}` turns（无 `itertracks`）
   - segment 按时间重叠度分配 speaker，单人/双人区分正确
4. **IndexTTS2 按句换音色可行**：`D:/index-tts/indextts_server.py` 每请求读 `voice_ref`、传 `spk_audio_prompt`，模型常驻，零服务端改动。
5. **TTS 无语速参数**（IndexTTS2 与 VoxCPM 均无）：合成时长不可预测，逐句对齐只能事后测量 + 变速。

## 目标

1. 中文配音逐句时长贴合原语音（±15% 容差，≥95% 达标，碎句率归零）。
2. 转录自动判断多人/单人；多人视频按人配音、翻译保持说话人语气。
3. 单人视频行为与现状一致（零回归）。
4. 全程本地、免费，IndexTTS2 服务端零改动。

## 范围

### 做
- `tools/analysis/transcriber.py`：重写 `_apply_diarization` 适配 pyannote 4.x（serialize/cuda/librosa）；新增**原句合并**（Utterance）输出。
- `apps/auto-dub/batch/pipeline_automator.py`：
  - 转录调用传 `diarize`（受 config 开关），转录后按规则合并 Whisper 段为原句。
  - `_translate_segments`：按原句翻译，注入 speaker 上下文，字数预算控制。
  - sections 加 `speaker` 字段；字幕单位 = 原句。
  - 新增 `_extract_speaker_voice_refs(transcript)`：按 speaker 从原视频切各自 voice_ref。
  - `_do_assets_stage`：按原句切合成子块（Chunk，中文标点），每子块一个 WAV、按 `speaker` 选 voice_ref；单说话人回退现有单 ref 逻辑。
  - 新增逐句对齐闭环：子块合成 → 实测时长 → atempo 变速（±5%）→ 超限回退重翻；SRT 按原句合并为一条。
- `schemas/artifacts/script.schema.json`：sections item 增加可选 `speaker` 字段。
- `apps/auto-dub/config.yaml`：新增 `pipeline.diarize`（`auto`/`off`，默认 `auto`）与对齐参数（合并间隙 0.5s、原句上限 15s、变速 ±5%、容差 ±15%、inherently_long 阈值 1s）。

### 不做
- 不改 `D:/index-tts/indextts_server.py`。
- 不改混音 100ms 串行排队算法；TTS 引擎不动。
- 字幕不标注 speaker；SRT 不拆碎（按原句合并）。
- 不动 whisperx 包本身（仅用 `load_audio`/`align` 工具）。
- 已处理/已发布旧成品不重跑（新行为只影响新处理视频）。

## 技术决策

| # | 决策项 | 结论 | 理由 |
|---|--------|------|------|
| 1 | 原句单位 | 转录后按「句末标点 `. ! ?` + 间隙 <0.5s + 上限 15s」规则合并为 Utterance | 确定性、零 LLM 成本、可验证；不依赖语义合并 |
| 2 | 字幕/合成单位分离 | 1 原句 = N 合成子块 = 1 字幕 | 字幕干净、对齐精确；打破「一段=一WAV=一SRT」以原句为边界重定义 |
| 3 | 逐句对齐闭环 | 合成 → 实测 → 变速 → 校验 | TTS 时长不可预测，只能事后测量 |
| 4 | 变速预算 | 逐句 atempo ≤ ±5%，超限回退 LLM 重翻 | 变速保音高、±5% 听感自然；重翻控制译文长度 |
| 5 | 对齐容差与验收 | ±15%；≥95% 达标、单句偏差 <0.5s、碎句率归零；排除 Inherently-Long | 务实可达，避免物理不可达句导致验收失败 |
| 6 | 短回应句 | 原句 <1s 标记 `inherently_long`，允许超容差、不计入达标率；优先并入相邻句 | 中文朗读物理上不可贴合极短句 |
| 7 | 排队间隔归属 | 变速目标时长 = 原句时长 − 100ms | 避免逐句对齐后 100ms 硬间隔累积漂移 |
| 8 | 多人判断 | 不预判，`diarize: auto` 全量跑 diarization 按 speaker 数分档 | pyannote 即判断器；单人视频多耗 2-3 分钟，可 `off` 关闭 |
| 9 | diarization 音频 | `whisperx.load_audio()`（librosa），不修 torchcodec | torchcodec DLL 与当前环境不匹配 |
| 10 | 模型来源 | 固定 `models/hf_cache`（`cache_dir=`），离线加载 | 已验证；迁移不重下载 |
| 11 | 多音色切换 | 每子块合成按原句 `speaker` 传对应 voice_ref | IndexTTS server 每请求读 ref，零改动 |
| 12 | 单说话人回退 | `speaker_refs` 为空时走现有 `external_voice_ref` | 零回归保障 |
| 13 | 超短句/无 speaker | 继承相邻原句 speaker；全无则单音色 | 边缘情况（如 0.24s "Yeah."）不单独成档 |
| 14 | chunk 不进 schema | 合成子块属合成层产物，不写入 script.json | 最小化 schema 改动，仅加 `speaker` |
| 15 | 变速与音色正交 | atempo 保音高，不干扰多音色辨识 | 两特性独立成立 |

## 验证策略

1. **单测**：`_extract_speaker_voice_refs` 对含 3 个 speaker_turns 的合成 transcript 输出 3 个 ref；单说话人返回空映射。
2. **单测**：原句合并函数——相邻碎段按间隙/标点正确合并、超上限不硬并。
3. **单测**：逐句变速/重翻分支——变速不可达标记重翻、inherently_long 判定、容差计算。
4. **schema 校验**：script.json 含 `speaker` 字段通过 `script.schema.json`。
5. **TikTok 实测**（83s 双人访谈）：轻任务 `process` 检查 script.json 每原句带正确 speaker；`render-assets`（派发 Compute Worker）检查多音色可区分 + 逐句对齐指标。
6. **回归**：单说话人视频（现队列任一条）行为与改造前一致；`python bin/auto_dub.py status` 正常。
7. **基线**：用 `auto-dub-F3lL98Pj90o`（67s 漂移案例）验证新流程不再出现碎段累积超长。
8. **GPU 锁**：`_get_indextts_server` 持锁逻辑不变，无并发回归。

## 执行策略

1. 确认 GPU 锁释放（无 run-heavy 在跑）后开始。
2. **阶段 1 转录层**：重写 `transcriber.py`（pyannote 4.x + cuda + speaker + 原句合并输出）→ TikTok 视频单测 diarize + 合并输出。
3. **阶段 2 结构层**：`script.schema.json` 加 `speaker`；`config.yaml` 加 `diarize` 与对齐参数。
4. **阶段 3 翻译层**：`_translate_segments` 按原句翻译 + speaker 上下文 + 字数预算。
5. **阶段 4 音色层**：`_extract_speaker_voice_refs` + `_do_assets_stage` 按 speaker 选 ref（单说话人回退）。
6. **阶段 5 对齐层**：子块合成 + 实测 + 逐句变速 ±5% + 超限重翻 + SRT 按原句合并 + 验收指标计算。
7. **阶段 6 验证层**：TikTok 多人端到端（轻任务 + `render-assets`，重算力派发 Compute Worker）；单人回归；F3lL98Pj90o 基线；`pytest tests/`。

## 待办事项

- [ ] 阶段 1：重写 `_apply_diarization`（pyannote 4.x，cuda，serialize，librosa）
- [ ] 阶段 1：新增原句合并（间隙 0.5s / 上限 15s / 句末标点）
- [ ] 阶段 1：TikTok 视频单测 diarize + 合并输出
- [ ] 阶段 2：`script.schema.json` 加 `speaker`
- [ ] 阶段 2：`config.yaml` 加 `pipeline.diarize` + 对齐参数
- [ ] 阶段 3：`_translate_segments` 按原句 + speaker 上下文 + 预算
- [ ] 阶段 4：`_extract_speaker_voice_refs` + `_do_assets_stage` 按 speaker 选 ref
- [ ] 阶段 5：子块合成 + 实测 + 逐句变速 ±5% + 超限重翻
- [ ] 阶段 5：SRT 按原句合并 + 验收指标（±15% 达标率、碎句率、inherently_long）
- [ ] 阶段 6：TikTok 多人端到端（派发 Worker 执行 render-assets）
- [ ] 阶段 6：单人回归 + F3lL98Pj90o 基线 + `pytest tests/`

## 风险与约束

| 风险 | 影响 | 缓解 |
|------|------|------|
| diarization 长视频耗时 | 每视频 +2-3 分钟 | `diarize: off` 可关；`auto` 为默认 |
| 合并规则参数（0.5s/15s）未精调 | 合并过粗/过细 | 用 F3lL98Pj90o 等实测项目回归校准 |
| ±5% 变速对极快/极慢句听感 | 轻微发闷/偏快 | 超限一律回退重翻，不强行变速 |
| 变速 5~15% 区间句子全走重翻 | LLM 重翻调用量上升 | 重翻复用现有 `_retranslate_shorter` 扩展，成本可控 |
| 多音色 speaker 过多 | 每 speaker 独立 ref 克隆 | IndexTTS 按 ref 克隆无上限；过密时只取前 N 个 |
| pyannote/torchcodec 环境 | 已规避 | librosa 读音频 |
| whisperx `--no-deps` 缺依赖 | import 失败 | 仅用 `load_audio`/`align`，核心不依赖其 transcribe |

## 成功标准

1. 多人视频（TikTok 双人访谈）每个原句带正确 `speaker` 标签，成品多音色听感可区分。
2. 逐句对齐：新处理视频原句 ±15% 达标率 ≥95%（排除 inherently_long）、单句偏差 <0.5s、碎句率归零。
3. F3lL98Pj90o 类访谈碎段不再出现 60s+ 漂移。
4. 单人视频成品与改造前一致（零回归）。
5. 全程本地免费，IndexTTS2 服务端零改动。
