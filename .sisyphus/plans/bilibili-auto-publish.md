# 全自动视频搬运 + B 站统一投稿系统 实施方案

## 摘要

在 OpenMontage 现有 Auto-Dub 搬运管线基础上，新增 **B 站统一投稿与运营层**，实现"白名单频道新视频进站 → 全自动搬运/制作 → 飞书确认 → 自动上传 B 站 → 半自动护持"的全链路自动化。架构上它不是搬运系统的扩展，而是 **OpenMontage 所有视频管线的统一 B 站出口**：auto-dub（翻译搬运）只是第一个接入的管线，repo-to-video 紧随其后，其余管线按统一 `publish_bundle` 规范逐个接入。

核心形态为「**发布闸门**」：内容制作全自动，但发布前推飞书待确认，人工在带 token 的本地确认页点一次确认（或驳回/改元数据）。全自动无人值守直发被明确排除——B 站风控与账号健康不允许。

## 背景

### 现状差距（代码级定位）

| 需求 | 现状 | 差距 |
|------|------|------|
| 定时触发 | 无任何调度设施，`scan` 靠手动 | 无 autopilot，无计划任务 |
| 通知/确认 | 无通知推送；review 靠 CLI `approve-review` 人工查 | 无飞书通道、无确认交互 |
| B 站上传 | 全库无 B 站上传代码，`_run_publish_stage` 只归档不发布；`bin/youtube.py` 仅 YouTube | 无 biliup 封装、无凭证管理 |
| 账号路由 | `bilibili-channel-strategy` skill 是纯人工运营规则书 | 选题池/节奏/护持全人工 |
| 产出类型 | auto-dub 只产配音版；auto-subtitle 字幕版为未提交半成品 | 无类型路由（访谈→配音 / 展示→字幕） |
| 统一投稿 | repo-to-video 有独立 publish_log 雏形，各管线元数据各管各 | 无统一 publish_bundle 契约 |
| GPU 算力 | TTS 重活需派 Compute Worker 子 Agent 在场执行 | 无人值守时无法自动跑 TTS |
| 失败处理 | 无熔断概念，失败记日志跳过 | 无自动熔断/恢复/报警 |

### 关键既有资产（复用，不重造）

- `apps/auto-dub/`：发现（channel_monitor/keyword_searcher/video_filter）→ 翻译（llm_client/glossary）→ TTS（IndexTTS2 本地 GPU，经 `lib/gpu_lock.py` 互斥）→ 混音/压制 → 归档待审。tracking.db 151 条记录，六阶段管线已稳定。
- `apps/auto-subtitle/`：字幕版路线的半成品，需并入类型路由。
- `apps/repo-to-video/`：GitHub 仓库 → 中文 AI 解说 B 站视频（B 号），已有 publish_log 雏形与 AI 披露声明。
- `.agents/skills/bilibili-channel-strategy/SKILL.md`：三号矩阵运营规则书（选题池/19:30 发布/30 分钟护持期/封面验收）。
- `lib/gpu_lock.py`：文件级 GPU 互斥锁，跨引擎共享。

## 目标

1. 白名单频道新视频进站后，全程零代码干预产出成品并推送飞书待确认。
2. 人工在飞书推送的本地确认页一次性确认后，自动按三号矩阵节奏上传 B 站。
3. 上传后的确定性护持动作（弹幕种子/置顶）自动执行；评论回复只生成草稿推飞书，人工确认后发送。
4. 任一管线（不只 auto-dub）都可通过统一 `publish_bundle` 投稿 B 站。
5. 全链路有明确熔断边界：坏状态不自动传播，失败可定位、可恢复。

## 范围

### 一期（MVP，先做）

- `apps/bilibili-publish/` 新模块：autopilot 调度 + 飞书通道 + 本地确认页 + biliup 封装 + publish_queue/publish_log 表。
- 只接 **auto-dub** 管线、只用 **C 号**、手动排期（不做三号矩阵自动分流）。
- 类型路由（访谈→配音 / 展示→字幕）接入，顺带收编 auto-subtitle。
- 双层熔断 + 飞书报警 + 一键恢复。
- 凭证：扫码登录（biliup）+ Cookie 导入兜底。
- 护持：仅发布后提醒，不做弹幕/评论自动。

