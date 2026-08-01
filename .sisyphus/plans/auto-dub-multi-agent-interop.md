# Auto-Dub 跨平台多智能体改造 + 翻译拆分修复 实施计划

## 摘要

对 OpenMontage 的 Auto-Dub 批量翻译管线做两项改造：
1. **跨平台多智能体协作**：将「主 Agent 不阻塞、重耗时任务交给专门子 Agent（Worker/Subagent）隔离运行」的架构从单一环境推广到 OpenCode、OpenClaw、Cursor、Windsurf 等外置智能体引擎，通过「规则契约层 → CLI 接口层 → 日志心跳层 → GPU 物理互斥锁」四层标准化落地。
2. **翻译拆分 bug 修复**：修复 `_split_semantic` 对短句预算过小、超长/错位翻译被切碎放大、子段时长均摊假设错误的问题链。

## 背景

### 现状差距（代码级定位）

| 需求 | 现状 | 差距 |
|------|------|------|
| 长短解耦命令 | `bin/auto_dub.py` 只有 `scan/filter/process/run/status/mark-done` | 无 `render-assets`/`render-video`/`run-heavy`；重算力阶段无法单独派发 |
| GPU 互斥锁 | `_get_indextts_server()` 仅进程内 `threading.Lock`（pipeline_automator.py:819）；VoxCPM 的 `_MODEL_CACHE` 也是进程内缓存（voxcpm_tts.py:16） | 跨智能体多进程并发时必然 VRAM OOM |
| 心跳 + flush | TTS 合成循环有 `print`（pipeline_automator.py:493）但无 `flush=True`、无 ETA、无耗时 | 管道下输出缓冲，子窗口看不到实时进度 |
| 日志屏障协议 | `AGENT_GUIDE.md`、`auto-dub/SKILL.md` 均无主/子会话输出规范 | 主 Agent 会被几百行进度淹没 |
| 跨平台契约 | `CLAUDE.md`/`CODEX.md`/`CURSOR.md`/`.windsurfrules`/`AGENTS.md` 全部指向 `AGENT_GUIDE.md` | 规范写入 `AGENT_GUIDE.md` 即可被所有客户端读取 |

### 翻译拆分 bug 链

| 环节 | 代码位置 | 现状 |
|------|---------|------|
| 预算计算 | `measured_char_budget`（voxcpm_speed_calibrator.py:148） | `max(2, int(dur*cps*0.95))`，1.4s 短句 → 8 字 |
| 拆分触发 | `_translate_segments`（pipeline_automator.py:329） | 翻译超预算即 `_split_semantic` 切碎 |
| 拆分放大 | `_split_semantic`（pipeline_automator.py:1015） | 按 8 字切 → 8 条碎段，复用整句英文 text |
| 时长分配 | pipeline_automator.py:341-343 | 子段 start/end 按字符比例均摊原句时长 |
| 重翻路径 | pipeline_automator.py:937 | `budget = max(3, ...)` 下限同样过低 |

## 目标

1. 所有智能体客户端能按同一套逻辑协调主/子 Agent 分工，主 Agent 保持非阻塞。
2. 重算力阶段可通过独立 CLI 子命令派发给 Compute Worker 隔离运行。
3. 子 Agent 运行时进度实时可见（心跳 + flush），但只向主 Agent 回报精简 JSON 摘要。
4. 跨智能体/多进程并发访问 GPU 时通过文件级互斥锁排队，杜绝 VRAM OOM。
5. 修复翻译拆分 bug：短句预算设下限、超长翻译不盲目切碎、子段时长用实测语速预测。

## 技术决策

| # | 决策项 | 结论 | 理由 |
|---|---|---|---|
| 1 | GPU 锁作用域 | pipeline assets 阶段持锁（覆盖 IndexTTS2 常驻服务全程）；voxcpm 工具层仅预留 | 当前 `tts_engine: indextts`，主战场在 pipeline_automator |
| 2 | 漂移重翻策略 | 重活走 `run-heavy`（保留自动重翻循环）；单段命令漂移超标返回结构化错误并建议 run-heavy | 逻辑最清晰，避免上下文跳跃 |
| 3 | DB 状态 | 复用现有 `processing/done/failed`，不扩状态机 | 最小侵入 |
| 4 | 锁文件位置 | `%LOCALAPPDATA%/openmontage/.gpu.lock`（可 `OPENMONTAGE_GPU_LOCK_PATH` 覆盖） | 用户级共享，不同智能体/工作目录共用一把锁 |
| 5 | 预算下限 | `max(15, measured_char_budget(...))`，config 可配置 `pipeline.min_char_budget` | 短句 15 字内可正常翻译 |
| 6 | 拆分阈值 | `≤max_chars` 单条 / `≤60` 整句不拆（混音自然顺延）/ `>60` 拆分；`pipeline.max_single_line_chars` 可配置 | 切断"错位翻译被切碎放大"问题链 |
| 7 | 子段时长 | 拆分子段 start/end 按 `len(chunk)/cps` 预测，不再按字符比例均摊 | 均摊把超长翻译硬压回原时长，放大漂移 |

