# 02 — Schema contract tests

**What to build:** 在 `tests/contracts/test_phase0_contracts.py` 中为两个新 schema 添加 `sample_artifact` 存根和验证测试，锁定契约。

**Blocked by:** 01 (Schema: fabric_edu_brief + note_manifest)

**Status:** ready-for-agent

- [ ] 新增 `sample_artifact("fabric_edu_brief")` 返回最小 schema-valid 样本
  - 遵循现有 `sample_artifact` 函数在 `test_phase0_contracts.py:46` 的惯例
- [ ] 新增 `sample_artifact("note_manifest")` 返回最小 schema-valid 样本
- [ ] `test_fabric_edu_brief_validates` — 验证有效样本通过
- [ ] `test_fabric_edu_brief_rejects_invalid` — 验证缺失必填字段被拒绝
- [ ] `test_note_manifest_validates` — 验证有效样本通过
- [ ] `test_note_manifest_rejects_invalid` — 验证缺失必填字段被拒绝
- [ ] 运行 `pytest tests/contracts/test_phase0_contracts.py -k "fabric_edu or note_manifest"` 确认全绿