### 二期

- 三号矩阵自动分流 + 自动排期（遵守 C/A/B 号节奏，配额熔断）。
- repo-to-video 接入统一 bundle。
- 弹幕种子/置顶自动投 + 评论回复草稿推飞书。
- GPU 低峰时段调度（23:00–8:00 集中跑 TTS）。

### 三期（预留）

- 其余管线（fabric-promotion/animated-explainer/series-adapt 等）逐个接入。
- 阿里云 Green 内容审核复核。
- 飞书自建应用交互卡片升级（直接卡片点确认）。
- 护持全自动（在二期评论草稿人工验证充分后评估）。

## 技术决策（全部轮次收敛结论）

| # | 决策项 | 结论 | 理由 |
|---|---|---|---|
| Q1/Q6 | 全自动形态 | **发布闸门**：制作全自动，发布前飞书推送待确认，本地确认页（带 token）批准/驳回/改元数据 | 平台风控下无人值守直发不可持续；确认页是一期"轻量 Web 面板"雏形 |
| Q2 | 平台 | 仅 B 站（先），AcFun 等后补 | 复用三号矩阵运营资产 |
| Q3 | 内容源 | 白名单频道池（现有 9 个 AI 频道，可扩展） | 全站化会让筛选/合规/选题失控 |
| Q4/Q16 | 产出形态 | **类型路由**：访谈→配音版，纯展示/资讯→字幕版。判定 = 频道风格表锁定 + LLM 元数据判定兜底，确认页可改 | 单人解说频道直接锁定 subtitle 不判，多人访谈直接锁定 dub 不判 |
| Q5 | 架构归属 | 扩展现有 OpenMontage + auto-dub，新增 `apps/bilibili-publish/`；**全管线统一投稿** | 独立 Flask 应用=重写 Y2A 且重踩 TTS 对齐坑 |
| Q7 | B 站上传 | `biliup` + 自包 `bin/bilibili.py` 统一入口 | 成熟、扫码登录、多号、社区持续对抗风控；自研留作后手 |
| Q8 | 账号/排期 | 二期起三号矩阵自动分流 + 自动排期（遵守各号节奏，超配额顺延进待发队列） | 运营规则书已写清，缺的只是"把规则变成自动路由" |
| Q9 | 投稿契约 | 统一 `publish_bundle`（video+cover+title/desc/tags+chapters+AI披露+source_info+目标号），管线只产 bundle，发布层统一校验/排期/上传。首批 auto-dub + repo-to-video | 一次接 5 个管线=同时维护 5 种元数据质量门 |
| Q10 | 护持 | 弹幕种子/置顶自动（确定性无害动作）；评论回复只生成草稿推飞书人工确认 | 自动回评论是唯一"AI 对真人说话"环节，必须留人 |
| Q11 | 调度形态 | 无守护的 `autopilot` 模块 + Windows 计划任务定时调用 CLI 各阶段（每天唤醒 4–6 次） | Windows 下计划任务比守护进程稳（崩溃自动重拉、可手动补跑）；autopilot 纯函数可测 |
| Q12 | GPU 调度 | 后台串行消费 GPU 队列（遵守 gpu_lock，一次一个，失败重试，超时熔断）；二期默认低峰时段跑 TTS | IndexTTS2 占 8–16GB VRAM，白天撞 GPU 工作互抢 |
| Q13 | 失败熔断 | 双层熔断：单任务失败重试 N 次后跳过；**连续 3 任务失败** → 全管线熔断 + 飞书报警；**单号达当日配额** → 该号今日停发。恢复 = 确认页一键解除或次日 8:00 自动复位 | 坏状态不自动传播；三号节奏错了比失败更伤账号 |
| Q14 | 合规 | 规则级自检（关键词黑名单 + 标题/简介必填校验 + AI 披露/转载标记**强制必填**，不过审不发）；Green 留三期 | 白名单内容源 + 人工闸门下规则自检足够 |
| Q15 | 凭证 | 扫码登录（biliup）为主 + Cookie 导入兜底；三号凭证隔离存储；失效推飞书"请重新扫码" | 扫码是主路径，导入是逃生通道 |
| Q17/Q18 | 分期/验收 | 一期→二期→三期；一期验收 = 连续 10 个视频稳定跑通 + 1 次人为制造失败验证熔断 | 一期刻意"窄而通"验证真实链路稳定，再横向扩管线 |
| Q19 | 数据模型 | tracking.db 加 `publish_queue` + `publish_log` 两张表，管线状态与发布状态**解耦**，经 `source_record_id` 关联 | 塞进 record 表会状态机绞在一起，熔断/重排/换号互相污染 |

