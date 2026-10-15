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

1. **`wan22-i2v-4step.json`** -- Image-to-video (WAN 2.2 14B, fp8, 4-step LightX2V LoRA)
2. **`wan22-t2v-4step.json`** -- Text-to-video (WAN 2.2 14B, fp8, 4-step LightX2V LoRA)

These bundled WAN 2.2 14B FP8 workflows are the high-quality profile and
recommend roughly 16GB VRAM. That is not a ComfyUI-wide requirement. The
`comfyui_video` tool's top-level `resource_profile` is an 8GB provider floor so
preflight does not imply ComfyUI itself requires 16GB. Low-VRAM users should use
custom workflows such as Wan 2.1 1.3B, LTX-Video/LTXV FP8 or quantized graphs,
or Wan 2.2 GGUF/quantized community workflows, with shorter frame counts and
lower resolutions as needed.

**I2V workflow -- templated nodes:**

| Node | Class | Templated field |
|------|-------|-----------------|
| 93 | CLIPTextEncode | `text` (positive prompt) |
| 97 | LoadImage | `image` (server filename from upload) |
| 98 | WanImageToVideo | `width`, `height`, `length` |
| 86 | KSamplerAdvanced | `noise_seed` |
| 108 | SaveVideo | `filename_prefix` |

**Input schema:**

```yaml
prompt:               string    # required
operation:            string    # "text_to_video" | "image_to_video" (default: t2v)
reference_image_path: string    # local path (for i2v)
reference_image_url:  string    # URL (for i2v, downloaded first)
width:                integer   # default 640
height:               integer   # default 640
num_frames:           integer   # default 81 (5s at 16fps)
seed:                 integer   # optional
output_path:          string    # where to save the video
workflow_json:        string    # optional custom workflow; requires output_node
workflow_path:        string    # optional path to workflow JSON; requires output_node
output_node:          string    # required for custom workflows
workflow_name:        string    # optional custom workflow provenance label
workflow_model:       string    # optional custom model/provenance label
workflow_model_stack: []        # optional custom dependency provenance
timeout_seconds:      integer   # optional, default 3600 (see below)
resume_prompt_id:     string    # optional, resume a timed-out job without resubmitting
```

**execute() flow (i2v):**
1. Upload reference image via `client.upload_image()`
2. Deep-copy i2v workflow template
3. Inject prompt, uploaded image name, seed, dimensions
4. `client.generate(workflow, output_node="108", dest=output_path, timeout=inputs.get("timeout_seconds", 3600), resume_prompt_id=inputs.get("resume_prompt_id"))`
5. Return `ToolResult`

**execute() flow (t2v):**
1. Deep-copy t2v workflow template
2. Inject prompt, seed, dimensions
3. `client.generate(workflow, output_node="16", dest=output_path, timeout=inputs.get("timeout_seconds", 3600), resume_prompt_id=inputs.get("resume_prompt_id"))`
4. Return `ToolResult`

**Timeout and resume (added after real-world local-GPU testing):** the
default client wait was raised from 900s to 3600s — non-accelerated custom
Wan 1.3B workflows on modest local GPUs were observed taking ~1360-1630s at
832x480/81-97 frames, and the old 900s default false-failed those jobs even
though ComfyUI kept rendering server-side. `ComfyUIError` now carries a
`prompt_id` on both execution errors and timeouts (`ComfyUIError.prompt_id`),
and `ComfyUIVideo`'s `ToolResult.error`/`.data` surface it on timeout so the
caller isn't left guessing whether the job is dead. Callers recover a
timed-out-but-still-running job by calling `execute()` again with
`resume_prompt_id` set to that `prompt_id` (and a longer `timeout_seconds` if
needed) — `client.generate()` then skips `submit()` entirely and just resumes
polling/downloading the existing job instead of queuing a duplicate.

`comfyui_video` publishes `operation_statuses` in `get_info()` and implements
`is_operation_available(operation)` for selector routing. This keeps partial
ComfyUI installs useful for the installed mode without advertising unavailable
operation modes as ready. `video_selector` also applies this readiness check
when `operation="rank"` by using `target_operation`, so preflight rankings do
not promote ComfyUI for an operation whose bundled models are missing.

---

### `comfyui_music` -- Music Generation (shipped, with a native-node bundled workflow)

`tools/audio/comfyui_music.py`. `capability="music_generation"`, `provider="comfyui"`.

**Bundled default:** ACE-Step v1 (3.5B) text-to-audio, via `tools/_comfyui/workflows/ace-step-1-t2a.json`.
The node-pack fragmentation that originally blocked this tool (`AceStepModelLoader`
vs native `TextEncodeAceStepAudio`, etc.) turned out to be moot for ACE-Step v1:
ComfyUI ships `TextEncodeAceStepAudio`/`EmptyAceStepLatentAudio` as **native core
nodes** (`comfy_extras/nodes_ace.py`), not a third-party pack, and Comfy-Org's own
[`workflow_templates`](https://github.com/Comfy-Org/workflow_templates) repo bundles
an official ACE-Step-v1 template built entirely from those native nodes plus
long-stable core nodes (`CheckpointLoaderSimple`, `KSampler`, `ModelSamplingSD3`,
`VAEDecodeAudio`, `SaveAudioMP3`). Every node's `class_type` and input names in
`ace-step-1-t2a.json` were cross-checked against ComfyUI's own source
(`comfy_extras/nodes_ace.py`, `nodes_audio.py`, `nodes_latent.py`, `nodes.py`) --
not guessed from the UI export -- since the UI-format template Comfy-Org ships
isn't directly usable as the API-format JSON this client submits.

`prompt` maps to ACE-Step's `tags` field (style/genre/mood description, matching
the "prompt = description of desired music" convention `suno_music` already uses).
`lyrics` is a separate optional field (empty for instrumental). `duration_seconds`,
`steps`, `cfg`, `lyrics_strength`, and `seed` are all patchable; `shift` and the
tonemap `multiplier` stay at the official template's defaults.

