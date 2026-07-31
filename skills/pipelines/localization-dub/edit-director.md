# Edit Director - Localization Dub Pipeline

## When To Use

Translate the scene plan and localized asset kit into concrete timeline decisions for each language output. The goal is to preserve the source structure where possible without pretending all languages land on the same timing.

## Reference Inputs

- `skills/pipelines/localization-dub/lessons-learned.md` — **必读**，包含铁律 A（禁止变速）和铁律 B（串行排队混音）

## Process

### 1. Preserve Structure By Default

Keep the original scene order and major timing unless the translated audio clearly requires extension, compression, or coverage.

### 2. Apply The Chosen Dub Mode

Per deliverable, decide where to:

- keep original picture with new subtitles,
- replace only the audio,
- use lip-sync output,
- cover mismatch with graphics or B-roll.

### 3. Specify Audio Timeline Algorithm (MANDATORY)

The `edit_decisions` artifact **MUST** include the following fields:

```yaml
mix_algorithm: "serial_queue"          # 串行排队混音，见 lessons-learned.md 铁律 B
timing_drift_policy: "allow_natural_extension"  # 允许配音自然延伸到原始停顿间隙
min_pause_between_segments_ms: 100     # 相邻段落最小物理间隔（毫秒）
speed_modification: "forbidden"        # 严禁 atempo 等任何变速处理
```

**硬性约束**：
- ❌ 禁止在 `timing_adjustments` 中输出任何 `atempo`、`speed`、`tempo` 相关指令
- ✅ 唯一允许的时间调整方式是串行排队推延（Push-Forward）

### 4. Keep Language Variants Organized

Separate timeline decisions by locale so versioning stays clear all the way into compose and publish.

### 5. Use Metadata For Variant Control

Recommended metadata keys:

- `locale_timeline_map`
- `timing_adjustments`
- `coverage_sections`
- `subtitle_strategy_by_locale`
- `mix_algorithm`
- `timing_drift_policy`

### 6. Quality Gate

- language variants are explicit,
- timing changes are recorded,
- coverage decisions are deliberate,
- the original structure is only changed where necessary,
- **`mix_algorithm` is set to `"serial_queue"`**,
- **no atempo or speed modification directives exist in the output**.

## Common Pitfalls

- Forcing every language to match source timing exactly.
- Mixing locale-specific notes into one ambiguous edit list.
- Hiding sections where the dub treatment is visually weak.
- **Using atempo to compress TTS audio into the original time window** — this causes speed instability and is strictly forbidden.
