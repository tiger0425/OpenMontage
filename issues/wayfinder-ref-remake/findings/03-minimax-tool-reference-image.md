# 03 MiniMaxImage 工具补强 reference_image 参数（完成）

> 工单《MiniMaxImage 工具补强 reference_image 参数》决议（2026-08-26，AFK 任务票，已完成）。

## 改动

文件：`tools/graphics/minimax_image.py`（MiniMaxImage，v0.1.0 → 未升版，仅增强）

1. **capabilities**：新增 `image_to_image`。
2. **supports**：新增 `reference_image: True`。
3. **input_schema**：新增两个参数——
   - `reference_image`（string）：本地图片路径或 http(s) URL 视觉锚点；本地文件自动转 base64 data URL，经 API `messages` 字段发送。
   - `reference_instruction`（string，可选）：参考图配套指令文本，默认 `"Copy this character design and 2D cartoon art style exactly."`（与已验证脚本一致）。
4. **execute()**：当传入 `reference_image` 时构造 `messages` 负载（image_url + text 双 content 块，与 `projects/outsmart-cn/scripts/gen_all_frames.py` 实测格式一致）；**参考图模式下 `prompt_optimizer` 默认 OFF**（沿用已验证管线行为），非参考图模式保持原默认 ON；本地文件不存在时提前返回错误。
5. **idempotency_key_fields**：加入 `reference_image`。

## 冒烟验证（真实 API，$0.005）

- 输入：锚点图 `projects\times-you-almost-died-cn\assets\images\v2\01_opening_title.png` + 9:16 竖屏 prompt + seed 6001
- 结果：`success: true`；输出 `projects\ref-remake-smoke\assets\images\smoke_ref_test.png`（720×1280 RGB，99KB）
- 工具状态：`ToolStatus.AVAILABLE`（key 从 `~/.local/share/opencode/auth.json` 的 `minimax-cn-coding-plan.key` 注入）

## 回归

- 不带 `reference_image` 的既有调用路径未改动（`prompt_optimizer` 默认 ON 分支保留）。
- schema 检查通过：`reference_image` / `reference_instruction` 均在 input_schema 中。

## 备注

- 冒烟产物保留在 `projects/ref-remake-smoke/`（gitignored，可删）。
- 生图质量/角色一致性的数值验收（75-80%）属于成片质检环节（review 阶段 M3 抽帧），不在本工具票范围。
