"""TDD 测试：漏译/未翻译检测 + 单条重译（ticket 05）。

覆盖：
1. _looks_untranslated：英文残留占比高判漏译；中文译文不误判；短句不误判
2. _translate_blocks 触发重译：返回纯中文时用重译结果；重译仍英文保留原译文
3. untranslated_check=False 关闭检测
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


def _make_automator(untranslated_check=True):
    inst = object.__new__(PipelineAutomator)
    inst._cps = 5.0
    inst._voxcpm_calibrator = None
    inst.min_char_budget = 15
    inst.translation_domain = "tech"
    inst.untranslated_check = untranslated_check
    inst.untranslated_ratio = 0.5

    class _G:
        def build_translation_prompt(self, source_text=None):
            return "GLOSSARY PROMPT"

    inst.glossary = _G()
    return inst


class TestLooksUntranslated:
    def test_english_leftover_detected(self):
        assert PipelineAutomator._looks_untranslated(
            "This is still English sentence left over"
        )

    def test_clean_chinese_not_detected(self):
        assert not PipelineAutomator._looks_untranslated("这是完整的中文翻译，没有英文残留")

    def test_mixed_terms_not_detected(self):
        # GPU/API 等少量术语 + 中文主体，CJK 占比仍高 -> 不算漏译
        assert not PipelineAutomator._looks_untranslated("这个 GPU 适合做模型推理 API 调用")

    def test_short_text_not_flagged(self):
        # "OK" 单字回应不算漏译（太短无法判断）
        assert not PipelineAutomator._looks_untranslated("OK")

    def test_threshold_configurable(self):
        # 半英半中文本 CJK 占比 ~0.2：threshold 0.1 判漏译，threshold 0.5 也判漏译
        assert PipelineAutomator._looks_untranslated(
            "half English half Chinese mixed text", cjk_ratio_threshold=0.5
        )
        # 中文主体 + 术语，CJK 占比 ~0.65：threshold 0.5 通过，threshold 0.8 判漏译
        assert not PipelineAutomator._looks_untranslated(
            "这个 GPU 适合做模型推理 API 调用", cjk_ratio_threshold=0.5
        )
        assert PipelineAutomator._looks_untranslated(
            "这个 GPU 适合做模型推理 API 调用", cjk_ratio_threshold=0.8
        )


class TestRetranslateOnUntranslated:
    def test_untranslated_triggers_retranslate(self):
        inst = _make_automator()
        calls = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            # 第一次返回英文残留，第二次（重译）返回中文
            if len(calls) == 1:
                return "This is the English translation not done"
            return "这是完整的中文翻译。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello world this is a test", "speaker": "A", "utterances": []}]
        out = inst._translate_blocks(blocks)
        assert len(calls) == 2  # 初译 + 重译
        assert out[0]["translated_text"] == "这是完整的中文翻译。"

    def test_retranslate_still_english_keeps_original(self):
        inst = _make_automator()
        calls = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            return "Still English again"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello there", "speaker": "A", "utterances": []}]
        out = inst._translate_blocks(blocks)
        # 初译(英文) + 重译(仍英文) -> 保留初译文（日志警告，不阻断）
        assert len(calls) == 2
        assert out[0]["translated_text"] == "Still English again"

    def test_clean_translation_no_retranslate(self):
        inst = _make_automator()
        calls = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            return "这是干净的中文翻译。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": "A", "utterances": []}]
        out = inst._translate_blocks(blocks)
        assert len(calls) == 1  # 只初译，无重译
        assert out[0]["translated_text"] == "这是干净的中文翻译。"

    def test_check_disabled_no_retranslate(self):
        inst = _make_automator(untranslated_check=False)
        calls = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            calls.append(prompt)
            return "This is English but check is off"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": "A", "utterances": []}]
        out = inst._translate_blocks(blocks)
        assert len(calls) == 1  # 关闭检测不重译
        assert out[0]["translated_text"] == "This is English but check is off"
