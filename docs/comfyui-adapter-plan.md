# ComfyUI Provider Adapter — Implementation Status

**Status: IMPLEMENTED** (原 RFC 已在 2026-07 前全部实现)

> 本文档原为 RFC 计划，现转为实现状态记录。标记为 ✅ 的组件已实现并注册，
> 标记为 ❓ 的组件需要进一步确认。

---

## 实现状态总览

| 组件 | 文件 | 状态 |
|------|------|------|
| 共享客户端 | `tools/_comfyui/client.py` | ✅ 已实现 |
| 共享元数据 | `tools/_comfyui/metadata.py` | ✅ 已实现 |
| 图片工具 | `tools/graphics/comfyui_image.py` | ✅ 已实现并注册 |
| 视频工具 | `tools/video/comfyui_video.py` | ✅ 已实现并注册 |
| Layer 3 技能 | `.agents/skills/comfyui/SKILL.md` | ✅ 已实现 |
| 工作流模板 | `tools/_comfyui/workflows/*.json` | ✅ 3 个模板已就绪 |
| 注册表集成 | `tools/tool_registry.py` 自动发现 | ✅ 自动注册 |
| Selector 就绪过滤 | `tools/video/video_selector.py` | ❓ 待确认 |
| 测试 | `tests/contracts/test_comfyui_tools.py` | ❓ 待确认 |

---

## 动机（保留）

OpenMontage 的本地 GPU 工具（`wan_video`、`hunyuan_video`、`cogvideo_video`、
`local_diffusion`）使用 HuggingFace `diffusers` 直接调用。这在 x86 + 消费级 GPU
上工作正常，但在 PyTorch 生态尚未跟上的新硬件上有问题：

| 问题 | 详情 |
|-------|--------|
| **NVIDIA Blackwell (sm_121)** | aarch64 + CUDA 13.0 无稳定的 PyTorch wheels |
| **Flash Attention** | 不支持 sm_121，需替换为 SageAttention v3 或原生 SDPA |
| **统一内存 (GB10/DGX Spark)** | `nvidia-smi` 无法报告 VRAM |
| **模型格式不匹配** | 生产环境使用 `.safetensors` checkpoints，`diffusers` 不原生支持 |

ComfyUI 已经解决了上述所有问题。适配器让 OpenMontage 能运行 ComfyUI 支持的任何模型，
任何 ComfyUI 能运行的硬件，而无需维护 PyTorch 构建。

---

## 架构（已实现 ✅）

```
OpenMontage Agent
    |
    v
video_selector / image_selector
    |
    v
comfyui_video    comfyui_image    (已实现)
    |                |
    v                v
ComfyUI REST API  (POST /prompt, GET /history, GET /view)
    |
    v
GPU (any hardware ComfyUI supports)
```

两个 `BaseTool` 子类加一个共享客户端库，目录结构如下：

```
tools/
  _comfyui/
    __init__.py           ✅
    client.py             ✅  — 共享 ComfyUI REST 客户端（296 行）
    metadata.py           ✅  — 设置 Offer、模型栈、Provenance 助手（222 行）
    workflows/            ✅
      flux2-txt2img.json       — FLUX 2 Dev NVFP4
      wan22-t2v-4step.json     — WAN 2.2 14B FP8 T2V
      wan22-i2v-4step.json     — WAN 2.2 14B FP8 I2V
  graphics/
    comfyui_image.py      ✅  — capability="image_generation", provider="comfyui"
  video/
    comfyui_video.py      ✅  — capability="video_generation", provider="comfyui"
```

---

## 共享客户端 `tools/_comfyui/client.py` — ✅ 已实现

`ComfyUIClient` 封装了完整的 submit/poll/download 周期：

| 方法 | 功能 |
|------|------|
| `is_available()` | 健康检查 — GET /system_stats |
| `submit(workflow)` | POST /prompt，返回 prompt_id |
| `poll(prompt_id)` | GET /history/{id} 轮询直到完成 |
| `download(filename, subfolder, dest)` | GET /view 下载产出 |
| `upload_image(local_path, name)` | POST /upload/image 上传参考图 |
| `generate(workflow, output_node, dest)` | 全周期：submit → poll → download |
| `load_workbook(path)` | 从磁盘加载工作流 JSON |
| `patch_workflow(workflow, patches)` | 深拷贝并注入节点参数 |

## `tools/_comfyui/metadata.py` — ✅ 已实现

包含 `COMFYUI_SETUP_OFFER`、`BUNDLED_MODEL_STACKS`（3 个工作流的模型依赖）、
`workflow_hash()`、`model_stack()`、`missing_models_payload()` 等辅助函数，
在 image 和 video 工具间共享。

---

## 工具规格（已实现 ✅）

### `comfyui_image` — 图片生成 ✅

| 字段 | 值 |
|-------|-------|
| capability | `image_generation` |
| provider | `comfyui` |
| runtime | `LOCAL_GPU` |
| tier | `GENERATE` |
| stability | `EXPERIMENTAL` |
| capabilities | `text_to_image` |
| 内置工作流 | `flux2-txt2img.json` — FLUX 2 Dev NVFP4 |
| agent_skills | `["comfyui", "flux-best-practices"]` |

