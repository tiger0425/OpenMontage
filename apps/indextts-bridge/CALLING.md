# IndexTTS 桥调用规范（所有 Agent 必读）

> 2026-08-14 更新。**任何 Agent（OpenCode / OpenClaw / Cursor / Codex / Claude Code）
> 调用本地 IndexTTS 合成语音时，必须按本文档执行。**
> 违反本文档会导致：**生成内容为杂音**（权重错位）、**男声变女声**（情感混合）、**中文乱码**（编码问题）。

## ✅ 统一入口（唯一规范入口）

所有工作流（auto-dub / markhasara / repo-to-video / series-adapt）已统一到：

```
apps/indextts-bridge/client.py  →  IndexTTSSession 类
```

> 备注：双入口历史——`apps/auto-dub/batch/pipeline_automator.py` 曾自持 `_get_indextts_server/_synthesize_indextts` 与本客户端重复（双次合成含 `duration_factor` 对齐逻辑），
> 已在 `9fcbb9c/ADR-004 D3` 后标注为兼容封装并指向本规范入口。新代码一律走本 `client`，`pipeline` 侧仅保留路径解析薄封装，后续收敛为委托调用。

```python
# 推荐：用统一客户端（自动处理 UTF-8 / 情感纯净 / lang / duration_factor / GPU 锁）
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "indextts_client", r"E:\YifuAIForge\OpenMontage\apps\indextts-bridge\client.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

with _mod.IndexTTSSession(
    voice_ref="D:/ref.wav", model_version="2.5", lang="ZH", emotion="calm",
) as tts:
    ok = tts.synthesize("大家好", "D:/out.wav")
```

内部自动处理：桥位置、--version/--checkpoints、UTF-8 编码、calm 情感纯净（不传 emo_vector）、GPU 锁、超时。

## 🚨 最常见错误：用了旧桥 → 杂音

**错误写法（会产生杂音）：**
```python
subprocess.run([PY, r"D:/index-tts/indextts_server.py", ...])  # ❌ 旧桥已删除，不存在
```

**旧桥 `D:/index-tts/indextts_server.py`（2.0 模型）已删除（2026-08-14）**。
若 Agent 仍引用它，会直接报「文件不存在」——这是**有意为之**，提醒你用新桥/统一客户端。

**为什么杂音**：旧桥 `from indextts.infer_v2 import IndexTTS2`（**2.0 模型结构**）。
而 `D:/index-tts/checkpoints` 装的是 **2.5 权重**（含 `spk_emb_proj`/`lang_embedding` 等 2.5 新层）。
**2.0 模型 + 2.5 权重 = 权重错位**（日志 `missing keys (212)` + `skipping spk_emb_proj`）→ 杂音。

---

## ✅ 正确调用方法

### 1. 桥脚本位置（唯一正确入口）

```
E:\YifuAIForge\OpenMontage\apps\indextts-bridge\indextts_server.py
```

独立 skill 包内是：`<auto-dub-skill>/tools/audio/indextts_server.py`（同一份代码）。

**不要用** `D:/index-tts/indextts_server.py`（旧桥，2.0 模型）。

### 2. 启动命令

```bash
# 2.5（默认，bf16）
"D:/index-tts/.venv/Scripts/python.exe" "apps/indextts-bridge/indextts_server.py" --version 2.5 --checkpoints "D:/index-tts/checkpoints"

# 2（回退，fp16）——仅当 2.5 有问题时
"D:/index-tts/.venv/Scripts/python.exe" "apps/indextts-bridge/indextts_server.py" --version 2 --checkpoints "D:/index-tts/checkpoints_2"
```

- `--version 2.5|2`：模型版本分支（2.5 用 `infer_v2_5.py` + bf16；2 用 `infer_v2.py` + fp16）
- `--checkpoints`：**必须显式指定**（桥在 `apps/indextts-bridge/` 下，不能靠脚本同级推断）
- `--use-qwen-emo`：仅当需要 `use_emo_text=True` 自动判情感时加

### 3. 请求协议（stdin 一行 JSON / stdout 一行 JSON）

```json
{"id": "seg_1", "text": "中文文本", "output_path": "D:/tmp/out.wav",
 "voice_ref": "D:/voice_ref.wav", "lang": "ZH", "duration_factor": 1.0,
 "seed": 42, "use_emo_text": false}
```

