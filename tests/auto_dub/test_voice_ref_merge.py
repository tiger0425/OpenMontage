"""TDD 测试：说话人 voice_ref 合并（tt-test 反馈：pyannote 分裂同一人导致音色差别大）。

覆盖：
1. 相似度 >= 阈值 的两个 ref 合并为同一 label，删除多余 ref 文件
2. 相似度低的不合并
3. 少于 2 个 ref 不处理
4. 异常/embedding 提取失败回退原始 refs
"""

import sys
import numpy as np
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.pipeline_automator import PipelineAutomator


def _make_automator(tmp_path):
    inst = object.__new__(PipelineAutomator)
    inst.assets_dir = Path(tmp_path) / "assets"
    inst.assets_dir.mkdir(parents=True, exist_ok=True)
    return inst


class TestMergeVoiceRefsBySimilarity:
    def test_merges_similar_refs_and_deletes_dup(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        # 两个 ref 文件（A 较大保留，B 被删）
        a = tmp_path / "voice_ref_A.wav"
        b = tmp_path / "voice_ref_B.wav"
        a.write_bytes(b"\x00" * 10000)
        b.write_bytes(b"\x00" * 2000)
        refs = {"A": a, "B": b}

        # mock embedding：A 与 B 高度相似
        va = np.array([1.0, 0.0])
        vb = np.array([0.95, 0.1])
        monkeypatch.setattr(
            inst, "_compute_ref_embeddings", lambda refs: {"A": va, "B": vb}
        )
        out, mm = inst._merge_voice_refs_by_similarity(refs, similarity_threshold=0.7)
        assert set(out) == {"A"}
        assert mm == {"A": "A", "B": "A"}
        assert out["A"] == a  # 保留较大 ref
        assert not b.exists()  # 删除重复 ref

    def test_low_similarity_not_merged(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        a = tmp_path / "voice_ref_A.wav"
        b = tmp_path / "voice_ref_B.wav"
        a.write_bytes(b"\x00" * 10000)
        b.write_bytes(b"\x00" * 2000)
        refs = {"A": a, "B": b}
        va = np.array([1.0, 0.0])
        vb = np.array([0.0, 1.0])  # 正交，相似度 0
        monkeypatch.setattr(
            inst, "_compute_ref_embeddings", lambda refs: {"A": va, "B": vb}
        )
        out, mm = inst._merge_voice_refs_by_similarity(refs, similarity_threshold=0.7)
        assert set(out) == {"A", "B"}
        assert mm == {"A": "A", "B": "B"}  # 无合并时恒等映射
        assert a.exists() and b.exists()

    def test_single_ref_untouched(self, tmp_path):
        inst = _make_automator(tmp_path)
        a = tmp_path / "voice_ref_A.wav"
        a.write_bytes(b"\x00" * 10000)
        out, mm = inst._merge_voice_refs_by_similarity({"A": a})
        assert out == {"A": a}
        assert mm == {}

    def test_embedding_failure_falls_back(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        a = tmp_path / "voice_ref_A.wav"
        b = tmp_path / "voice_ref_B.wav"
        a.write_bytes(b"\x00" * 10000)
        b.write_bytes(b"\x00" * 2000)
        refs = {"A": a, "B": b}
        # embedding 提取失败 -> 返回空，走回退
        monkeypatch.setattr(inst, "_compute_ref_embeddings", lambda refs: {})
        out, mm = inst._merge_voice_refs_by_similarity(refs)
        assert out == refs
        assert mm == {}

    def test_threshold_boundary(self, tmp_path, monkeypatch):
        inst = _make_automator(tmp_path)
        a = tmp_path / "voice_ref_A.wav"
        b = tmp_path / "voice_ref_B.wav"
        a.write_bytes(b"\x00" * 10000)
        b.write_bytes(b"\x00" * 2000)
        refs = {"A": a, "B": b}
        va = np.array([1.0, 0.0])
        vb = np.array([0.71, 0.71])  # 相似度 0.707
        monkeypatch.setattr(
            inst, "_compute_ref_embeddings", lambda refs: {"A": va, "B": vb}
        )
        # 0.707 >= 0.7 合并；> 0.75 不合并
        out1, mm1 = inst._merge_voice_refs_by_similarity(refs, similarity_threshold=0.7)
        assert len(out1) == 1
        assert mm1 == {"A": "A", "B": "A"}
        # 重新写回 B（被删）
        b.write_bytes(b"\x00" * 2000)
        out2, mm2 = inst._merge_voice_refs_by_similarity(refs, similarity_threshold=0.75)
        assert len(out2) == 2
        assert mm2 == {"A": "A", "B": "B"}
