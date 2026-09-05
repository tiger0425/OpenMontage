# 1-3 小时长视频极速混流架构

---
状态: done
类型: wayfinder:prototype
指派: 1293e4db
阻塞于: 无
---

> 已产出 `findings/06-stream-loop-architecture.md`

## 问题

针对 1~3 小时超长视频合成过程中的算力过载与耗时瓶颈，建立轻量、极速、高质量的「长音轨 + 短视频母本」混流渲染方案：

1. **工程痛点验证**：
   - 如果使用传统视频渲染引擎逐帧渲染 1 小时 30fps 视频（108,000 帧），耗时需数小时且产生巨大临时文件；
   - 本方案必须将视觉渲染限制在 10s~30s 短母本，长视频阶段只做流式复用。
2. **FFmpeg Stream Loop 方案设计**：
   - 探究 `ffmpeg -stream_loop -1 -i visual_loop.mp4 -i audio_3h.mp3 -shortest -c:v copy -c:a aac -b:a 320k output_3h.mp4` 之类的极速混流命令；
   - 验证视频流 `-c:v copy` 是否会导致音视频不同步（PTS 溢出、关键帧漂移）？如果不 copy，使用极速硬件编码（如 NVENC / QSV / x264 ultrafast）耗时如何？
3. **输出规格与文件体积控制**：
   - 1080p 16:9 30fps 目标码率设定（建议 4000-6000 kbps）；
   - 1 小时与 3 小时成品的最终体积评估（确保符合 YouTube 推荐标准且磁盘友好）。
4. **性能基准测试（Benchmark）**：
   - 实测合成 15 分钟、1 小时、3 小时视频的 CPU 占用、显存占用与耗时（目标：1 小时视频 2 分钟内完成混流合成）。

产出：`findings/06-stream-loop-architecture.md`
