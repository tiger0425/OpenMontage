# Proposal Director — Vox Paper Collage

## 职责

执行 VOX 引擎 STATE 3（DURATION）：确定视频时长，锁定 render_runtime、预算、旁白语言，产出 `proposal_packet` + `decision_log`。这是成本与治理决策点。

## 流程

1. **时长选择**：向用户呈现引擎选项
   ```
   "How long should the video be? Options: 30 seconds, 1 minute, 2 minutes,
   3 minutes, or 5 minutes. Reply with a length."
   ```
2. **字数目标**：按 2.5 words per second 计算：
   - 30s → 约 75 词
   - 1 min → 约 150 词
   - 2 min → 约 300 词
   - 3 min → 约 450 词
   - 5 min → 约 750 词
   - 容差：目标 ±5%
3. **锁定 render_runtime = hyperframes**（本机 remotion 不可用；引擎 FINAL RULE 要求确定性动画，hyperframes 是唯一合规路径）。在 `decision_log` 记录 `category: "render_runtime_selection"`，说明 remotion 不可用
4. **预算估算**：
   - 图像：节拍数 × $0.05（约等于字数目标/6，因为每节拍 5-8 词）
   - 配音：indextts_tts 本地免费
   - 音乐：pixabay_music 免费
   - 纸 ASMR：freesound_music 免费
   - 默认总预算上限 $3.00
5. **旁白语言**：`narration_language` 默认 `en`，可切换 `zh`（影响 script 与 TTS 音色选择）
6. 产出 `proposal_packet`，含概念、工具路径、成本明细、approval 状态

## 质量要求

- 工具绑定来自注册表实测：image_selector（google_imagen 首选，flux/FAL_KEY 升级路径）、tts_selector（indextts_tts）、music_search（pixabay_music）、freesound_music、video_compose（hyperframes）
- 预算明细 itemized，免费路径明确标注
- 无 approvaal 前不进入任何付费生成

## 成功标准

- `proposal_packet` 含 duration、word_target、render_runtime、cost_estimate（line_items）
- `decision_log` 记录 render_runtime_selection 与预算决策
- `approval.status` 为 approved 或 approved_with_changes 后才继续