响应：`{"id": "seg_1", "ok": true, "path": "..."}` 或 `{"ok": false, "error": "..."}`

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 请求标识（回显用） |
| `text` | ✅ | 待合成文本 |
| `output_path` | ✅ | 输出 wav 路径 |
| `voice_ref` | ✅ | 声纹参考 wav（5-30s 干净人声） |
| `lang` | 2.5 必填 | 语种：`ZH`/`EN`/`JA`/`ES` 等 |
| `duration_factor` | 可选 | 语速 0.5-2.0，默认 1.0 |
| `seed` | 可选 | 复现种子，默认 42 |
| `use_emo_text` | 可选 | **默认 false**（纯净克隆） |
| `emo_vector` | 可选 | 8 维情感向量 |

### 4. 关键：编码必须 UTF-8（防中文乱码）

**必须用 Python 父进程写 stdin**（`text=True, encoding="utf-8"`），**不要用 PowerShell 管道**：

```python
import subprocess, json
req = {"id": "x", "text": "大家好", "output_path": "D:/tmp/out.wav",
       "voice_ref": "D:/ref.wav", "lang": "ZH", "duration_factor": 1.0,
       "seed": 42, "use_emo_text": False}
p = subprocess.Popen(
    ["D:/index-tts/.venv/Scripts/python.exe",
     "E:/YifuAIForge/OpenMontage/apps/indextts-bridge/indextts_server.py",
     "--version", "2.5", "--checkpoints", "D:/index-tts/checkpoints"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8")  # ← 必须 utf-8
out, err = p.communicate(json.dumps(req, ensure_ascii=False) + "\n", timeout=300)
print(out.strip())  # {"id": "x", "ok": true, "path": "..."}
```

**⚠️ 警告**：PowerShell `Write-Output $json | python ...` 会把中文按 GBK 传进管道，
桥按 UTF-8 读 → 中文变 `?` → 生成乱码。**必须用 Python `subprocess` 传。**

### 5. 关键：情感参数（防音色漂移/女声化）

2.5 下**固定 calm 不要传 `emo_vector`**：

```python
# ❌ 错误（触发 2.5 情感-音色混合，男声变女声）：
req["use_emo_text"] = False
req["emo_vector"] = [0,0,0,0,0,0,0,1]  # calm 向量

# ✅ 正确（纯净克隆，保声纹）：
req["use_emo_text"] = False   # 不传 emo_vector
```

- **默认（推荐）**：只传 `use_emo_text: false`，不传 `emo_vector` → 官方纯净克隆，声纹最保真
- 需要特定情感：传 `emo_vector`（8 维，顺序 `[高兴,愤怒,悲伤,害怕,厌恶,忧郁,惊讶,平静]`）
- 需要自动判情感：`use_emo_text: true` + 启动时加 `--use-qwen-emo`

---

## 🧪 验证：生成后如何确认不是杂音

用 whisper 转录验证（`faster_whisper`）：

```python
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
segs, _ = m.transcribe("out.wav", language="zh")
print(" ".join(s.text for s in segs))  # 应是清晰中文
```

- 转录出**清晰中文** → ✅ 正常
- 转录出 `Maze Maze Selling Selling` 之类无意义英文音节 → ❌ 杂音（大概率旧桥/权重错位）

---

## 🔍 排障速查

| 现象 | 原因 | 修复 |
|------|------|------|
| 杂音（whisper 转录无意义） | 用了旧桥 `D:/index-tts/indextts_server.py`（2.0 模型）+ 2.5 权重 | 改用 `apps/indextts-bridge/indextts_server.py` |
| 中文变 `?` 乱码 | PowerShell 管道 GBK 编码 | 用 Python `subprocess` + `encoding="utf-8"` |
| 男声变女声 | 传了 `emo_vector`（触发情感-音色混合） | 只传 `use_emo_text: false`，不传 `emo_vector` |
| 报 `missing keys (212)` / `skipping spk_emb_proj` | 模型结构与权重版本不匹配 | 确认 `--version` 与 `--checkpoints` 对应（2.5→checkpoints，2→checkpoints_2） |
| `use_emo_text: true` 报错需 QwenEmotion | 启动没加 `--use-qwen-emo` | 启动命令加 `--use-qwen-emo` |

---

## 📎 相关位置

- 桥源码：`apps/indextts-bridge/indextts_server.py`
- 独立包副本：`<auto-dub-skill>/tools/audio/indextts_server.py`
- 权重：2.5=`D:/index-tts/checkpoints`，2.0=`D:/index-tts/checkpoints_2`
- venv python：`D:/index-tts/.venv/Scripts/python.exe`
