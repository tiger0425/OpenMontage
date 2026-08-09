"""TDD 测试：翻译字数预算短句缩放下限（tt-test 反馈修复）。

背景：固定 min_budget=15 会让 1-2s 短句被逼出 15 字译文，IndexTTS 合成远超
原句时长，靠变速/溢出推挤救不回，听感"没说完被截断"。_char_budget_for 改为
短句下限随时长缩放（min(15, max(2, dur*4))），长句保持实测预算。

覆盖：
1. 短句（<4s）预算随时长缩放，不被 15 下限顶高
2. 长句预算 = 实测预算（min=15 不干扰）
3. 与 _budget_cps 打折配合，译文更贴合原句
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.pipeline_automator import PipelineAutomator


def _make_automator(min_char_budget=15, cps_safety_factor=0.7, cps=5.8):
    inst = object.__new__(PipelineAutomator)
    inst.min_char_budget = min_char_budget
    inst.cps_safety_factor = cps_safety_factor
    inst._budget_cps = lambda: cps * cps_safety_factor
    return inst


class TestLengthRule:
    def test_short_sentence_hard_constraint(self):
        inst = _make_automator()
        rule = inst._build_length_rule(1.5, 5, 4.1)
        assert "硬约束" in rule
        assert "超时会被截断" in rule or "会被截断" in rule
        assert "宁短勿长" in rule

    def test_long_sentence_fill_directive(self):
        inst = _make_automator()
        rule = inst._build_length_rule(6.0, 25, 4.1)
        assert "硬约束" not in rule
        assert "填满" in rule or "完整覆盖" in rule


class TestCharBudgetFor:
    def test_short_sentence_floor_scales(self):
        inst = _make_automator()
        # 1.2s：floor=3，实测 int(1.2*4.06*0.95)=4 → 取 max = 4（远低于旧 15）
        assert inst._char_budget_for(1.2) == 4
        # 2.1s：floor=6，实测 int(2.1*4.06*0.95)=8 → 取 max = 8
        assert inst._char_budget_for(2.1) == 8

    def test_medium_sentence_uses_measured_budget(self):
        inst = _make_automator()
        # 5.4s * 5.8 * 0.7 * 0.95 ≈ 20.8 → 20（未达 15 下限干扰，floor=min(15, 5.4*3.2=17)=15）
        assert inst._char_budget_for(5.4) == 20

    def test_long_sentence_keeps_measured_budget(self):
        inst = _make_automator()
        # 9.3s * 4.06 * 0.95 ≈ 35.9 → 35
        assert inst._char_budget_for(9.3) == 35

    def test_very_short_floor_min_2(self):
        inst = _make_automator()
        # 0.1s：floor = max(2, 0.32) = 2，预算 = 2（保证 LLM 能输出）
        assert inst._char_budget_for(0.1) == 2

    def test_budget_cps_discount_applied(self):
        inst = _make_automator(cps_safety_factor=1.0)
        # 无打折：5.4s * 5.8 * 0.95 ≈ 29.8 → 29；打折 0.7 时 20
        assert inst._char_budget_for(5.4) == 29

    def test_translate_uses_scaled_budget(self):
        """集成：_translate_utterances 对短句用缩放下限预算。"""
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "短译。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        inst.translation_domain = "tech"
        inst.untranslated_check = False
        inst._get_cps = lambda: 5.8
        inst._build_translation_system_prompt = lambda: "system"
        inst._build_translation_rules = lambda spk=None: ["rule"]
        inst._build_preceding_context = lambda translated: ""

        class _G:
            def build_translation_prompt(self, source_text=None):
                return "GLOSSARY"

        inst.glossary = _G()
        utterances = [{
            "id": "u0", "start": 0.0, "end": 1.2, "text": "Short question",
            "speaker": "A",
        }]
        out = inst._translate_utterances(utterances)
        # prompt 中 max_chinese_characters 应为 4（短句缩放），而非 15
        assert '"max_chinese_characters": 4' in seen[0]
