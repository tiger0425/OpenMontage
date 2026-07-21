# 01 — Schema: fabric_edu_brief + note_manifest

**What to build:** 新增两个 artifact JSON Schema 文件，定义面料教育简报和笔记产出的数据结构。确保它们与 OpenMontage 现有的 schema 惯例一致（JSON Schema 2020-12，`$id` 命名空间，existing schema style）。

**Blocked by:** None — 可立即开始

**Status:** ready-for-agent

- [ ] `schemas/artifacts/fabric_edu_brief.schema.json` — 面料教育简报
  - 必填字段：`version`, `fabric_name`, `composition`, `weight`, `knowledge_depth`, `pitfalls`, `educational_angle`
  - 可选字段：`weave`, `finishing`, `season`, `comparison_materials`, `origin_image`, `metadata`
  - `version` 为 `"1.0"`（const）
  - `knowledge_depth` 枚举：`"basic"`, `"deep"`
- [ ] `schemas/artifacts/note_manifest.schema.json` — 笔记产出清单
  - 必填字段：`version`, `core_article`, `platform_versions`, `fabric_origin_image`
  - `platform_versions` 为数组，每项含 `platform`（枚举：xiaohongshu / wechat_public / zhihu / moments / bilibili）、`title`、`body`、`images` 数组、`tags` 数组
  - `images` 数组每项含 `path`、`educational_role`（枚举：`microscopic_detail` / `comparison_diagram` / `care_label_explained` / `test_scene` / `diagram`）
- [ ] 遵循现有 schema 惯例：`$schema`、`$id`、`title`、`description`、`type`、`additionalProperties: false`
- [ ] `$id` 格式：`openmontage/artifacts/fabric_edu_brief`
- [ ] 验证两个新 schema 本身是合法 JSON Schema（可通过 JSON Schema 验证工具）
