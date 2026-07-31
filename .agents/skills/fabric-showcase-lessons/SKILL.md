# Fabric Showcase — 经验教训

## 图生图（Klein I2I）

### 提示词规则
1. **不要描述面料材质/颜色/纹理** — 参考图提供这些，提示词只描述场景状态（平铺/挂起/人台/模特）
2. **不要写灯光方向** — 参考图自带灯光
3. **正面描述替代否定词** — FLUX 不支持反面提示词
4. **30-80 词** — FLUX 最佳长度
5. **重要信息前置** — FLUX 对早期词更敏感

### 场景模板（已验证）

**面料特写（平铺）：**
> 面料 laid flat on a light wooden table, dried lavender sprigs beside it, tailor's scissors in corner, soft focus background. Preserve exact fabric color and texture from reference image.

**面料飘动（横杆挂起）：**
> A large piece of [面料名] fabric hanging on a wooden clothes rack, the fabric hangs down over the horizontal bar in natural folds, bright studio, clean empty background. Keep original fabric color and texture exactly from reference.

**手部触碰（关键！）**
> [面料名] fabric spread on linen-draped worktable, a single beautiful hand with exactly five fingers, palm resting on fabric, one thumb on left, four clearly separated fingers on right, all five digits perfectly formed and naturally positioned. Keep original fabric color unchanged.

⚠️ **必须明确写 "one thumb on left, four clearly separated fingers on right"** — 只写 "five fingers" 或"自然手势"会多指。这是反复验证过的正确写法。

**模特上身：**
> Woman in her 30s wearing a dress made of [面料名] fabric, standing in a bright minimalist room with large window, facing camera, arms at sides, neutral expression. Preserve exact fabric color and texture from reference.

### Workflow 调用

```python
# 上传参考图
with open(local_path, "rb") as f:
    r = requests.post("http://127.0.0.1:8188/upload/image",
        files={"image": (filename, f, "image/jpeg")})
server_name = r.json()["name"]

# 加载 Klein 工作流
wf = json.load(open("tools/_comfyui/workflows/klein_fabric.json"))
wf["76"]["inputs"]["image"] = server_name  # patch LoadImage node

# 关键修改：用参考图 latent 代替空 latent（true I2I）
wf["114:100"]["inputs"]["latent_image"] = ["114:107:78", 0]

# 设置提示词
wf["114:113"]["inputs"]["text"] = scene_prompt
wf["114:112"]["inputs"]["noise_seed"] = int(time.time()*1000)

# 提交
requests.post("http://127.0.0.1:8188/prompt",
    json={"prompt": wf, "client_id": str(uuid.uuid4())})
```

## 图生视频（LTX 2.3 I2V）

### 提示词规则
1. **保持 80 词以内** — 超出后 LTX 退化
2. **6 要素结构**：镜头 → 场景/光线 → 动作 → 角色(如有) → 镜头运动 → 音频(可选)
3. **静态镜头 = 零位移** — 不能同时说静态和缩放
4. **帧数 97** — (97-1)%8=0 ✅ 有效

### 面料动态模板

**面料挂杆（微风拂过）：**
> Medium shot of [面料名] fabric hanging on a wooden clothes rack. Barely noticeable air barely touches the fabric surface, the fabric edge trembles almost imperceptibly, very subtle barely visible movement. Natural daylight. Static camera. Keep original fabric color from reference.

⚠️ **风力要" barely noticeable"** — 写 "gentle breeze" 都太大，面料的摆动幅度会很不自然。

**手部在面料上滑动：**
> Macro shot of a hand resting on [面料名] fabric. The hand slowly glides across the fabric surface from right to left, palm stays in constant contact with fabric throughout, fingers gently press and slide along the surface without lifting. Static camera. Preserve exact fabric color.

### 反面提示词（LTX 支持）
```python
wf["69:6"]["inputs"]["text"] = (
    "clean fabric surface, natural woven texture, "
    "barely moving fabric, very subtle ripple, still calm fabric, "
    "hand-free fabric, person-free scene"
)
```

## 常见失败模式

| 问题 | 原因 | 修复 |
|------|------|------|
| 手多一指 | 提示词写"五指/自然手"不够精确 | "one thumb on left, four clearly separated fingers on right" |
| 手抬手/离开面料 | 未明确约束手不离面 | "palm stays in constant contact with fabric throughout, never lifts away" |
| 面料被手拉 | LTX 幻觉出手来拉动面料 | 反面提示词加 "hand-free fabric, person-free scene" |
| 面料颜色漂移 | 提示词描述面料材质/颜色 | 提示词只写场景状态，不写面料特征 |
| 风太大面料乱飞 | "gentle breeze" 也太大 | "barely noticeable air barely touches" |
| 人台图变穿着 | "draped on" 被理解为"穿着" | "fabric draped OVER / thrown over / covering the mannequin" |
