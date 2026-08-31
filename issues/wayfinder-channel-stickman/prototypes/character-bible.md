# 火柴人角色圣经 · channel-stickman v1（定案）

> 来源：工单《SVG 火柴人角色圣经原型》人审通过（2026-08-25）。原型见同目录 `character-bible-preview.html / .png`。

## 1. 视觉规范

| 项 | 值 |
|---|---|
| 头身比 | 大头亲和系 ≈ 1 : 2.2（全身约 3 头身） |
| 画布 | 240 × 320（viewBox），输出按需缩放 |
| 线条 | `#1A1A1A`，7px，round cap / round join |
| 头部 | 白底圆，r = 34px，中心 (120,58) |
| 点缀色 | 思考橙 `#FF7A45`——仅用于道具与情绪符号（?号、灯泡等），不用于肢体 |
| 部件 | 头 / 双眼 / 双眉 / 嘴 / 躯干 / 双臂 / 双腿；地面椭圆阴影 opacity .06 |

关节枢轴：颈 (120,96) · 肩 (120,112) · 髋 (120,172)。

## 2. 分层动效架构（关键决策）

- **表情层（SVG 手绘）**：眉/眼/嘴由 RIG 数据渲染（`character-bible-preview.html` 的 `face()` 函数），GSAP 可直接驱动。
- **肢体层（InkPuppet 动捕）**：全身动作不走手调 transform，统一用 `ink-theater` 的 `InkPuppet.choreograph` 播放 CMU 动捕 clip（`mocap/catalog.json` 12 个：walk/run/climb/march/shuffle/jump/kick/sit/wave/dance_spin/dance_glide/twist）；扩展动作用 `node mocap/add-motion.mjs`。
- 两层叠加：InkPuppet 出骨架位姿，表情层贴头部区域；boil 滤镜全片统一（~9fps stepped seed，seek-safe）。
- 禁止项：禁止对整躯干施加旋转动画（历史踩坑：误把 class 挂在躯干线导致"身体挥手"）。

## 3. 表情库（7，最小集）

calm 平静 · talking 说话 · thinking 思考(配 ? 号) · surprised 惊讶 · sad 沮丧 · determined 坚定 · happy 开心

参数化字段：`mouth(flat/talk/o/frown/smile/firm/side)`、`bigEyes`、`eyeDX/DY`、`bl/br`（眉角度）、`bdy`（眉位移）。试点期不够再扩。

## 4. 动作 clip 映射表（≥8）

| 叙事用途 | InkPuppet clip | 表情搭配 |
|---|---|---|
| 开场自我介绍 | wave | happy |
| 讲述推进 | walk | calm/talking |
| 强调观点 | march | determined |
| 抛出问题 | stand + thinking 表情 | thinking(?号) |
| 转折/惊讶点 | jump | surprised |
| 案例演绎 | run / kick | talking |
| 收尾总结 | sit | calm |
| 片尾引导关注 | dance_glide | happy |
| 兜底静止 | STAND pose | 按台词轮换表情 |

## 5. 接入规范（执行期引用）

```js
var pup = InkPuppet.create(mount, {cx:960, ground:902, boil:"boil", headR:48, strokeWidth:6});
pup.drawIn(tl, {start:0.4});
InkPuppet.choreograph(tl, pup, [{clip:"wave"},{clip:"walk"}], {start:3.0});
```

需复制进产线项目：`ink-theater.js`、`ink-puppet.js`、`clips.js`、`assets/patrickhand.ttf`（OFL，字幕字体）。
