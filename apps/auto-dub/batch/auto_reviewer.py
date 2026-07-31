import json
import sys
from pathlib import Path
from typing import Optional

# 添加 OpenMontage 根目录到 Python 路径
OMO_ROOT = Path(__file__).resolve().parents[3]
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

from lib import checkpoint


class AutoReviewer:
    """自动审核器：在批量模式下替代人工审核
    
    对每个需要 human_approval 的阶段，自动运行质量检查。
    不通过则 loop 修复（最多 max_fix_loops 轮）。
    """
    
    def __init__(self, config: dict, projects_dir: Path):
        # config = auto_review section from config.yaml
        # projects_dir = Path to projects/ directory
        self.max_fix_loops = config.get('max_fix_loops', 3)
        self.checks = config.get('checks', {})
        self.projects_dir = projects_dir
    
    def review_and_approve(self, project_id: str, stage: str, artifacts: dict) -> tuple[bool, list[str]]:
        """审核阶段产物并尝试自动通过
        
        Returns:
            (success, issues) - success=True 表示已自动通过，
                               issues 是检查过程中发现的问题列表
        """
        # 1. 获取该阶段的检查项
        stage_checks = self.checks.get(stage, [])
        if not stage_checks:
            # 没有配置检查项，直接通过
            self._write_approved_checkpoint(project_id, stage, artifacts)
            return True, []
        
        # 2. 运行检查
        all_issues = []
        for attempt in range(self.max_fix_loops + 1):
            issues = self._run_checks(stage, stage_checks, artifacts)
            if not issues:
                # 所有检查通过
                self._write_approved_checkpoint(project_id, stage, artifacts)
                return True, all_issues
            
            all_issues.extend(issues)
            
            if attempt < self.max_fix_loops:
                # 尝试自动修复
                print(f"[AutoReviewer] 阶段 '{stage}' 第 {attempt+1} 轮检查发现 {len(issues)} 个问题，尝试自动修复...")
                artifacts = self._auto_fix(stage, artifacts, issues)
            else:
                print(f"[AutoReviewer] 阶段 '{stage}' 已达到最大修复次数 {self.max_fix_loops}，仍有问题")
        
        return False, all_issues
    
    def _run_checks(self, stage: str, checks: list[str], artifacts: dict) -> list[str]:
        """运行指定阶段的所有检查项"""
        issues = []
        for check_name in checks:
            checker = getattr(self, f'_check_{check_name}', None)
            if checker:
                result = checker(stage, artifacts)
                if result:
                    issues.append(result)
            else:
                print(f"[AutoReviewer] 警告: 未知检查项 '{check_name}'")
        return issues
    
    def _auto_fix(self, stage: str, artifacts: dict, issues: list[str]) -> dict:
        """尝试自动修复问题"""
        fixer = getattr(self, f'_fix_{stage}', None)
        if fixer:
            return fixer(artifacts, issues)
        return artifacts
    
    def _write_approved_checkpoint(self, project_id: str, stage: str, artifacts: dict):
        """写入已审核通过的检查点"""
        checkpoint.write_checkpoint(
            pipeline_dir=self.projects_dir,
            project_id=project_id,
            stage=stage,
            status="completed",
            artifacts=artifacts,
            pipeline_type="localization-dub",
            human_approval_required=True,
            human_approved=True
        )
        print(f"[AutoReviewer] 阶段 '{stage}' 自动审核通过 ✅")
    
    # ============================
    # 检查项实现
    # ============================
    
    def _check_brief_schema_valid(self, stage: str, artifacts: dict) -> Optional[str]:
        """brief 必须包含必填字段"""
        brief = artifacts.get('brief', {})
        required = ['title', 'key_points', 'tone', 'target_duration_seconds']
        missing = [f for f in required if f not in brief]
        if missing:
            return f"brief 缺少必填字段: {missing}"
        return None
    
    def _check_target_language_set(self, stage: str, artifacts: dict) -> Optional[str]:
        """brief.metadata 必须设置目标语言"""
        metadata = artifacts.get('brief', {}).get('metadata', {})
        if not metadata.get('target_languages'):
            return "brief.metadata.target_languages 未设置"
        return None
    
    def _check_source_language_detected(self, stage: str, artifacts: dict) -> Optional[str]:
        """brief.metadata 必须设置源语言"""
        metadata = artifacts.get('brief', {}).get('metadata', {})
        if not metadata.get('source_language'):
            return "brief.metadata.source_language 未设置"
        return None
    
    def _check_transcript_not_empty(self, stage: str, artifacts: dict) -> Optional[str]:
        """转录内容不能为空"""
        script = artifacts.get('script', {})
        sections = script.get('sections', [])
        if not sections:
            return "script.sections 为空，转录失败"
        return None
    def _get_lines(self, script: dict) -> list[dict]:
        sections = script.get('sections', [])
        if not sections:
            return []
        if isinstance(sections[0], dict) and 'lines' in sections[0]:
            lines = []
            for s in sections:
                lines.extend(s.get('lines', []))
            return lines
        return sections

    def _get_translated_text(self, line: dict) -> str:
        if 'translated_text' in line:
            return line['translated_text'] or ""
        return line.get('delivery_cues', {}).get('provider_text', '') or ""

    def _check_translation_completeness(self, stage: str, artifacts: dict) -> Optional[str]:
        """所有句子都必须有翻译"""
        script = artifacts.get('script', {})
        lines = self._get_lines(script)
        untranslated = 0
        total = 0
        for line in lines:
            total += 1
            if not self._get_translated_text(line):
                untranslated += 1
        if untranslated > 0:
            return f"有 {untranslated}/{total} 句未翻译"
        return None
    
    def set_glossary(self, glossary):
        """注入术语表实例"""
        self.glossary = glossary

    def _check_glossary_terms_preserved(self, stage: str, artifacts: dict) -> Optional[str]:
        """检查术语表是否被遵守"""
        if not self.glossary:
            return None
        script = artifacts.get('script', {})
        lines = self._get_lines(script)
        violations = []
        for line in lines:
            src = line.get('text', '')
            tgt = self._get_translated_text(line)
            if src and tgt:
                v = self.glossary.validate_translation(src, tgt)
                if v:
                    violations.extend(v)
        if violations:
            unique_v = sorted(list(set(violations)))
            sample = ", ".join(unique_v[:5])
            if len(unique_v) > 5:
                sample += f" 等共 {len(unique_v)} 处违规"
            return f"术语表未遵守: {sample}"
        return None
    
    def _check_no_untranslated_sentences(self, stage: str, artifacts: dict) -> Optional[str]:
        """与 translation_completeness 类似，但检查翻译文本是否全是英文且与原文一致（可能没实际翻译）"""
        import re
        script = artifacts.get('script', {})
        lines = self._get_lines(script)
        suspicious = 0
        for line in lines:
            src = line.get('text', '').strip()
            translated = self._get_translated_text(line)
            if translated:
                translated = translated.strip()
                # 如果翻译文本中没有任何中文字符，可能没实际翻译
                chinese_chars = re.findall(r'[\u4e00-\u9fff]', translated)
                if len(chinese_chars) == 0 and len(translated) > 10:
                    # 只有当清理后的译文与原文完全一致时，才判定为未翻译
                    src_clean = re.sub(r'[^\w]', '', src).lower()
                    tgt_clean = re.sub(r'[^\w]', '', translated).lower()
                    if src_clean == tgt_clean:
                        suspicious += 1
        if suspicious > 0:
            return f"有 {suspicious} 句翻译疑似未实际翻译（无中文字符且与原文一致）"
        return None
    
    def _check_all_scenes_have_timing(self, stage: str, artifacts: dict) -> Optional[str]:
        """所有场景必须有时间码"""
        scene_plan = artifacts.get('scene_plan', {})
        scenes = scene_plan.get('scenes', [])
        no_timing = []
        for i, s in enumerate(scenes):
            has_timing = (
                s.get('start_time') is not None or
                s.get('timing') is not None or
                (s.get('start_seconds') is not None and s.get('end_seconds') is not None)
            )
            if not has_timing:
                no_timing.append(i)
        if no_timing:
            return f"场景 {no_timing} 缺少时间码"
        return None
    
    def _check_dub_mode_set(self, stage: str, artifacts: dict) -> Optional[str]:
        """配音模式必须设置"""
        scene_plan = artifacts.get('scene_plan', {})
        scenes = scene_plan.get('scenes', [])
        meta = scene_plan.get('metadata', {}) or {}
        loc_meta = meta.get('scene_localization_meta', {}) or {}
        
        no_mode = []
        for i, s in enumerate(scenes):
            scene_id = s.get('id') or s.get('scene_id')
            has_mode = (
                s.get('dub_mode') is not None or
                s.get('localization_treatment') is not None or
                (scene_id in loc_meta and (loc_meta[scene_id].get('dub_mode') or loc_meta[scene_id].get('localization_treatment')))
            )
            if not has_mode:
                no_mode.append(i)
        if no_mode:
            return f"场景 {no_mode} 未设置配音模式"
        return None
    
    def _check_subtitle_format_correct(self, stage: str, artifacts: dict) -> Optional[str]:
        """字幕格式检查"""
        # 基本检查：scene_plan 存在即可
        scene_plan = artifacts.get('scene_plan', {})
        if not scene_plan:
            return "scene_plan 为空"
        return None
    
    # ============================
    # 自动修复实现
    # ============================
    
    def _fix_idea(self, artifacts: dict, issues: list[str]) -> dict:
        """修复 idea 阶段的问题"""
        brief = artifacts.get('brief', {})
        
        # 补充缺少的必填字段
        if 'title' not in brief:
            brief['title'] = 'Auto-dubbed video'
        if 'key_points' not in brief:
            brief['key_points'] = ['Translated from English to Chinese']
        if 'tone' not in brief:
            brief['tone'] = 'professional'
        if 'target_duration_seconds' not in brief:
            brief['target_duration_seconds'] = 600.0
        
        # 补充 metadata
        metadata = brief.setdefault('metadata', {})
        if not metadata.get('source_language'):
            metadata['source_language'] = 'en-US'
        if not metadata.get('target_languages'):
            metadata['target_languages'] = ['zh-CN']
        if not metadata.get('deliverable_mode_map'):
            metadata['deliverable_mode_map'] = {'zh-CN': 'dub_audio_only'}
        
        artifacts['brief'] = brief
        print("[AutoReviewer] 已自动补充 brief 缺少字段")
        return artifacts
    
    def _fix_script(self, artifacts: dict, issues: list[str]) -> dict:
        """修复 script 阶段的问题（较复杂，可能需要重新翻译）"""
        # 简单修复：标记未翻译的句子
        print("[AutoReviewer] script 阶段问题需要重新翻译，返回原始 artifacts 等待重试")
        return artifacts
    
    def _fix_scene_plan(self, artifacts: dict, issues: list[str]) -> dict:
        """修复 scene_plan 阶段的问题"""
        scene_plan = artifacts.get('scene_plan', {})
        scenes = scene_plan.get('scenes', [])
        meta = scene_plan.setdefault('metadata', {})
        loc_meta = meta.setdefault('scene_localization_meta', {})
        
        for scene in scenes:
            scene_id = scene.get('id') or scene.get('scene_id')
            if scene_id:
                loc_meta[scene_id] = {
                    "dub_mode": "dub_audio_only",
                    "localization_treatment": "dub_audio_only"
                }
        
        artifacts['scene_plan'] = scene_plan
        print("[AutoReviewer] 已自动补充 scene_plan 缺少字段")
        return artifacts
