# 本机可复用资产盘点

---
状态: done
类型: wayfinder:research
指派: 已完成
阻塞于: 无
---

> 已产出 `findings/01-reusable-assets.md`

## 问题

为 channel-stickman 管线摸清可复用家底，逐项给出「可复用结论 + 入口路径 + 缺口清单」：

1. auto-dub 的下载（yt-dlp）、转录（whisper）、混音、字幕环节，哪些函数/CLI 可直接复用？入口在哪？
2. character-animation 管线的 SVG rig 规格、pose library、动作 clip 机制、预览与 QA 工具的调用方式？
3. google_imagen 工具的入参契约：支持哪些尺寸/数量？是否支持参考图或 seed 固定？
4. wrc-pipeline 的分幕脚本与成品包经验，哪些适用于「按叙事内容拆集」？
5. LLM 脚本改写在本仓库的先例做法（哪个管线/工具承担文本生成）？

产出：`findings/01-reusable-assets.md`
