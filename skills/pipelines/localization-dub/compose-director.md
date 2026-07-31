# Compose Director - Localization Dub Pipeline

## When To Use

Render the localized outputs. The quality bar is intelligibility, timing coherence, and clear version labeling across every language package.

## Reference Inputs

- `skills/pipelines/localization-dub/lessons-learned.md` — **必读**，包含串行排队混音的完整算法定义与校验标准

## Runtime Routing (HARD CONSTRAINT — Remotion or FFmpeg only)

Phase 1 deferred from HyperFrames. `edit_decisions.render_runtime` must be `"remotion"` or `"ffmpeg"`. Localization depends on Remotion's caption stack (per-locale subtitle burn) and, when dubbing with lip-sync, on the Remotion TalkingHead pipeline. HyperFrames has no parity for either in Phase 1.

- If `edit_decisions.render_runtime == "hyperframes"`, stop. Re-open the idea stage and surface the constraint — don't silently rewrite the runtime.
- Per AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)": the pipeline's constraint does NOT skip the conversation. Present the constraint to the user so they know HyperFrames exists but isn't viable here. Log a `render_runtime_selection` decision with hyperframes `rejected_because: "caption + lip-sync parity deferred on localization-dub"`.
- Pass `proposal_packet`/`brief` to `video_compose.execute()` for end-to-end runtime-swap detection.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Guidelines | `skills/pipelines/localization-dub/lessons-learned.md` | 串行排队混音算法定义与铁律约束 |
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["edit"]["edit_decisions"]`, `state.artifacts["assets"]["asset_manifest"]` | Locale-specific render instructions |
| Tools | `video_compose`, `audio_mixer`, `video_trimmer`, `audio_enhance` | Final render and audio finishing |
| Playbook | Active style playbook | Subtitle placement and output quality |

## Process

### 1. Execute Serial Queue Mix (MANDATORY)

混音阶段**必须**严格执行 `lessons-learned.md` 中定义的串行排队混音算法：

```python
# 伪代码 — Serial Queue Mix
previous_end = 0
min_pause = 0.10  # 100ms

for segment in tts_segments:
    ideal_start = segment.original_timestamp
    actual_start = max(ideal_start, previous_end + min_pause)
    # 将 TTS 音频完整放入 master_buffer[actual_start : actual_start + audio_len]
    # 段首段尾各施加 15ms 淡入淡出
    previous_end = actual_start + audio_len
    # 记录 actual_start / actual_end 用于 SRT 重对齐
```

**硬性禁止**：
- ❌ 不得对 TTS 音频施加任何 atempo / 变速处理
- ❌ 不得截断 TTS 音频尾部
- ❌ 不得按原始英文时间戳硬放（会导致重叠）

### 2. Dynamic SRT Resync (MANDATORY)

字幕文件的时间戳**必须**根据混音后各段的实际 `actual_start` 和 `actual_end` 重新生成。

**严禁**沿用原始英文时间戳作为字幕时间。

### 3. Render By Locale

Treat each target language as its own deliverable set. Keep names and output directories explicit.

### 4. Expect Timing Adjustments

Allow for:

- subtitle reflow,
- dub-audio duration drift (natural extension into pauses),
- longer CTA holds,
- optional trims or coverage sections.

### 5. Post-Render Verification (MANDATORY)

渲染完成后，**必须**执行以下校验：

1. **零重叠校验**：检测最终音频中任意相邻段落的间隔 ≥ 100ms
2. **零变速校验**：确认未使用任何 atempo 滤镜
3. **SRT 同步校验**：抽检至少 5 个段落的字幕显示时间与音频播放时间的偏差 ≤ 50ms
4. **完整性校验**：运行 `ffprobe` 验证最终 MP4 的音视频轨完整性

Record findings in:

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.locale_notes`

### 6. Quality Gate

- each locale output exists,
- the dub and subtitle timing are acceptable,
- **Serial Queue Mix algorithm was used (no atempo, no truncation)**,
- **SRT timestamps match actual audio placement**,
- labels and filenames are unambiguous,
- warnings are preserved.

## Common Pitfalls

- Rendering all locales as if they were timing-identical.
- Forgetting to re-check subtitle line length after translation.
- Naming outputs in ways that hide the locale or treatment mode.
- **Placing TTS audio at original English timestamps without serial queue adjustment** — causes overlap.
- **Using atempo to fit TTS into original time windows** — causes speed instability.
- **Reusing English SRT timestamps for dubbed audio** — causes subtitle desync.
