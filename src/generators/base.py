import re
from abc import ABC, abstractmethod

from src.models import AnalysisContext, SectionConfig


class BaseGenerator(ABC):
    OFFICIAL_WORDS = {
        "神评": "高赞评论",
        "你怎么看": "",
        "网友热议": "引发关注",
        "评论区": "讨论区",
        "热搜": "热点话题",
        "点赞": "支持",
        "刷屏": "广泛传播",
        "吃瓜": "关注",
        "围观": "关注",
        "爆料": "反映",
        "曝": "反映",
        "翻车": "出现问题",
        "实锤": "证实",
        "凉凉": "降温",
        "躺平": "观望",
        "内卷": "竞争",
        "emo": "情绪低落",
        "YYDS": "表现优异",
        "绝绝子": "非常",
        "咱就是说": "认为",
        "一整个": "十分",
        "破防": "受到冲击",
        "蚌埠住了": "难以接受",
        "栓Q": "感谢",
        "下头": "失望",
        "上头": "投入",
        "真香": "认可",
        "套路": "方式",
        "整活": "采取行动",
        "整活了": "采取行动",
        "整活儿": "采取行动",
        "引爆": "引发",
        "炸锅": "引发热议",
        "崩了": "出现问题",
        "逆天": "异常",
        "无语": "不解",
        "离谱": "异常",
        "卧槽": "表示惊讶",
        "扎心": "触动",
        "硬核": "核心",
        "打call": "支持",
        "冲鸭": "继续努力",
        "奥利给": "加油",
        "集美": "朋友们",
        "社死": "尴尬",
        "内娱": "娱乐圈",
        "高燃": "振奋",
        "炸裂": "强烈",
    }

    @abstractmethod
    def generate(self, context: AnalysisContext, section_config: SectionConfig) -> str:
        pass

    @staticmethod
    def _ensure_word_count(text: str, min_words: int, max_words: int) -> str:
        words = text.replace("。", " ").replace("，", " ").replace("；", " ").split()
        if len(words) < min_words and min_words > 0:
            text += "。"
        if len(words) > max_words and max_words > 0:
            text = text[:max_words * 2]
        return text

    @staticmethod
    def _clean_text(text: str) -> str:
        text = BaseGenerator._replace_net_words(text)
        text = BaseGenerator._normalize_punctuation(text)
        text = BaseGenerator._remove_duplicate_punctuation(text)
        text = BaseGenerator._remove_redundant_ending(text)
        text = BaseGenerator._fix_number_format(text)
        return text.strip()

    @staticmethod
    def _replace_net_words(text: str) -> str:
        for net_word, official_word in BaseGenerator.OFFICIAL_WORDS.items():
            text = text.replace(net_word, official_word)
        return text

    @staticmethod
    def _normalize_punctuation(text: str) -> str:
        text = text.replace("，", "，").replace("。", "。")
        text = text.replace(",", "，")
        text = re.sub(r'(?<![\d])\.(?![\d])', '。', text)
        return text

    @staticmethod
    def _remove_duplicate_punctuation(text: str) -> str:
        text = re.sub(r"。{2,}", "。", text)
        text = re.sub(r"，{2,}", "，", text)
        text = re.sub(r"；{2,}", "；", text)
        text = re.sub(r"\.{2,}", "。", text)
        text = re.sub(r",{2,}", "，", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r'。\s+。', '。', text)
        text = re.sub(r'(?<=\d)。(?=\d)', '.', text)
        text = re.sub(r'(？\s*)+', '？', text)
        text = re.sub(r'？(?=[。，；])', '', text)
        return text

    @staticmethod
    def _remove_redundant_ending(text: str) -> str:
        redundant_patterns = [
            r'相关情况仍在持续关注中[。]?$',
            r'相关情况仍在持续监测中[。]?$',
            r'具体情况将后续通报[。]?$',
            r'请以官方通报为准[。]?$',
            r'请广大网民不信谣、不传谣[。]?$',
        ]
        for pattern in redundant_patterns:
            text = re.sub(pattern, '', text)
        text = re.sub(r'[。]\s*$', '', text)
        return text

    @staticmethod
    def _fix_number_format(text: str) -> str:
        text = re.sub(r'(?<=\d)[。](?=\d)', '.', text)
        return text

    @staticmethod
    def _smart_keyword(event_keyword: str, suffix: str = "事件") -> str:
        """智能处理关键词，避免重复（如'治安案件事件' -> '治安案件'）"""
        if not event_keyword:
            return "相关事件"
        if event_keyword.endswith(suffix):
            return event_keyword
        for end in ["案件", "事故", "事件"]:
            if event_keyword.endswith(end):
                return event_keyword
        return f"{event_keyword}{suffix}"
