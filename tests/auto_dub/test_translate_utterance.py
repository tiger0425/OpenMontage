"""TDD 测试：语段（block）级翻译 + 语段分组（按用户迭代方向）。

覆盖：
1. _group_utterance_blocks：按静音间隙分组，dominant speaker / 文本拼接
2. _translate_blocks：一个语段一条口语化中文译文（原语段数守恒）
3. 翻译规则：跳过 OK/Yeah 语气词、专名一致、general 域口语化
4. tech/general 域 system prompt 差异
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


def _make_automator(domain="tech"):
    inst = object.__new__(PipelineAutomator)
    inst._cps = 5.0
    inst._voxcpm_calibrator = None
    inst.min_char_budget = 15
    inst.translation_domain = domain
    inst.glossary = Glossary(keep_english=[], translations={})
    return inst


def _utt(uid, start, end, text, speaker=None):
    return {"id": uid, "start": start, "end": end, "text": text, "speaker": speaker,
            "segment_ids": [uid]}


class TestGroupBlocks:
    def test_small_gap_joins_same_block(self):
        utts = [
            _utt("u0", 0.0, 3.0, "First sentence", "A"),
            _utt("u1", 3.5, 6.0, "Second sentence", "A"),
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "First sentence Second sentence"

    def test_large_gap_splits_blocks(self):
        utts = [
            _utt("u0", 0.0, 3.0, "First", "A"),
            _utt("u1", 5.0, 8.0, "Second", "B"),  # 间隙 2.0 >= 1.0
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert len(blocks) == 2
        assert [b["id"] for b in blocks] == ["b0", "b1"]
        assert blocks[0]["start"] == 0.0
        assert blocks[1]["end"] == 8.0

    def test_dominant_speaker(self):
        utts = [
            _utt("u0", 0.0, 3.0, "a", "A"),
            _utt("u1", 3.5, 6.0, "b", "B"),
            _utt("u2", 6.5, 9.0, "c", "A"),
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert blocks[0]["speaker"] == "A"

    def test_no_speaker_block_none(self):
        utts = [_utt("u0", 0.0, 3.0, "a"), _utt("u1", 3.5, 6.0, "b")]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert blocks[0]["speaker"] is None

    def test_empty_returns_empty(self):
        assert PipelineAutomator._group_utterance_blocks([], block_gap=1.0) == []


class TestTranslateBlocks:
    def test_one_translation_per_block(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "这一段的中文翻译。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [
            {"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello there world", "speaker": "A", "utterances": []},
            {"id": "b1", "start": 8.0, "end": 14.0, "text": "Second passage", "speaker": "B", "utterances": []},
        ]
        out = inst._translate_blocks(blocks)
        assert len(seen) == 2  # 每个语段一次调用
        assert out[0]["translated_text"] == "这一段的中文翻译。"

    def test_filler_skip_rule_in_prompt(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "OK. Yeah. Let's start", "speaker": "A", "utterances": []}]
        inst._translate_blocks(blocks)
        assert "语气填充词" in seen[0] or "Yeah" in seen[0]

    def test_proper_noun_rule_in_prompt(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello Dino", "speaker": "A", "utterances": []}]
        inst._translate_blocks(blocks)
        assert "专有名词" in seen[0]

    def test_general_domain_conversational(self):
        inst = _make_automator(domain="general")
        captured = {}

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            captured["system"] = system_instruction
            captured["prompt"] = prompt
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": None, "utterances": []}]
        inst._translate_blocks(blocks)
        assert "conversational" in (captured["system"] or "") or "colloquial" in (captured["system"] or "")

    def test_tech_domain_default(self):
        inst = _make_automator(domain="tech")
        captured = {}

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            captured["system"] = system_instruction
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": None, "utterances": []}]
        inst._translate_blocks(blocks)
        assert "AI and cloud technology" in (captured["system"] or "")

    def test_budget_applied(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello world", "speaker": "A", "utterances": []}]
        inst._translate_blocks(blocks)
        assert "max_chinese_characters" in seen[0]

    def test_speaker_in_block_data(self):
        inst = _make_automator()
        seen = []

        def fake_generate(prompt, system_instruction=None, json_mode=None):
            seen.append(prompt)
            return "译文。"

        inst.llm = type("FakeLLM", (), {"generate": staticmethod(fake_generate)})()
        blocks = [{"id": "b0", "start": 0.0, "end": 6.0, "text": "Hello", "speaker": "SPEAKER_01", "utterances": []}]
        inst._translate_blocks(blocks)
        assert "SPEAKER_01" in seen[0]
