# MiniMaxImage 工具补强 reference_image 参数

---
状态: done
类型: wayfinder:task
指派: opencode 主会话（2026-08-26 认领）
阻塞于: 无
---

> 完成（AFK 任务票）：`tools/graphics/minimax_image.py` 已补 `reference_image` + `reference_instruction` 参数，走 `messages` 参考图格式（与已验证脚本一致），参考图模式下 prompt_optimizer 默认 OFF；真实 API 冒烟通过（锚点图 → 720×1280 竖屏，$0.005）。详见 `findings/03-minimax-tool-reference-image.md`。

## 问题

`tools/graphics/minimax_image.py` 的 MiniMaxImage 工具类**不支持**参考图参数，而 ref-remake 管线依赖 MiniMax image-01 的 `messages` 参考图调用方式（实测 75-80% 角色一致性）；当前会话用 requests 直调 `https://api.minimaxi.com/v1/image_generation` 绕过工具类。

本票（AFK，可独立执行）：给 MiniMaxImage 工具类补 `reference_image`（及必要的参考图强度/风格参数）支持，让生图环节走回 registry 工具契约（继承 BaseTool，selector 路由），并验证：

- 参数契约与既有 image-01 参数（aspect_ratio、seed 等）的兼容
- 参考图 + 强风格约束的调用格式（对照交接文档「参考图无风格约束 6/10 / 参考图+强风格约束 7.5/10」的实测）
- 回归：不带参考图的既有调用不受影响

产出：工具类改动 + 冒烟验证记录。这是 assets 阶段生图规范的前置条件。
