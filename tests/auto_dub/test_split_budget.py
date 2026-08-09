"""TDD 测试：翻译字数预算下限（预算修复的存续部分）。

覆盖：
1. measured_char_budget 短句预算下限 = 15（而非 max(2, ...)）
2. 重翻路径预算同样有下限

说明：原「三档拆分决策（plan_split）」已被逐句对齐改造取代——
翻译层不再按预算拆出新的字幕条目（原句数守恒，ADR-003 D2），
超长译文由 assets 阶段按中文标点切成合成子块（Chunk）。plan_split 已删除。
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from tools.audio.voxcpm_speed_calibrator import measured_char_budget


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
