"""TDD 测试：翻译层按原句翻译 + speaker 上下文（ticket 05）。

覆盖：
1. 每条原句得到一条原句级译文（不再逐碎段翻译，也不按标点拆分新条目）
2. 多人视频翻译时单句数据携带 speaker，prompt 注入说话人上下文
3. 原句数守恒：输入 N 条原句 -> 输出 N 条译文
4. 字数预算仍生效（single_data 含 max_chinese_characters）
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.glossary import Glossary
from batch.pipeline_automator import PipelineAutomator


def _make_automator():
    inst = object.__new__(PipelineAutomator)
    inst._cps = 5.0
    inst._voxcpm_calibrator = None
    inst.min_char_budget = 15
    inst.glossary = Glossary(keep_english=[], translations={})
    return inst


class TestTranslateUtterances:
    def test_one_translation_per_utterance(self):
        inst = _make_automator()
        captured = {}

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            captured["prompt"] = prompt
            captured["system"] = system_instruction
            return "这是一个完整的中文译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()

        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello there", "speaker": "A"},
            {"id": "u1", "start": 3.5, "end": 6.0, "text": "How are you", "speaker": "B"},
            {"id": "u2", "start": 6.5, "end": 9.0, "text": "Great thanks", "speaker": "A"},
        ]
        lines = inst._translate_segments(utterances)
        assert lines is not None
        assert len(lines) == 3  # 原句数守恒
        assert [l["line_id"] for l in lines] == ["u0", "u1", "u2"]

    def test_speaker_carried_into_output(self):
        inst = _make_automator()
        inst.llm = type(
            "FakeLLM",
            (),
            {"generate": staticmethod(lambda *a, **k: "译文。")},
        )()
        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "SPEAKER_01"},
            {"id": "u1", "start": 3.5, "end": 6.0, "text": "World", "speaker": None},
        ]
        lines = inst._translate_segments(utterances)
        assert lines[0]["speaker"] == "SPEAKER_01"
        assert lines[1]["speaker"] is None

    def test_speaker_context_injected_into_prompt(self):
        inst = _make_automator()
        seen_prompts = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen_prompts.append(prompt)
            return "这是翻译。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "SPEAKER_01"},
        ]
        inst._translate_segments(utterances)
        assert any("SPEAKER_01" in p for p in seen_prompts)

    def test_budget_still_applied(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello world of ai", "speaker": "A"},
        ]
        inst._translate_segments(utterances)
        assert "max_chinese_characters" in seen[0]

    def test_no_new_entries_from_long_translation(self):
        # 即使译文超长，也保持单条，不产生新字幕条目（原句数守恒，D2）
        inst = _make_automator()
        inst.llm = type(
            "FakeLLM",
            (),
            {"generate": staticmethod(lambda *a, **k: "这是一段特别特别特别特别特别特别特别特别特别特别特别长以至于超过单行阈值的中文译文。")},
        )()
        utterances = [
            {"id": "u0", "start": 0.0, "end": 3.0, "text": "Hello", "speaker": "A"},
        ]
        lines = inst._translate_segments(utterances)
        assert len(lines) == 1
        assert lines[0]["translated_text"].startswith("这是一段")
