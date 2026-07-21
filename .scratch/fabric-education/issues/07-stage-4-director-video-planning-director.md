# 07 — Stage 4 director: video-planning-director.md

**What to build:** 新建 `skills/pipelines/fabric-education/video-planning-director.md`，定义从 note_manifest（或 fabric_edu_brief）到视频产出的两条路径——深度完整视频（4a）和普通知识切片（4b）。

**Blocked by:** 03 (Pipeline manifest: fabric-education.yaml)

**Status:** ready-for-agent

**路径 4a — 深度视频（3-8min）：**
- [ ] 教育叙事骨架：钩子→问题→拆解→解决方案→总结
- [ ] 脚本书写：基于 note_manifest.core_article 提取配音稿，5 段结构
- [ ] 场景规划：每场指定配图/视频类型、时长、shot_language
- [ ] 通过 `tts_selector`（VoxCPM）生成配音，确保多段音色一致
- [ ] 通过 `pixabay_music` 挑选匹配面料调性的 BGM
- [ ] 通过 `comfyui_video`（img2img）生成面料动态展示画面
- [ ] 通过 `video_compose`（render_runtime="hyperframes"）合成
- [ ] 产出 `edit_decisions` + `render_report`
- [ ] 自动切出 1-2 条知识切片（用于小红书/朋友圈）

**路径 4b — 知识切片（15-30s）：**
- [ ] 从 note_manifest 或 fabric_edu_brief 提取一个核心知识点
- [ ] 出一条竖版（9:16）短视频
- [ ] 配音 + 静态面料画面（Ken Burns 或 img2img）
- [ ] 通过 `video_compose` 合成
- [ ] 产出 `edit_decisions` + `render_report`
