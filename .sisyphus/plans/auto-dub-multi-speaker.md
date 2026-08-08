# Auto-Dub 多人视频翻译与多音色配音改造 实施计划

> ⚠️ **已被合并取代**：本计划已与「逐句时长对齐与分句合并」方案合并为
> `auto-dub-utterance-alignment-multispeaker.md`（2026-08-09）。
> 原因：两者改动同一批文件、同一链路，script sections 结构只能重构一次。
> 本文件保留仅供追溯，不再作为执行依据。

## 摘要

对 OpenMontage 的 Auto-Dub 批量翻译管线做改造，使其从「单说话人假设」升级为「自动判断多人/单人，多人时区分说话人并按人配音」：

1. **转录升级**：`transcriber.py` 的 `_apply_diarization` 适配 pyannote 4.x 新 API（当前用的是已废弃的 whisperx 旧 API，在 pyannote 4.0.7 下必然崩溃）。
2. **自动分档**：以 `diarize: auto` 模式全量跑说话人分离，按结果自动判断——1 个 speaker 走现有单音色路径（零回归），≥2 个走多音色路径。
3. **多人翻译**：翻译阶段注入 speaker 上下文，script.json 的每个 section 携带 `speaker` 字段。
4. **多音色配音**：按 speaker 从原视频切出各自的 voice_ref，TTS 合成时按行选择对应音色（IndexTTS2 服务端已支持每句切换 `spk_audio_prompt`，已确认）。

## 背景

### 现状（代码级定位）

| 环节 | 文件:行 | 现状 | 问题 |
|------|---------|------|------|
| 转录 | `tools/analysis/transcriber.py:214` | `_apply_diarization` 用 whisperx 旧 API：`DiarizationPipeline(use_auth_token=...)`、`assign_word_speakers`、`.itertracks` | 与 pyannote 4.0.7（已装）不兼容，`use_auth_token`/`itertracks` 均已移除，一调用即 `AttributeError`/`TypeError` |
| 设备 | `transcriber.py:229,243` | 硬编码 `device="cpu"` | 浪费 RTX 3090，未用 cuda |
| 转录调用 | `apps/auto-dub/batch/pipeline_automator.py:324` | `transcriber.execute({...})` 未传 `diarize` | 默认 `False`，永远不分离说话人 |
| 翻译 | `pipeline_automator.py:403` `_translate_segments` | 逐句 LLM 翻译，`single_data` 无 speaker | 不知道谁在说话，语气/称谓无法保持 |
| script | `pipeline_automator.py:357` | sections 无 `speaker` 字段 | 下游无法按人分音色 |
| 声纹 | `pipeline_automator.py:926` `_extract_voice_ref` | silencedetect 取视频最长一段人声作为唯一 voice_ref | 单说话人假设 |
| TTS | `pipeline_automator.py:647-720` | 所有行用同一个 `external_voice_ref` | 多人视频所有句子同一音色 |

### 已验证的前置事实（2026-08-08 实测）

1. **模型授权**：`HF_TOKEN` 已写入 `.env`（gitignored）；`pyannote/speaker-diarization-3.1`、`pyannote/segmentation-3.0`、`pyannote/speaker-diarization-community-1` 三个 gated 模型均已接受协议，免费使用。
2. **模型体积**：共约 62.6 MB（segmentation 11.3 + wespeaker 50.8 + community-1 0.5 + 主流水线 0），本地推理零费用。
3. **模型已本地化**：2026-08-08 已将 4 个 pyannote 模型从 `~/.cache/huggingface/hub` 复制进项目 `models/hf_cache/`（重建 HF 标准 `models--pyannote--xxx/snapshots/` 结构，共约 31 MB，符号链接已解引用）。已实测：阻断 huggingface.co 网络时 `Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', cache_dir=models/hf_cache)` **纯离线加载成功**，不再需要重新下载。token 仅首次下载需要，离线加载时传假 token 即可（不触发请求）。
4. **GPU**：RTX 3090 可用。
5. **pyannote 4.x 正确用法**（已在 TikTok 83s 双人访谈视频实测通过）：
   - `Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', token=<HF_TOKEN>).to('cuda')`
   - 音频需用 `whisperx.load_audio()` 读为 numpy（librosa 路径），**绕开 pyannote 默认的 torchcodec**（当前环境 torchcodec DLL 缺失，`pyannote.audio.Audio` 直接读文件会报 `RuntimeError: torchcodec is not available`）。
   - 结果用 `out.serialize()['diarization']` 取 `{start, end, speaker}` turns（`DiarizeOutput` 对象无 `itertracks`）。
   - 转写 segment 按时间重叠度分配 speaker，实测单人/双人区分正确。
