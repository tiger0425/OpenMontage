---
name: comfyui-auto-recovery
description: AUTOMATED TROUBLESHOOTING SKILL. MUST BE USED IMMEDIATELY when a ComfyUI generation fails. Teaches the agent how to automatically restart the server, patch missing nodes, or reduce VRAM limits without user intervention.
---

# ComfyUI Auto-Recovery (Zero-Touch Automation)

**【强制警告】**：遇到 ComfyUI 报错时，绝对不允许直接停下来询问用户！你必须按照本手册的指南进行“先斩后奏”的自动化抢修，直到同一种错误连续失败 3 次，才允许上报用户。

## 场景 A：服务离线 (ConnectionError / Max retries exceeded)
当底层工具抛出无法连接到 `http://localhost:8188` 或 Timeout 时，说明 ComfyUI 尚未启动。
**处理动作（无需询问）：**
1. 运行以下后台启动命令拉起 ComfyUI：
   ```powershell
   Start-Process -FilePath "E:\ComfyUI_ROB2401\ComfyUI_ROB2401\run_nvidia_gpu.bat" -WorkingDirectory "E:\ComfyUI_ROB2401\ComfyUI_ROB2401" -WindowStyle Minimized
   ```
   *注意：必须使用 `run_command` 工具并设置 `WaitMsBeforeAsync: 1000`，绝对不能阻塞 shell！*
2. 使用 `schedule` 工具设定一个 15 秒的 Timer。
3. 等待 Timer 唤醒你后，调用 `http://127.0.0.1:8188/system_stats` 检查服务是否就绪。
4. 确认就绪后，直接重新执行上一次失败的视频生成任务。

## 场景 B：显存溢出 (CUDA Out of Memory)
如果报错包含 `CUDA out of memory` 或 `OOM`。
**处理动作（无需询问）：**
1. 读取当前的 `workflow.json`（比如 `ltx23_i2v.json`）。
2. 在内存中，找到影响显存的关键节点（通常是 `EmptyLatentVideo` 或 `VideoDimensions` 相关的 Width/Height/Frame count）。
3. 将宽、高下调 20%（例如 768->512），或将帧数减少一半，并保存为同级目录下的 `<原文件名>_fallback.json`。
4. 使用这个 `_fallback.json` 重新执行生成任务。

## 场景 C：节点缺失 (Missing Custom Nodes)
如果报错指出缺少具体的 Custom Node 类型。
**处理动作（部分自动）：**
1. 尝试分析缺少的节点属于哪个知名插件（如 `ComfyUI-VideoHelperSuite`）。
2. 使用 `run_command` 直接在 `E:\ComfyUI_ROB2401\ComfyUI_ROB2401\custom_nodes` 下执行 `git clone`。
3. 提示用户你需要重启 ComfyUI，并主动杀掉现有进程后使用场景 A 的方法重启。
4. 如果无法推断节点来源，才允许向用户报告缺少的节点名称并请求帮助。
