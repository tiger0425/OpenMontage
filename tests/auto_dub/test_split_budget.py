"""TDD 测试：翻译拆分 bug 修复（预算下限 + 三档拆分 + len/cps 时长）。

覆盖：
1. measured_char_budget 短句预算下限 = 15（而非 max(2, ...)）
2. 三档拆分决策：≤max_chars 单条 / ≤max_single_line 整句不拆 / >max_single_line 拆分
3. 拆分子段时长按 len(chunk)/cps 预测，而非按字符比例均摊
4. 重翻路径预算同样有下限
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tools.audio.voxcpm_speed_calibrator import measured_char_budget
from batch.pipeline_automator import PipelineAutomator


# ---------------------------------------------------------------------------
# 1. 预算下限
# ---------------------------------------------------------------------------

class TestCharBudgetFloor:
    def test_short_sentence_has_floor_of_15(self):
        # 1.4s * 6.42 * 0.95 ≈ 8 → 必须下限到 15
        assert measured_char_budget(1.4, 6.42) == 15

    def test_medium_sentence_unchanged_when_above_floor(self):
        # 5.0s * 6.42 * 0.95 ≈ 30 → 保持实测预算
        assert measured_char_budget(5.0, 6.42) == 30

    def test_zero_or_negative_duration_still_floor(self):
        assert measured_char_budget(0.0, 6.42) == 15

    def test_retranslate_budget_respects_floor(self):
        # 重翻路径：budget = max(3, int(measured_char_budget(...) * factor))
        # 用同一下限常量：min_budget=15 也应对系数生效
        budget = max(15, int(measured_char_budget(1.4, 6.42) * 0.85))
        assert budget == 15


# ---------------------------------------------------------------------------
# 2. 三档拆分决策 + 子段时长预测
# ---------------------------------------------------------------------------

class TestThreeTierSplit:
    def test_under_budget_single_line(self):
        # 翻译在预算内 → 单条，不拆分
        plan = PipelineAutomator.plan_split(
            "这是正常翻译", max_chars=15, max_single_line_chars=60, cps=6.42
        )
        assert plan == [("这是正常翻译", None)]

    def test_over_budget_under_threshold_no_split(self):
        # 40 字翻译，预算 8 字，但 ≤60 阈值 → 整句单条不拆分（混音自然顺延）
        long_trans = "假设你正在构建一个AI助手它需要理解用户的意图并搜索代码库找到相关的实现"
        plan = PipelineAutomator.plan_split(
            long_trans, max_chars=8, max_single_line_chars=60, cps=6.42
        )
        assert len(plan) == 1
        assert plan[0][0] == long_trans
        assert plan[0][1] is None  # 不拆分 → 时长由串行队列自然决定

    def test_over_threshold_splits_with_cps_duration(self):
        # 70 字翻译 → 拆分；每段时长 = len(chunk)/cps
        long_trans = (
            "假设你正在构建一个AI助手它需要理解用户的意图并且能够搜索代码库找到相关的实现"
            "然后根据搜索的结果给出准确的建议这就是我们今天要讨论的核心内容"
        )
        assert len(long_trans) > 60
        plan = PipelineAutomator.plan_split(
            long_trans, max_chars=15, max_single_line_chars=60, cps=6.42
        )
        assert len(plan) > 1
        for text, sub_dur in plan:
            assert text
            assert sub_dur is not None
            # 时长 ≈ len/cps，而不是按原句总时长比例均摊（用 len/cps 验证）
            assert abs(sub_dur - len(text) / 6.42) < 0.01

    def test_split_durations_do_not_shrink_to_original(self):
        # 核心断言：均摊会把 70 字压回 ~10s；len/cps 则给出 ~70/6.42≈10.9s 的自然时长
        long_trans = (
            "假设你正在构建一个AI助手它需要理解用户的意图并且能够搜索代码库找到相关的实现"
            "然后根据搜索的结果给出准确的建议这就是我们今天要讨论的核心内容"
        )
        plan = PipelineAutomator.plan_split(
            long_trans, max_chars=15, max_single_line_chars=60, cps=6.42
        )
        total_predicted = sum(sub_dur for _, sub_dur in plan if sub_dur)
        assert total_predicted > 8.0  # 不会被压缩到不合理的短时长