## 架构设计

### 模块与目录布局

```
apps/bilibili-publish/            # 新增：B 站统一投稿与运营层
├── config.py                     # 读取 config.yaml 的 publish 段 + 三号矩阵档案
├── scheduler/
│   └── autopilot.py              # 无守护调度逻辑（纯函数，读 cron 规则执行各阶段）
├── notify/
│   ├── feishu.py                 # 飞书 webhook 推送（待确认卡片/熔断报警/护持提醒/凭证失效）
│   └── confirm_server.py         # 极简本地确认页（带 token：approve/reject/edit）
├── publish/
│   ├── bilibili_uploader.py      # biliup 封装（上传/状态/发布后数据）
│   ├── credential.py             # 扫码登录 + Cookie 导入/隔离存储 + 失效检测
│   └── bundle.py                 # publish_bundle schema 校验器（发布前 lint）
├── routing/
│   └── type_router.py            # 频道风格表 + LLM 元数据判定 → dub/subtitle
├── account/
│   └── scheduler.py              # 三号矩阵分流 + 排期（配额熔断，二期）
├── support/
│   ├── nurture.py                # 弹幕种子/置顶脚本（二期）+ 评论草稿生成
│   └── circuit_breaker.py        # 双层熔断
└── db/
    └── publish_store.py          # publish_queue / publish_log 表读写
bin/autopilot.py                  # 新增：autopilot CLI 主入口
bin/bilibili.py                   # 新增：B 站统一发布 CLI（login/upload/status/confirm/nurture）
config.yaml                       # 修改：新增 publish 段（cron 规则/频道风格表/飞书 webhook/号档案）
```

### 数据模型（tracking.db 新增两表）

```sql
CREATE TABLE publish_queue (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  source_record_id INTEGER,            -- 关联 auto-dub/repo-to-video 记录（可空）
  pipeline         TEXT NOT NULL,      -- 'auto-dub' | 'repo-to-video' | ...
  bundle_path      TEXT NOT NULL,      -- publish_bundle.json 路径
  target_account   TEXT NOT NULL,      -- 'C号' | 'A号' | 'B号'
  route_type       TEXT,               -- 'dub' | 'subtitle'
  scheduled_at     TEXT,               -- 排期时间（二期）
  status           TEXT NOT NULL,      -- pending_confirm|confirmed|uploading|uploaded|queued_nurture|done|rejected|failed|circuit_open
  attempts         INTEGER DEFAULT 0,
  last_error       TEXT,
  feishu_msg_id    TEXT,               -- 对应待确认卡片
  created_at       TEXT,
  updated_at       TEXT
);

CREATE TABLE publish_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  queue_id    INTEGER NOT NULL REFERENCES publish_queue(id),
  event       TEXT NOT NULL,           -- confirmed|upload_start|upload_success|upload_fail|nurture_done|circuit_open
  detail      TEXT,
  created_at  TEXT
);
```

### 状态机

```
pending_confirm ──确认──> confirmed ──> uploading ──> uploaded ──> queued_nurture ──> done
       │                  │                                    │
       ├──驳回──> rejected         └──失败──> failed ──重试──> confirmed（attempts+1）
       └──改元数据──> pending_confirm                       │
                                     连续3失败或连续N次上传失败
                                              │
                                          circuit_open（飞书报警；确认页一键解除或次日8:00复位）
```

### 类型路由规则

- **频道风格表（锁定，最高优先）**：`config.yaml.publish.channel_styles` 配置每频道的产出类型（dub / subtitle / unknown）。`unknown` 才走 LLM。
- **LLM 元数据判定（兜底）**：标题 + 简介 + 时长喂 LLM，输出 `dub` 或 `subtitle`。
- 判定结果写入 publish_queue.route_type，**确认页可改**。

### 凭证管理

