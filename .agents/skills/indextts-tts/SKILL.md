---
name: indextts-tts
description: |
  本地 GPU 语音合成（IndexTTS2）的使用指南：零样本音色克隆、8 维情感控制、多段音色一致性，
  以及 OpenMontage 各配音管线的正确调用姿势（桥协议 / UTF-8 / 纯净克隆保声纹）。
  触发条件：使用 indextts_tts 工具、中文/多语言本地配音、需要克隆固定音色、auto-dub /
  erchuang / wrc / console-remake / vox-course / vox-collage 等管线的配音阶段。
---

# IndexTTS2 — Agent 使用指南

IndexTTS2 是本地 GPU 语音合成引擎（CUDA，~12GB VRAM），支持中/英/日/西等多语种、零样本
音色克隆与 8 维情感控制，完全离线。工具路径：`tools/audio/indextts_tts.py`。

> **动笔前必读**：`apps/indextts-bridge/CALLING.md`（桥调用规范，所有 Agent 必读。
> 违反它会导致：杂音（权重错位）、男声变女声（情感混合）、中文乱码（编码问题））。

---

## ⚠️ 三条铁律

1. **桥只能是 `apps/indextts-bridge/indextts_server.py`**（2.5 版）。
   `D:/index-tts/indextts_server.py` 旧桥（2.0 模型）已删除——用它 + 2.5 权重 = 杂音。
   启动示例：
   ```bash
   "D:/index-tts/.venv/Scripts/python.exe" "apps/indextts-bridge/indextts_server.py" --version 2.5 --checkpoints "D:/index-tts/checkpoints"
   ```
2. **传送必须走 Python `subprocess`（`encoding="utf-8"`）**，不要用 PowerShell 管道：
   GBK 管道会让中文变 `?` 生成乱码。
3. **纯净克隆保声纹：`use_emo_text: false` 且不传 `emo_vector`**。
   传 calm 向量 `[0,0,0,0,0,0,0,1]` 会触发 2.5 的情感-音色混合（男声变女声）。

---

## 工具参数（`indextts_tts`）

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `text` | str | 必填 | 待合成文本 |
| `output_path` | str | — | 输出 WAV 路径 |
| `spk_audio_prompt` | str | — | 声纹参考音频（5-30s 干净人声）。**多段必须用同一文件**；未传时回退 `INDEXTTS_VOICE_REF` 环境变量 |
| `emo_vector` | float[8] | — | 固定情感向量，顺序 `[高兴,愤怒,悲伤,害怕,厌恶,惊讶,中性,平静]`；不传=由服务端按文本判断 |
| `use_emo_text` | bool/null | null | 是否用内置 Qwen 分类器自动判情感；`true` 需桥启动加 `--use-qwen-emo` |
| `emo_alpha` | float | `0.6` | 自动判情感强度（`0.35` 弱档、`0.6` 自然解说）；固定向量模式下忽略 |
| `seed` | int | `42` | 复现种子；多段共享同一 seed + 同一参考音 → 音色一致；`-1` 跳过 |
| `speed` | float | `1.0` | 后期重采样语速。**配音管线保持 1.0**（零变速原则） |

**多段一致性模式**：同一 `spk_audio_prompt` + 同一 `seed` 逐段合成；
逐句复刻原片情感时走桥协议字段 `emo_audio_prompt`（见 `CALLING.md`，erchuang 管线）。

---

## 各管线约定

| 管线 | 说明 |
|---|---|
| `auto-dub` | 中文搬运配音主引擎（`bin/auto_dub.py`，标点自适应停顿） |
| `erchuang` | 抖音二创：逐句 `emo_audio_prompt` 克隆原片情感、情感强度 0.6 |
| `wrc` | 拉力解说：固定音色 + 低情绪强度（0.325），见 `apps/wrc/specs/` |
| `console-remake` / `vox-course` / `vox-collage` | 克隆配音 + 读 WAV 头精确秒数排时间轴 |

具体种子 / 情感 / 参考音锁定值以各管线 `apps/*/specs/` 与 `CALLING.md` 为准。

---

## 生成后校验（防杂音）

用 whisper 转录回读：清晰中文 ✅；无意义英文音节（如 “Maze Maze Selling…”）❌ 杂音，
检查是否误用了旧桥或 `--version`/`--checkpoints` 错配。

## 排障速查

| 现象 | 原因 | 修复 |
|---|---|---|
| 杂音 | 旧桥（2.0）+ 2.5 权重 | 改用 `apps/indextts-bridge/indextts_server.py` |
| 中文乱码 `?` | PowerShell GBK 管道 | Python `subprocess` + `encoding="utf-8"` |
| 男声变女声 | 传了 `emo_vector` | 只传 `use_emo_text: false`，不传向量 |
| `missing keys (212)` | 模型/权重版本错配 | 2.5→`checkpoints`；2→`checkpoints_2`（显式 `--checkpoints`） |

## 相关位置

- 工具：`tools/audio/indextts_tts.py`（`fallback_tools: voxcpm_tts, piper_tts, google_tts`）
- 桥：`apps/indextts-bridge/{CALLING.md, client.py, indextts_server.py}`
- 回退引擎：`voxcpm_tts`（本技能旁边的 `voxcpm-tts` skill）
