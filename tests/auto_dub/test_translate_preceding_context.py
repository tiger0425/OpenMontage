"""TDD 测试：翻译前文上下文注入（ticket 03，对标 tachidubb preceding_context）。

覆盖：
1. _build_preceding_context：最近 4 条、600 字符预算封顶、时间序、空列表返回空串
2. _translate_blocks 注入前文：第 2 个语段 prompt 含前文块，第 1 个无
3. 失败重试：LLM 抛异常时去掉前文再试一次
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


def _make_automator():
    inst = object.__new__(PipelineAutomator)
    inst._cps = 5.0
    inst._voxcpm_calibrator = None
    inst.min_char_budget = 15
    inst.translation_domain = "tech"
    # 本测试聚焦前文上下文逻辑，显式关闭漏译检测避免调用次数干扰
    inst.untranslated_check = False
    inst.untranslated_ratio = 0.5

    class _G:
        def build_translation_prompt(self, source_text=None):
            return "GLOSSARY PROMPT"

    inst.glossary = _G()
    return inst


class TestBuildPrecedingContext:
    def test_empty_returns_empty(self):
        inst = _make_automator()
        assert inst._build_preceding_context([]) == ""

    def test_includes_recent_pairs_chronological(self):
        inst = _make_automator()
        translated = [
            {"text": "Hello", "translated_text": "你好"},
            {"text": "World", "translated_text": "世界"},
        ]
        ctx = inst._build_preceding_context(translated)
        assert "Hello  ->  你好" in ctx
        assert "World  ->  世界" in ctx
        # 时间序：Hello 在前
        assert ctx.index("Hello") < ctx.index("World")
        assert "不要重译这些行" in ctx

    def test_only_last_four(self):
        inst = _make_automator()
        translated = [
            {"text": f"S{i}", "translated_text": f"译{i}"} for i in range(6)
        ]
        ctx = inst._build_preceding_context(translated)
        # 只应含 S2..S5（最后 4 条）
        assert "S5" in ctx
        assert "S1" not in ctx

    def test_char_budget_caps_long_pairs(self):
        inst = _make_automator()
        translated = [
            {"text": "x" * 300, "translated_text": "译" * 300},  # 600 chars 已到预算
            {"text": "y" * 300, "translated_text": "译" * 300},  # 超预算 -> 截断
        ]
        ctx = inst._build_preceding_context(translated, char_budget=600)
        # 最近优先：保留 y（最近），截断 x（更早）
        assert "y" * 300 in ctx
        assert "x" * 300 not in ctx

    def test_skips_missing_translation(self):
        inst = _make_automator()
        translated = [
            {"text": "Has no translation"},
            {"text": "OK", "translated_text": "好的"},
        ]
        ctx = inst._build_preceding_context(translated)
        assert "OK  ->  好的" in ctx
        assert "Has no translation" not in ctx


class TestTranslateBlocksPreceding:
    def test_second_block_has_preceding_context(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [
            {"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello Dino", "speaker": "A", "utterances": []},
            {"id": "b1", "start": 8.0, "end": 14.0, "text": "He is here", "speaker": "A", "utterances": []},
        ]
        inst._translate_blocks(blocks)
        assert len(seen) == 2
        # 第 1 个语段无前文；第 2 个有
        assert "前文对话" not in seen[0]
        assert "前文对话" in seen[1]
        assert "Hello Dino" in seen[1]

    def test_retry_without_context_on_failure(self):
        inst = _make_automator()
        calls = []

        def flaky_generate(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            if len(calls) == 1:
                raise RuntimeError("context overflow")
            return "重试成功译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(flaky_generate)})()
        blocks = [
            {"id": "b0", "start": 0.0, "end": 6.0, "text": "First", "speaker": "A", "utterances": []},
            {"id": "b1", "start": 8.0, "end": 14.0, "text": "Second", "speaker": "A", "utterances": []},
        ]
        out = inst._translate_blocks(blocks)
        assert len(calls) == 3  # b0(成功) + b1(失败1) + b1(去前文重试)
        assert out[1]["translated_text"] == "重试成功译文。"

    def test_no_context_first_block_retry_fallback(self):
        inst = _make_automator()
        calls = []

        def always_fail(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            raise RuntimeError("boom")

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(always_fail)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": "A", "utterances": []}]
        out = inst._translate_blocks(blocks)
        # 两次尝试均失败 -> 保留原文
        assert out[0]["translated_text"] == "Hello"
        assert len(calls) == 2
