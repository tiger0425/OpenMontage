"""TDD 测试：script.schema.json 支持可选 speaker 字段（ticket 03）。

覆盖：
1. 含 speaker 字段的 script.json 通过 schema 校验
2. 缺省（无 speaker）也通过（兼容旧数据）
"""

import json
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

import jsonschema

SCHEMA = json.loads((OMO_ROOT / "schemas" / "artifacts" / "script.schema.json").read_text(encoding="utf-8"))


def _base_script():
    return {
        "version": "1.0",
        "title": "Test",
        "total_duration_seconds": 120.0,
        "narration_language": "zh",
        "paragraph_structure": {
            "mode": "six-act",
            "compressed_to": 3,
            "rationale": "test",
        },
        "sections": [
            {
                "id": "u0",
                "text": "Hello world",
                "paragraph_label": "quick_intro",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "delivery_cues": {"provider_text": "你好世界"},
            }
        ],
        "metadata": {},
    }


class TestSchemaSpeaker:
    def test_speaker_field_passes(self):
        script = _base_script()
        script["sections"][0]["speaker"] = "SPEAKER_00"
        jsonschema.validate(script, SCHEMA)

    def test_no_speaker_field_passes(self):
        jsonschema.validate(_base_script(), SCHEMA)

    def test_speaker_is_string(self):
        script = _base_script()
        script["sections"][0]["speaker"] = 123
        try:
            jsonschema.validate(script, SCHEMA)
            assert False, "speaker 非 string 应校验失败"
        except jsonschema.ValidationError:
            pass

    def test_two_speakers_in_sections_pass(self):
        script = _base_script()
        script["sections"].append(
            {
                "id": "u1",
                "text": "Second",
                "paragraph_label": "main_story",
                "start_seconds": 2.0,
                "end_seconds": 4.0,
                "speaker": "SPEAKER_01",
                "delivery_cues": {"provider_text": "第二个"},
            }
        )
        jsonschema.validate(script, SCHEMA)
