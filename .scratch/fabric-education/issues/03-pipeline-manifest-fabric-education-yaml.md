# 03 — Pipeline manifest: fabric-education.yaml

**What to build:** 新建 `pipeline_defs/fabric-education.yaml`，定义面料教育内容生产管线，包含 6 个 stage 的完整编排。

**Blocked by:** 01 (Schema: fabric_edu_brief + note_manifest)

**Status:** ready-for-agent

- [ ] 继承 `fabric-promotion-directed.yaml` 的 YAML 结构和安全惯例（Provider Lockdown 引用、路径规范、governance 字段）
- [ ] 6 个 stage 定义：
  - `brief`（产出 `fabric_edu_brief`，`human_approval_default: true`）
  - `notes`（产出 `note_manifest`，`human_approval_default: true`）
  - `decide`（不产出 JSON artifact 的决策路由 stage，`human_approval_default: true`）
  - `video`（产出 `edit_decisions` + `render_report`，`human_approval_default: false`）
  - `publish`（产出 `publish_copy`，`human_approval_default: true`）
  - `retrospective`（产出 `retrospective`，`human_approval_default: false`）
- [ ] 每个 stage 有正确的 `skill` 引用（`pipelines/fabric-education/<stage>-director`）
- [ ] 每个 stage 有合适的 `tools_available`（教育管线只用现有工具：`image_selector`, `tts_selector`, `comfyui_video`, `pixabay_music`, `video_compose`）
- [ ] `required_skills` 列表正确引用 4 个 director + 2 个 meta skill（reviewer, checkpoint-protocol）
- [ ] `orchestration` 块：`executive-producer` 模式，合理的 `budget_default_usd` 和 `max_revisions_per_stage`
- [ ] `metadata.governance` 块声明 4 条 AGENTS.md 红线的落地位置
- [ ] Truth-Gate 约束声明（所有面料画面必须 img2img，知识点不可虚构）
- [ ] `review_focus` 和 `success_criteria` 对每个 stage 完整
