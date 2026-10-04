# console-remake template 说明

> 本目录是深色控制台世界的全部实现资产。世界规则见 `../specs/design-system.md`，实战坑见 `../specs/LESSONS.md`。

| 文件 | 角色 | 何时改 |
|---|---|---|
| `console.css` | 九零件 + 辅助原语 + 字幕条 + HUD 框架 + 舞台底纹 的样式 | 加/改零件样式、背景层、HUD |
| `console.js` | 运行时：`buildScene`（每幕 DOM+时间轴，幕内相对时间）/ `buildHost`（字幕、章节翻页、进度轨）/ 动作动效库 / 连接件测量 | 加/改零件、动效、连接件 |
| `generate_composition.py` | 装配器：episode+tts → timings.json + 薄宿主 index.html + 每幕 compositions/<id>.html + 烘焙音频 + 颗粒图 | 改数据结构、宿主模板、时间轴算法 |
| `make_cover.py` | 封面排版层（无字底稿 → 遮罩 + 标题叠字，16:9/4:3） | 改封面排版 |

## 装配器用法

```bash
python apps/console-remake/template/generate_composition.py --project projects/<slug>
python ... --no-audio              # 无配音预览（字数估时长）
python ... --scenes s01,s02,s03    # 只装指定幕（样片；时间轴归零）
```

产物结构（HyperFrames modular 架构）：

```
hyperframes/
├── index.html               # 薄宿主：槽位 + 音频 + 字幕条 + HUD 框架 + 根时间轴 "main"
├── compositions/sXX.html    # 每幕独立子合成（<template> 内自带脚本与数据）
└── assets/                  # gsap.min.js / console.css / console.js / grain.png / audio/ / images/ / footage/
```

> v2.2 真实素材：`image` 零件（真实图片，`assets/images/`，`provenance` 必填）与 scene 级
> `footage`（真实录屏，`assets/footage/`）由装配器自动拷入 `assets/`；纪律见 SKILL.md §9 / LESSONS §12。

## 运行时扩展点（加新零件/动效的步骤）

1. `console.js`：加 `buildXxx()`（DOM）与 `animElement()` 分支（时间轴，只用 fromTo）；
2. `console.css`：加样式（挂在 `.p` 基类下，初始 `opacity:0`）；
3. `specs/console_episode.schema.json`：加字段；
4. `specs/design-system.md`：加规格；若属于"关系"类零件，同步第 6.3 节；
5. 跑一遍：`compose` → `npx hyperframes snapshot --at …` 快照验形 → 再全片 `render`。

## 三个容易忘的纪律

- 子合成根样式**只能用内联**（class 会被作用域化，见 LESSONS §1）；
- 连接件（arrow/leader/bracket）几何**延迟测量**，绘制用 proxy+onUpdate（LESSONS §2）；
- 样式/背景/HUD 改动 → **全片重渲**；只改某幕台词 → 该幕重 synth + 全片 compose/render 复用。