支持自定义工作流（`workflow_json` / `workflow_path` + `output_node`）。

### `comfyui_video` — 视频生成 ✅

| 字段 | 值 |
|-------|-------|
| capability | `video_generation` |
| provider | `comfyui` |
| runtime | `LOCAL_GPU` |
| tier | `GENERATE` |
| stability | `EXPERIMENTAL` |
| capabilities | `text_to_video`, `image_to_video` |
| 内置工作流 | `wan22-t2v-4step.json`, `wan22-i2v-4step.json` |
| agent_skills | `["comfyui", "ai-video-gen", "ltx2"]` |

资源配置：

| 配置 | VRAM | 说明 |
|-----------|------|-------------|
| provider_floor | 8 GB | ComfyUI 可用性最低要求 |
| bundled_wan22_14b_fp8 | 16 GB | 内置 WAN 2.2 14B 工作流 |
| low_vram_custom_workflows | 8-12 GB | 适用 Wan 2.1 1.3B、LTX-Video、GGUF |

---

## `comfyui_music` — 未发布 ❌

ACE-Step 3.5B 模型可在 ComfyUI 中运行，但节点接口尚未标准化（存在多个第三方
自定义节点包，类名不同）。等音乐生成路由方案确定后再重新审视。

---

## 工作流覆盖机制 ✅

两个工具都已实现 `workflow_json` 和 `workflow_path` 参数。自定义工作流会记录
`workflow_provenance.source = "user_supplied"`，并提供 SHA-256 hash。

---

## 配置（已验证 ✅）

**环境变量：**

```bash
COMFYUI_SERVER_URL=http://localhost:8188    # 默认值
COMFYUI_POLL_INTERVAL=5                     # 工具内硬编码
COMFYUI_POLL_TIMEOUT=600                    # 工具内硬编码
COMFYUI_VIDEO_TIMEOUT=900                   # 工具内硬编码
```

Docker Compose 场景：`COMFYUI_SERVER_URL=http://host.docker.internal:8188`

---

## 选择器行为（部分实现）

当适配器可用时，选择器通过标准 7 维评分将 ComfyUI 与其他提供商并列排名。

**已知限制：**
- 操作级别的 readiness 过滤（如只为 t2v 配置了模型时避免选择 i2v）在 `video_selector` 
  中是否已实现 → ❓ 待确认
- `provider_menu()` 和 `setup_offer` 已通过 `COMFYUI_SETUP_OFFER` 注册

---

## 已实现的功能

### 立即可用（内置模型）

- ✅ **FLUX 2 Dev NVFP4** 图片生成 — Blackwell 优化
- ✅ **WAN 2.2 14B FP8** I2V 视频生成（4 步加速 LightX2V LoRA），推荐 ~16GB VRAM
- ✅ **WAN 2.2 14B FP8** T2V 视频生成，推荐 ~16GB VRAM

### 低 VRAM 配置

- ✅ 通过 `workflow_json` / `workflow_path` 支持自定义低 VRAM 工作流
- ✅ Wan 2.1 1.3B、LTX-Video、GGUF 等社区工作流

### 硬件可移植性

- ✅ NVIDIA DGX Spark (GB10, aarch64, CUDA 13.0)
- ✅ 消费级 GPU (RTX 3090/4090, x86)
- ✅ 云实例 (A100, H100)
- ✅ 多 GPU 设置

---

## 待办 / 待确认项 ❓

| 项目 | 状态 | 说明 |
|------|------|------|
| `video_selector` 操作级 readiness 过滤 | ❓ 待确认 | 当只装了 t2v 模型时是否不会推荐 i2v |
| `tests/contracts/test_comfyui_tools.py` | ❓ 待确认 | 契约测试是否存在 |
| `registry.setup_offer` 自动注册 | ❓ 待确认 | 已在 metadata.py 中定义但注册暴露未验证 |

---

## 实现范围总结

| 组件 | 文件 | 预估大小 | 实际状态 |
|-----------|-------|----------------|-------------|
| 共享客户端 | `tools/_comfyui/client.py` | ~180 行 | ✅ 296 行 |
| 共享元数据 | `tools/_comfyui/metadata.py` | — | ✅ 222 行 |
| 图片工具 | `tools/graphics/comfyui_image.py` | ~140 行 | ✅ 295 行 |
| 视频工具 | `tools/video/comfyui_video.py` | ~190 行 | ✅ 473 行 |
| Layer 3 技能 | `.agents/skills/comfyui/SKILL.md` | 使用指南 | ✅ 已实现 |
| 工作流模板 | `tools/_comfyui/workflows/*.json` | 3 个文件 | ✅ 已就绪 |
| 选择器就绪过滤 | `tools/video/video_selector.py` | 小改动 | ❓ 待确认 |
| 测试 | `tests/contracts/test_comfyui_tools.py` | ~200 行 | ❓ 待确认 |
| 文档 | `docs/comfyui-adapter-plan.md` | 本文档 | ✅ 已转换 |

无需修改：`base_tool.py`、现有非 ComfyUI 生成工具、流水线定义、schema。
