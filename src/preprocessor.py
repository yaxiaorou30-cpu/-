import re
import html
from datetime import datetime
from typing import List, Optional

from src.models import RawRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Preprocessor:
    def __init__(self):
        pass

    def process(self, raw_data: List[dict]) -> List[RawRecord]:
        logger.info(f"开始预处理，原始记录数: {len(raw_data)}")
        records = []
        for item in raw_data:
            try:
                rec = self._parse_record(item)
                if rec:
                    records.append(rec)
            except Exception as e:
                logger.warning(f"解析单条记录失败: {e}")
        logger.info(f"解析成功记录数: {len(records)}")
        return records

    def _parse_record(self, item: dict) -> Optional[RawRecord]:
        pub_time_str = item.get("pub_time")
        pub_time = self._parse_time(pub_time_str) if pub_time_str else datetime.now()
        pub_time_confirmed = bool(
            pub_time_str
            and str(item.get("time_basis") or "").strip().lower() != "unknown"
        )

        content = item.get("content", "")
        content = self.clean_content(content)

        return RawRecord(
            url=item.get("url", ""),
            title=item.get("title", ""),
            content=content,
            pub_time=pub_time,
            source=item.get("platform") or item.get("source", "未知"),
            author=item.get("author"),
            repost_count=item.get("repost_count", 0),
            comment_count=item.get("comment_count", 0),
            like_count=item.get("like_count", 0),
            heat_index=item.get("heat_index", 0.0),
            extra={
                "source": item.get("source"),
                "platform": item.get("platform"),
                "source_type": item.get("source_type"),
                "data_type": item.get("data_type"),
                "collector": item.get("collector"),
                "crawl_time": item.get("crawl_time"),
                "keyword": item.get("keyword"),
                "region": item.get("region"),
                "source_group": item.get("source_group"),
                "time_basis": item.get("time_basis"),
                "pub_time_confirmed": pub_time_confirmed,
                "discussion_samples": item.get("discussion_samples") or [],
                "view_count": item.get("view_count", 0),
                "case_location": item.get("case_location"),
                "case_type": item.get("case_type"),
                "injury_count": item.get("injury_count"),
                "main_event_type": item.get("main_event_type"),
                "event_type": item.get("event_type"),
                "content_category": item.get("content_category"),
                "content_category_source": item.get("content_category_source"),
                "sentiment_label": item.get("sentiment_label"),
                "sentiment_source": item.get("sentiment_source"),
                "machine_content_category": item.get("machine_content_category"),
                "machine_sentiment_label": item.get("machine_sentiment_label"),
                "machine_sentiment_score": item.get("machine_sentiment_score"),
                "human_review": item.get("human_review") or {},
            },
        )

    @staticmethod
    def clean_content(text: str) -> str:
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def deduplicate(records: List[RawRecord], method: str = "url") -> List[RawRecord]:
        if method == "url":
            seen = set()
            result = []
            for r in records:
                if r.url not in seen:
                    seen.add(r.url)
                    result.append(r)
            logger.info(f"去重前: {len(records)}, 去重后: {len(result)}")
            return result
        return records

    @staticmethod
    def filter_by_time(records: List[RawRecord], start: Optional[datetime], end: Optional[datetime]) -> List[RawRecord]:
        result = []
        for r in records:
            if start and r.pub_time < start:
                continue
            if end and r.pub_time > end:
                continue
            result.append(r)
        logger.info(f"时间筛选后记录数: {len(result)}")
        return result

    @staticmethod
    def _parse_time(time_str: str) -> datetime:
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析时间: {time_str}")
