# 04 — Pipeline manifest 结构测试

**What to build:** 在 `tests/contracts/test_phase0_contracts.py` 中验证新 pipeline manifest 能加载、结构正确、artifact 依赖闭环。

**Blocked by:** 03 (Pipeline manifest: fabric-education.yaml)

**Status:** ready-for-agent

- [ ] `test_fabric_education_manifest_loads` — `load_pipeline("fabric-education")` 不抛异常，返回合法结构
- [ ] `test_fabric_education_stages_have_skills` — 所有 stage 有非空 `skill` 字段
- [ ] `test_fabric_education_artifact_dependencies_close` — 所有 `required_artifacts_in` 都能被上游某 stage 的 `produces` 覆盖
- [ ] `test_fabric_education_pipeline_listed` — `"fabric-education"` 在 `list_pipelines()` 返回中
- [ ] 运行 `pytest tests/contracts/test_phase0_contracts.py -k "fabric_education"` 确认全绿
