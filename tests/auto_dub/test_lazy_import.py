"""验证：indextts 模式下 pipeline_automator 顶层不再 import voxcpm_tts。

sys.modules 断言必须在独立子进程中执行 —— 全量 pytest 中其他测试模块
可能已提前加载 voxcpm_tts，共享进程内断言会误报。
"""

import subprocess
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"


def test_header_has_no_voxcpm_import():
    """pipeline_automator 模块源码顶层无 voxcpm_tts 工具 import（voxcpm_speed_calibrator 是测速器，不算）。"""
    src = (OMO_ROOT / "apps" / "auto-dub" / "batch" / "pipeline_automator.py").read_text(encoding="utf-8")
    header = src.split("class PipelineAutomator")[0]
    assert "from tools.audio.voxcpm_tts import" not in header
    assert "import VoxCPMTTS" not in header


def test_import_does_not_load_voxcpm_in_fresh_process():
    """子进程隔离验证：import pipeline_automator 不触发 voxcpm_tts 加载。"""
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(OMO_ROOT)!r})\n"
        f"sys.path.insert(0, {str(APP_ROOT)!r})\n"
        "import batch.pipeline_automator\n"
        "assert 'tools.audio.voxcpm_tts' not in sys.modules, 'voxcpm_tts 被意外提前加载！'\n"
        "print('OK: 未触发 voxcpm_tts 加载')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"子进程失败: {res.stderr}"


def test_voxcpm_tool_still_registered():
    """voxcpm_tts 工具类仍可正常 import（注册表/其他 pipeline 依赖保留）。"""
    import tools.audio.voxcpm_tts  # noqa: F401
    from tools.audio.voxcpm_tts import VoxCPMTTS
    assert VoxCPMTTS.name == "voxcpm_tts"
