# vox-collage 管线精简：从双路线收敛到单一路线

> 写于 2026-10-04，工作区 `E:\YifuAIForge\OpenMontage`。
> 本文所有数字都是**本次实测**的，并已在 §附录 留下复核命令。
> 交接文档 `handoff-vox-wrc27-regs-90s.md` §3.4 的诊断有三处不准确，已在下文更正 —— 更正后的结论**指向一个更省力的解法**。

---

## Problem Statement（问题陈述）

用户的原话是「我发现这个管线现在非常复杂」。这个感受是真实的，但复杂度**不在实际跑出片子的那条路里**。

VOX 纸质拼贴视觉风格有**两条平行实现的路线**：

- **路线 A** —— `bin/vox_collage.py` + `apps/vox-collage/`。WRC 2027 那条已验收的片子是它跑的。
- **路线 B** —— `pipeline_defs/vox-paper-collage.yaml` + `skills/pipelines/vox-paper-collage/` + `styles/vox-paper-collage*.yaml`。由 `pipeline-forge` 元管线**机器生成**（manifest 自述 `category: custom` / `stability: beta` / "Forged by the pipeline-forge meta-pipeline"）。

路线 B 可以被调用（`bin/omo.py` 按 `pipeline_defs/<name>.yaml` 通用解析），但**一次都没被执行过**。

于是真正的痛点是：

1. **维护面积被一条不跑的路占了大半。** 改动节奏参数要动 10 个文件（`f454040` 实证），而这 10 个文件全在路线 B。
2. **改一处数字，改不到真正跑的那条路。** `4.7`（字/秒估算）实测 11 个文件，**没有一个是路线 A 的代码**——路线 A 根本不估算，它读 WAV 实测秒数。所以为 `4.7` 做的收敛工作，对实际出片零收益。
3. **真正会咬人的重复在路线 A 内部，且没人追过它。** 见下节 —— `lead 0.30 / tail 0.25` 这个决定「音频时间轴 == 字幕时间轴」的常数，**在 3 个文件 4 处各写了一遍**，其中字幕烧录器独立持有一份。它们一旦漂移，表现是字幕与画面缓慢失步 —— 最难查、也最伤成片的那类 bug。
4. **这个区域零测试覆盖**（实测：`tests/` 下没有任何测试指向 `vox_collage` / `vox-collage` / `vox_paper` / `paper-collage`）。

---

## 实测数据（并更正交接文档）

| 项目 | 交接文档说 | 实测 | 结论 |
|---|---|---|---|
| 视觉风格总规模 | 49 文件 / 7575 行 | **50 文件 / 10442 行** | 文件数对，行数少算了 38% |
| 路线 B 规模 | 「manifest + skills + 10 份 schema」 | **29 文件 / 6216 行** | 体量被严重低估：占总量 **59.5%** |
| 路线 A 规模 | 未单列 | **21 文件 / 4226 行** | 实际出片的那条路只占 40.5% |
| 路线 B schema | 10 份 | **0 份** | 路线 B 复用 `schemas/artifacts/` 下 33 份通用 schema，没造新 schema |
| 路线 B 产物 | 0 产物 | 0 checkpoint ✓，但 **6 份 sample 产物** | `examples/vox-paper-collage/` 下有 idea/proposal/script/scene_plan×2/assets 样例 |
| `4.7` 散布 | 8 文件 | **11 文件**（路线 B 域内） | 且**全部是路线 B 与文档**，路线 A 代码 0 处 |
| `ducking` 散布 | 14 文件 | **6 文件**（路线 B 域内） | 真正的 ducking 实现是共享的 `tools/audio/audio_mixer.py`（26 处），不属本管线 |
| `f454040` 改动面 | 10 文件 | **10 文件** ✓ | 实证成立；10 个文件**全部是路线 B + docs + styles** |

**更正后的核心结论**：交接文档说「管线太复杂」，并建议「B 参数收敛 → C 宪法对齐 → A 冻结路线 B」。
实测显示 **C 与 B 的工作量都花在一条不跑的路上**，而路线 A 内部那个真正危险的重复（lead/tail）从未被点名。

所以建议把顺序**倒过来**：先冻结路线 B 止血 → 再收敛路线 A 真正共享的时间轴常数 → 最后处置路线 B 的存废。

### 路线 A 的 lead/tail 重复（本次新发现，交接文档未提）

同一个 `lead = 0.30 / tail = 0.25` 语义，写了 4 遍：

