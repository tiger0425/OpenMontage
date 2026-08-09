"""TDD 测试：逐句对齐数学层（ticket 07）。

覆盖：
1. compute_utterance_tempo：预算内返回 atempo 因子，超限返回 None
2. is_inherently_long：物理不可达句判定（原句 < 1s）
3. compute_alignment_metrics：±15% 达标率、碎句率、物理不可达句数（排除统计）
4. 变速目标 = 原句时长 − 排队间隔（由调用方计算后传入 target）
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


class TestComputeUtteranceTempo:
    def test_fits_exactly_returns_one(self):
        # 合成 10s，目标 10s -> factor 1.0
        assert PipelineAutomator.compute_utterance_tempo([10.0], 10.0) == 1.0

    def test_speedup_within_budget(self):
        # 合成 10.3s，目标 10.0s -> 需加速 3%（<=5%），返回 ~1.03
        f = PipelineAutomator.compute_utterance_tempo([10.3], 10.0)
        assert f is not None
        assert abs(f - 1.03) < 0.001

    def test_slowdown_within_budget(self):
        # 合成 9.6s，目标 10.0s -> 需减速到 0.96（>=1/1.05≈0.952），返回 ~0.96
        f = PipelineAutomator.compute_utterance_tempo([9.6], 10.0)
        assert f is not None
        assert abs(f - 0.96) < 0.001

    def test_out_of_budget_too_long_returns_none(self):
        # 合成 12s，目标 10s -> 需加速 20%，超过 ±5% -> None（回退重翻）
        assert PipelineAutomator.compute_utterance_tempo([12.0], 10.0) is None

    def test_out_of_budget_too_short_returns_none(self):
        # 合成 8s，目标 10s -> 需减速 0.8，超过预算 -> None
        assert PipelineAutomator.compute_utterance_tempo([8.0], 10.0) is None

    def test_multiple_chunks_summed(self):
        # 3 个子块合计 10.3s，目标 10s -> 同一因子作用于各子块
        f = PipelineAutomator.compute_utterance_tempo([3.5, 3.4, 3.4], 10.0)
        assert f is not None
        assert abs(f - 1.03) < 0.001

    def test_zero_total_returns_none(self):
        assert PipelineAutomator.compute_utterance_tempo([0.0, 0.0], 10.0) is None

    def test_target_equals_utterance_minus_queue_gap(self):
        # 变速目标 = 原句时长 − 100ms（D4）：6.0s 原句 -> target 5.9s
        target = 6.0 - 0.10
        f = PipelineAutomator.compute_utterance_tempo([6.1], target)
        assert f is not None
        assert abs(f - (6.1 / 5.9)) < 0.001


class TestInherentlyLong:
    def test_short_response_is_inherently_long(self):
        # 0.24s "Yeah." -> 物理不可达
        assert PipelineAutomator.is_inherently_long(0.24) is True

    def test_boundary_1s_is_not_inherently_long(self):
        assert PipelineAutomator.is_inherently_long(1.0) is False

    def test_normal_utterance_not_inherently_long(self):
        assert PipelineAutomator.is_inherently_long(4.0) is False


class TestAlignmentMetrics:
    def test_pass_rate_excludes_inherently_long(self):
        reports = [
            {"target": 10.0, "actual": 10.2, "inherently_long": False},   # 达标
            {"target": 10.0, "actual": 12.0, "inherently_long": False},   # 超 ±15%
            {"target": 0.3, "actual": 1.2, "inherently_long": True},      # 豁免
        ]
        m = PipelineAutomator.compute_alignment_metrics(reports)
        assert m["total_utterances"] == 3
        assert m["inherently_long_count"] == 1
        assert m["pass_rate"] == 0.5  # 排除后 1/2

    def test_all_pass_is_one(self):
        reports = [
            {"target": 5.0, "actual": 5.1, "inherently_long": False},
            {"target": 3.0, "actual": 3.2, "inherently_long": False},
        ]
        m = PipelineAutomator.compute_alignment_metrics(reports)
        assert m["pass_rate"] == 1.0

    def test_clutter_rate_counts_short_subtitles(self):
        # 碎句率：字幕 < 2s 的比例（合并后应为 0）
        reports = [
            {"target": 5.0, "actual": 1.5, "inherently_long": False},   # 碎
            {"target": 5.0, "actual": 5.0, "inherently_long": False},
        ]
        m = PipelineAutomator.compute_alignment_metrics(reports)
        assert m["clutter_rate"] == 0.5

    def test_empty_reports_safe(self):
        m = PipelineAutomator.compute_alignment_metrics([])
        assert m["total_utterances"] == 0
        assert m["pass_rate"] == 1.0
        assert m["clutter_rate"] == 0.0

    def test_single_sentence_deviation_flag(self):
        # 单句最长偏差 < 0.5s 判定（验收 D5）
        reports = [
            {"target": 10.0, "actual": 10.45, "inherently_long": False},  # 偏差 0.45s
            {"target": 10.0, "actual": 10.6, "inherently_long": False},   # 偏差 0.6s
        ]
        m = PipelineAutomator.compute_alignment_metrics(reports, max_deviation_seconds=0.5)
        assert m["max_deviation_seconds"] == 0.6
        assert m["single_sentence_within_limit"] is False
