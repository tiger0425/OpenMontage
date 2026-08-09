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

    def test_speaker_change_splits_even_with_small_gap(self):
        # 对话：提问-回答，间隙 < block_gap 但说话人不同 → 必须分开（防独白化）
        utts = [
            _utt("u0", 0.0, 3.0, "Why did you do that?", "A"),
            _utt("u1", 3.3, 6.0, "Because I had to", "B"),
            _utt("u2", 6.3, 9.0, "I see", "A"),
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert len(blocks) == 3
        assert [b["speaker"] for b in blocks] == ["A", "B", "A"]

    def test_same_speaker_continuous_merges(self):
        # 同一说话人连续发言（间隙小）→ 一个语段
        utts = [
            _utt("u0", 0.0, 3.0, "First point", "A"),
            _utt("u1", 3.2, 6.0, "Second point", "A"),
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert len(blocks) == 1
        assert blocks[0]["speaker"] == "A"

    def test_none_speakers_merge_by_gap_only(self):
        # 未分离说话人（diarize off）：按间隙合并（单人视频回归路径）
        utts = [
            _utt("u0", 0.0, 3.0, "a", None),
            _utt("u1", 3.3, 6.0, "b", None),
        ]
        blocks = PipelineAutomator._group_utterance_blocks(utts, block_gap=1.0)
        assert len(blocks) == 1

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


class TestSubtitleDrivenBuckets:
    def test_signature_to_intervals_detects_changes(self):
        # 3 个签名段 → 3 条字幕条
        sigs = ["a"] * 4 + ["b"] * 4 + ["c"] * 4  # 2fps: 0-2s, 2-4s, 4-6s
        iv = PipelineAutomator._signature_to_intervals(sigs, fps=2.0)
        assert iv == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]

    def test_signature_to_intervals_filters_short(self):
        sigs = ["a"] * 4 + ["b"] + ["c"] * 4  # "b" 只 0.5s → 过滤
        iv = PipelineAutomator._signature_to_intervals(sigs, fps=2.0, min_duration=0.6)
        assert iv == [(0.0, 2.0), (2.5, 4.5)]

    def test_empty_signatures(self):
        assert PipelineAutomator._signature_to_intervals([], fps=2.0) == []

    def test_bucket_utterances_by_intervals(self):
        intervals = [(0.0, 3.0), (3.5, 6.5)]
        utts = [
            _utt("u0", 0.2, 2.5, "Q one", "A"),
            _utt("u1", 4.0, 6.0, "A two", "B"),
        ]
        blocks = PipelineAutomator._bucket_utterances_by_intervals(utts, intervals)
        assert len(blocks) == 2
        # 段 start/end 取自字幕条区间，而非原句
        assert blocks[0]["start"] == 0.0
        assert blocks[0]["end"] == 3.0
        assert blocks[1]["start"] == 3.5
        assert blocks[1]["end"] == 6.5

    def test_bucket_skips_empty_interval(self):
        intervals = [(0.0, 2.0), (3.0, 5.0)]
        utts = [_utt("u0", 3.2, 4.8, "only second", "A")]
        blocks = PipelineAutomator._bucket_utterances_by_intervals(utts, intervals)
        assert len(blocks) == 1
        assert blocks[0]["id"] == "b0"


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
