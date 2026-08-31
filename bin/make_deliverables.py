#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_deliverables.py — 自动生成「最终交付包」文件夹（流程化，publish 阶段收尾必调）

用法:
  python bin/make_deliverables.py --project <name> \
      --title "<B 站标题>" \
      --description "<简介全文，可含 \n>" \
      --chapters "<章节列表，逗号分隔 '0:00 反直觉开场,0:10 核心句'>" \
      --tags "DeepSeek Harness,DSH,插件系统" \
      [--cover "projects/<name>/renders/cover_design.png"] \
      [--video "projects/<name>/renders/final.mp4"] \
      [--series "DSH 插件系统"] [--episode "第 1 节"] \
      [--cost "0.00"] [--duration "101.5s"] \
      [--glossary "apps/auto-dub/user_glossary_hb.json"]

glossary 模式（tickets #78 / #79）：
  --glossary 指向的 JSON 含 disclaimer_text 字段时，简介文案末尾自动追加
  健康免责声明段（向前兼容，不传则与旧版行为完全一致）。

产出（全部在顶层，用户只找这一个文件夹）:
  projects/<name>/deliverables/
    final.mp4            成片
    cover.png            设计封面
    发布文案.txt          标题+简介+章节+标签 一份搞定（UTF-8 中文）
    README.md            交付清单 + 后续指引

约定（铁律 G，见 lessons-learned.md）:
  - 成片/封面/文案全部放 deliverables 顶层，不分子文件夹
  - 文案合成一个「发布文案.txt」（标题/简介/章节/标签四段），不拆多个 txt
  - 视频 + 封面 + 文案 + README = 4 件套
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load_disclaimer_block(glossary_path):
    """从 glossary JSON 读取 disclaimer_text 字段，返回拼接后的 disclaimer 段落。

    Returns:
        str | None: 含 2 行中文 disclaimer 的段落（含换行），或 None（不追加）。

    触发条件（tickets #78 / #79）：
      - glossary_path 指向的 JSON 文件存在
      - 文件可被解析为 JSON
      - JSON 含 disclaimer_text 字段（非空字符串）

    标准 2 行格式：
      ⚠️ 本视频仅供科普参考，不构成医疗建议
      如有健康问题，请咨询专业医生

    disclaimer_triggers 字段（11 个医学触发词）也从此 JSON 读取，本脚本
    不直接使用它（用于内容命中检测，本任务只做「字段存在即追加」的简化触发）。
    """
    if not glossary_path:
        return None
    p = Path(glossary_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    text = data.get("disclaimer_text")
    if not isinstance(text, str) or not text.strip():
        return None
    triggers = data.get("disclaimer_triggers", [])
    trigger_count = len(triggers) if isinstance(triggers, list) else 0
    first_line = text.rstrip()
    return f"{first_line}\n如有健康问题，请咨询专业医生", trigger_count


def maybe_append_disclaimer(description, glossary_path):
    """若 glossary 含 disclaimer_text，在 description 末尾追加独立段落（前后各留一空行）。

    向后兼容：glossary_path 为 None / 文件不存在 / 无 disclaimer_text → 返回原 description。
    """
    result = load_disclaimer_block(glossary_path)
    if result is None:
        return description, 0
    block, trigger_count = result
    base = description.rstrip("\n")
    return f"{base}\n\n{block}\n", trigger_count


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the final deliverables folder")
    ap.add_argument("--project", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--chapters", required=True, help="Comma-separated '0:00 标题,...'")
    ap.add_argument("--tags", required=True, help="Comma-separated tags")
    ap.add_argument("--cover", default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--series", default="DSH 插件系统")
    ap.add_argument("--episode", default="第 1 节")
    ap.add_argument("--cost", default="0.00")
    ap.add_argument("--duration", default="")
    ap.add_argument(
        "--glossary",
        default=None,
        help="可选：用户术语表 JSON 路径；含 disclaimer_text 字段时简介文案末尾自动追加健康免责声明段",
    )
    args = ap.parse_args()

    proj = REPO / "projects" / args.project
    dest = proj / "deliverables"
    dest.mkdir(parents=True, exist_ok=True)

    # 1) 视频（顶层）
    video_src = Path(args.video) if args.video else proj / "renders" / "final.mp4"
    if not video_src.exists():
        print(f"ERROR: video not found: {video_src}")
        return 1
    shutil.copy(video_src, dest / "final.mp4")
    print(f"[deliverables] final.mp4 <- {video_src}")

    # 2) 封面（顶层）
    cover_src = Path(args.cover) if args.cover else proj / "renders" / "cover_design.png"
    if not cover_src.exists():
        print(f"WARN: cover not found: {cover_src}（跳过封面）")
    else:
        shutil.copy(cover_src, dest / "cover.png")
        print(f"[deliverables] cover.png <- {cover_src}")

    # 3) 发布文案.txt（一份搞定：标题/简介/章节/标签）
    chapters = [c.strip() for c in args.chapters.split(",") if c.strip()]
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    # 3a) 若 glossary 含 disclaimer_text，在简介末尾追加健康免责声明段
    description_with_disclaimer, _trigger_count = maybe_append_disclaimer(
        args.description, args.glossary
    )
    copy_lines = [
        "【发布文案 · %s】" % args.episode,
        "",
        "━━━ 标题 �━━",
        args.title,
        "",
        "━━━ 简介 ━━━",
        description_with_disclaimer,
        "",
        "━━━ 章节 ━━━",
    ]
    copy_lines += chapters
    copy_lines += ["", "━━━ 标签 ━━━"] + tags
    (dest / "发布文案.txt").write_text("\n".join(copy_lines) + "\n", encoding="utf-8")
    print("[deliverables] 发布文案.txt 已生成（标题/简介/章节/标签 一份搞定）")

    # 4) README.md
    size_mb = round(video_src.stat().st_size / 1048576, 1) if video_src.exists() else 0
    readme = f"""# {args.series} · {args.episode} — 最终交付包

> 本文件夹是**全部最终成品**的集中地，上传 B 站只需从这里取件。
> 项目：`projects/{args.project}` · 成本 ${args.cost}

## 📦 内容清单

| 文件 | 说明 | 用途 |
|---|---|---|
| `final.mp4` | 成片（{args.duration} · {size_mb} MB） | 上传视频本体 |
| `cover.png` | 设计封面（1920x1080，与视频同视觉语言） | B 站封面 |
| `发布文案.txt` | 全部文案：标题 + 简介 + 章节 + 标签（UTF-8 中文） | 标题/简介/章节/标签栏，复制粘贴 |
| `README.md` | 本清单 + 后续指引 | — |

## 📝 定稿文案速览

**标题**：{args.title}

**简介**：{args.description.splitlines()[0] if args.description else ''}

## 🔁 生成方式（后续视频复用）

- 封面：`python bin/make_cover.py --project <name> ...`
- 标题：`python bin/make_title.py --topic ... --claim ...`
- 交付包：`python bin/make_deliverables.py --project <name> ...`
- 流程规范：`skills/pipelines/explainer/publish-director.md` Step 4b/4c + `lessons-learned.md` 铁律 F/G

## ⏭️ 后续

- 上传运营（标题 A/B、封面验收、护持期）走 `bilibili-channel-strategy` skill
"""
    (dest / "README.md").write_text(readme, encoding="utf-8")
    print("[deliverables] README.md 已生成")
    print(f"[deliverables] DONE -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
