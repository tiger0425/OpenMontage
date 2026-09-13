# -*- coding: utf-8 -*-
"""ErChuang 文案与剧作规范质检器 (Validator)

用于检验 manifest.json 中的 chunks 是否满足 apps/erchuang/specs/STORYTELLING.md
的 2秒黄金开篇、五步张力、深入分析下潜与未闭合悬念要求。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ScriptValidationReport:
    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [f"=== ErChuang 文案质检报告: {Path(self.manifest_path).name} ==="]
        lines.append(f"结果: {'[通过 PASS]' if self.is_valid else '[未通过 FAIL]'}")
        if self.errors:
            lines.append(f"\n[阻断性硬伤 ERRORS ({len(self.errors)})]:")
            for e in self.errors:
                lines.append(f"  [X] {e}")
        if self.warnings:
            lines.append(f"\n[改进建议 WARNINGS ({len(self.warnings)})]:")
            for w in self.warnings:
                lines.append(f"  [!] {w}")
        if self.passed:
            lines.append(f"\n[合格项目 PASSED ({len(self.passed)})]:")
            for p in self.passed:
                lines.append(f"  [OK] {p}")
        return "\n".join(lines)



def validate_manifest_script(manifest_data: dict[str, Any], manifest_path: str = "") -> ScriptValidationReport:
    report = ScriptValidationReport(manifest_path)
    chunks = manifest_data.get("chunks", [])

    if not chunks:
        report.errors.append("manifest 中未包含任何 chunks")
        return report

    # 1. 黄金 2 秒开篇检测 (Chunk 0)
    c0 = chunks[0]
    t0 = c0.get("text", "").strip()

    # 1.1 禁忌词检查
    banned_starters = ["IMSA", "WSC", "Group C", "LMGT1", "GTP"]
    for b in banned_starters:
        if t0.startswith(b) or f" {b}" in t0[:15]:
            report.errors.append(f"开篇 2 秒使用了圈内黑话/赛事缩写 '{b}'（违背 0~2s 降低认知门槛铁律）")

    time_starters = ["一九", "19", "二〇", "20", "上世纪", "八十年代", "九十年代"]
    for ts in time_starters:
        if t0.startswith(ts):
            report.errors.append(f"开篇 2 秒使用了年份/时代词 '{ts}' 起手（流水账纪录片式开头，极易导致高跳出）")

    # 1.2 报菜名检测
    champion_matches = re.findall(r"冠军", t0[:30])
    if len(champion_matches) >= 2:
        report.errors.append("开篇前 30 字包含多个'冠军'头衔陈列（报菜名式叙事，缺乏剧情张力）")

    # 1.3 提前报车名自毁悬念检测
    if re.search(r"叫[A-Za-z0-9一-龥]{2,8}。$", t0) or "这台车叫" in t0 or "就是保时捷" in t0[:20]:
        report.warnings.append("开篇过早揭晓车名，可能削弱观众对后续谜底的探索欲（建议将大悬念贯穿至中后段）")

    # 1.4 爆点模型特征识别
    shock_keywords = [
        # 模型 A: 荒谬漏洞
        "假装", "后备箱", "真皮座椅", "买菜车", "漏洞", "空子", "荒谬", "笑话", "合法上街",
        # 模型 B: 极限代价
        "肋骨", "震断", "易耗品", "解体", "噩梦", "极限", "锁死", "重击", "病态", "疯子",
        # 模型 C: 降维打击
        "四缸", "小排量", "小卡车", "全干趴", "取消", "摩擦", "颠覆", "掀了", "打趴"
    ]
    matched_shock = [k for k in shock_keywords if k in t0]
    if matched_shock:
        report.passed.append(f"开篇包含高张力认知冲突词汇: {', '.join(matched_shock)}")
    else:
        report.warnings.append("开篇未检测到明显的反常识矛盾词汇（荒谬漏洞/生理绝境/降维反杀），可能偏向平淡描述")

    # 2. 篇幅结构与戏剧张力
    total_text = "".join(c.get("text", "") for c in chunks)

    # 检查转折词与冲突词密度
    conflict_words = ["可", "但", "没想到", "谁都没想到", "荒唐", "死局", "代价", "危机", "故障", "断裂", "反转", "崩溃", "算盘"]
    matched_conflicts = [w for w in conflict_words if w in total_text]
    if len(matched_conflicts) >= 4:
        report.passed.append(f"全片剧情张力词汇充足 ({len(matched_conflicts)} 处冲突标记)")
    else:
        report.warnings.append("全片缺乏足够的冲突与转折词汇（但/可/没想到/代价），叙事可能过于顺遂平铺")

    # 3. 单句长度与 TTS 易读性
    long_sentence_count = 0
    raw_year_digits = []
    symbol_issues = []

    for idx, c in enumerate(chunks):
        t = c.get("text", "")
        # 按逗号句号分句
        subs = re.split(r"[，。！？；]", t)
        for s in subs:
            s_clean = s.strip()
            if len(s_clean) > 28:
                long_sentence_count += 1

        # 检查未汉化的4位年份（如 1994、1982）
        year_matches = re.findall(r"\b(19\d\d|20\d\d)\b", t)
        if year_matches:
            raw_year_digits.extend(year_matches)

        # 检查口播不友好符号
        if "——" in t or "--" in t:
            symbol_issues.append(f"Chunk {idx} 包含破折号 '——'")
        if "**" in t:
            symbol_issues.append(f"Chunk {idx} 包含 Markdown 加粗 '**'")

    if long_sentence_count == 0:
        report.passed.append("所有分句均控制在 28 字以内，呼吸感良好")
    else:
        report.warnings.append(f"存在 {long_sentence_count} 处超过 28 字的长分句，建议拆分为短句以保证口播紧凑感")

    if raw_year_digits:
        report.errors.append(f"发现阿拉伯数字年份: {set(raw_year_digits)}。TTS 会误读为数词，必须改为汉字年份（如'一九九四年'）")
    else:
        report.passed.append("所有年份均规范使用汉字读法")

    if symbol_issues:
        report.errors.append(f"发现不适宜口播的符号: {', '.join(symbol_issues[:3])}")

    # 4. 结尾争议与互动检测 (Chunk -1)
    c_last = chunks[-1]
    t_last = c_last.get("text", "")
    interactive_keywords = ["聊", "你怎么看", "评论区", "关注", "你觉得", "到底", "值不值", "争议"]
    matched_interact = [k for k in interactive_keywords if k in t_last]
    if matched_interact:
        report.passed.append(f"结尾具备互动争议引导: {', '.join(matched_interact)}")
    else:
        report.warnings.append("结尾未检测到鲜明的评论区互动钩子或反思问题（建议强化留存争议）")

    return report