| 位置 | 形态 | 谁依赖它 |
|---|---|---|
| `bin/vox_collage.py:1093` | `slot_of = lambda sid: 0.30 + seconds + 0.25` | H3 单幕片段的生成长度 |
| `bin/vox_collage.py:661` | 幕模板 `lead_sec: 0.3, tail_sec: 0.25` | episode.json 契约初值 |
| `template/hyperframes/generate_composition.py:90` | `def generate_index_html(..., lead=0.30, tail=0.25)` | 画面时间轴 |
| `template/tools/subtitle_burner.py:120` | `lead, tail = 0.30, 0.25` | **字幕时间轴** |

**这是「音频时间轴 == 字幕时间轴」这一不变量的四个独立副本。** 任何一处被单独改动，字幕就会与音画失步 —— 而管线目前没有任何机制或测试阻止它。

⚠️ **陷阱**：`generate_composition.py:29` 有 `WIPE_SEC = 0.30`，**数值碰巧相同但语义完全不同**（换幕纸擦除的单侧时长）。任何「把 0.30 收敛成一个常数」的粗暴重构都会把两个无关概念错误合并。这是本计划必须显式防住的错误。

---

## Solution（解法）

三步，按此顺序：

**第一步 · 止血（phase 0）** —— 把路线 B 标记为**冻结**。不删代码、不改行为，只是让「下一个 agent」不再往里投入。当前每分钟的维护成本都发生在错误的文件上。

**第二步 · 收敛真正共享的常数（phase 1）** —— 为路线 A 的 `lead / tail / media_start` 建立**机器可读的单一事实源**，让上面 4 处全部从它读取；**先补一致性测试再改**（当前零覆盖，先固化现状）。这是唯一能消除「字幕失步」这类事故的改动。

**第三步 · 处置路线 B（phase 3，需用户决策）** —— 冻结保留，或整体删除 6216 行。因为它是 `pipeline-forge` 生成的脚手架且从未执行，删除是安全的；但这是用户的资产决策，不由 agent 单方面执行。

关键设计原则：**单一事实源只覆盖真正跨进程共享的量。** 路线 A 的时长本来就以「WAV 实测秒数」为准（`voice.get(sid)["seconds"]`），所以**不需要**引入字/秒估算常数 —— 那正是路线 B 的问题。不要为了让两条路「对齐」而把估算模型塞进路线 A。

---

## Commits（分步计划）

每一步都必须让仓库处于可工作状态。步骤尽量小，便于随时看到程序仍在工作。

### Phase 0 — 冻结路线 B（零行为变更）✅ 已完成 2026-10-04

> 实施记录：3 项编辑**合并为一个提交**（纯标记/文档，拆三个提交只增加噪音），与计划原文的
> 「3 个小提交」不同，行为等价。

1. ✅ **在路线 B manifest 声明冻结。** 用 `metadata.frozen: true` + 顶部注释块。
   **⚠️ 实施中发现一个计划没预见的约束**：`schemas/pipelines/pipeline_manifest.schema.json` 里
   `stability` 是**封闭枚举** `["production", "beta"]`，顶层又是 `additionalProperties: false`（第 160 行），
   且 `lib/pipeline_loader.py:48` 确实会执行 `jsonschema.validate` —— 所以**不能**写
   `stability: frozen`，也**不能**新增顶层键，否则 manifest 直接加载失败。
   唯一合法的自由字段是 `metadata`（schema 第 134 行 `{"type": "object"}`，另有 3 个 manifest 已在用）。
   改动后已实测 `load_pipeline('vox-paper-collage')` 仍通过校验（8 stages）。
2. ✅ **在路线 B 的 EP 技能顶部加冻结横幅。** `skills/pipelines/vox-paper-collage/executive-producer.md`
3. ✅ **在总纲标注。** `docs/VOX_PIPELINE_MASTER.md` §0 总览 + §4 路线 B 章首；
   并顺手修正 §0 表格里「`apps/vox-collage/`（本地目录，不在 git）」这句已过期的话（本次已入库）。

> 完成 phase 0 后，`f454040` 那类「改一个数字动 10 个文件」的维护行为应当停止发生。

### Phase 1 — 路线 A 时间轴常数的单一事实源（6 个提交）

