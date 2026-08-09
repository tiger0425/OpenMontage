"""TDD 测试：域术语表按触发词注入 + 用户词表（ticket 04）。

覆盖：
1. build_translation_prompt(source_text)：命中触发词才注入域术语
2. 只注入 source_text 实际出现的词条（聚焦注意力）
3. 用户词表覆盖内置词表（优先级）
4. user_glossary.json 缺失/非法不阻断（仅内置词表）
5. 不传 source_text 时兼容旧行为（仅全局词表）
"""

import json
import sys
from pathlib import Path

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = OMO_ROOT / "apps" / "auto-dub"
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from batch.glossary import Glossary


DOMAINS = [
    {
        "name": "tech",
        "triggers": ["GPU", "model", "token"],
        "terms": {"fine-tuning": "微调", "token": "token", "dataset": "数据集"},
    },
    {
        "name": "interview",
        "triggers": ["relationship", "affair"],
        "terms": {"four times": "四次", "affair": "婚外情"},
    },
]


class TestDomainInjection:
    def test_trigger_hit_injects_terms(self):
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS)
        prompt = g.build_translation_prompt(source_text="GPU model fine-tuning is costly")
        assert "域术语表" in prompt
        assert "fine-tuning -> 微调" in prompt

    def test_no_trigger_no_domain_block(self):
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS)
        prompt = g.build_translation_prompt(source_text="Hello how are you")
        assert "域术语表" not in prompt

    def test_only_relevant_terms_injected(self):
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS)
        # 含触发词 "model"，但文本只出现 "dataset"，不含 "fine-tuning" -> 只注入 dataset
        prompt = g.build_translation_prompt(source_text="the model uses a large dataset")
        assert "dataset -> 数据集" in prompt
        assert "fine-tuning" not in prompt

    def test_global_terms_always_included(self):
        g = Glossary(keep_english=["GPU"], translations={"inference": "推理"}, domains=DOMAINS)
        prompt = g.build_translation_prompt(source_text="GPU inference")
        assert "保留英文原文" in prompt
        assert "GPU" in prompt
        assert "inference -> 推理" in prompt


class TestUserGlossary:
    def test_user_overrides_builtin(self, tmp_path):
        user_file = tmp_path / "user_glossary.json"
        user_file.write_text(json.dumps({
            "domains": [{
                "name": "tech",
                "triggers": ["GPU", "model"],
                "terms": {"fine-tuning": "自定义微调"},
            }]
        }), encoding="utf-8")
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS,
                     user_glossary_path=user_file)
        prompt = g.build_translation_prompt(source_text="GPU model fine-tuning")
        # 用户覆盖内置
        assert "fine-tuning -> 自定义微调" in prompt
        assert "fine-tuning -> 微调" not in prompt

    def test_missing_user_file_ok(self, tmp_path):
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS,
                     user_glossary_path=tmp_path / "nonexistent.json")
        prompt = g.build_translation_prompt(source_text="GPU model fine-tuning")
        assert "fine-tuning -> 微调" in prompt  # 内置仍生效

    def test_invalid_user_file_ok(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS,
                     user_glossary_path=bad)
        prompt = g.build_translation_prompt(source_text="GPU model fine-tuning")
        assert "fine-tuning -> 微调" in prompt  # 内置仍生效

    def test_no_user_path_ok(self):
        g = Glossary(keep_english=[], translations={}, domains=DOMAINS)
        prompt = g.build_translation_prompt(source_text="GPU model fine-tuning")
        assert "fine-tuning -> 微调" in prompt


class TestBackwardCompat:
    def test_no_source_text_still_builds_global_prompt(self):
        g = Glossary(keep_english=["GPU"], translations={"inference": "推理"}, domains=DOMAINS)
        prompt = g.build_translation_prompt()
        assert "保留英文原文" in prompt
        assert "inference -> 推理" in prompt
        assert "域术语表" not in prompt  # 无 source 不注入域词表

    def test_validate_translation_unchanged(self):
        g = Glossary(keep_english=["GPU"], translations={"inference": "推理"}, domains=DOMAINS)
        assert g.validate_translation("GPU inference", "GPU 推理") == []
        assert g.validate_translation("GPU inference", "图形处理器 推理") != []
