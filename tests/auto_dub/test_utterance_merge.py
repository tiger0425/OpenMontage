"""TDD 测试：原句（Utterance）合并与说话人继承（ticket 02 / 04）。

覆盖（ADR-003 D1 合并规则）：
1. 相邻碎段（间隙 < 0.5s、无句末标点、不超 15s 上限）合并为一个原句
2. 句末标点（. ! ?）是句子边界，强制开启新原句
3. 间隙 >= merge_gap 时开启新原句
4. 超过 max_seconds 上限不硬并
5. Utterance 的 speaker 取段内多数说话人；无 speaker 时继承相邻原句
6. 合并后 start/end/text/segment_ids 正确
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.analysis.transcriber import assign_utterance_speakers, merge_into_utterances


def _seg(seg_id, start, end, text, speaker=None):
    return {"id": seg_id, "start": start, "end": end, "text": text, "speaker": speaker}


class TestMergeRules:
    def test_adjacent_fragments_merge(self):
        # 三个无标点碎段，间隙 < 0.5s -> 合并为一个原句
        segs = [
            _seg(0, 0.0, 0.8, "That's a"),
            _seg(1, 0.9, 1.6, "great"),
            _seg(2, 1.7, 2.4, "idea"),
        ]
        utts = merge_into_utterances(segs)
        assert len(utts) == 1
        assert utts[0]["text"] == "That's a great idea"
        assert utts[0]["start"] == 0.0
        assert utts[0]["end"] == 2.4
        assert utts[0]["segment_ids"] == [0, 1, 2]

    def test_sentence_punctuation_breaks_merge(self):
        # "idea." 以句号结尾 -> 下一段开启新原句，即使间隙很小
        segs = [
            _seg(0, 0.0, 1.0, "That's an idea."),
            _seg(1, 1.05, 2.0, "It works."),
        ]
        utts = merge_into_utterances(segs, merge_gap=0.5)
        assert len(utts) == 2
        assert utts[0]["text"].endswith(".")
        assert utts[1]["text"].startswith("It")

    def test_large_gap_breaks_merge(self):
        # 间隙 1.2s >= merge_gap 0.5 -> 新原句
        segs = [
            _seg(0, 0.0, 1.0, "Hello"),
            _seg(1, 2.2, 3.0, "world"),
        ]
        utts = merge_into_utterances(segs)
        assert len(utts) == 2

    def test_over_max_seconds_not_force_merged(self):
        # 并入会超过 15s 上限 -> 保持独立原句（不硬并）
        segs = [
            _seg(0, 0.0, 14.0, "long opening"),
            _seg(1, 14.05, 16.0, "continuation"),
        ]
        utts = merge_into_utterances(segs, merge_gap=0.5, max_seconds=15.0)
        assert len(utts) == 2
        assert utts[0]["id"] != utts[1]["id"]

    def test_within_limit_merge_regardless_of_punct_in_middle(self):
        # 中间段无标点，整体 8s，未超上限 -> 合并
        segs = [
            _seg(0, 0.0, 2.0, "part one"),
            _seg(1, 2.05, 5.0, "part two"),
            _seg(2, 5.05, 8.0, "part three"),
        ]
        utts = merge_into_utterances(segs, max_seconds=15.0)
        assert len(utts) == 1

    def test_empty_input_returns_empty(self):
        assert merge_into_utterances([]) == []

    def test_single_segment_returns_one_utterance(self):
        utts = merge_into_utterances([_seg(0, 0.0, 1.0, "hi")])
        assert len(utts) == 1
        assert utts[0]["id"] == "u0"


class TestUtteranceSpeaker:
    def test_majority_speaker_wins(self):
        segs = [
            _seg(0, 0.0, 0.8, "a", speaker="SPEAKER_00"),
            _seg(1, 0.9, 1.6, "b", speaker="SPEAKER_01"),
            _seg(2, 1.7, 2.4, "c", speaker="SPEAKER_00"),
        ]
        utts = merge_into_utterances(segs)
        assert utts[0]["speaker"] == "SPEAKER_00"

    def test_all_none_speaker(self):
        segs = [_seg(0, 0.0, 1.0, "x"), _seg(1, 1.1, 2.0, "y")]
        utts = merge_into_utterances(segs)
        assert utts[0]["speaker"] is None

    def test_inherit_from_previous_utterance(self):
        utts = [
            {"id": "u0", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"id": "u1", "start": 1.5, "end": 2.5, "speaker": None},
            {"id": "u2", "start": 3.0, "end": 4.0, "speaker": "SPEAKER_01"},
        ]
        assign_utterance_speakers(utts)
        assert utts[1]["speaker"] == "SPEAKER_00"

    def test_inherit_backward_for_leading_none(self):
        utts = [
            {"id": "u0", "start": 0.0, "end": 1.0, "speaker": None},
            {"id": "u1", "start": 1.5, "end": 2.5, "speaker": "SPEAKER_01"},
        ]
        assign_utterance_speakers(utts)
        assert utts[0]["speaker"] == "SPEAKER_01"

    def test_all_none_stays_none(self):
        utts = [
            {"id": "u0", "start": 0.0, "end": 1.0, "speaker": None},
            {"id": "u1", "start": 1.5, "end": 2.5, "speaker": None},
        ]
        assign_utterance_speakers(utts)
        assert all(u["speaker"] is None for u in utts)

    def test_short_fragment_absorbed(self):
        # 确定性合并规则（非专门短句吸收）：前段无句末标点时，<1s 碎段按间隙规则并入相邻原句。
        # 若前段以标点结尾，碎段独立成句（D7：无法并入时标记 inherently_long 豁免）。
        segs = [
            _seg(0, 0.0, 3.0, "That is a solid question"),
            _seg(1, 3.05, 3.3, "Yeah."),
            _seg(2, 3.35, 6.0, "Let me walk through it"),
        ]
        utts = merge_into_utterances(segs, merge_gap=0.5)
        # "Yeah." 并入 u0（前一段无句末标点）；"Yeah." 以句号结尾使 u1 从下一句开始
        assert len(utts) == 2
        assert "Yeah." in utts[0]["text"]
        assert utts[1]["text"] == "Let me walk through it"

    def test_short_fragment_after_punctuation_stands_alone(self):
        # 前段以句号结尾时，短碎段独立成原句 → 由下游标记 inherently_long 豁免
        segs = [
            _seg(0, 0.0, 3.0, "That is a solid question."),
            _seg(1, 3.05, 3.3, "Yeah."),
            _seg(2, 3.35, 6.0, "Let me walk through it"),
        ]
        utts = merge_into_utterances(segs, merge_gap=0.5)
        assert any(u["text"] == "Yeah." for u in utts)
        assert len(utts) == 3
