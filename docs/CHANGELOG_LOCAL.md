# OpenMontage 本地修改记录

> 记录基于上游 [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) 的本地定制改动。
> 最后同步上游 commit: `0c202b5` (2026-07-03)

---

## 目录

- [新增工具](#新增工具)
  - [MiniMax 工具集](#minimax-工具集)
  - [VoxCPM TTS 离线语音合成](#voxcpm-tts-离线语音合成)
- [新增文档](#新增文档)
- [新增技能资源](#新增技能资源)
  - [Website-to-Video 增强](#website-to-video-增强)
- [文件修改](#文件修改)
- [新增依赖](#新增依赖)

---

## 新增工具

### MiniMax 工具集

MiniMax (minimax.com) 平台集成，支持图像生成、TTS、音乐生成和视频直出。

| 文件 | 说明 |
|------|------|
| `tools/audio/minimax_tts.py` | MiniMax TTS 语音合成（对标 elevenlabs/google_tts） |
| `tools/audio/minimax_music.py` | MiniMax 音乐生成 |
| `tools/graphics/minimax_image.py` | MiniMax 图像生成 |
| `tools/video/minimax_video_direct.py` | MiniMax 视频直出（S2V-01 模型） |
| `tests/contracts/test_minimax_contracts.py` | MiniMax 工具合约测试 |

**配置：** 在 `.env` 中设置 `MINIMAX_API_KEY`（从 https://platform.minimaxi.com 获取）

### VoxCPM TTS 离线语音合成

完全离线的 GPU 加速 TTS，支持音色克隆和文本描述语音设计。

| 文件 | 说明 |
|------|------|
| `tools/audio/voxcpm_tts.py` | VoxCPM TTS 工具 |
| `models/voxcpm/` | 模型文件（tokenizer、config、weights） |
| `tests/qa/test_10_voxcpm_tts.py` | QA 测试 |

**要求：** CUDA GPU，~8-10GB VRAM

---

## 新增文档

| 文件 | 说明 |
|------|------|
| `docs/ARCHITECTURE.zh-CN.md` | 架构文档中文翻译版 |

---

## 新增技能资源

### Website-to-Video 增强

对 `website-to-hyperframes` skill 的补充文件（上游后续已重命名为 `website-to-video`）：

| 文件 | 说明 |
|------|------|
| `website-to-hyperframes/references/step-0-capture.md` | 捕获步骤 0 - 前置准备 |
| `website-to-hyperframes/references/step-1-design.md` | 设计步骤 1 |
| `website-to-hyperframes/references/step-2-brief.md` | 简报步骤 2 |
| `website-to-hyperframes/references/step-3-storyboard.md` | 故事板步骤 3 |
| `website-to-hyperframes/references/step-4-vo.md` | 配音步骤 4 |
| `website-to-hyperframes/references/step-5-build.md` | 构建步骤 5 |
| `website-to-hyperframes/references/step-6-validate.md` | 验证步骤 6 |
| `website-to-hyperframes/references/capabilities.md` | 能力文档 |
| `website-to-hyperframes/references/beat-builder-guide.md` | 节奏构建指南 |
| `website-to-hyperframes/scripts/w2h-verify.mjs` | 验证脚本 |
| `website-to-hyperframes/assets/sfx/` | 音效资源包（20 个 SFX + manifest） |

---

## 文件修改

| 文件 | 修改内容 |
|------|----------|
| `.env.example` | 添加 `MINIMAX_API_KEY` 配置项 |
| `.gitignore` | 添加 `.omo/` 忽略规则 |
| `AGENT_GUIDE.md` | 更新 HyperFrames 技能描述（反映多模块拆分） |
| `docs/ARCHITECTURE.md` | 更新 Audio 工具列表（添加 doubao_tts, voxcpm_tts, freesound/pixabay/suno music） |
| `docs/PROVIDERS.md` | 添加 VoxCPM TTS 离线部署文档章节 |
| `lib/checkpoint.py` | JSON 文件读取添加 `encoding="utf-8"` 参数 |
| `lib/pipeline_loader.py` | JSON/YAML 文件读取添加 `encoding="utf-8"` 参数 |
| `schemas/artifacts/__init__.py` | Schema JSON 读取添加 `encoding="utf-8"` 参数 |
| `skills/core/hyperframes.md` | 更新技能引用路径（website-to-video 重命名） |
| `tests/contracts/test_phase3_contracts.py` | TTS provider 检测添加 `minimax` 和 `voxcpm` |
| `tools/video/hyperframes_compose.py` | CSS 使用 `system-ui` 字体回退；`data-composition-id="root"` 补充 `id="root"` |

---

## 新增依赖

| 文件 | 新增 |
|------|------|
| `requirements-gpu.txt` | `torch>=2.5.0` (升版), `voxcpm` |

---

## 与上游差异摘要

```
git diff origin/main..HEAD --stat
50 files changed, 187300 insertions(+), 15 deletions(-)
```

其中 `models/voxcpm/tokenizer.json`（~178K 行）为主要体积贡献者，为 VoxCPM 模型的 tokenizer 配置。
