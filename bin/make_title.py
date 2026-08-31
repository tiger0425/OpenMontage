#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_title.py — 自动生成 B 站 hook 标题候选（流程化，供 animated-explainer 等管线 publish 阶段调用）

用法:
  python bin/make_title.py --topic "DSH 插件组合模型" \
      --claim "改能力 = 改组合" \
      --duration "3 分钟" \
      --partition "编程" \
      [--file "cordis.yml"] \
      [--surprise "里面是空的"] \
      [--misconception "不是你没配好"] \
      [--why "为什么「改能力」等于「改组合」"]

产出:
  3 个标题候选（反直觉 / 悬念 / 求知）+ 推荐第一个，stdout JSON

调用方（publish director / agent）：
  - 从候选选一个（或让用户挑），作为 export_bundle 的 title
  - 标题候选是基于 hook 公式的骨架，可微调；机制内容须与视频一致
"""
import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Bilibili hook-style title candidates")
    ap.add_argument("--topic", required=True, help="Topic keyword, e.g. DSH 插件组合模型")
    ap.add_argument("--claim", required=True, help="Core conclusion, e.g. 改能力 = 改组合")
    ap.add_argument("--duration", default="3 分钟", help="Duration promise, e.g. 3 分钟")
    ap.add_argument("--partition", default="编程", help="Bilibili partition tag in 【】")
    ap.add_argument("--file", default=None, help="File/mystery object for suspense title, e.g. cordis.yml")
    ap.add_argument("--surprise", default="里面是空的", help="Unexpected thing about the file")
    ap.add_argument("--misconception", default="不是你没配好", help="Common misconception debunked")
    ap.add_argument("--why", default=None, help="Why-question phrasing for knowledge title")
    args = ap.parse_args()

    why = args.why or f"「{args.claim}」"

    candidates = [
        {
            "style": "反直觉钩子（推荐）",
            "title": f"【{args.partition}】{args.claim}，{args.duration}讲透{args.topic}",
        },
        {
            "style": "悬念钩子",
            "title": f"打开{args.file or '配置文件'}，{args.surprise}——{args.misconception}",
        },
        {
            "style": "求知钩子",
            "title": f"{args.topic}：为什么{why}",
        },
    ]

    out = {"candidates": candidates, "recommended": candidates[0]["title"]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
