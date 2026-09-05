# 设计产物：管线 manifest 与 CLI 阶段设计

label: wayfinder:finding
工单: 《管线 manifest 与 CLI 阶段设计》

---

## 1. 管线阶段划分与阶段契约 (Stage Contracts)

针对 YouTube lofi 音乐与长视频生产特点，建立六阶段标准流水线（`pipeline_defs/lofi-tiger.yaml`）：

| 序号 | 阶段代号 (Stage) | 职责与产出物 | 工具与机制 | 人审闸门 / 角色所有权 |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `brand-kit` | 生成/选定频道名、1:1 Logo、2560x1440 Banner、通用 SEO 模板 | `minimax_image` / 模板装配 | **一次性人审**（开号期锁定） / 主 Agent |
| **02** | `scene-spec` | 选定单集主题（5×5×5 矩阵组合）、伴侣与场景，输出场景 JSON 蓝图 | LLM / 提示词装配引擎 | 自动推进 / 主 Agent |
| **03** | `audio-prep` | 生成 Lofi 乐段，检索/合成环境雨声白噪音，执行 72/28 混音与自回环闭合 | `test_audio_loop.py` / FFmpeg `acrossfade` | **【闸门 A·音频人审】** 试听放行 / 主 Agent |
| **04** | `visual-prep` | 生成 16:9 超高清主图，图生 6s 微动短片，执行中段交叉淡化（Mid-Crossfade）闭环 | `minimax_image` + `minimax_video_direct` | **【闸门 B·视觉人审】** 闭环质检 / 主 Agent |
| **05** | `stream-compose` | 将 5s 视效母本与 1~3 小时长音轨做流式极速打包混流，输出最终 MP4 | FFmpeg `-stream_loop -1 -c:v copy` | **自动执行 / Compute Worker 派发**（Log Barrier 保护） |
| **06** | `package` | 打包成片、生成带 `1 HOUR LO-FI` 角标的高清封面、YouTube 标题与分章节简介 | Pillow / FFmpeg / 元数据装配器 | 自动归档 / 主 Agent |

---

## 2. 轻重任务拆分与 Log Barrier 规范

严格遵循 `AGENT_GUIDE.md` 的 multi-agent 执行契约：
- **轻量交互阶段（Stage 1 ~ 4）**：在主 Agent 对话中交互执行，秒级响应，主 Agent 负责与用户进行方案确认与试听/质检；
- **重量级长混流阶段（Stage 5）**：虽然本管线采用极速 Stream Copy（15 分钟视频 0.59s，1 小时视频 2.4s），但为规避超大文件 I/O 导致主进程超时，依然规范包装为 Worker 命令：
  ```bash
  python bin/lofi_tiger.py render-long --project <name> --duration-hours 1 --json
  ```
  Worker 单行返回 `{"status": "completed", "output": "...", "duration": 3600, "elapsed": 2.4}`。

---

## 3. CLI 命令体系规范 (`bin/lofi_tiger.py`)

```bash
# 1. 品牌物料初始化（一次性）
python bin/lofi_tiger.py brand-kit --channel-name "Tiger & Tea"

# 2. 创建新单集（按主题组合矩阵装配）
python bin/lofi_tiger.py create-episode --theme rainy-study --companion pip --scene attic-nook

# 3. 生成并试听音频样段（闸门 A）
python bin/lofi_tiger.py preview-audio --project <project-id>

# 4. 生成并预览视觉微动母本（闸门 B）
python bin/lofi_tiger.py preview-visual --project <project-id>

# 5. 极速长视频流式混流（轻重分离执行）
python bin/lofi_tiger.py render-long --project <project-id> --duration 1h

# 6. 生成发布物料成品包（封面、SEO、标题、简介）
python bin/lofi_tiger.py package --project <project-id>
```

---

## 4. 工单关闭结论

本设计完全对齐 OpenMontage 规范，打通了从创意选型到工程落地的标准阶段链路，具备关闭条件。
