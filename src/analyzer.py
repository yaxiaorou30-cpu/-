import math
import re
from collections import Counter
from datetime import datetime
from typing import List, Dict, Tuple

from src.models import RawRecord, AnalysisContext
from src.record_analysis import (
    classify_sentiment,
    effective_content_category,
    effective_sentiment_label,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseSubAnalyzer:
    def analyze(self, records: List[RawRecord]) -> dict:
        raise NotImplementedError


class StatsAnalyzer(BaseSubAnalyzer):
    def analyze(self, records: List[RawRecord]) -> dict:
        total = len(records)
        if total == 0:
            return {
                "total_posts": 0,
                "time_range": (None, None),
                "platform_dist": {},
                "heat_index": 0.0,
            }

        times = [
            r.pub_time
            for r in records
            if r.extra.get("pub_time_confirmed", True)
        ]
        platform_dist = Counter(r.source for r in records)
        avg_heat = sum(r.heat_index for r in records) / total

        return {
            "total_posts": total,
            "time_range": (min(times), max(times)) if times else (None, None),
            "platform_dist": dict(platform_dist),
            "heat_index": round(avg_heat, 2),
            "confirmed_time_count": len(times),
        }


class SentimentAnalyzer(BaseSubAnalyzer):
    def __init__(self, method: str = "conservative_rules"):
        self.method = method
        logger.info("情感分析使用保守关键词初判；结果仅供人工筛选")

    def analyze(self, records: List[RawRecord]) -> dict:
        if not records:
            return {"sentiment_ratio": {"正面": 0.0, "中性": 1.0, "负面": 0.0}}

        pos, neu, neg = 0, 0, 0
        for r in records:
            label = effective_sentiment_label(r.extra, f"{r.title}。{r.content}")
            if label == "正面":
                pos += 1
            elif label == "负面":
                neg += 1
            else:
                neu += 1

        total = pos + neu + neg
        return {
            "sentiment_ratio": {
                "正面": round(pos / total, 2),
                "中性": round(neu / total, 2),
                "负面": round(neg / total, 2),
            }
        }

    def _classify(self, text: str) -> str:
        return classify_sentiment(text)["label"]

    @staticmethod
    def _rule_classify(text: str) -> str:
        positive_words = {"好评", "支持", "点赞", "满意", "感谢", "欣慰"}
        negative_words = {"质疑", "不满", "失望", "愤怒", "谴责", "抗议", "慢", "差"}
        p = sum(1 for w in positive_words if w in text)
        n = sum(1 for w in negative_words if w in text)
        if p > n:
            return "正面"
        elif n > p:
            return "负面"
        return "中性"


class KeywordExtractor(BaseSubAnalyzer):
    STOP_WORDS = {
        "关于", "本次", "我们", "他们", "进行", "表示", "认为", "建议",
        "警情", "通报", "事件", "网民", "相关", "警方", "发布", "关注",
        "案件", "情况", "调查", "处理", "回应", "回应称", "发布通报",
        "开展", "依法", "目前", "正在", "已经", "近日", "网络", "平台",
        "舆论", "网民称", "有关部门", "官方", "微博", "视频", "信息",
        "公共", "安全", "交通", "治安", "发生", "引发", "造成", "导致",
    }

    SEMANTIC_MERGES = {
        ("公共", "安全"): "公共安全",
        ("交通", "安全"): "交通安全",
        ("社会", "治安"): "社会治安",
        ("治安", "案件"): "治安案件",
        ("火灾", "事故"): "火灾事故",
    }

    def __init__(self, method: str = "tfidf", topk: int = 10):
        self.method = method
        self.topk = topk
        self._jieba = None
        try:
            import jieba
            self._jieba = jieba
            logger.info("jieba 分词器已加载")
        except ImportError:
            logger.warning("jieba 未安装，关键词提取将回退到简单规则")

    def analyze(self, records: List[RawRecord]) -> dict:
        if not records:
            return {"top_keywords": [], "event_keyword": ""}

        texts = [r.title + "。" + r.content for r in records]
        if self._jieba and self.method == "tfidf":
            keywords = self._extract_with_jieba(texts)
        else:
            keywords = self._extract_simple(texts)

        keywords = [k for k in keywords if k not in self.STOP_WORDS]
        
        keywords = self._merge_semantic_keywords(keywords, texts)

        event_keyword = keywords[0] if keywords else "相关事件"
        return {
            "top_keywords": keywords,
            "event_keyword": event_keyword,
        }

    def _merge_semantic_keywords(self, keywords: List[str], texts: List[str]) -> List[str]:
        """合并语义重叠词"""
        merged = []
        seen = set()
        
        for (word1, word2), merged_word in self.SEMANTIC_MERGES.items():
            if merged_word not in seen:
                for text in texts:
                    if word1 in text and word2 in text and merged_word in text:
                        merged.append(merged_word)
                        seen.add(merged_word)
                        seen.add(word1)
                        seen.add(word2)
                        break
        
        for kw in keywords:
            if kw not in seen and len(kw) >= 2:
                merged.append(kw)
                seen.add(kw)
        
        return merged[:self.topk]

    def _extract_with_jieba(self, texts: List[str]) -> List[str]:
        try:
            import jieba.analyse
            all_text = " ".join(texts)
            tags = jieba.analyse.extract_tags(all_text, topK=self.topk + 5, withWeight=False)
            return [t for t in tags if t not in self.STOP_WORDS][:self.topk]
        except Exception as e:
            logger.warning(f"jieba 提取失败: {e}")
            return self._extract_simple(texts)

    def _extract_simple(self, texts: List[str]) -> List[str]:
        all_text = " ".join(texts)
        words = re.findall(r"[\u4e00-\u9fff]{2,8}", all_text)
        filtered = [w for w in words if w not in self.STOP_WORDS and len(w) >= 2]
        counter = Counter(filtered)
        return [w for w, _ in counter.most_common(self.topk)]


class ContentExtractor(BaseSubAnalyzer):
    """从原始记录中提取官方回应、网民观点、风险点、案件进展等结构化信息。"""

    TITLE_FEATURES = ["解读", "观察", "？", "！", "如何", "怎么看", "深度", "独家", "热搜", "爆", "热议"]
    CATEGORY_TYPES = {"公共安全", "交通安全", "社会治安", "治安案件", "火灾事故", "自然灾害", "公共卫生"}

    def _is_title_like(self, text: str) -> bool:
        if not text:
            return True
        if len(text) < 10:
            return True
        return any(f in text for f in self.TITLE_FEATURES)

    def _is_related_to_main_event(self, text: str, case_location: str, case_type: str) -> bool:
        """检查文本是否与主事件相关"""
        if not text:
            return False
        if case_location and case_location in text:
            return True
        if case_type and case_type in text:
            return True
        return False

    def _deduplicate_similar(self, items: list, threshold: float = 0.6) -> list:
        """去重相似项，保留第一个"""
        if not items:
            return []
        result = [items[0]]
        for item in items[1:]:
            is_duplicate = False
            for existing in result:
                if self._similarity(item, existing) > threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                result.append(item)
        return result

    def _similarity(self, s1: str, s2: str) -> float:
        """简单相似度计算（基于字符重叠）"""
        if not s1 or not s2:
            return 0.0
        set1 = set(s1)
        set2 = set(s2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _clean_injury_count(self, injury_count: str) -> str:
        """清理伤亡数字，确保语义完整"""
        if not injury_count:
            return ""
        injury_count = injury_count.strip()
        if injury_count.isdigit():
            return f"{injury_count}人受伤"
        if not any(kw in injury_count for kw in ["人", "受伤", "死亡", "伤亡"]):
            return f"{injury_count}人受伤"
        return injury_count

    def analyze(self, records: List[RawRecord]) -> dict:
        official = []
        opinions = []
        risks = []
        progress = []
        events = []

        official_records = []
        public_records = []

        trusted_official_markers = {
            "政府", "公安", "警方", "交警", "应急", "消防", "法院",
            "检察", "气象", "网信", "发布", "办事处", "委员会",
        }
        trusted_official_event_types = {
            "police_briefing", "government_notice", "official_notice",
        }

        for r in records:
            src = r.source.lower()
            source_type = r.extra.get("source_type", "")
            original_source = (r.extra.get("source") or "").lower()
            source_group = r.extra.get("source_group", "")
            event_type = r.extra.get("event_type", "")
            trusted_publisher = any(
                marker in src + original_source
                for marker in trusted_official_markers
            )
            if (
                (source_type == "official" and source_group == "stable")
                or event_type in trusted_official_event_types
                or trusted_publisher
            ):
                official_records.append(r)
            else:
                public_records.append(r)

        main_event = ""
        main_event_type = ""
        case_location = ""
        case_type = ""
        injury_count = ""
        brief_description = ""
        event_keyword = ""

        main_event_record = None
        for r in records:
            if r.extra.get("event_type") == "main_event":
                main_event_record = r
                break

        if main_event_record:
            main_event = main_event_record.content
            main_event_type = main_event_record.extra.get("main_event_type", "") or "社会治安事件"
            case_location = main_event_record.extra.get("case_location", "") or ""
            case_type = main_event_record.extra.get("case_type", "") or ""
            injury_count = self._clean_injury_count(main_event_record.extra.get("injury_count", ""))
            brief_description = main_event[:100] if main_event else ""

            if case_location and case_type:
                type_str = case_type
                if type_str in self.CATEGORY_TYPES:
                    type_str = f"{type_str}事件"
                elif not any(type_str.endswith(end) for end in ["案件", "事故", "事件", "纠纷", "冲突", "伤亡"]):
                    type_str = f"{type_str}事件"
                event_keyword = f"{case_location}{type_str}"
            elif case_location and main_event_type:
                event_keyword = f"{case_location}{main_event_type}"
            elif main_event_type:
                event_keyword = main_event_type
            
            official.insert(0, main_event[:200] if len(main_event) > 200 else main_event)

        for r in official_records:
            if r.extra.get("event_type") == "main_event":
                continue
            
            content = r.content or ""
            title = r.title or ""
            
            related_to_main = (
                not case_location and not case_type
            ) or self._is_related_to_main_event(content, case_location, case_type) or self._is_related_to_main_event(title, case_location, case_type)

            if related_to_main:
                if content and len(content) > 30 and not self._is_title_like(content):
                    official.append(content[:150])
                elif title and not self._is_title_like(title):
                    official.append(title)

                if any(k in title + content for k in ["处理", "侦办", "进展", "通报", "完毕", "恢复"]):
                    if content and len(content) > 30 and not self._is_title_like(content):
                        progress.append(content[:150])

                if any(k in title + content for k in ["发生", "引发", "造成", "导致"]):
                    if content and len(content) > 30 and not self._is_title_like(content):
                        events.append(content[:100])
                    elif title and not self._is_title_like(title):
                        events.append(title)

        for r in public_records:
            content = r.content or ""
            title = r.title or ""
            
            if content and len(content) > 20 and not self._is_title_like(content):
                opinions.append(content[:100])
            elif title and not self._is_title_like(title):
                opinions.append(title)

            if any(k in title + content for k in ["质疑", "风险", "隐患", "漏洞", "担忧"]):
                if content and len(content) > 20 and not self._is_title_like(content):
                    risks.append(content[:100])
                elif title and not self._is_title_like(title):
                    risks.append(title)

        official = list(dict.fromkeys(official))[:3]
        progress = self._deduplicate_similar(progress, threshold=0.4)
        
        return {
            "official_responses": official[:3],
            "netizen_opinions": list(dict.fromkeys(opinions))[:5],
            "risk_points": list(dict.fromkeys(risks))[:5],
            "case_progress": "；".join(progress[:2]) if progress else "",
            "key_events": [main_event[:150]] if main_event else [],
            "main_event": main_event,
            "main_event_type": main_event_type,
            "case_location": case_location,
            "case_type": case_type,
            "injury_count": injury_count,
            "brief_description": brief_description,
            "event_keyword": event_keyword,
        }


class UrlSelector(BaseSubAnalyzer):
    def analyze(self, records: List[RawRecord]) -> dict:
        sorted_recs = sorted(records, key=lambda x: x.heat_index, reverse=True)
        return {"top_urls": [r.url for r in sorted_recs[:5]]}


class Analyzer:
    def __init__(self, config: dict = None):
        cfg = config or {}
        self.stats_analyzer = StatsAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer(method=cfg.get("sentiment_method", "conservative_rules"))
        self.keyword_extractor = KeywordExtractor(
            method=cfg.get("keyword_method", "tfidf"),
            topk=cfg.get("keyword_topk", 10),
        )
        self.content_extractor = ContentExtractor()
        self.url_selector = UrlSelector()

    def analyze(
        self,
        records: List[RawRecord],
        *,
        topic_hint: str = "",
        query_keywords: List[str] = None,
        evidence_samples: List[Dict] = None,
    ) -> AnalysisContext:
        logger.info(f"开始分析，记录数: {len(records)}")
        ctx = AnalysisContext()

        stats = self.stats_analyzer.analyze(records)
        for k, v in stats.items():
            setattr(ctx, k, v)

        sentiment = self.sentiment_analyzer.analyze(records)
        for k, v in sentiment.items():
            setattr(ctx, k, v)

        keywords = self.keyword_extractor.analyze(records)
        for k, v in keywords.items():
            setattr(ctx, k, v)

        content = self.content_extractor.analyze(records)
        for k, v in content.items():
            setattr(ctx, k, v)

        urls = self.url_selector.analyze(records)
        for k, v in urls.items():
            setattr(ctx, k, v)

        ctx.task_topic = self._clean_topic_hint(topic_hint)
        ctx.query_keywords = self._clean_query_keywords(query_keywords or [])
        ctx.top_keywords = self._merge_query_keywords(ctx.query_keywords, ctx.top_keywords)
        ctx.evidence_samples = list(evidence_samples or [])
        ctx.source_type_dist = dict(Counter(
            str(r.extra.get("source_type") or "unknown")
            for r in records
        ))
        ctx.content_category_dist = dict(Counter(
            effective_content_category(
                r.extra,
                {
                    "title": r.title,
                    "content": r.content,
                    "source": r.extra.get("source") or r.source,
                    "platform": r.extra.get("platform") or r.source,
                    "keyword": r.extra.get("keyword"),
                },
            )
            for r in records
        ))
        ctx.human_reviewed_count = sum(
            1 for r in records if isinstance(r.extra.get("human_review"), dict)
            and r.extra.get("human_review", {}).get("reviewed_at")
        )
        ctx.data_limitations = self._build_data_limitations(ctx)

        GENERIC_KEYWORDS = {"警情通报", "通报", "舆情", "警情", "事件", "相关事件", "相关舆情", "案件", ""}
        CATEGORY_TYPES = {"公共安全", "交通安全", "社会治安", "治安案件", "火灾事故", "自然灾害", "公共卫生"}
        
        if ctx.task_topic and ctx.task_topic not in GENERIC_KEYWORDS:
            ctx.event_keyword = ctx.task_topic
        elif not ctx.event_keyword or ctx.event_keyword in GENERIC_KEYWORDS:
            parts = []
            if ctx.case_location:
                parts.append(ctx.case_location)
            if ctx.case_type:
                type_str = ctx.case_type
                if type_str in CATEGORY_TYPES:
                    type_str = f"{type_str}事件"
                elif not any(type_str.endswith(end) for end in ["案件", "事故", "事件", "纠纷", "冲突", "伤亡"]):
                    type_str = f"{type_str}事件"
                parts.append(type_str)
            if parts:
                ctx.event_keyword = ''.join(parts)
            elif ctx.main_event_type and ctx.main_event_type not in GENERIC_KEYWORDS:
                type_str = ctx.main_event_type
                if type_str in CATEGORY_TYPES:
                    type_str = f"{type_str}事件"
                ctx.event_keyword = type_str
            else:
                ctx.event_keyword = "舆情事件"

        if ctx.injury_count and not any(kw in ctx.injury_count for kw in ["人", "受伤", "死亡", "伤亡"]):
            ctx.injury_count = f"{ctx.injury_count}人受伤"

        if ctx.case_location and ctx.top_keywords:
            extra_keywords = []
            if ctx.case_location and ctx.case_location not in ctx.top_keywords:
                extra_keywords.append(ctx.case_location)
            if ctx.case_type and ctx.case_type not in ctx.top_keywords:
                extra_keywords.append(ctx.case_type)
            if extra_keywords:
                remaining = [k for k in ctx.top_keywords if k not in extra_keywords]
                ctx.top_keywords = extra_keywords + remaining[:10 - len(extra_keywords)]

        logger.info(f"分析完成，关键词: {ctx.top_keywords}, 事件关键词: {ctx.event_keyword}")
        return ctx

    @staticmethod
    def _clean_topic_hint(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" ，,；;。")
        text = re.sub(
            r"(?:[-_\s]*)20\d{2}[.\-/年]\d{1,2}(?:[.\-/月]\d{1,2}日?)?$",
            "",
            text,
        ).strip(" -_，,；;。")
        return text[:60]

    @staticmethod
    def _clean_query_keywords(values: List[str]) -> List[str]:
        result = []
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip(" ，,；;。")
            if len(text) >= 2 and text not in result:
                result.append(text[:30])
        return result[:10]

    @staticmethod
    def _merge_query_keywords(query_keywords: List[str], extracted: List[str]) -> List[str]:
        merged = list(query_keywords)
        for keyword in extracted or []:
            text = str(keyword or "").strip()
            if not text or text in merged:
                continue
            if any(text in query and len(text) < len(query) for query in query_keywords):
                continue
            if re.fullmatch(r"[\d.\-/]+", text):
                continue
            merged.append(text)
        return merged[:10]

    @staticmethod
    def _build_data_limitations(ctx: AnalysisContext) -> List[str]:
        limitations = []
        if ctx.total_posts and ctx.confirmed_time_count < ctx.total_posts:
            limitations.append(
                f"{ctx.total_posts - ctx.confirmed_time_count}条样本缺少可靠发布时间"
            )
        official_count = (
            ctx.source_type_dist.get("official", 0)
            + ctx.source_type_dist.get("media", 0)
        )
        if ctx.total_posts and official_count == 0:
            limitations.append("未采集到官方或媒体来源样本")
        if ctx.total_posts and not any(
            sample.get("source_group") == "stable"
            for sample in ctx.evidence_samples
        ):
            limitations.append("本次任务未包含政府官网样本")
        return limitations


class EventClusterer:
    """事件聚类器 - 将多条记录按事件聚类分组"""

    LOCATION_KEYWORDS = [
        "小区", "花园", "苑", "广场", "路", "街", "大道", "巷", "路口",
        "医院", "学校", "公园", "商场", "超市", "酒店", "车站", "机场",
        "体育馆", "图书馆", "政务中心", "隧道", "桥梁", "高架",
    ]

    EVENT_TYPES = [
        "交通事故", "治安案件", "刑事案件", "公共安全事件", "社会事件",
        "火灾事故", "自然灾害", "公共卫生事件", "纠纷", "冲突",
    ]

    def cluster(self, records: List[RawRecord], min_cluster_size: int = 3) -> List[List[RawRecord]]:
        """
        基于地点和事件类型的关键词重叠聚类
        返回聚类后的记录列表，每个子列表代表一个独立事件
        """
        if not records:
            return []

        main_event_records = [r for r in records if r.extra.get("event_type") == "main_event"]
        other_records = [r for r in records if r.extra.get("event_type") != "main_event"]

        clusters = []
        used_indices = set()

        for main_rec in main_event_records:
            cluster = [main_rec]
            case_location = main_rec.extra.get("case_location", "")
            case_type = main_rec.extra.get("case_type", "")

            for i, rec in enumerate(other_records):
                if i in used_indices:
                    continue
                text = (rec.title or "") + (rec.content or "")
                if case_location and case_location in text:
                    cluster.append(rec)
                    used_indices.add(i)
                elif case_type and case_type in text and self._has_common_location(rec, main_rec):
                    cluster.append(rec)
                    used_indices.add(i)

            clusters.append(cluster)

        remaining = [rec for i, rec in enumerate(other_records) if i not in used_indices]
        if remaining:
            sub_clusters = self._simple_keyword_cluster(remaining, min_cluster_size)
            clusters.extend(sub_clusters)

        if not clusters and records:
            clusters = [records]

        logger.info(f"事件聚类完成，共 {len(clusters)} 个事件簇")
        return clusters

    def _has_common_location(self, rec1: RawRecord, rec2: RawRecord) -> bool:
        """检查两条记录是否有共同地点词"""
        text1 = (rec1.title or "") + (rec1.content or "")
        text2 = (rec2.title or "") + (rec2.content or "")
        for kw in self.LOCATION_KEYWORDS:
            if kw in text1 and kw in text2:
                return True
        return False

    def _simple_keyword_cluster(self, records: List[RawRecord], min_size: int) -> List[List[RawRecord]]:
        """简单关键词聚类 - 基于地点词和事件类型词"""
        if not records:
            return []

        clusters = []
        used = [False] * len(records)

        for i, rec in enumerate(records):
            if used[i]:
                continue
            used[i] = True
            cluster = [rec]
            text_i = (rec.title or "") + (rec.content or "")
            loc_words_i = self._extract_location_words(text_i)
            evt_words_i = self._extract_event_words(text_i)

            for j in range(i + 1, len(records)):
                if used[j]:
                    continue
                text_j = (records[j].title or "") + (records[j].content or "")
                loc_words_j = self._extract_location_words(text_j)
                evt_words_j = self._extract_event_words(text_j)

                common_loc = loc_words_i & loc_words_j
                common_evt = evt_words_i & evt_words_j

                if common_loc or common_evt:
                    cluster.append(records[j])
                    used[j] = True

            if len(cluster) >= min_size:
                clusters.append(cluster)

        singletons = [records[i] for i in range(len(records)) if not used[i]]
        if singletons:
            if clusters:
                clusters[-1].extend(singletons)
            else:
                clusters.append(singletons)

        return clusters

    def _extract_location_words(self, text: str) -> set:
        """提取地点特征词"""
        words = set()
        for kw in self.LOCATION_KEYWORDS:
            if kw in text:
                words.add(kw)
        return words

    def _extract_event_words(self, text: str) -> set:
        """提取事件类型特征词"""
        words = set()
        for kw in self.EVENT_TYPES:
            if kw in text:
                words.add(kw)
        return words