## 验证策略

1. **预算下限单测**：`measured_char_budget(1.4, 6.42)` 返回 15（而非 8）。
2. **拆分逻辑单测**：40 字翻译 + max_chars=8 → 不拆分（单条）；70 字 → 拆，且子段时长按 `len/cps`。
3. **CLI 冒烟**：`--help` 确认新子命令；`render-assets --json` 末行单行 JSON。
4. **锁**：双进程并发 `_generate`，第二个排队等待、无 OOM。
5. **回归**：`status`/`run` 正常；`tests/tools/test_clip_cache.py` 不回归。

## 执行策略

```
阶段 0  基线固化（提交 IndexTTS2 迁移、写本计划文档）
阶段 1  规则契约层（AGENT_GUIDE.md + SKILL.md，文档先行）
阶段 2  翻译拆分 bug 修复（TDD：先写回归测试再改代码）
阶段 3  CLI 长短解耦（render-assets/render-video/run-heavy + --json/--quiet）
阶段 4  日志心跳层（_heartbeat + 结构化心跳 + summary + 分阶段方法）
阶段 5  GPU 物理互斥锁（lib/gpu_lock.py + assets 持锁）
阶段 6  综合回归
```

每个阶段独立 commit，便于 review 与回滚。

## 变更文件清单

| 类型 | 文件 | 改动 |
|------|------|------|
| 文档 | `AGENT_GUIDE.md` | 新增《多智能体分工与任务解耦规范》《日志屏障协议》两节 |
| 文档 | `.agents/skills/auto-dub/SKILL.md` | 命令速查 + 《子 Agent 汇报契约》 |
| 修复 | `tools/audio/voxcpm_speed_calibrator.py` | `measured_char_budget` 加 `min_budget=15` 参数 |
| 修复 | `apps/auto-dub/config.yaml` | 新增 `pipeline.min_char_budget`、`pipeline.max_single_line_chars` |
| 修复 | `apps/auto-dub/batch/pipeline_automator.py` | 三档拆分、`len/cps` 时长、`_heartbeat`、`summary`、`render_assets_only`/`render_video_only`、gpu_lock |
| 新增 | `bin/auto_dub.py` | `--json`/`--quiet` + 三个新子命令 |
| 新增 | `apps/auto-dub/batch/batch_runner.py` | `render_assets`/`render_video`/`run_heavy` 方法 |
| 新增 | `lib/gpu_lock.py` | `filelock.FileLock` + `O_EXCL` 兜底；`gpu_lock(label, timeout=1800)` |

## 风险与约束

- 拆分只会在 `len(trans) > 60` 时发生，正常短句（≤60）不再被切碎。
- 子段时长改用 `len/cps` 后，若 cps 缓存不准，预测偏差由 assets 阶段串行队列与 SRT 重同步兜底。
- 文档（第 1 层）先行，可立即验证 OpenCode/OpenClaw 读取即生效。
- IndexTTS2 常驻服务持锁期间另一 Agent 排队等待，最长 30 分钟超时；超时后报错不崩溃。

## 成功标准

- [x] 三档拆分逻辑生效，短句不再被切碎，超长翻译时长按实测语速预测
- [x] `render-assets`/`render-video`/`run-heavy` 子命令可用，`--json` 输出单行摘要
- [x] TTS 合成循环 stdout 实时显示 `[AutoDub] ... ETA` 心跳
- [x] 双进程并发访问 GPU 时第二个进程排队等待，无 OOM（tests/auto_dub/test_gpu_lock.py）
- [x] `AGENT_GUIDE.md` + `SKILL.md` 含完整主/子 Agent 协作契约与日志屏障协议

## 执行结果

| 阶段 | Commit | 状态 |
|------|--------|------|
| 0a 基线固化（IndexTTS2 迁移） | `3ef4887` | 完成 |
| 0b 计划文档 | `c277575` | 完成 |
| 1 规则契约层 | `747fc39` | 完成 |
| 2 翻译拆分 bug 修复（TDD） | `d6b05c9` | 完成，8 测试 |
| 3 CLI 长短解耦 | `57a37b9` | 完成 |
| 4 日志心跳层 | `3461f73` | 完成 |
| 5 GPU 物理互斥锁 | `38a4104` | 完成，2 测试 |
| 6 综合回归 | — | 33 测试全绿 + CLI 冒烟通过 |