- biliup 扫码登录 → token 本地加密存储（三号各一份，隔离目录）。
- 失效检测：上传前预检，失效 → publish_queue 记状态 + 飞书推"请重新扫码"。
- Cookie 文件导入兜底（`bin/bilibili.py login --import cookie.txt`）。

## 验证策略

1. **一期验收（正式定义"做完了"）**：白名单频道新视频进站 → 自动产出成品 → 飞书待确认 → 本地确认页确认 → biliup 上传 B 站成功，全程零代码干预；**连续 10 个视频**稳定跑通（发布成功率 100%，熔断 0 次误触发）；第 5–10 个期间**人为制造 1 次失败**（如删除成品文件/伪造上传失败），验证熔断会响、飞书报警可达、确认页一键恢复有效、次日自动复位有效。
2. **publish_bundle lint 单测**：缺 AI 披露/缺 cover/标题超长等非法 bundle 一律拒绝发布。
3. **熔断单测**：连续 3 失败 → `circuit_open`；单号当日配额达上限 → 该号今日停发。
4. **类型路由单测**：已知风格频道锁定不判；unknown 频道 LLM 判定结果可被确认页覆盖。
5. **凭证单测**：无效 Cookie 上传前被预检拦截并触发飞书提醒。
6. **回归**：现有 auto-dub 六阶段管线 + `tests/` 全绿，auto-subtitle 收编后原有 CLI 不破坏。

## 执行策略

```
阶段 0  基线固化：收编 auto-subtitle、确认 bilibili-channel-strategy 规则可读入
阶段 1  数据层：publish_queue/publish_log 表 + publish_store（TDD）
阶段 2  bundle 契约：schema 校验器 + auto-dub 产出 publish_bundle
阶段 3  上传层：biliup 封装 + 凭证管理 + bin/bilibili.py
阶段 4  通知层：飞书 webhook + 本地确认页（token）
阶段 5  调度层：autopilot 模块 + Windows 计划任务 + 类型路由接入
阶段 6  熔断：circuit_breaker + 飞书报警 + 一键恢复
阶段 7  一期验收：连续 10 个 + 人为失败演练
阶段 8  （二期）三号矩阵分流排期 + repo-to-video 接入 + 护持半自动 + GPU 低峰调度
阶段 9  （三期）多管线接入 + Green + 飞书卡片 + 护持评估
```

每个阶段独立 commit，便于 review 与回滚。

## 风险与约束

- **B 站风控不可控**：biliup 是社区对抗风控的产物，上传可能被限流/风控。缓解：发布闸门 + 配额熔断 + 三号凭证隔离，任一账号异常只伤该号。
- **Cookie 生命周期**：SESSDATA 几周到几个月失效。缓解：上传前预检 + 失效飞书提醒 + 导入兜底。
- **TTS 与 GPU 争抢**：无人值守时 TTS 串行执行，若白天与用户其他 GPU 工作撞车。缓解：一期随机串行（gpu_lock），二期低峰时段调度。
- **全自动 ≠ 无监督**：确认闸门是硬边界，不因自动化程度提升而撤销。
- **规则书 → 代码的翻译损耗**：bilibili-channel-strategy 的人工运营细节转成 config 规则时可能失真。缓解：二期接入前先对照规则书评审号档案配置。
- 一期刻意不做三号矩阵分流与自动护持，避免范围爆炸。

## 成功标准

- [ ] 一期：连续 10 个视频白名单进站 → B 站发布成功，零代码干预，仅确认页点 1 次确认
- [ ] 一期：人为制造 1 次失败，熔断触发、飞书报警、一键恢复、次日自动复位全链路验证
- [ ] 统一 publish_bundle 契约生效，auto-dub 与 repo-to-video 均可产出合法 bundle
- [ ] 类型路由生效：访谈→配音版、展示→字幕版，确认页可改判定
- [ ] 三号凭证扫码登录 + Cookie 导入兜底 + 失效自动提醒（二期）
- [ ] 双层熔断：连续 3 失败全停 + 单号日配额熔断（二期）
- [ ] 护持：弹幕种子/置顶自动投，评论回复草稿推飞书人工确认（二期）
- [ ] 三期预留项（Green/飞书卡片/全管线接入）评估后按需推进