5. **IndexTTS2 按句换音色可行**：`D:/index-tts/indextts_server.py:93` 每请求读取 `voice_ref`，`:132` 传入 `spk_audio_prompt`；模型只加载一次（worker 线程常驻），每句传不同 ref 即可切换音色，服务端零改动。

## 目标

1. Auto-Dub 管线自动判断视频多人/单人，无需人工标记。
2. 多人视频：转录带 speaker 标签、翻译保持说话人语气、配音按人分音色。
3. 单人视频：行为与现状完全一致（零回归）。
4. 全程本地、免费，不改动 IndexTTS2 服务端。

## 范围

### 做
- `tools/analysis/transcriber.py`：重写 `_apply_diarization` 适配 pyannote 4.x，`diarize=True` 时输出每段 `speaker` 字段 + 顶层 `speaker_turns`；设备 cuda 优先。
- `apps/auto-dub/batch/pipeline_automator.py`：
  - 转录调用传 `diarize: True`（受 config 开关控制）。
  - `_translate_segments`：每条 translated_lines 继承 `speaker`；`plan_split` 子行继承 speaker。
  - `_run_script_stage`：sections 加 `speaker` 字段。
  - 翻译 prompt 注入 speaker 上下文。
  - 新增 `_extract_speaker_voice_refs(transcript)`：按 speaker 从原视频切各自 voice_ref（复用 silencedetect + 音量归一化逻辑）。
  - `_do_assets_stage`：构建 `speaker_refs` 映射，按 `line.speaker` 选择 voice_ref；单说话人回退现有单 ref 逻辑。
- `schemas/artifacts/script.schema.json`：sections item 增加可选 `speaker` 字段（当前 `additionalProperties: false`，不加会被校验拒绝）。
- `apps/auto-dub/config.yaml`：新增 `pipeline.diarize`（`auto`/`off`，默认 `auto`）。

### 不做
- 不改 `D:/index-tts/indextts_server.py`（已支持按句换 ref）。
- 不改混音 / SRT / 压制逻辑（多音色对下游透明）。
- 字幕不标注 speaker（后续可选）。
- 不动 whisperx 包本身（`--no-deps` 安装仅作对齐/读音频工具，不依赖其 transcribe）。

## 技术决策

| # | 决策项 | 结论 | 理由 |
|---|--------|------|------|
| 1 | 多人/单人判断 | 不预判，全量跑 diarization，按 speaker 数量分档 | pyannote 本身即判断器，零误判；代价是单人视频多耗约 2-3 分钟 |
| 2 | config 开关 | `pipeline.diarize: auto`（全跑分档）/ `off`（跳过，现状） | 批量搬运单人占多数时可关，批量跑省时间 |
| 3 | 音频解码 | 用 `whisperx.load_audio()`（librosa），不修 torchcodec | torchcodec DLL 与当前 torch/FFmpeg 不匹配，修复成本高且不必要 |
| 4 | 模型来源 | 固定用项目内 `models/hf_cache`（`cache_dir=` 参数），不依赖 `~/.cache/huggingface` | 已离线验证可加载；迁移/换机不重下载 |
| 5 | 设备 | pyannote pipeline 用 `cuda`；对齐/分离均 GPU | RTX 3090 已确认 |
| 6 | 多音色切换 | 每句合成传 `line.speaker` 对应 voice_ref | IndexTTS server 每请求独立读 ref，零服务端改动 |
| 7 | speaker 字段 schema | sections item 加可选 `speaker: string` | 放行校验，兼容旧数据（缺省为空） |
| 8 | 超短句/无 speaker | 继承相邻 speaker；全无则单音色 | 实测末尾 0.24s "Yeah." 重叠 <0.3s，属边缘情况 |
| 9 | 单说话人回退 | `speaker_refs` 为空时走现有 `external_voice_ref` | 零回归保障 |

