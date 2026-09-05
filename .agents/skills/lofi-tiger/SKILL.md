---
name: lofi-tiger
description: >
  YouTube 治愈系小老虎 Lofi 音乐电台（Tiger & Tea）专属生产流水线技能。
  根据用户指定的场景与时长（1~3小时），自动生成 35mm 胶片风小老虎母图、
  Mid-Crossfade 绝对无缝微动视频、-14 LUFS Lofi+雨声无缝音频，并完成秒级极速流式混流与 YouTube 全自动发布。
  触发词：lofi-tiger, 做条lofi, 小老虎视频, Tiger & Tea, 小老虎lofi, 做小老虎, lofi视频, 森林木屋, 雨夜咖啡馆, 卧铺列车.
metadata:
  tags: "lofi, youtube, tiger, animation, music, stream-loop, autonomous"
---

# Lofi 小老虎电台流水线（Tiger & Tea）专属操作指南

## 📌 业务背景与频道信息

本技能用于为用户的 YouTube 独立品牌频道 **Tiger & Tea** 批量生产 1~3 小时横屏 16:9 治愈系 Lofi 音乐微动视频并全自动发布。

* **频道名称**：Tiger & Tea
* **Channel ID**：UCaT0oUucwfduP_FKcLUje5A
* **已绑定专用凭证**：%USERPROFILE%\.youtube-upload\token_tiger_tea.json（已授权无需再弹窗）
* **参考母本库**：projects/lofi-tiger-pilot/
* **首集样片参考**：[https://youtu.be/LfTizJmfSsc](https://youtu.be/LfTizJmfSsc)

---

## 🐯 角色圣经核心铁律（最新方案，严禁违背！）

任何生成 Tora 视觉资产的 Prompt 必须严格遵循以下契约：

1. **形象与比例**：Chibi 幼态小老虎 Tora，2.5~3 头身，大圆脸，暖蜜琥珀色毛皮（#F5A642），脸颊奶白，额头与身体为柔和巧克力深棕条纹。
2. **耳朵修正（严禁大耳朵）**：**小圆杯状虎耳（深色耳缘）**，严禁生成过大像熊或猫的耳朵。
3. **彻底无耳机（STRICTLY NO HEADPHONES）**：**严禁在 Tora 头上加耳机！** 露出干净自然的毛茸茸小圆耳。
4. **服装**：宽松大号鼠尾草绿大卫衣（oversized sage green hoodie）。
5. **Lofi 音乐象征物（必备）**：桌角或木架上必须有一台**发着暖黄琥珀色光芒的复古木质收音机（vintage retro wooden radio）**，体现音乐氛围。
6. **画风风格**：**Cinematic 35mm film still（35mm 胶片电影质感）**，色调温暖细腻，窗外雨丝夜景具有柔和的光斑（bokeh）。

---

## 🎨 5×5×5 内容组合矩阵

通过以下插拔式组合，单集视频永不重样：

* **主角动作**：① 伏案写字画画 | ② 双爪捧热茶吹气 | ③ 托腮看窗外落雨 | ④ 趴在桌上小憩 | ⑤ 翻阅精装画册
* **迷你伴侣**：① 灰山雀皮皮 | ② 抹茶树蛙 | ③ 卫衣口袋小仓鼠 | ④ 蜷缩打呼白猫 | ⑤ 垂耳兔豆芽
* **场景空间**：① 雨夜天窗阁楼 | ② 阴雨森林木屋茶室 | ③ 暖光街角落雨咖啡馆 | ④ 深夜复古卧铺列车 | ⑤ 榻榻米庭院听雨房

---

## ⚙️ 标准生产四步流程

### Step 1: 视觉母图生成（视觉人审闸门）
1. 组装 Prompt（包含 35mm film still、小圆耳、无耳机、角落复古收音机、雨窗、绿卫衣）。
2. 参考图：传入 projects/lofi-tiger-pilot/assets/images/tora_master_final.png。
3. 调用 generate_image（比例 16:9）或 MiniMax Image-01。
4. **【视觉闸门】**：将生成的母图第一时间展示给用户确认。

### Step 2: 视觉微动生成（Mid-Crossfade 绝对无缝算法）
1. 使用 MiniMax Video Direct 图生视频 6 秒微动（呼吸、眨眼、茶汽袅袅、窗外雨丝）。
2. 运行 Mid-Crossfade 算法对半调换位置并淡化 1 秒，消除接缝跳帧，产出 100% 闭环 5s 微动母本：
   `ash
   python projects/lofi-tiger-pilot/scripts/test_video_loop.py
   `

### Step 3: 音频自回环与环境混音
1. 生成/检索 Lofi 乐段 + 环境雨声（Freesound / 本地库）。
2. 自回环交叉淡化消除接缝爆音，72% 音乐 + 28% 雨声混音，标准化至 **-14.0 LUFS**。
3. 生成目标时长（如 1 小时）的无缝长音轨：
   `ash
   python projects/lofi-tiger-pilot/scripts/test_audio_loop.py
   `

### Step 4: 秒级极速混流与 YouTube 全自动发布
1. 利用 FFmpeg Stream Copy 架构，秒级生成 1~3 小时长视频：
   `ash
   ffmpeg -stream_loop -1 -i loop_5s.mp4 -i audio_1h.m4a -c:v copy -c:a copy -shortest output_1h.mp4
   `
2. 调用专用发布脚本，使用 	oken_tiger_tea.json 自动上传至 Tiger & Tea 频道，自动写入双核标题、分章节时间戳、简介与三级标签。

---

## 🗣️ 自然语言指令映射

| 用户自然语言指令 | 执行动作 |
| :--- | :--- |
| “做一条森林木屋的视频，1小时” | 选定场景②，生成森林木屋主图 -> 质检 -> 制作 1 小时成片 -> 上传发布 |
| “做一条雨夜咖啡馆的视频，带上白猫，2小时” | 选定场景③+伴侣④，生成咖啡馆与白猫主图 -> 质检 -> 制作 2 小时成片 -> 上传发布 |
| “做一条卧铺列车小老虎小憩，1小时，做完发油管” | 选定场景④+动作④，生成卧铺列车主图 -> 质检 -> 制作 1 小时成片 -> 自动推送到 Tiger & Tea |
