# ComfyUI + LTX-2.3 本地视频生成 setup 指南

本指南用于在 RTX 3090（24GB VRAM）上通过 ComfyUI 运行 LTX-2.3 image-to-video，替代 diffusers 路径。

## 前置条件

- NVIDIA RTX 3090（已验证）
- Windows 11 + NVIDIA 驱动 595.79+
- 磁盘空间：E 盘至少预留 60GB（模型 27GB + 依赖 + 输出）
- 已安装 miniconda3 / scoop 或任意 Python 3.12

## 1. 给 ComfyUI 创建独立 Python 环境

项目里的 `ComfyUI/` 已经存在。建议为它单独创建一个 conda env：

```powershell
& "C:\Users\tiger\scoop\apps\miniconda3\current\shell\condabin\conda-hook.ps1"
conda create -n comfy python=3.12 -y
conda activate comfy

# CUDA torch
cd E:\YifuAIForge\OpenMontage\ComfyUI
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

# ComfyUI 依赖
pip install -r requirements.txt
```

## 2. 安装 LTX-2.3 节点

```powershell
cd E:\YifuAIForge\OpenMontage\ComfyUI\custom_nodes
git clone https://github.com/kijai/ComfyUI-LTXVideo.git
git clone https://github.com/kijai/ComfyUI-KJNodes.git

cd ComfyUI-LTXVideo
pip install -r requirements.txt
cd ..\ComfyUI-KJNodes
pip install -r requirements.txt
```

## 3. 下载模型

### 3.1 主模型（必选）

3090 24GB 推荐 fp8 量化版：

| 文件名 | 大小 | 下载地址 | 放到 |
|---|---|---|---|
| `ltx-2.3-22b-dev-fp8.safetensors` | ~27GB | [Lightricks/LTX-2.3-fp8](https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors) | `ComfyUI\models\diffusion_models\` |

备选：
- `ltx-2.3-22b-distilled-fp8.safetensors`（~27.5GB，蒸馏版，步数更少）
- `ltx-2.3-22b-dev.safetensors`（~43GB，bf16，需要更多显存）

### 3.2 Text encoder 和 VAE

Kijai 的 ComfyUI-LTXVideo 节点通常会在首次运行时自动从 HuggingFace 下载：
- Text encoder: `Gemma3ForConditionalGeneration`（可用 fp8/int8 量化版）
- VAE: `AutoencoderKLLTX2Video`

如果你想手动下载以加速/离线使用，可以放到：
- `ComfyUI\models\text_encoders\`
- `ComfyUI\models\vae\`

推荐 HuggingFace 路径：
- Text encoder: `Lightricks/LTX-2.3` 里的 `text_encoder` 相关文件
- VAE: `Lightricks/LTX-2.3` 里的 vae 权重

> 注意：ComfyUI-LTXVideo 可能会用特定的子目录名或自动下载，具体参考该节点的 README。

## 4. 启动 ComfyUI

```powershell
conda activate comfy
cd E:\YifuAIForge\OpenMontage\ComfyUI
python main.py --listen 127.0.0.1 --port 8188
```

## 5. 构建 image-to-video workflow

1. 打开浏览器 `http://127.0.0.1:8188`
2. 使用 Kijai 的 LTXVideo 节点搭建 I2V 工作流：
   - `LoadImage`：上传你的 fashion 设计图
   - `UNETLoader`：选择 `ltx-2.3-22b-dev-fp8.safetensors`
   - `LTXImageToVideo` 或等效节点
   - `KSampler` / 专用 LTX sampler
   - `VAEDecode` → `SaveVideo`
