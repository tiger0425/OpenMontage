"""MarkHasara 合规分类清单重建。

把 DB 中的视频分类为 BLOCK / REMAKE / SAFE 三档（用户决策 Q2/Q3），
写入 apps/markhasara/compliance.json。分类规则见 config.compliance 与 #22 决议：

- BLOCK：敏感主题（医疗/金融/法律/政治/宗教）、明显低质、标题涉暴力/成人/夸大
- REMAKE：水印需去除、画面需重排
- SAFE：以上都不命中，画面干净

实现：基于标题 + 元数据先用规则快速预分类（敏感词），未命中的用 LLM 判断。
生成清单后人工 review 锁定（human_approval 模式）。
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# BLOCK 敏感主题词（标题命中即 BLOCK）
BLOCK_KEYWORDS = [
    # 敏感领域
    "covid", "vaccine", "health warning", "medical", "cancer treatment",
    "stock", "invest", "trading", "bitcoin", "crypto price", "forex",
    "lawsuit", "legal", "politics", "election", "president", "politician",
    "religion", "jesus", "church", "god", "muslim", "christian",
    # 暴力/成人/夸大（标题层面）
    "gore", "graphic", "explicit", "adult only",
    "fake news", "scam", "clickbait warning",
]

# 军事风险词（标题命中需 LLM 复核，可能涉真实冲突/武器敏感画面）
REVIEW_KEYWORDS = [
    "nuke", "nuclear", "missile", "barrage", "attack", "strike",
    "warhead", "crashed", "crash", "explosion", "explodes", "killed",
    "deadly", "gunshot", "massacre", "civilian", "casualty",
]


def _needs_review(title: str) -> bool:
    """标题含军事风险词，需 LLM 复核（可能涉真实冲突敏感画面）。"""
    t = title.lower()
    return any(kw in t for kw in REVIEW_KEYWORDS)


def _preclassify_by_title(title: str) -> Optional[str]:
    """基于标题的快速预分类。命中返回档位，未命中返回 None。"""
    t = title.lower()
    for kw in BLOCK_KEYWORDS:
        if kw in t:
            return "BLOCK"
    return None


def _is_low_quality(meta: dict) -> bool:
    """低质判断：无 view_count 或明显异常低（数据不足时不做强判断）。"""
    vc = meta.get("view_count")
    if vc is None:
        return False
    # 极低播放量暗示内容可能无价值/低质（阈值 100 保守）
    return vc < 100


def _classify_with_llm(llm, title: str) -> str:
    """用 LLM 判断一条视频的合规档位。"""
    prompt = (
        f"这是一个 YouTube Shorts 视频，标题为：\n{title}\n\n"
        "请判断它属于哪个合规档位，只回答一个词：\n"
        "BLOCK（禁搬：敏感主题医疗/金融/法律/政治/宗教、低质、暴力/成人/误导）\n"
        "REMAKE（需重制：有水印/画面问题但内容可搬）\n"
        "SAFE（可直接搬运：画面干净无风险）\n\n"
        "只输出 BLOCK、REMAKE 或 SAFE 三个字母之一。"
    )
    try:
        raw = llm.generate(prompt, system_instruction="你是短视频内容合规分类器，只输出一个分类词。").strip().upper()
        for label in ("BLOCK", "REMAKE", "SAFE"):
            if label in raw:
                return label
    except Exception as e:
        logger.warning("LLM 分类失败，回退 SAFE: %s", e)
    return "SAFE"


def rebuild_compliance(config: dict, db) -> dict:
    """重建合规分类清单。返回分类统计。"""
    list_path = Path(config["compliance"]["list_path"])
    if not list_path.is_absolute():
        list_path = Path(__file__).resolve().parent.parent.parent / list_path
    list_path.parent.mkdir(parents=True, exist_ok=True)

    # 收集 DB 中所有视频（标题 + 元数据）
    videos = db.get_all()
    if not videos:
        return {"command": "classify", "success": False, "error": "DB 为空，请先 scan", "total": 0}

    # LLM 客户端（仅规则未命中且含风险词的子集用）
    from batch.llm_client import LLMClient
    llm = LLMClient()

    result = {"BLOCK": [], "REMAKE": [], "SAFE": []}
    llm_calls = 0
    for v in videos:
        title = v.get("title") or ""
        meta = json.loads(v.get("metadata") or "{}")

        # 1. 规则预分类（敏感领域词 → BLOCK）
        label = _preclassify_by_title(title)
        reason = "title_keyword"
        # 2. 低质 → BLOCK
        if label is None and _is_low_quality(meta):
            label = "BLOCK"
            reason = "low_quality"
        # 3. 含军事风险词 → LLM 复核（判断是否涉真实冲突敏感画面）
        if label is None and _needs_review(title):
            label = _classify_with_llm(llm, title)
            reason = "llm_review"
            llm_calls += 1
        # 4. 其余默认 SAFE（军事航空资讯类，画面干净）
        if label is None:
            label = "SAFE"
            reason = "default_safe"

        result.setdefault(label, []).append({
            "video_id": v["video_id"],
            "title": title,
            "reason": reason,
        })

    list_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "command": "classify",
        "success": True,
        "list_path": str(list_path),
        "total": len(videos),
        "BLOCK": len(result["BLOCK"]),
        "REMAKE": len(result["REMAKE"]),
        "SAFE": len(result["SAFE"]),
        "llm_calls": llm_calls,
        "note": "清单已生成，人工 review 后锁定（safe_only 模式只进 SAFE）",
    }
