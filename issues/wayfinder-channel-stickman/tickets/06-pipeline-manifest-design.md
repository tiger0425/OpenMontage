# 管线 manifest 与阶段设计

---
状态: done
类型: wayfinder:grilling
指派: opencode 主会话
阻塞于: 无
---

> 定案（用户确认七阶段+双闸门、brand-kit 一次性人审）：`findings/06-pipeline-manifest-design.md`。执行期落 `pipeline_defs/channel-stickman.yaml`。

## 问题

channel-stickman 管线的正式设计定案：

- 阶段划分草案：频道摄取 → 资产包 → 选片与分集 → 脚本【闸门】→ 场景/资产 → 合成 → 包装，是否成立？要不要增删？
- 每阶段 produces 的 canonical artifact 与 schema 字段
- human_approval_default 设置（脚本闸门必须 true）
- required_tools / fallback_tools 清单（依据盘点结论填实）
- 与既有 checkpoint / reviewer 协议的对齐方式

产出形态：设计定案的文本提案（manifest/schema 落文件属执行期工作，本图不落码）。
