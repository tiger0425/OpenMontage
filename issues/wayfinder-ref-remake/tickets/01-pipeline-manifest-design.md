# 管线 manifest 与阶段设计定案

---
状态: done
类型: wayfinder:grilling
指派: opencode 主会话（2026-08-26 认领）
阻塞于: 无
---

> 定案（用户确认七项决策，全部按推荐采纳）：八阶段 fetch → brief(含参考分析子阶段) → script【闸门A】→ scene_plan → assets → compose → review【人审】→ package；拆集提案入 brief 随闸门审；时间轴=TTS 实测+字数比例兜底；全复用既有 schema（publish_copy/cover_manifest 执行期补 douyin 分支）；红线扫描入 script 产物为闸门必需附件；checkpoint 策略 guided；assets/compose 派 Compute Worker。详见 `findings/01-pipeline-manifest-design.md`。

## 问题

ref-remake 管线的正式设计定案，输出形式为设计定案文本提案（manifest/schema 落文件属执行期工作，本图不落码）：

- 阶段划分草案：fetch（下载+转录+抽帧+风格分析）→ brief（知识提取+改写要点）→ script【闸门A】→ scene_plan（时间轴分配）→ assets（IndexTTS 配音 + MiniMax 生图+锚点）→ compose（HyperFrames 合成）→ review（M3 抽帧质检·人审）→ package（双平台成品包+图文笔记）。是否成立？要不要增删？
- 超长片可选拆（>8 分钟、内容可分、提案人审拆 2 集）落在哪个阶段、如何表达？
- 时间轴分配：按字数比例（已验证 3 条）vs whisper 时间戳；是否固定为「ffprobe 实测段长 + 字数比例」？
- 每阶段 produces 的 canonical artifact 与 schema 字段（参考 series-adapt / repo-to-video 既有 schema）
- human_approval_default 设置（script 与 review 必须 true）
- required_tools / fallback_tools 清单（依据交接文档工具现状填实）
- BGM 可选接口的挂载点（默认无）
- 与既有 checkpoint / reviewer 协议的对齐方式；轻/重阶段拆分（配音/生图/渲染属重，派 Worker）

参考基线：交接文档通用生产流程①-⑦ + 既有管线 `pipeline_defs/series-adapt.yaml`、`pipeline_defs/repo-to-video.yaml`。
