# V2 风格规范与锚点沉淀

---
状态: done
类型: wayfinder:task
指派: opencode 主会话（2026-08-26 认领）
阻塞于: 无
---

> 完成（AFK 任务票）：`styles/ref-remake.yaml` playbook 落盘并通过 schema 校验；锚点图沉淀至 `background_library/ref-remake/anchor/ahhuang_anchor.png`；使用规范写入 `background_library/ref-remake/README.md`（工具调用 + 防漂移关键词 + 实测基线）。详见 `findings/04-v2-style-spec-settling.md`。

## 问题

把已验证的视觉方案沉淀为管线默认资产，落位到正式路径（styles playbook + 项目模板），供 ref-remake 每集复用：

- 风格规范 `projects/healthy-body-cn/artifacts/visual_style_v2.md` → 提炼为管线 playbook（`styles/ref-remake.yaml`，对照 `schemas/styles/playbook.schema.json`）
- 角色一致性 `projects/healthy-body-cn/artifacts/character_consistency_guide.md` → 锚点图固定为项目级资产（候选：`projects/<project>/assets/images/anchor.png` 或管线级 `assets/` 下），写明调用规范（messages 参考图 + 强风格约束块）
- 锚点源图 `projects/times-you-almost-died-cn/assets/images/v2/01_opening_title.png` 的复制/引用策略
- 风格块英文模板（含防 3D、防墨镜、防堆砌关键词）随 playbook 固化

本票（AFK，可独立执行）：产出 playbook 草案 + 锚点资产落位 + 每集调用指引。与《管线 manifest 与阶段设计定案》对接 assets 阶段用法。
