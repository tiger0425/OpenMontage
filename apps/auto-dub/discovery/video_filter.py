"""视频筛选器：根据配置规则过滤不适合搬运的视频"""

import re
import logging
import os
from datetime import datetime, timedelta

# 使用新版 google.genai SDK（如果可用）
try:
    from google import genai
    _GENAI_AVAILABLE = True
except ImportError:
    try:
        # 回退到旧版 SDK
        import google.generativeai as genai
        _GENAI_AVAILABLE = True
    except ImportError:
        genai = None
        _GENAI_AVAILABLE = False


class VideoFilter:
    """YouTube 视频智能筛选器
    
    筛选顺序：去重 -> 时长 -> 发布时间 -> 语言 -> LLM 相关性
    """
    
    def __init__(self, config: dict, dedup_db):
        """初始化筛选器
        
        Args:
            config: filters 配置段
            dedup_db: DedupDB 实例，用于去重检查
        """
        self.config = config
        self.dedup_db = dedup_db
        
        # 初始化 Gemini（如果可用）
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.use_llm = bool(_GENAI_AVAILABLE and api_key)
        self._llm_client = None
        
        if self.use_llm:
            try:
                # 尝试新版 SDK
                self._llm_client = genai.Client(api_key=api_key)
            except (AttributeError, TypeError):
                # 回退到旧版 SDK
                genai.configure(api_key=api_key)
                self._llm_client = genai
    
    def filter_batch(self, videos: list[dict]) -> list[dict]:
        """依次应用所有过滤器，返回通过筛选的视频
        
        每步过滤后记录日志，方便调试。
        """
        current_videos = videos.copy()
        
        # 初始化 filter_log
        for v in current_videos:
            v["filter_log"] = []
            
        filters = [
            ("dedup", self._filter_dedup, []),
            ("duration", self._filter_duration, [
                self.config.get("min_duration_seconds", 180),
                self.config.get("max_duration_seconds", 1200)
            ]),
            ("age", self._filter_age, [self.config.get("max_age_days", 30)]),
            ("language", self._filter_language, [self.config.get("exclude_languages", ["zh"])]),
        ]
        
        if "relevance_prompt" in self.config:
            filters.append(("relevance", self._filter_relevance, [self.config.get("relevance_prompt")]))
            
        for name, func, args in filters:
            before_count = len(current_videos)
            if before_count == 0:
                break
                
            current_videos = func(current_videos, *args)
            after_count = len(current_videos)
            removed = before_count - after_count
            print(f"  [Filter] {name}: {before_count} -> {after_count} ({removed} removed)")
            
            for v in current_videos:
                v["filter_log"].append(name)
                
        return current_videos
    
    def _filter_duration(self, videos: list[dict], min_sec: int, max_sec: int) -> list[dict]:
        """时长过滤：只保留指定范围内的视频"""
        return [v for v in videos if min_sec <= v.get("duration_seconds", 0) <= max_sec]
    
    def _filter_age(self, videos: list[dict], max_age_days: int) -> list[dict]:
        """发布时间过滤：只保留最近 N 天内的视频"""
        cutoff_date_str = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y%m%d")
        return [v for v in videos if v.get("published_at", "") >= cutoff_date_str]
    
    def _filter_language(self, videos: list[dict], exclude_languages: list[str]) -> list[dict]:
        """语言过滤：排除指定语言的视频
        
        通过检查标题和描述中的 CJK 字符比例来判断中文视频。
        CJK 字符占比超过 10% 则认为是中文视频。
        """
        if "zh" not in exclude_languages:
            return videos
            
        filtered = []
        for v in videos:
            text = f"{v.get('title', '')} {v.get('description', '')}"
            cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
            total_chars = len(text)
            
            # 如果中文字符占比过高，认为是中文视频
            if total_chars > 0 and (cjk_chars / total_chars) > 0.1:
                continue
                
            filtered.append(v)
        return filtered
    
    def _filter_dedup(self, videos: list[dict]) -> list[dict]:
        """去重过滤：排除已在处理流程中或已完成的视频

        注意：filter_videos() 已经只取 discovered 状态的视频，
        所以 dedup 在这里主要用于防止视频被重复加入（scan 时尚未入库的情况）。
        对于已在 DB 中但仍是 discovered 状态的视频，直接放行。
        """
        # 已处理完成或正在处理中的状态，需要排除
        processed_statuses = {'queued', 'processing', 'done', 'published', 'failed', 'skipped'}
        result = []
        for v in videos:
            vid = v["video_id"]
            status = self.dedup_db.get_video_status(vid)
            if status is None:
                # 完全没有记录，放行（scan 外直接调用 filter 时的情况）
                result.append(v)
            elif status not in processed_statuses:
                # discovered 或 filtering 状态，放行
                result.append(v)
            # 否则已处理过，跳过
        return result
    
    def _filter_relevance(self, videos: list[dict], prompt: str) -> list[dict]:
        """LLM 相关性过滤：用 Gemini 判断视频内容是否符合搬运标准
        
        将视频按批次（每批 10 个）发送给 Gemini 评估。
        如果 API 不可用或调用失败，降级为保留所有视频。
        """
        if not self.use_llm or not videos:
            return videos
            
        filtered = []
        batch_size = 10
        
        for i in range(0, len(videos), batch_size):
            batch = videos[i:i+batch_size]
            prompt_text = (
                f"{prompt}\n\n"
                "评估以下视频列表的相关性，只需回复每行的 ID 和 YES/NO，"
                "格式如: video_id: YES\n\n"
            )
            for v in batch:
                desc = v.get('description', '')[:100]
                prompt_text += f"ID: {v['video_id']}, Title: {v['title']}, Description: {desc}\n"
                
            try:
                # 尝试新版 SDK 调用方式
                if hasattr(self._llm_client, 'models'):
                    response = self._llm_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=prompt_text
                    )
                    response_text = response.text
                else:
                    # 旧版 SDK
                    model = self._llm_client.GenerativeModel('gemini-2.0-flash')
                    response = model.generate_content(prompt_text)
                    response_text = response.text
                
                # 解析返回的 YES/NO
                relevance_map = {}
                for line in response_text.split('\n'):
                    match = re.search(r'([a-zA-Z0-9_-]{11})\s*:\s*(YES|NO)', line, re.IGNORECASE)
                    if match:
                        vid = match.group(1)
                        is_yes = match.group(2).upper() == 'YES'
                        relevance_map[vid] = is_yes
                
                for v in batch:
                    if relevance_map.get(v['video_id'], True):  # 默认通过
                        filtered.append(v)
                        
            except Exception as e:
                logging.warning(f"[Filter] Gemini API 调用失败，降级保留本批视频: {e}")
                # 降级：如果 API 调用失败，保留这批视频
                filtered.extend(batch)
                
        return filtered
