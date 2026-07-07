---
name: provider-lockdown
description: MUST USE before any generation task. Locks which providers to use for video, image, TTS, music, and composition — enforced by user preference. This skill overrides all selector auto-routing. Providers not listed here are prohibited.
---

# Provider Lockdown — 强制规则

## 调用前必须阅读

本 skill 定义了哪些 provider 可用、哪些被禁止。所有 agent 在执行任何生成任务（图片、语音、音乐、视频生成、视频合成）前，**必须先加载此 skill**，并按以下规则传递参数。

---

## 五条锁定规则

### 规则 1：图片生成 → `google_imagen`

调用 `image_selector` 时固定传 `preferred_provider="google_imagen"`：

```
image_selector.execute({
    "prompt": "...",
    "preferred_provider": "google_imagen",  // 锁定，不要改
    "width": ...,
    "height": ...,
})
```

### 规则 2：语音合成 → `voxcpm`（回退 `piper`）

调用 `tts_selector` 时固定传 `preferred_provider="voxcpm"`：

```
tts_selector.execute({
    "text": "...",
    "preferred_provider": "voxcpm",  // 锁定
})
```

> **回退策略**：如果 VoxCPM 当前机器不可用（无 CUDA、模型加载失败），使用 `preferred_provider="piper"`。Piper 不需要 GPU，纯 CPU 可跑，但音质低于 VoxCPM。

### 规则 3：音乐搜索 → `pixabay_music` 直接调用

`pixabay_music` 不走 selector，直接调用：

```
pixabay_music.execute({
    "query": "calm ambient piano",  // 搜索关键词
})
```

不需要 API key。

### 规则 4：视频后处理/合成 → `hyperframes` 引擎

在 `edit_decisions` 中锁定 `render_runtime="hyperframes"`：

```
edit_decisions = {
    "render_runtime": "hyperframes",
    ...
}
```

> **禁止使用** Remotion 或 FFmpeg 做合成（除非用户再次明确要求）。如果 HyperFrames 不可用（Node < 22、ffmpeg 缺失、npx 不可达），阻塞并告知用户。

### 规则 5：视频生成 → `comfyui_video` + 自定义 LTX 2.3 图生图工作流

调用 `comfyui_video` 直接执行，使用 `image_to_video` 操作 + 自定义工作流：

```
comfyui_video.execute({
    "prompt": "...",
    "operation": "image_to_video",            // 图生图模式
    "reference_image_path": "/path/to/img.png", // 输入图片
    "workflow_path": "tools/_comfyui/workflows/ltx23_i2v.json", // 真实的 LTX 2.3 workflow 路径
})
```

> **前提条件**：
> - ComfyUI 服务必须运行在 `http://127.0.0.1:8188/`（已在 `.env` 配置 `COMFYUI_SERVER_URL`）
> - **ComfyUI 目录**：`E:\ComfyUI_ROB2401\ComfyUI_ROB2401`
> - 每次执行前检查 ComfyUI 状态：
>   ```
>   python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=5).read()"
>   ```
> - **如果服务未启动，从该目录启动 ComfyUI**（不要自行构建/安装，目录已完整就绪）：
>   ```
>   E:\ComfyUI_ROB2401\ComfyUI_ROB2401\run_nvidia_gpu.bat
>   ```
>   也可直接双击 `run_nvidia_gpu.bat` 启动。
> - 启动后等待几秒待服务就绪，重新运行上面的 health check 确认。
> - **如果 ComfyUI 无法启动**，必须**阻塞并报告用户**，**不能降级到其他 video generation provider**。

---

## 绝对禁止的 provider（即使可用也不允许使用）

| 能力 | 禁止使用的 provider |
|---|---|
| **图片生成** | flux, minimax, pixabay, pexels, openai, grok, recraft, comfyui, local_diffusion |
| **TTS** | minimax, elevenlabs, openai, doubao |
| **视频生成** | minimax, kling, veo, seedance, grok, heygen, runway, pexels, pixabay, cogvideo, hunyuan, ltx_local, ltx_modal, wan, higgsfield |

---

## 为什么锁定

1. **google_imagen**：`GOOGLE_API_KEY` 已配，Imagen 质量可靠
2. **voxcpm**：本地 GPU TTS，模型已下载（~4.6GB），不需要 API key，支持中文
3. **pixabay_music**：免费音乐搜索，不需要 API key
4. **hyperframes**：用户指定全部用 HyperFrames 后处理
5. **comfyui + LTX 2.3**：自定义工作流走本地 ComfyUI，不依赖任何外部 API

其他 provider 要么 key 没配，要么不是用户想要的。不要在未获许可的情况下切换。
