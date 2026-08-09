"""
术语表管理模块
"""
import json
import logging
import re
from pathlib import Path


class Glossary:
    """AI/科技术语表管理器，保证多视频翻译一致性

    支持三层：
    1. keep_english / translations（config.yaml 内置，全局恒生效）
    2. domains（config.yaml 内置域词表，按触发词命中注入）
    3. user_glossary.json（用户可编辑，优先级最高，按触发词命中注入）
    """

    def __init__(self, keep_english: list[str], translations: dict[str, str],
                 domains: list[dict] | None = None,
                 user_glossary_path: str | Path | None = None):
        self.keep_english = keep_english or []
        self.translations = translations or {}
        self.domains = domains or []
        self.user_glossary_path = Path(user_glossary_path) if user_glossary_path else None
        self._user_glossary = None

    @classmethod
    def from_config(cls, config: dict) -> 'Glossary':
        """从 config.yaml 的 glossary 部分加载"""
        keep_english = config.get("keep_english", [])
        translations = config.get("translations", {})
        domains = config.get("domains", [])
        user_path = config.get("user_glossary_path")
        return cls(keep_english=keep_english, translations=translations,
                   domains=domains, user_glossary_path=user_path)

    # ---------- 用户词表 ----------
    def _load_user_glossary(self) -> dict:
        """加载用户可编辑术语表（presets/user_glossary.json 格式）。

        缺失/非法 JSON 返回空 dict，不阻断翻译。
        格式: {"domains": [{"name": ..., "triggers": [...], "terms": {...}}]}
        """
        if self._user_glossary is not None:
            return self._user_glossary
        self._user_glossary = {}
        if not self.user_glossary_path:
            return self._user_glossary
        try:
            if not self.user_glossary_path.exists():
                return self._user_glossary
            with open(self.user_glossary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._user_glossary = data if isinstance(data, dict) else {}
        except Exception as e:
            logging.warning(f"[glossary] 加载用户术语表失败: {e}")
            self._user_glossary = {}
        return self._user_glossary

    def _find_domain_terms(self, context: str, target_lang: str = "zh-CN") -> dict:
        """扫描 context 命中触发词，返回本域术语映射（内置 + 用户，用户优先）。"""
        hint = (context or "").lower()
        merged: dict = {}
        # 内置域词表
        for domain in self.domains:
            triggers = [t.lower() for t in domain.get("triggers", [])]
            if triggers and any(t in hint for t in triggers):
                terms = domain.get("terms", {})
                if isinstance(terms, dict):
                    merged.update(terms)
        # 用户词表（覆盖内置）
        user_data = self._load_user_glossary()
        for domain in user_data.get("domains", []):
            triggers = [t.lower() for t in domain.get("triggers", [])]
            if triggers and any(t in hint for t in triggers):
                terms = domain.get("terms", {})
                if isinstance(terms, dict):
                    merged.update(terms)
        return merged

    def build_domain_prompt(self, source_text: str, target_lang: str = "zh-CN") -> str:
        """生成按当前句命中的域术语表约束文本（只注入本句实际出现的词条）。

        保持 prompt 精简：只列出 source_text 中真实出现的术语，聚焦模型注意力。
        """
        merged = self._find_domain_terms(source_text, target_lang)
        if not merged:
            return ""
        lower_src = source_text.lower()
        relevant = {k: v for k, v in merged.items() if k in lower_src}
        if not relevant:
            return ""
        pairs = "\n".join(f"  {k} -> {v}" for k, v in sorted(relevant.items()))
        return (
            "### 域术语表（使用这些精确译文，覆盖上面的一般规则）：\n"
            f"{pairs}\n"
        )

    def build_translation_prompt(self, source_text: str | None = None) -> str:
        """生成注入到 Gemini 翻译 prompt 中的术语表约束文本。

        source_text 提供时，追加按触发词命中的域术语表（只注入本句相关词条）。
        """
        lines = [
            "## 术语表约束（必须严格遵守）",
            ""
        ]

        if self.keep_english:
            lines.append("### 保留英文原文，不要翻译：")
            lines.append(", ".join(self.keep_english))
            lines.append("")

        if self.translations:
            lines.append("### 固定翻译映射：")
            for src, tgt in self.translations.items():
                lines.append(f"- {src} -> {tgt}")
            lines.append("")

        if source_text:
            domain_block = self.build_domain_prompt(source_text)
            if domain_block:
                lines.append(domain_block.strip())
                lines.append("")

        return "\n".join(lines).strip()

    def validate_translation(self, source_text: str, translated_text: str) -> list[str]:
        """
        校验翻译结果是否遵守术语表
        返回违规项列表（空列表=通过）
        """
        violations = []
        # 1. 检查 keep_english 词汇
        for word in self.keep_english:
            pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
            if pattern.search(source_text):
                # 检查译文是否包含原词（不限词首尾边界，以防中文连写导致 \b 失败）
                if not re.search(re.escape(word), translated_text, re.IGNORECASE):
                    violations.append(f"术语 '{word}' 应该保留英文原文")

        # 2. 检查 translations 映射
        for src, tgt in self.translations.items():
            pattern = re.compile(rf'\b{re.escape(src)}\b', re.IGNORECASE)
            if pattern.search(source_text):
                if tgt not in translated_text:
                    violations.append(f"术语 '{src}' 应该翻译为 '{tgt}'")

        return violations

    def get_protected_terms(self) -> list[str]:
        """返回所有不应被翻译的术语（用于注入 brief 的 protected_terms）"""
        return self.keep_english.copy()
