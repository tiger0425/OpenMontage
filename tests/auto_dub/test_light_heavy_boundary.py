"""长短解耦边界测试：process 必须走轻任务（run_light），绝不允许执行重算力。

防止回归：主 Agent 的 process/run 在代码层面不可能调用 run_pipeline/run_heavy。
"""

import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class TestLightHeavyBoundary:
    def test_process_single_video_calls_run_light_not_run_pipeline(self):
        """_process_single_video(heavy=False) 必须调用 run_light()，绝不调用 run_pipeline()。"""
        from batch import batch_runner
        import inspect
        src = inspect.getsource(batch_runner.BatchRunner._process_single_video)
        # 默认路径（heavy=False）必须走 run_light
        assert "automator.run_light()" in src, "轻任务路径必须调用 run_light()"
        assert "automator.run_heavy()" in src, "heavy=True 路径必须调用 run_heavy()"
        # 代码中不允许出现 run_pipeline 直调（保持边界纯粹）
        assert "automator.run_pipeline()" not in src, "process 路径不允许调用 run_pipeline()"

    def test_run_light_exists_and_heavy_exists(self):
        """PipelineAutomator 同时提供 run_light（轻）与 run_heavy（重）两个入口。"""
        from batch.pipeline_automator import PipelineAutomator
        assert hasattr(PipelineAutomator, "run_light")
        assert hasattr(PipelineAutomator, "run_heavy")

    def test_process_summary_contains_dispatch_commands(self):
        """process 的返回必须包含 next_heavy_commands 派发指引（机器可读）。"""
        from batch import batch_runner
        import inspect
        src = inspect.getsource(batch_runner.BatchRunner.process)
        assert "next_heavy_commands" in src, "process 返回必须含 next_heavy_commands"
        assert "run-heavy" in src, "process 必须打印 run-heavy 派发指引"