Newer/different setups aren't locked out: `workflow_json`/`workflow_path` +
`output_node` still works exactly like the image/video tools' override path --
for ACE-Step 1.5, a different node pack, or a non-ACE-Step audio model entirely.

**Selector integration:** no dedicated `music_selector` exists in OpenMontage
(unlike `tts_selector`/`image_selector`/`video_selector`) -- music tools are
already routed directly via `registry.get_by_capability("music_generation")`,
and `comfyui_music` participates in that the same way `suno_music`/`music_gen`
do. `fallback_tools = ["suno_music", "music_gen"]`.

**Audio artifact schema:** `ToolResult.data` follows the same shape as the
image/video tools (`provider`, `model`, `output`, `format`, `workflow_provenance`),
plus `lyrics` and `duration_seconds` -- the latter a best-effort `ffprobe` probe
of the downloaded file (`None` if `ffprobe` isn't on PATH), since even the bundled
workflow doesn't report actual rendered duration back through `/history`.

**Workflow/output-node contract:** identical to image/video -- `output_node`
must be the ID of the node that writes the final artifact (the bundled workflow's
is `SaveAudioMP3`, ComfyUI's native audio saver). `ComfyUIClient.generate()`'s
artifact extraction now also checks the `"audio"` output key (previously only
`"images"`/`"gifs"`), which is what `SaveAudioMP3`/`SaveAudio` write to in
ComfyUI's `/history` response.

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

**Multi-server (optional):** point `comfyui_image`, `comfyui_video`, and
`comfyui_music` at separate ComfyUI instances -- e.g. one GPU running FLUX 2,
another running WAN 2.2, another running ACE-Step -- by setting a
per-capability override. Each takes priority over `COMFYUI_SERVER_URL` for
its own tool only; leave all three unset and everything talks to the single
shared server.

```bash
COMFYUI_IMAGE_SERVER_URL=http://gpu-a:8188
COMFYUI_VIDEO_SERVER_URL=http://gpu-b:8188
COMFYUI_MUSIC_SERVER_URL=http://gpu-c:8188
```

**For Docker Compose setups** (ComfyUI in a container):

```bash
COMFYUI_SERVER_URL=http://host.docker.internal:8188
# or
COMFYUI_SERVER_URL=http://comfyui:8188      # if on same docker network
```

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

### 上游已解决项（Open Questions 状态更新）

2. ~~**Async generation:**~~ **Resolved.** `ComfyUIClient.generate()` now
   waits via ComfyUI's websocket feed (`wait_ws()`) by default, reacting to
   `executing`/`execution_error` events immediately instead of sleeping
   between REST polls — completion and errors are caught without the
   `interval`-seconds lag, and an optional `on_progress` callback gets live
   `progress` events (`comfyui_video` uses this to print step progress on
   long renders). No new hard dependency: `websocket-client` is an optional
   import, and `_wait()` transparently falls back to the original
   `poll()` REST loop when it isn't installed or the connection fails —
   `resume_prompt_id` recovery behaves identically either way.

3. ~~**Multi-server:**~~ **Resolved.** `ComfyUIClient(capability="image"|"video"|"music")`
   resolves its server URL from a per-capability env var first
   (`COMFYUI_IMAGE_SERVER_URL` / `COMFYUI_VIDEO_SERVER_URL` / `COMFYUI_MUSIC_SERVER_URL`),
   then the shared `COMFYUI_SERVER_URL`, then the `http://localhost:8188` default.
   All three tools pass their capability at construction, so image, video, and
   music generation can each point at different ComfyUI instances (different GPUs,
   different model sets) with zero code changes -- single-server setups need no extra
   configuration since all three env vars are optional. `client.capability`/
   `client.is_default_url`/`client.unavailable_reason()` all account for the
   override, and `COMFYUI_SETUP_OFFER.per_capability_env_var_overrides` documents
   it for the setup-offer surfacing in `provider_menu()`.

4. ~~**Music generation:**~~ **Resolved -- shipped with a bundled ACE-Step v1 workflow.**
   `comfyui_music` is a real tool now (not a hidden image/video override), routed
   through the existing `registry.get_by_capability("music_generation")` path
   like `suno_music`/`music_gen`. The node-pack fragmentation that originally
   blocked this turned out not to apply to ACE-Step v1: its ComfyUI nodes are
   native core nodes, not a third-party pack, so `ace-step-1-t2a.json` ships as
   the default, verified node-by-node against ComfyUI's own source. Custom
   `workflow_json`/`workflow_path` + `output_node` remains available for other
   versions/packs. See the `comfyui_music` section above for the full contract.
