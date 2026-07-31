"""
术语表管理模块
"""
import re

class Glossary:
    """AI/科技术语表管理器，保证多视频翻译一致性"""
    
    def __init__(self, keep_english: list[str], translations: dict[str, str]):
        self.keep_english = keep_english or []
        self.translations = translations or {}
    
    @classmethod
    def from_config(cls, config: dict) -> 'Glossary':
        """从 config.yaml 的 glossary 部分加载"""
        keep_english = config.get("keep_english", [])
        translations = config.get("translations", {})
        return cls(keep_english=keep_english, translations=translations)
    
    def build_translation_prompt(self) -> str:
        """生成注入到 Gemini 翻译 prompt 中的术语表约束文本"""
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
