"""TDD 测试：word 级说话人分配 + 跨说话人 segment 切分（tt-test 反馈）。

背景："西尔维，迪诺出轨几次？"（主持人问）+ "四次"（Sylvie 答）在同一个
Whisper segment 里，旧逻辑整句只配一个音色。现在按 word 时间中点归属 speaker_turn，
说话人切换处切分子段。

覆盖：
1. segment 内 words 分属两个 speaker -> 切成两个子段，各自正确 speaker
2. 无说话人切换 -> 保留原 segment
3. 无 words -> segment 级 overlap 兜底
4. word 无 turn 覆盖 -> 继承前一词
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.analysis.transcriber import Transcriber


def _word(w, s, e):
    return {"word": w, "start": s, "end": e, "probability": 1.0}


def _seg_with_words(seg_id, start, end, words):
    return {"id": seg_id, "start": start, "end": end, "text": " ".join(w["word"] for w in words), "words": words}


class TestWordLevelSpeakerSplit:
    def test_host_question_then_answer_splits(self):
        # "西尔维，迪诺出轨几次？四次" 一词到底：前半主持人，后半 Sylvie
        words = [
            _word("So,", 47.3, 47.7),
            _word("Sylvie,", 47.7, 48.3),
            _word("how", 48.3, 48.5),
            _word("many", 48.5, 48.8),
            _word("times", 48.8, 49.1),
            _word("has", 49.1, 49.3),
            _word("Dino", 49.3, 49.6),
            _word("cheated?", 49.6, 50.0),
            _word("Four.", 50.3, 50.7),
        ]
        seg = _seg_with_words(0, 47.3, 50.7, words)
        turns = [
            {"start": 47.6, "end": 50.1, "speaker": "HOST"},
            {"start": 50.2, "end": 51.0, "speaker": "SYLVIE"},
        ]
        out = Transcriber._assign_speakers([seg], turns)
        # 切成 2 段：主持人问句 + Sylvie 回答
        assert len(out) == 2
        spks = [s["speaker"] for s in out]
        assert "HOST" in spks and "SYLVIE" in spks
        # 时间边界正确
        assert out[0]["end"] <= out[1]["start"] + 0.1
        # 文本切分正确
        assert "cheated?" in out[0]["text"]
        assert out[1]["text"].strip() == "Four."

    def test_no_speaker_change_keeps_single(self):
        words = [_word("a", 0.0, 0.5), _word("b", 0.5, 1.0)]
        seg = _seg_with_words(0, 0.0, 1.0, words)
        turns = [{"start": 0.0, "end": 1.0, "speaker": "A"}]
        out = Transcriber._assign_speakers([seg], turns)
        assert len(out) == 1
        assert out[0]["speaker"] == "A"

    def test_no_words_uses_overlap_fallback(self):
        seg = {"id": 0, "start": 0.0, "end": 3.0, "text": "hello", "words": []}
        turns = [{"start": 1.0, "end": 3.0, "speaker": "B"}]
        out = Transcriber._assign_speakers([seg], turns)
        assert out[0]["speaker"] == "B"

    def test_word_no_turn_inherits_previous(self):
        words = [_word("a", 0.0, 0.5), _word("b", 1.5, 2.0)]  # b 无 turn 覆盖
        seg = _seg_with_words(0, 0.0, 2.0, words)
        turns = [{"start": 0.0, "end": 0.6, "speaker": "A"}]
        out = Transcriber._assign_speakers([seg], turns)
        # b 继承 a 的 speaker A -> 整段 A
        assert len(out) == 1
        assert out[0]["speaker"] == "A"

    def test_word_midpoint_picks_shorter_turn(self):
        # 词中点落在两个 turn 重叠区，选更短的 turn
        words = [_word("x", 1.0, 1.2)]
        seg = _seg_with_words(0, 1.0, 1.2, words)
        turns = [
            {"start": 0.5, "end": 1.5, "speaker": "LONG"},
            {"start": 1.1, "end": 1.2, "speaker": "SHORT"},
        ]
        out = Transcriber._assign_speakers([seg], turns)
        assert out[0]["speaker"] == "SHORT"
