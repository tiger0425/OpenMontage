"""TDD 测试：分段清理链（ticket 01，对标 tachidubb segment_post.py）。

覆盖：
1. 合并续句：同说话人、间隙 <= 0.5s、前段未以句末标点结尾 -> 合并
2. 吸收微段：<1s 且 <40 字符的段并入前段/后段（假说话人翻转产物）
3. 拆超长段：>15s 的段在句子边界就近中位拆分
4. 链式组合：postprocess_segments 依次执行三 pass
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.analysis.transcriber import (
    _absorb_micro_segments,
    _merge_continuation_segments,
    _split_very_long_segments,
    postprocess_segments,
)


def _seg(seg_id, start, end, text, speaker=None, words=None):
    s = {"id": seg_id, "start": start, "end": end, "text": text, "speaker": speaker}
    if words is not None:
        s["words"] = words
    return s


class TestMergeContinuation:
    def test_merge_incomplete_sentence_with_gap(self):
        # 前段无句末标点，间隙 0.3s <= 0.5s，同说话人 -> 合并
        segs = [
            _seg(0, 0.0, 0.8, "That's a", speaker="S0"),
            _seg(1, 1.1, 1.6, "great idea", speaker="S0"),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 1
        assert out[0]["text"] == "That's a great idea"
        assert out[0]["end"] == 1.6

    def test_do_not_merge_finished_sentence(self):
        # 前段以句号结尾且间隙 >= 0.2s -> 不合并
        segs = [
            _seg(0, 0.0, 1.0, "That's an idea.", speaker="S0"),
            _seg(1, 1.3, 2.0, "It works", speaker="S0"),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 2

    def test_merge_tight_gap_even_with_punctuation(self):
        # 间隙 < 0.2s 视为短语中切断 -> 即使前段有标点也合并
        segs = [
            _seg(0, 0.0, 1.0, "who's the most spaz?", speaker="S0"),
            _seg(1, 1.15, 2.0, "Nicky", speaker="S0"),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 1
        assert out[0]["text"] == "who's the most spaz? Nicky"

    def test_do_not_merge_different_speaker(self):
        segs = [
            _seg(0, 0.0, 0.8, "question", speaker="S0"),
            _seg(1, 0.9, 1.6, "answer", speaker="S1"),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 2

    def test_merge_when_speaker_missing_on_one_side(self):
        segs = [
            _seg(0, 0.0, 0.8, "part", speaker="S0"),
            _seg(1, 0.9, 1.6, "two", speaker=None),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 1

    def test_do_not_merge_over_char_limit(self):
        long_text = "x" * 300
        segs = [
            _seg(0, 0.0, 0.8, long_text, speaker="S0"),
            _seg(1, 0.9, 1.6, "tail", speaker="S0"),
        ]
        out = _merge_continuation_segments(segs, 0.5, 15.0, 240)
        assert len(out) == 2


class TestAbsorbMicro:
    def test_absorb_into_previous(self):
        # <1s 且 <40 字符，同说话人、间隙 <1.5s -> 并入前段
        segs = [
            _seg(0, 0.0, 3.0, "That is a solid question", speaker="S0"),
            _seg(1, 3.05, 3.3, "Yeah", speaker="S0"),
            _seg(2, 3.35, 6.0, "Let me walk through it", speaker="S0"),
        ]
        out = _absorb_micro_segments(segs, 1.0, 40)
        assert len(out) == 2
        assert "Yeah" in out[0]["text"]

    def test_absorb_into_next_when_prev_fails(self):
        # 前段间隙太大 -> 并入后段
        segs = [
            _seg(0, 0.0, 3.0, "Longer question segment", speaker="S0"),
            _seg(1, 8.0, 8.3, "Hmm", speaker="S0"),
            _seg(2, 8.4, 11.0, "Next statement", speaker="S0"),
        ]
        out = _absorb_micro_segments(segs, 1.0, 40)
        # 微段并入后段（间隙 0.1 < 1.5），前段保留
        assert len(out) == 2

    def test_micro_with_different_speaker_not_absorbed(self):
        # 微段 (S1) 与前后段 (S0) 说话人均不同 -> 无同说话人可并入，保留独立
        segs = [
            _seg(0, 0.0, 3.0, "question", speaker="S0"),
            _seg(1, 3.05, 3.3, "ok", speaker="S1"),
            _seg(2, 3.35, 6.0, "next", speaker="S0"),
        ]
        out = _absorb_micro_segments(segs, 1.0, 40)
        assert len(out) == 3  # 无同说话人可并入 -> 保留

    def test_long_segment_not_absorbed(self):
        segs = [
            _seg(0, 0.0, 3.0, "question", speaker="S0"),
            _seg(1, 3.05, 6.0, "a much longer phrase than forty characters here", speaker="S0"),
        ]
        out = _absorb_micro_segments(segs, 1.0, 40)
        assert len(out) == 2


class TestSplitLong:
    def test_split_long_at_sentence_boundary(self):
        text = ("First sentence is complete. " * 3).strip() + " Final sentence."
        seg = _seg(0, 0.0, 20.0, text, speaker="S0")
        out = _split_very_long_segments([seg], 15.0)
        assert len(out) == 2
        assert out[0]["end"] <= out[1]["start"] + 1e-6

    def test_no_boundary_keeps_as_is(self):
        seg = _seg(0, 0.0, 20.0, "no punctuation anywhere to split this long run on segment text", speaker="S0")
        out = _split_very_long_segments([seg], 15.0)
        assert len(out) == 1

    def test_short_segment_untouched(self):
        seg = _seg(0, 0.0, 5.0, "Short segment. Fine as is.", speaker="S0")
        out = _split_very_long_segments([seg], 15.0)
        assert len(out) == 1
        assert out[0]["text"] == seg["text"]


class TestPostprocessChain:
    def test_full_chain_reduces_fragment_count(self):
        # 模拟 diarization 输出：碎段 + 微段 + 一个超长段
        segs = [
            _seg(0, 0.0, 0.8, "That's a", speaker="S0"),
            _seg(1, 0.9, 1.6, "great idea", speaker="S0"),
            _seg(2, 1.7, 3.0, "Let me explain.", speaker="S0"),
            _seg(3, 3.05, 3.25, "Yeah", speaker="S1"),
            _seg(4, 3.3, 18.0, "First part is done. Second part continues here. Third part wraps up the idea.", speaker="S1"),
        ]
        out = postprocess_segments(segs)
        # 碎段合并（1）+ 微段吸收（3）+ 超长段拆分（4）
        assert len(out) < len(segs)

    def test_empty_input(self):
        assert postprocess_segments([]) == []