4. **先补特征化测试（固化现状，不改代码）。** 新增测试断言三处 lead/tail 当前相等，以及 `slot == lead + wav_seconds + tail`。**此时应全绿**；这是后续重构的安全网。
5. **新增单一事实源。** 在路线 A 内建立机器可读的时间轴参数载体，承载 `lead_sec / tail_sec / media_start_sec / hero_media_start_sec`。**明确排除** `WIPE_SEC`。
6. **让画面时间轴读取它。** `generate_composition.py` 改为从事实源取默认值（保留函数签名默认参数，向后兼容既有调用）。
7. **让字幕时间轴读取它。** `subtitle_burner.py` 改为从事实源读取——**这一步是整条计划里价值最高的一次改动**，因为它消除了字幕失步的根因。
8. **让 CLI 与 episode 契约读取它。** `bin/vox_collage.py` 的 `slot_of` 与幕模板改为引用同一来源。
9. **收紧测试。** 把第 4 步的「当前相等」断言升级为「结构上不可能不等」（改为从单一来源派生，而非三处比对）。

### Phase 2 — 宪法与代码对齐（3 个提交）

10. **修 `.agents/skills/vox-collage/SKILL.md` 的两处已知错误。** 该文件声称 master sheet 锁为 `<image_2>`（实际代码已 `pop`，且母版从未传入）；声称 HyperFrames「0.8.105 锁版」（实际 `npx hyperframes@latest`）。文档说谎会让后续 agent 做错决策。
11. **消除 master sheet 的「文档 vs 代码」分歧。** 二选一：让代码真正传入母版，或把文档改为描述现状。**先决定再动手**，不要把两者都改成第三种状态。
12. **标注 `4.7` 系参数的定位。** 在路线 B 的 `bilingual-spec.md` 与 manifest 中注明：这是**估算模型**（用于 scene_plan 的时长预估），**不是运行时事实源**；运行时以 WAV 实测秒数为准。这正是 79.9s vs 90s 落差的成因，写清楚可避免下次再次误判。

### Phase 3 — 路线 B 的最终处置（需用户决策后再排提交）

13. **决策：冻结保留，还是删除。** 若删除，独立成一个提交：移除 manifest + 11 份 director 技能 + 2 份 style，并把 `examples/vox-paper-collage/` 的 6 份样例迁入路线 A 的 specs 作为参考（它们是路线 B 唯一有价值的产出）。

---

## Decision Document（决策记录）

- **冻结标记用 `metadata.frozen`，绝不用 `stability`。** manifest schema 里 `stability` 是封闭枚举
  （`production|beta`）、顶层 `additionalProperties: false`，而 `lib/pipeline_loader.py` 会真正校验 ——
  写 `stability: frozen` 会让 manifest 无法加载。`metadata` 是 schema 里唯一合法的自由字段。
- **不建立统一的「管线常数注册表」。** 实测表明跨路线的常数重复（`4.7`）只存在于不跑的路线 B；为它建注册表是在给死代码修路。事实源只覆盖路线 A 内**跨进程共享**的时间轴量。
- **单一事实源的形式采用「机器可读」而非「文档约定」。** 现有 `bilingual-spec.md` 已是「文档即事实源」，正是 `f454040` 要改 10 个文件的根因。
- **`WIPE_SEC` 与 `lead/tail` 必须保持分离**，尽管数值都是 0.30。前者是换幕擦除时长，后者是幕内首尾留白。计划明确禁止合并。
- **不引入字/秒估算常数到路线 A。** 路线 A 已由 WAV 实测秒数驱动（`voice.get(sid, {}).get("seconds", 3.0)`），这是它比路线 B 更准的原因（实测 5.11 vs 估算 4.7）。
- **路线 B 属用户资产，删除不由 agent 单方面执行。** 计划只负责把它冻结、并把决策点显式化。
- **接口影响**：`generate_index_html(..., lead, tail)` 与 `subtitle_burner` 的 lead/tail 保留为带默认值的参数（向后兼容），改的是默认值的来源。
- **Schema 影响**：无。路线 B 复用通用 schema，本次不改 `schemas/artifacts/`。
- **不动 `bin/omo.py`**：它是通用 harness，route B 的可调用性是它的正常行为，不是缺陷。

---

## Testing Decisions（测试决策）

**现状：路线 A / 路线 B 均为零测试覆盖。** 实测 `tests/` 下无任何文件指向 `vox_collage` / `vox-collage` / `vox_paper` / `paper-collage`（唯一的 `vox` 命中是 `voxcpm` TTS provider，与本管线无关）。

- **先补测试，再重构。** 在触碰任何时间轴常数之前，先写固化现状的特征化测试。零覆盖之下重构时间轴，等于蒙眼改一个会静默失步的系统。
- **什么算好测试**：只测**外部行为**——即「字幕时间窗 == slot 时间窗」「slot 总长 == lead + WAV 实测 + tail」这类可观察不变量；**不要**测「某文件里有个 0.30 字面量」这类实现细节。
- **要测的模块**：`subtitle_burner` 的时间轴推导、`generate_composition` 的画面时间轴、`bin/vox_collage.py` 的 `slot_of`。核心断言是三者**互相一致**（这是跨模块契约，不是单元内部细节）。
- **先例**：`tests/auto_dub/test_assets_alignment.py`（对齐类断言）与 `tests/contracts/`（跨模块契约）是最贴近的写法参考；`tests/qa/` 是端到端脚本，不适合本用途。
- **不做**：不为冻结的路线 B 补测试。给死代码补测试是最昂贵的自我安慰。

