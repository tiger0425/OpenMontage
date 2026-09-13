# VOX 课程模板引擎 (apps/vox-course/template/)

本目录包含 VOX 风格科技/硬核课程的自动化合成渲染引擎。

## 1. 核心文件
- `generate_composition.py`: 根据 `course_episode.json` 与合成音频，动态计算各幕起止时间、组装全套纸张卡片、撕纸动效、硬核印章、动态折线与条形图表、毫秒级高对比度字幕条，输出标准的 HyperFrames `index.html`。

## 2. 设计规范与技术指标
- **渲染分辨率**：`1920x1080`（可无损重采样压制为 4K UHD HEVC）。
- **帧率**：`30fps`。
- **时间轴驱动**：GSAP 3.14.2（`window.__timelines["main"]`，纯函数式时间驱动，具备毫秒级 Seek 确定性与回放一致性）。
- **音效自动化**：换幕自动挂载 `paper_slide.wav`，关键结论印章下落自动挂载 `stamp_thud.wav`。
- **字幕规范**：悬浮暗黑卡片 + 终端荧光绿强调条，毫秒级高亮与字句淡入淡出。
- **尾部留白**：课程解说完结后，预留 4.0 秒视觉展板定格与 BGM 优雅渐弱淡出（volume -> 0）。

## 3. 手动调试与验证
```powershell
python apps/vox-course/template/generate_composition.py `
  projects/agent-harness-ep01/artifacts/course_episode.json `
  projects/agent-harness-ep01/assets `
  projects/agent-harness-ep01/hyperframes_test/index.html
```
