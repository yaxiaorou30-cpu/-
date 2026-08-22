from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any


@dataclass
class RawRecord:
    url: str
    title: str
    content: str
    pub_time: datetime
    source: str
    author: Optional[str] = None
    repost_count: int = 0
    comment_count: int = 0
    like_count: int = 0
    heat_index: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisContext:
    total_posts: int = 0
    time_range: Tuple[Optional[datetime], Optional[datetime]] = (None, None)
    platform_dist: Dict[str, int] = field(default_factory=dict)
    sentiment_ratio: Dict[str, float] = field(default_factory=dict)
    top_keywords: List[str] = field(default_factory=list)
    top_urls: List[str] = field(default_factory=list)

    official_responses: List[str] = field(default_factory=list)
    netizen_opinions: List[str] = field(default_factory=list)
    risk_points: List[str] = field(default_factory=list)
    case_progress: str = ""
    key_events: List[str] = field(default_factory=list)
    event_keyword: str = ""
    heat_index: float = 0.0

    # 主事件信息（确保事件阐述有具体内容）
    main_event: str = ""
    main_event_type: str = ""

    # 实体字段（从主事件中提取）
    case_location: str = ""
    case_type: str = ""
    injury_count: str = ""
    brief_description: str = ""

    # 报告生成使用的任务语境和可追溯证据。
    task_topic: str = ""
    query_keywords: List[str] = field(default_factory=list)
    evidence_samples: List[Dict[str, Any]] = field(default_factory=list)
    source_type_dist: Dict[str, int] = field(default_factory=dict)
    content_category_dist: Dict[str, int] = field(default_factory=dict)
    human_reviewed_count: int = 0
    confirmed_time_count: int = 0
    data_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _fmt_dt(dt):
            return dt.strftime("%Y-%m-%d %H:%M") if dt else None

        return {
            "total_posts": self.total_posts,
            "time_range": (_fmt_dt(self.time_range[0]), _fmt_dt(self.time_range[1])),
            "platform_dist": self.platform_dist,
            "sentiment_ratio": self.sentiment_ratio,
            "top_keywords": self.top_keywords,
            "top_urls": self.top_urls,
            "official_responses": self.official_responses,
            "netizen_opinions": self.netizen_opinions,
            "risk_points": self.risk_points,
            "case_progress": self.case_progress,
            "key_events": self.key_events,
            "event_keyword": self.event_keyword,
            "heat_index": self.heat_index,
            "task_topic": self.task_topic,
            "query_keywords": self.query_keywords,
            "evidence_samples": self.evidence_samples,
            "source_type_dist": self.source_type_dist,
            "content_category_dist": self.content_category_dist,
            "human_reviewed_count": self.human_reviewed_count,
            "confirmed_time_count": self.confirmed_time_count,
            "data_limitations": self.data_limitations,
        }


@dataclass
class SectionConfig:
    id: str
    name: Optional[str] = None
    generator: str = "rule"
    rule_class: Optional[str] = None
    prompt_template: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    min_words: int = 0
    max_words: int = 1000
    is_title: bool = False
    content: Optional[str] = None
    require_manual_review: bool = False


@dataclass
class TemplateConfig:
    id: str
    name: str
    description: str
    sections: List[SectionConfig] = field(default_factory=list)


@dataclass
class DocumentContext:
    template_id: str
    title: str
    sections: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    event_keyword: Optional[str] = None
