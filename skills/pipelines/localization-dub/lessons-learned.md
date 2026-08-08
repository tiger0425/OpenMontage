# Localization-Dub Pipeline — 实战避坑与最佳实践指南 (Lessons Learned)

> **适用范围**：使用 `localization-dub` 管线时，所有 Agent **必须在执行任何阶段前强制阅读本文档**。
> 本文档包含从真实项目中反复迭代总结的硬性规则，违反任何一条都会导致成品质量严重下降。

---

## 🚨 两条铁律 (Iron Rules)

### 铁律 A：禁止 atempo 变速 (Zero Speed Modification)

**严禁**对 TTS 生成的配音音频施加任何形式的变速处理。

- ❌ 禁止使用 `ffmpeg atempo`
- ❌ 禁止使用 `rubberband`、`sox tempo`、`pydub speedup` 或任何等效工具
- ❌ 禁止通过重采样率变更（如 44100→48000）间接改变语速

**原因**：中文与英文的自然语速天然不同。强行将中文音频压入英文时间窗会导致：
- 语速忽快忽慢，听感极度恶劣
- 音调失真、机械感严重
- 不同段落的变速倍率不一致，全片节奏混乱

**正确做法**：TTS 音频以 **原生 1.0x 速度**直接使用，配合铁律 B 的串行排队算法自然放置。

---

### 铁律 B：串行排队混音算法 (Serial Queue Mix)

所有配音段落在主音轨上按**串行排队**方式放置，保证每段语音 **100% 完整播放、0% 重叠**。

#### 算法规则：

```
对于第 i 段配音：
  ideal_start = 原始英文时间戳（秒）
  actual_start = max(ideal_start, previous_end + 0.10)   ← 100ms 最小停顿
  actual_end   = actual_start + len(tts_audio) / sample_rate
  previous_end = actual_end
```

#### 关键约束：

| 约束项 | 值 | 说明 |
|--------|-----|------|
| 最小段落间隔 | **100ms** | 相邻段落物理隔离，杜绝重叠 |
| 段尾淡出 | **15ms** | 消除截断爆音与边缘噪声 |
| 段首淡入 | **15ms** | 消除起始爆音 |
| 截断 | **禁止** | 每段 TTS 音频必须完整放入，不允许裁剪尾部 |
| 变速 | **禁止** | 见铁律 A |

#### 字幕动态重同步：

SRT 字幕的时间戳**必须**根据混音后各段的 `actual_start` 和 `actual_end` 重新生成，**严禁**沿用原始英文时间戳。

---

## 📋 各阶段执行要点

### Script 阶段（翻译）
- **尽量简炼**：用地道凝练的中文口语表达，避免不必要的长句
- **严禁过度砍删**：不为了机械匹配时间而删除有意义的内容
- 极短段落（`< 0.8s`）可精简为 2~4 个字

### Assets 阶段（TTS 合成）
- 全局锚点文件 `voice_reference.wav`（5~10 秒纯净人声）必须存在
- 每次 TTS 调用必须传入 `reference_wav_path`，保证多段音色 100% 一致
- 保持 `seed=42`、`cfg_value=3.0` 参数稳定

### Edit 阶段（时间轴规划）
- `edit_decisions` 必须包含 `mix_algorithm: "serial_queue"`
- `timing_drift_policy: "allow_natural_extension"` — 允许自然延伸
- 禁止输出任何 atempo 相关的变速指令

### Compose 阶段（混音渲染）
- 严格执行 Serial Queue Mix 算法
- 渲染后校验：相邻段落间隔 ≥ 100ms，无能量重叠区间
- SRT 字幕必须与实际音频位置毫秒级同步

---

## ⚠️ 反模式警示 (Anti-Patterns)

以下做法在本管线中**绝对禁止**：

1. ❌ 按原始英文时间戳硬放中文音频 → 必然重叠
2. ❌ 用 atempo 压缩音频去适配时间窗 → 语速失真
3. ❌ 截断超长音频的尾部 → 句子说不完
4. ❌ 字幕沿用英文原始时间戳 → 字幕脱节
5. ❌ 不同段落使用不同变速倍率 → 全片语速混乱

---

## 🎨 系列封面设计 — 实战经验 (Cover Series Best Practices)

> 来源：`auto-dub-gaDdrDdczO4` 封面重建（2026-08-08 验证）。

### 铁律 C：系列封面用「固定 HTML 母版」，不做图生图

- ❌ 不要用 `image_selector` 每期重新生图 → 人物、色彩、字体、构图必然漂移
- ❌ 不要让右侧每期换视频缩略图（`thumb_path` 兜底）→ 系列感破碎
- ✅ 全系列共用 `apps/auto-dub/templates/cover.html` 一个母版
- ✅ 右侧使用 HTML/CSS 绘制固定技术视觉（代码窗口/技能节点/版本徽章），不依赖任何图片
- ✅ 中文标题一律由 HTML 文本渲染，绝不交给生图模型（杜绝错别字）

### 单母图双画幅：一张 16:9 母图内嵌完整 4:3 主封面区

- 画布固定 `1920x1080`；**中央** `1440x1080`（x=240..1680）为完整 4:3 主封面区
- 左右各 `240px` 只做延展背景（延续渐变，不放任何关键信息）
- 4:3 场景直接用中央区域等比输出（1200x900），**禁止**从普通 16:9 成品临时裁图
- 只维护一张母图，两个平台画幅共用，杜绝双版本漂移

### 关键坐标（cover.html 当前基线）

| 元素 | 位置 |
|------|------|
| 4:3 主区 | x `240..1680`，y `0..1080` |
| 左侧内容列 `.content` | top `115px`、bottom `115px`、left `320px`、宽 `820px` |
| 右侧技术面板 `.tech-panel` | top `115px`、right `288px`、宽 `480px`、高 `850px` |
| 垂直对齐 | 左右两块统一 `top:115 / bottom:115`，上下对称居中 |
| 左侧垂直分布 | `.content` 用 `justify-content: space-between`，顶部与面板平齐、底部金句贴左栏底部 |

### 排版避坑

- 左侧内容若用 `justify-content: center` 会在区间内下沉，顶部与右侧面板不平齐 → 用 `space-between` 或 `flex-start`
- 底部金句 `.footer-quote` **必须放进 `.content` 容器内**（`margin-top:auto`），不能绝对定位到画布底部，否则内容区移动时它原地不动
- 左右两块要同时调 `top/bottom`，保证顶边与底边都平齐

### HyperFrames 渲染避坑

- PowerShell 直接传 `--variables '{...}'` 会吞掉双引号导致 JSON 解析失败 → 改用 `--variables-file path.json`
- 静态单帧封面在 `#root` 上补 `data-no-timeline` 可跳过 45s 的 timeline 轮询超时
- 字体 `url('/e:/...')` 绝对路径在渲染 file server 下 404，会回退系统字体；如需精确字体，放到模板同目录用相对路径


