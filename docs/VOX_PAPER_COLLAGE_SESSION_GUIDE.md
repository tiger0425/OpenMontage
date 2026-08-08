# vox-paper-collage 新会话复现指南（2026-08）

> 面向 agent 的复现手册：在新会话中重建/续跑 vox-paper-collage 测试案例时，
> 按本文档执行即可复用已验证的流程、工具和素材。核心场景 = 每个 beat 的
> 画面（蓝图）生成 + 元素提取 + HTML 组合。

## 1. 关键文件位置

| 用途 | 路径 |
|---|---|
| 管线定义 | `pipeline_defs/vox-paper-collage.yaml` |
| 导演 skill（画面写作规则）| `skills/pipelines/vox-paper-collage/scene-plan-director.md` |
| 资产 skill | `skills/pipelines/vox-paper-collage/assets-director.md` |
| 双语规范 | `skills/pipelines/vox-paper-collage/bilingual-spec.md` |
| 视觉模板（verbatim 红线）| `skills/pipelines/vox-paper-collage/templates/style_block.md` / `closer.md` |
| Playbook 原文 | `docs/made-by-ai-playbook-zh.md` |
| 领域术语 | `CONTEXT.md` |
| 测试案例 scene_plan | `examples/vox-paper-collage/scene_plan/scene_plan_v2_tts_actual.json` |
| 素材库（字体/装饰）| `assets/shared_library/`（fonts/ decals/，gitignore 排除）|
| 素材库文档 | `docs/global-asset-library/README.md` |
| 印刷 CSS 技法 | `docs/global-asset-library/css-printing-techniques.md` |

## 2. 工具链（全部已验证可用）

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `comfyui_image` | 图像生成（本地 ComfyUI）| workflow_path + output_node + workflow_overrides |
| `Klein-txt2image.json` | **文生图**（蓝图/元素）| output_node=78, prompt 节点=115:111, seed=115:108 |
| `Klein-img2image.json` | 图生图（参考图重绘）| output_node=9, prompt=114:113, ref=76 `<UPLOADED_IMAGE>` |
| `Klein-sam3-extract.json` | **SAM3 抠图提取**（从蓝图提元素）| output_node=200, prompt=99:78, **alpha 必须 InvertMask** |
| `asset_library` | 素材库 search/add/touch | operation=search/add/touch |
| `minimax-m3-vision` | 视觉验证（看图评估）| `.agents/skills/minimax-m3-vision/scripts/analyze_media.py` |
| Chrome headless | HTML 组合截图 | `chrome --headless --screenshot` |

### 关键约定（实测教训）

- **SAM3 提取**：`JoinImageWithAlpha` 的 alpha 语义是"白色=透明"，必须接 `InvertMask`（SAM3 mask 白色=主体）。否则提取反了。
- **Klein 图生图"提取"不可靠**（楼变 4 层/线稿化）——不要用 img2img 做元素提取，用 SAM3。
- **元素缩放**：元素图要先 PIL 裁剪到主体 bbox（+2% 留白），否则放进 HTML 后主体太小。
- **蓝图尺寸**：`Klein-txt2image.json` 的 ResolutionSelector（节点 115:114）控制比例，B 站横屏 = `"16:9 (Widescreen)"`（1360×768）。已改好。
- **中文红线**：生图 prompt 一律英文，中文字符绝不进 prompt（中文走 CSS）。

## 3. 核心流程（每 beat 的画面生产）

### Step A：导演阶段写 image_prompt（Playbook 级）

scene_plan 每个 beat 必须有 `image_prompt` 字段（schema 已加）。写法见
`scene-plan-director.md`「画面叙事写作」章节。核心：

```
五件套: Sentence / Core Idea / Editorial Title / Visual Metaphor / Image Prompt
Image Prompt 必须包含:
  1. 背景(纸张材质+氛围词)  2. 主体(位置+大小关系+材质)
  3. 细节元素(叙事关联)     4. 排版(字体/颜色/叠压/占画面比例)
  5. 氛围与构图(负空间/投影) 6. 完整负向提示词
参考示例: scene_plan 里 b1.1 / b5.4 的 image_prompt（THE LAST COIN 风格）
```

