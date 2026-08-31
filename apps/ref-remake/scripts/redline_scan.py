# -*- coding: utf-8 -*-
"""ref-remake 改写红线相似度扫描：改写稿 vs 原转录稿。

红线阈值（findings/02 定案，沿用火柴人线）：单句相似度 >=0.75 判红（需改写），
整篇平均 >=0.45 判黄（人工复核）。产出 redline_scan.json 作为脚本闸门必需附件。

用法（workdir 必须在 OpenMontage 根目录）：
    python apps/ref-remake/scripts/redline_scan.py \
        --rewrite projects/<slug>/artifacts/script_cn.md \
        --original projects/<slug>/assets/source/transcript.txt \
        --out projects/<slug>/artifacts/redline_scan.json \
        [--sentence-red 0.75] [--script-yellow 0.45]

算法：中文按标点/句号分句 → 逐句 n-gram 重合率（1-3 gram 加权）+ 可选 LLM 自查
（--llm 时对高分组复核）。无外部依赖，n-gram 用纯 Python。
"""
import os
import re
import sys
import json
import argparse
import math
from collections import Counter

sys.path.insert(0, os.getcwd())


def split_sentences(text: str) -> list[str]:
    """按中文句末标点分句，去空白。"""
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [p.strip() for p in parts if p.strip()]


def ngrams(text: str, n: int) -> list[str]:
    """字符 n-gram（跳过空白）。"""
    chars = re.sub(r"\s+", "", text)
    if len(chars) < n:
        return [chars] if chars else []
    return [chars[i : i + n] for i in range(len(chars) - n + 1)]


def jaccard(a: list, b: list) -> float:
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 0.0


def sentence_similarity(s1: str, s2: str) -> float:
    """1-3 gram Jaccard 加权重合率（1-gram 0.3 / 2-gram 0.3 / 3-gram 0.4）。"""
    if not s1 or not s2:
        return 0.0
    score = 0.0
    for n, w in ((1, 0.3), (2, 0.3), (3, 0.4)):
        score += w * jaccard(ngrams(s1, n), ngrams(s2, n))
    return round(score, 3)


def best_match(s: str, originals: list[str]) -> tuple[float, str]:
    """改写句 vs 每个原句，取最高相似度。"""
    best = (0.0, "")
    for o in originals:
        sim = sentence_similarity(s, o)
        if sim > best[0]:
            best = (sim, o)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rewrite", required=True, help="改写稿路径（中文脚本）")
    ap.add_argument("--original", required=True, help="原转录稿路径（txt）")
    ap.add_argument("--out", required=True, help="redline_scan.json 输出路径")
    ap.add_argument("--sentence-red", type=float, default=0.75)
    ap.add_argument("--script-yellow", type=float, default=0.45)
    ap.add_argument("--llm", action="store_true", help="可选：对高分组做 LLM 复核（预留）")
    args = ap.parse_args()

    with open(args.rewrite, encoding="utf-8") as f:
        rewrite_text = f.read()
    with open(args.original, encoding="utf-8") as f:
        original_text = f.read()

    rewrite_sents = split_sentences(rewrite_text)
    original_sents = split_sentences(original_text)
    if not rewrite_sents:
        print("ERROR: rewrite script has no sentences")
        sys.exit(1)

    scores = []
    for i, s in enumerate(rewrite_sents, 1):
        sim, matched = best_match(s, original_sents)
        verdict = "red" if sim >= args.sentence_red else "ok"
        scores.append({"index": i, "sentence": s[:80], "score": sim, "verdict": verdict, "matched": matched[:80]})

    avg = round(sum(x["score"] for x in scores) / len(scores), 3)
    red_count = sum(1 for x in scores if x["verdict"] == "red")
    if red_count > 0:
        verdict = "red"
    elif avg >= args.script_yellow:
        verdict = "yellow"
    else:
        verdict = "pass"

    scan = {
        "thresholds": {"sentence_red": args.sentence_red, "script_yellow": args.script_yellow},
        "method": "n-gram jaccard (1/2/3-gram weighted 0.3/0.3/0.4) + optional LLM recheck",
        "sentence_scores": scores,
        "script_average": avg,
        "red_sentence_count": red_count,
        "verdict": verdict,
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(scan, f, ensure_ascii=False, indent=2)

    print(f"verdict: {verdict}  (avg={avg}, red_sentences={red_count})")
    print("saved", args.out)
    if verdict != "pass":
        print("RED/YELLOW: 脚本闸门需人工复核后再放行")
        sys.exit(1)


if __name__ == "__main__":
    main()