---

## Out of Scope（不在范围内）

- **不重跑任何 `stills` / `motion` / `render`**，不碰 WRC 2027 已成片（用户已验收）。
- **不动 GPU / ComfyUI / IndexTTS 侧**的模型、参数、显存策略。
- **不删除路线 B 的代码**（本计划只冻结；删除是 phase 3 的独立决策）。
- **不做仓库级的常数收敛**（其他管线无此问题；实测 `ducking` 的真实实现是共享的 `audio_mixer.py`，不在本管线）。
- **不改 `bin/omo.py` 的通用解析行为。**
- **不处理**交接文档 §3.5 待重新核实的 `emo_vector` 结论，以及 §4.4 记录的沙箱/权限环境问题。
- **不动幕 02 已烤进静帧的小标签**（用户已接受通过）。

---

## Further Notes（补充）

- **本次会话已顺手完成两件事**（因此不在上表计划中）：路线 A 三路径入库（`a42ce30`，含 7 项会话修复与 `.gitignore` 锚定），以及 `cmd_new` 中文选题 ID 与覆盖保护的修复（`4eda008`）。
- **交接文档 §3.1-1 已被证伪**：所谓「`motion` 的 asmr 抽取忽略 `--only`」不成立。`--only` 在 hero 循环前过滤，asmr 抽取在该循环内；探针实证 `motion --only 03` 只产出 `gen-scene-03.mp4`，预置的 `asmr-01`/`asmr-06` 哨兵字节未被改动。**据此未改动 `motion`。**
  但该现象背后**有一个真实且未被处理的隐患**：完整跑一次 `motion`（不带 `--only`）会静默重建所有 hero 幕的 asmr，覆盖用户用 Demucs 手工去人声后 4 条产物，无任何警告或备份。这属同类「静默覆盖人工产物」风险，建议在 phase 1 之后单独评估是否加 `--force` 式保护。
- **`.gitignore` 的一个静默陷阱已被修掉**：未锚定的 `ComfyUI/` / `hyperframes/` 会在任意深度匹配（Windows 上还大小写不敏感），曾吞掉 `template/comfyui/wf_{img,vid,edit}.json` 与 `template/hyperframes/generate_composition.py`，使 `git add apps/vox-collage` 无提示漏文件。已锚定为 `/ComfyUI/` 与 `/hyperframes/`。
- **分支现状**：这些提交都在 `research/douyin-retention-rules` 上，该分支领先 `main` 9 个提交，`main`（`5f75637`）**不含** `f454040` 及任何 vox-collage 工作。是否需要合并/搬迁到 `main` 由用户决定。

---

## 附录：复核命令

本文每个数字的复核方式（在仓库根执行）：

```powershell
# 总规模与 A/B 拆分
$vox = @(); $vox += Get-ChildItem apps/vox-collage,.agents/skills/vox-collage,skills/pipelines/vox-paper-collage,examples/vox-paper-collage -Recurse -File
$vox += Get-Item bin/vox_collage.py,pipeline_defs/vox-paper-collage.yaml,styles/vox-paper-collage*.yaml,styles/vox-collage.yaml
$vox += Get-Item docs/VOX_PIPELINE_MASTER.md,docs/VOX_PAPER_COLLAGE_*.md,docs/adr/ADR-002-*.md,docs/optimization-charters/vox-paper-collage-*.md
$vox = $vox | Where-Object { $_.Extension -notin '.png','.pyc' } | Sort-Object FullName -Unique
$vox.Count; ($vox | Where-Object { $_.FullName -match 'vox-paper-collage|VOX_PAPER_COLLAGE|ADR-002' }).Count

# 4.7 / ducking 在 VOX 域内的散布
$vox | Select-String '4\.7'    | Select-Object -ExpandProperty Path -Unique
$vox | Select-String 'ducking' | Select-Object -ExpandProperty Path -Unique

# f454040 的改动面
git show --stat f454040

# 路线 B 无执行痕迹
Get-ChildItem pipelines -Directory          # 无 vox-paper-collage
Get-ChildItem tests -Recurse -Include *.py | Select-String 'vox_collage|vox-collage|paper-collage' -List   # 空
```