### Step B：生成蓝图（AI 直接生成）

```python
tool.execute({
    "prompt": beat["image_prompt"],          # 直接用导演写的完整画面
    "workflow_path": "tools/_comfyui/workflows/Klein-txt2image.json",
    "output_node": "78",
    "workflow_overrides": {
        "115:111": {"text": beat["image_prompt"]},
        "115:108": {"noise_seed": <seed>}
    },
    "output_path": f"assets/blueprints/{beat_id}.png",
    "workflow_name": "klein-txt2image",
    "workflow_model": "flux-2-klein-9b",
})
```

### Step C：SAM3 提取元素（从蓝图切，100% 一致）

对蓝图中每个元素（hero/元素），用 SAM3 按描述提取：

```python
# Klein-sam3-extract.json 工作流（已验证）
# 节点: 99:77 checkpoint(sam3.1) + 99:78 prompt + 79 蓝图 + 99:75 SAM3_Detect
#     + 300 InvertMask + 111 JoinImageWithAlpha + 200 SaveImage
# 注入: 79.image = 蓝图, 99:78.text = 元素描述, 200.filename_prefix
# 提示词示例: "apartment building" / "large headline text" / "red pushpin"
# 支持多对象: "coin:1, question mark:1"
```

### Step D：抠图 + 裁剪

```python
# PIL: 四角取背景色 -> 色彩距离阈值(>40) -> alpha
# 然后裁剪到主体 bbox + 2% 留白（否则 HTML 里主体太小）
```

### Step E：HTML 组合（可复现 + 可调）

- 模板参考：`C:\Users\tiger\AppData\Local\Temp\opencode\klein_test\layered_v5.html`（参数化 CSS 变量）
- 每个元素一个 CSS 类：left/top/width/rot/z/filter(drop-shadow)
- 标题用深色条带 + 浅色字（防与背景混）
- 图钉/胶带用素材库 SVG（`assets/shared_library/images/decals/`）
- 全图加 `.grain` 纸张颗粒层（SVG noise + multiply）
- 截图: `chrome --headless --screenshot=out.png --window-size=1360,768 file:///...html`

### Step F：视觉验证

```bash
python .agents/skills/minimax-m3-vision/scripts/analyze_media.py 图.png -p "评估..."
```
检查：叙事完整性 / 元素大小 / 重叠 / 空白 / 融合度。
（最终审美由用户确认，视觉模型只给客观分析）

## 4. 测试案例当前状态（贝莱德 c1）

| 项 | 状态 |
|---|---|
| script（5 段式中文旁白）| ✅ examples/vox-paper-collage/script/script_sample.json |
| scene_plan v2（TTS 校准后）| ✅ 17 beats，b1.1/b5.4 已写 image_prompt |
| b1.1 元素图（hero v5/地图/年份章/双人/箭头）| ✅ `E:\YifuAIForge\OpenMontage\_tmp\layered_v3\` |
| b1.1 HTML 组合 v6 | ✅ 截图 layered_v6.png |
| SAM3 提取验证 | ✅ building/title/red_figure 提取成功 |

## 5. 新会话第一步做什么

1. 读本指南 + `CONTEXT.md` + `scene-plan-director.md`
2. 检查 ComfyUI 在线：`python -c "from tools._comfyui.client import ComfyUIClient; print(ComfyUIClient().is_available())"`
3. 确认模型：Klein（flux-2-klein-9b）和 SAM3（sam3.1_multiplex_fp16）在服务器
4. 续跑：从 scene_plan 取 beat → 写 image_prompt（若缺）→ 生成蓝图 → SAM3 提取 → 抠图裁剪 → HTML 组合 → 视觉验证 → 用户确认

## 6. 当前已知待办（下一步）

- [ ] 给剩余 15 个 beat 写 Playbook 级 image_prompt（b1.1/b5.4 已完成示例）
- [ ] assets-director.md 更新：蓝图生成直接用 `beat.image_prompt`（替代 SCENE+box 拼接）
- [ ] 用 b1.1 image_prompt 直接生成蓝图验证效果
- [ ] 把 HTML 组合模板固化为 `templates/composition_template.html`
- [ ] scene_plan 全量补齐后批量执行
