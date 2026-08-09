"""TDD 测试：全局调速退为末段兜底（ticket 07）。

覆盖：
1. _should_apply_global_atempo：小漂移不触发、预算内不触发、超预算才触发、超失败阈值不触发
2. 配置默认：drift_budget=1.5、max_drift=5.0
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


class TestShouldApplyGlobalAtempo:
    def test_no_drift_no_atempo(self):
        assert not PipelineAutomator._should_apply_global_atempo(0.0)

    def test_small_drift_within_budget_not_applied(self):
        # 漂移 0.8s <= 预算 1.5s -> 由逐句对齐吸收，不触发全局 atempo
        assert not PipelineAutomator._should_apply_global_atempo(0.8, drift_budget=1.5)

    def test_drift_over_budget_applied(self):
        # 漂移 2.0s > 预算 1.5s，且 <= max_drift 5.0 -> 末段兜底
        assert PipelineAutomator._should_apply_global_atempo(2.0, drift_budget=1.5, max_drift=5.0)

    def test_drift_over_max_not_applied(self):
        # 漂移 6.0s > max_drift 5.0 -> 超出失败阈值，不兜底（走缩短重翻/失败）
        assert not PipelineAutomator._should_apply_global_atempo(6.0, drift_budget=1.5, max_drift=5.0)

    def test_default_budget(self):
        # 默认 drift_budget=1.5：1.4 不触发，1.6 触发
        assert not PipelineAutomator._should_apply_global_atempo(1.4)
        assert PipelineAutomator._should_apply_global_atempo(1.6)

    def test_exact_budget_not_applied(self):
        # 漂移 == 预算：边界视为"吸收范围内"
        assert not PipelineAutomator._should_apply_global_atempo(1.5, drift_budget=1.5)

    def test_exact_max_applied(self):
        # 漂移 == max_drift：仍触发末段兜底
        assert PipelineAutomator._should_apply_global_atempo(5.0, drift_budget=1.5, max_drift=5.0)
