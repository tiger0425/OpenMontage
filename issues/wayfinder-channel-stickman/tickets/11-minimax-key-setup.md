# 配置 MINIMAX_API_KEY 并验证生图

---
状态: closed
类型: wayfinder:task
指派: 绘图会话
阻塞于: 无
---

## 问题

把用户提供的 MINIMAX_API_KEY 配进本机环境并验证 minimax 生图链路端到端可用。

## 决议（已完成）

- 密钥写入 `.env`（已确认 `.gitignore` 覆盖 `.env`/`*.env`，密钥不入库）
- 注册表验证：一把 key 解锁四件套——image_generation 3/11、music_generation 1/3、tts 5/8、video_generation 2/18
- 冒烟通过：`minimax_image`（provider MiniMax，model image-01）以 `aspect_ratio: "9:16"` 成功出图 1 张，链路端到端可用
- 安全提醒：该 key 曾在聊天中明文粘贴，若此对话会被分享，建议在 MiniMax 控制台轮换
