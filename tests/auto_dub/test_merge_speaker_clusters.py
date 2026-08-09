"""TDD 测试：说话人 cluster 合并（tt-test 反馈：pyannote 分裂同一人导致音色差别大）。

覆盖：
1. 相似度 >= 阈值 的两个 cluster 合并为同一 label
2. 相似度低的不合并
3. 少于 2 个 cluster 不处理
4. 异常回退原始 turns
"""

import sys
import numpy as np
import torch
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.analysis.transcriber import Transcriber


class _FakeEmbModel:
    """模拟 speaker embedding 模型：返回与输入时长无关的固定向量。"""

    def __init__(self, vectors):
        self.vectors = vectors  # {speaker_label: np.ndarray}
        self.device = torch.device("cpu")
        self._calls = []

    def __call__(self, clip):
        # clip: (1, 1, T)，无法直接从形状识别 speaker，用时长匹配预先登记的区间
        self._calls.append(clip)
        # 简化：根据调用顺序返回对应向量
        return self.vectors[len(self._calls) - 1]


def _turns(*pairs):
    """构造 speaker_turns。pairs: (start, end, speaker)"""
    return [{"start": s, "end": e, "speaker": spk} for s, e, spk in pairs]


def _make_wav_tensor(duration=100.0):
    return torch.zeros(1, int(duration * 16000))


class TestMergeSpeakerClusters:
    def test_merges_high_similarity_clusters(self):
        # SPEAKER_00 与 SPEAKER_01 高度相似（0.9）-> 合并为 SPEAKER_00
        v0 = np.array([1.0, 0.0])
        v1 = np.array([0.99, 0.1])
        v2 = np.array([0.0, 1.0])  # 与两者都不同
        emb = _FakeEmbModel([v0, v1, v2])

        turns = _turns(
            (0.0, 5.0, "SPEAKER_00"),
            (6.0, 10.0, "SPEAKER_01"),
            (12.0, 16.0, "SPEAKER_02"),
        )
        out = Transcriber._merge_speaker_clusters(
            turns, None, _make_wav_tensor(), emb,
            similarity_threshold=0.7,
        )
        speakers = {t["speaker"] for t in out}
        # SPEAKER_00 与 01 合并，02 独立 -> 2 个 cluster
        assert len(speakers) == 2
        assert "SPEAKER_02" in speakers
        assert any(t["speaker"] == "SPEAKER_00" for t in out if t["start"] >= 6.0)

    def test_low_similarity_not_merged(self):
        v0 = np.array([1.0, 0.0])
        v1 = np.array([0.0, 1.0])
        emb = _FakeEmbModel([v0, v1])
        turns = _turns(
            (0.0, 5.0, "SPEAKER_00"),
            (6.0, 10.0, "SPEAKER_01"),
        )
        out = Transcriber._merge_speaker_clusters(
            turns, None, _make_wav_tensor(), emb, similarity_threshold=0.7,
        )
        assert {t["speaker"] for t in out} == {"SPEAKER_00", "SPEAKER_01"}

    def test_single_cluster_untouched(self):
        emb = _FakeEmbModel([np.array([1.0, 0.0])])
        turns = _turns((0.0, 5.0, "SPEAKER_00"))
        out = Transcriber._merge_speaker_clusters(
            turns, None, _make_wav_tensor(), emb
        )
        assert out == turns

    def test_empty_turns_untouched(self):
        assert Transcriber._merge_speaker_clusters([], None, None, None) == []

    def test_merge_reassigns_all_turns_of_merged_cluster(self):
        # SPEAKER_00 与 01 相似，01 的所有 turn 都应改为 SPEAKER_00
        v0 = np.array([1.0, 0.0])
        v1 = np.array([0.98, 0.05])
        emb = _FakeEmbModel([v0, v1])
        turns = _turns(
            (0.0, 3.0, "SPEAKER_00"),
            (5.0, 7.0, "SPEAKER_01"),
            (9.0, 11.0, "SPEAKER_01"),
        )
        out = Transcriber._merge_speaker_clusters(
            turns, None, _make_wav_tensor(), emb, similarity_threshold=0.6,
        )
        assert all(t["speaker"] == "SPEAKER_00" for t in out)

    def test_exception_falls_back_to_original(self):
        class _BadEmb:
            def __call__(self, clip):
                raise RuntimeError("boom")

        turns = _turns((0.0, 5.0, "SPEAKER_00"), (6.0, 9.0, "SPEAKER_01"))
        out = Transcriber._merge_speaker_clusters(
            turns, None, _make_wav_tensor(), _BadEmb()
        )
        assert out == turns
