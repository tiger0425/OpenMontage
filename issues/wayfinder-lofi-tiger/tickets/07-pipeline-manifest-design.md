# 管线 manifest 与 CLI 阶段设计

---
状态: done
类型: wayfinder:task
指派: 1293e4db
阻塞于: 无
---

> 已产出 `findings/07-pipeline-manifest-design.md`

## 问题

将 lofi 小老虎长视频生产流程固化为 OpenMontage 标准管线（`pipeline_defs/lofi-tiger.yaml` 与 `bin/lofi_tiger.py`）：

1. **管线阶段划分（Stages）**：
   - Stage 1: `brand-kit`（一次性产出频道名、logo、banner、SEO 模板，人工选定）；
   - Stage 2: `scene-spec`（设定单集主题，如 "Rainy Midnight Study"，包含角色姿态、伴侣、环境声类型，产出场景描述与 Prompt）；
   - Stage 3: `audio-prep`【闸门 A·音频试听】（生成 lofi 音乐片段 + 检索白噪音 + 混音，生成 10s 预览供人工试听放行）；
   - Stage 4: `visual-prep`【闸门 B·视觉质检】（生成母图 + 视频微动母本，人工确认角色无崩坏、微动无突兀跳帧）；
   - Stage 5: `stream-compose`（极速混流生成 1-3 小时最终成片，Compute Worker 派发）；
   - Stage 6: `package`（打包成片、高清封面图、YouTube 标题、英文 Description、SEO 标签池）。
2. **轻/重任务拆分与 Log Barrier 规范**：
   - 严格遵循 `AGENT_GUIDE.md` 规范：Stage 1-4 为轻量交互阶段，Stage 5 (流式长混流) 派 Compute Worker 异步执行，以 JSON 单行返回进度与结果。
3. **Canonical Artifact Schemas**：
   - 梳理各阶段标准 JSON 产物 Schema（`brand_kit.schema.json`, `lofi_scene.schema.json`, `render_report.schema.json` 等）。

产出：`findings/07-pipeline-manifest-design.md`