## 验证策略

1. **单测**：`_extract_speaker_voice_refs` 对合成 transcript（含 3 个 speaker_turns）输出 3 个 voice_ref 文件；单说话人输入返回空映射。
2. **schema 校验**：script.json 含 `speaker` 字段通过 `script.schema.json`。
3. **TikTok 实测**（83s 双人访谈，已验证 diarization 正确）：跑轻任务 `process`，检查 script.json sections 每行带正确 speaker；跑 `render-assets`，检查生成多音色配音且每个 speaker 音色不同。
4. **回归**：`python bin/auto_dub.py status` 正常；单说话人视频（现有队列中任一条）行为与改造前一致。
5. **GPU 锁**：`_get_indextts_server` 持锁逻辑不变，无并发回归。

## 执行策略

1. 等当前 `run-heavy F3lL98Pj90o` 任务完成、GPU 锁释放后再开始改动。
2. 改 `transcriber.py` → 用 TikTok 测试视频单测 `diarize=True` 输出。
3. 改 `pipeline_automator.py` 转录调用 + speaker 透传 → 改 schema → 改 config。
4. 加 `_extract_speaker_voice_refs` + `_do_assets_stage` 多音色逻辑。
5. 端到端：轻任务 + `render-assets`（须派发 Compute Worker 子 Agent 执行重算力）。
6. 跑测试 `python -m pytest tests/`（关注 `tests/contracts/test_phase1_contracts.py` 对 `whisperx.md` 的引用）。

## 待办事项

- [ ] 等 `run-heavy F3lL98Pj90o` 完成
- [ ] 重写 `transcriber.py::_apply_diarization`（pyannote 4.x，cuda，serialize）
- [ ] TikTok 视频单测 diarize 输出
- [ ] `pipeline_automator.py`：转录传 `diarize` + speaker 透传（翻译、sections、拆分）
- [ ] 翻译 prompt 注入 speaker
- [ ] `script.schema.json` 加 `speaker`
- [ ] `config.yaml` 加 `pipeline.diarize`
- [ ] `_extract_speaker_voice_refs` + `_do_assets_stage` 多音色
- [ ] 端到端验证（多人在 TikTok / 单人在现队列）
- [ ] 回归测试

## 风险与约束

| 风险 | 影响 | 缓解 |
|------|------|------|
| diarization 在长视频上耗时 | 每视频 +2-3 分钟 | `diarize: off` 可整体关闭；`auto` 是默认 |
| pyannote 模型二次授权 | 已全部完成 | 三个 gated 模型均已接受协议 |
| torchcodec 环境问题 | 已规避 | 走 librosa 读音频 |
| 多音色时说话人数过多 | 每个 speaker 独立 ref 克隆 | IndexTTS 按 ref 克隆无上限；说话人过密时可只取前 N 个 |
| whisperx `--no-deps` 安装 | import 时缺依赖 | 仅用 `load_audio`/`align`，nltk 已补装；核心不依赖其 transcribe |

## 成功标准

1. 多人视频（TikTok 双人访谈）script.json 每行有正确 `speaker` 标签。
2. 多人视频成品中不同 speaker 使用不同音色，听感可区分。
3. 单人视频成品与改造前一致（无回归）。
4. 全程本地免费，IndexTTS2 服务端零改动。