3. 调试成功后，点击右上角 **Save (API Format)**，保存为 `ltx23_i2v.json`
4. 把 `ltx23_i2v.json` 放到 `E:\YifuAIForge\OpenMontage\tools\_comfyui\workflows\`

## 6. 用 OpenMontage 自动运行

运行示例脚本：

```powershell
conda activate comfy
python examples/run_ltx23_i2v.py --image path/to/fashion_design.png --prompt "A model walks down a runway wearing this design, elegant, cinematic lighting"
```

脚本会：
1. 连接本地 ComfyUI
2. 加载 `ltx23_i2v.json`
3. 替换参考图片和 prompt
4. 自动替换 seed、width、height、num_frames
5. 轮询直到完成，下载视频到 `outputs/ltx23_i2v_*.mp4`

## 7. 显存优化建议（3090 24GB）

- 分辨率：768×512 或 640×384
- 帧数：49（约 1.6s）或 73（约 2.4s）起步
- 使用 fp8 模型
- 在 ComfyUI workflow 中开启 VAE tiling
- 不要同时加载多个大模型
- 如果仍 OOM，改用 `ltx-2.3-22b-dev-fp8.safetensors` + 更低分辨率

## 8. 面料视频提示词经验：真实纹理 vs 平滑失真

使用 LTX-2.3 I2V 生成面料动态视频时，提示词对纹理真实感影响很大。以下是实测经验：

### 容易出现的问题

| 现象 | 原因 |
|------|------|
| 面料像塑料或丝绸，失去原图纹理 | 提示词里用了 `velvet`、`smooth` 等泛化词，或光影描述过强 |
| 纹理过度夸张，像卡通布料 | 反向提示太强（如反复强调 `rough texture`、`deep ridges`），模型过度补偿 |
| 动态模糊冲淡细节 | 风吹/手抚动作幅度太大，帧间变化过多 |

### 更真实的写法原则

1. **用中性材质词**：`woven fabric`、`textile cloth`、`fabric surface`，避免 `velvet` / `silk` / `plastic` 等强风格词。
2. **描述光线而非纹理**：让模型通过光影自己呈现纹理，如 `soft side light rakes across the surface`、`warm light moves slowly across the cloth`。
3. **动作要小**：`gentle subtle folds`、`slowly ripples`，不要 `flowing like water`。
4. **负面提示适度**：只排除明显问题，如 `plastic, synthetic, cartoon, overly dramatic folds, blurry texture`，不要加太多反向限制。

### 推荐示例（A+C 混合：微风 + 光影）

```text
A close-up of a real crimson red fabric with a soft woven texture
and tiny scattered golden sparkles. The cloth shifts gently with subtle folds,
showing the natural weave grain and light catching the surface fibers.
Soft warm light moves slowly across the fabric, revealing its honest material texture.
Photorealistic textile detail, gentle motion, elegant product shot.
```

### 不推荐示例

```text
❌ "A luxurious velvet fabric flows like dark water..."
   → 容易丢失真实纹理，变得像液体或塑料。

❌ "Deep corduroy ridges with dramatic shadows..."
   → 纹理会被过度放大，不自然。
```

### 参考输出

- `red-fabric-motion-ac.mp4`：柔和版，偏平滑
- `red-fabric-motion-ac-texture.mp4`：强纹理版，偏夸张
- `red-fabric-motion-balanced.mp4`：平衡版，真实自然纹理（推荐）

## 9. 常见问题

### Q: diffusers 路径为什么不能跑 LTX-2.3？
A: `Lightricks/LTX-2.3` 仓库只有原始 safetensors 权重，没有 diffusers 所需的 `model_index.json` 等配置文件。ComfyUI 直接加载原始权重更方便。
A: 很难。bf16 完整版约 43GB 权重，加载时容易爆 24GB VRAM。fp8 量化版是更实际的选择。

### Q: 可以跑 LTX-2.3-nvfp4 吗？
A: 不能。nvfp4 需要 NVIDIA Hopper 架构（如 H100），RTX 3090 是 Ampere，不支持 fp4/nvfp4 原生计算。

### Q: 模型一定要放 C 盘吗？
A: 不用。可以放到 E 盘。本项目的 ComfyUI 在 `E:\YifuAIForge\OpenMontage\ComfyUI`，模型放它下面的 `models\` 子目录即可。
