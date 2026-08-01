"""验证：indextts 模式下 pipeline_automator 顶层不再 import voxcpm_tts。"""
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(OMO_ROOT))
sys.path.insert(0, str(OMO_ROOT / "apps" / "auto-dub"))

# 1. 确认模块源码顶层无 voxcpm_tts 工具 import（voxcpm_speed_calibrator 是测速器，不算）
src = (OMO_ROOT / "apps" / "auto-dub" / "batch" / "pipeline_automator.py").read_text(encoding="utf-8")
header = src.split("class PipelineAutomator")[0]
assert "from tools.audio.voxcpm_tts import" not in header, "顶层仍有 voxcpm_tts import！"
assert "import VoxCPMTTS" not in header, "顶层仍有 VoxCPMTTS import！"
print("OK: pipeline_automator 顶层无 voxcpm_tts 工具 import（懒加载已生效）")

# 2. 确认 import 模块时 voxcpm_tts 未被加载（sys.modules 无记录）
import batch.pipeline_automator  # noqa: F401
assert "tools.audio.voxcpm_tts" not in sys.modules, "voxcpm_tts 被意外提前加载！"
print("OK: import pipeline_automator 未触发 voxcpm_tts 加载")

# 3. 确认 voxcpm_tts 模块仍可正常 import（注册表/其他 pipeline 依赖）
import tools.audio.voxcpm_tts  # noqa: F401
from tools.audio.voxcpm_tts import VoxCPMTTS
assert VoxCPMTTS.name == "voxcpm_tts"
print("OK: voxcpm_tts 工具类仍可用（注册表保留）")
