"""为单条、单来源和批量线索生成可追溯的机器摘要草稿。"""

from __future__ import annotations

from collections import Counter
import re
from typing import Dict, Iterable, List, Optional

from src.analyzer import Analyzer
from src.generators.evidence_generators import THEME_RULES
from src.preprocessor import Preprocessor
from src.record_analysis import annotate_records
from src.report_builder import select_key_samples


SUMMARY_SCOPE_TYPES = {"record", "source", "filtered"}


def build_evidence_summary(
    raw_data: List[dict],
    meta: Optional[dict] = None,
    *,
    scope_type: str = "filtered",
    scope_label: str = "当前筛选结果",
) -> Dict:
    """只依据传入线索生成摘要，并为每个内容观点保留证据编号。"""
    if scope_type not in SUMMARY_SCOPE_TYPES:
        raise ValueError("不支持的摘要范围")

    data = annotate_records(raw_data or [])
    if not data:
        raise ValueError("当前摘要范围没有可用数据")

    meta = meta if isinstance(meta, dict) else {}
    topic_hint = _topic_hint(meta)
    evidence = select_key_samples(data, limit=8, topic_hint=topic_hint)
    if not evidence:
        evidence = _fallback_evidence(data[:8])

    records = Preprocessor().deduplicate(Preprocessor().process(data))
    context = Analyzer().analyze(
        records,
        topic_hint=topic_hint,
        query_keywords=_query_keywords(meta),
        evidence_samples=evidence,
    )

    if scope_type == "record":
        overview, points = _single_record_summary(data[0], evidence[0])
    else:
        overview = _collection_overview(data, scope_label)
        points = _theme_points(evidence)
        if not points:
            points = _representative_points(evidence)

    cited_ids = _unique(
        evidence_id
        for point in points
        for evidence_id in point.get("evidence_ids", [])
    )
    available_ids = {str(item.get("reference_id")) for item in evidence}
    if not cited_ids or any(item not in available_ids for item in cited_ids):
        raise ValueError("摘要未能建立完整的原文追溯关系")

    reviewed_count = sum(
        1
        for item in data
        if isinstance(item.get("human_review"), dict)
        and item.get("human_review", {}).get("reviewed_at")
    )
    return {
        "scope": {
            "type": scope_type,
            "label": scope_label,
            "record_count": len(data),
        },
        "topic": context.task_topic or context.event_keyword or "本次任务",
        "overview": overview,
        "key_points": points,
        "keywords": context.top_keywords[:8],
        "evidence": evidence,
        "grounding": {
            "cited_ids": cited_ids,
            "available_ids": sorted(available_ids, key=_reference_sort_key),
            "all_citations_valid": True,
        },
        "review": {
            "reviewed_count": reviewed_count,
            "record_count": len(data),
            "labels_confirmed_for_all": reviewed_count == len(data),
        },
        "notice": (
            "机器生成草稿，仅概括当前采集线索，不代表事实已经核实；"
            "请通过 [S编号] 打开原文复核后再用于正式结论。"
        ),
    }


def _single_record_summary(record: dict, evidence: dict) -> tuple[str, List[Dict]]:
    title = _short(record.get("title") or "未命名线索", 100)
    platform = _short(record.get("platform") or record.get("source") or "未知来源", 24)
    source = _short(record.get("source") or record.get("author") or platform, 36)
    category = _short(record.get("content_category") or "其他", 20)
    sentiment = _short(record.get("sentiment_label") or "中性", 10)
    reference_id = str(evidence.get("reference_id") or "S1")
    excerpt = _extractive_excerpt(record.get("content") or record.get("title") or "")
    overview = (
        f"该线索来自{platform}的“{source}”，当前归为“{category}”，"
        f"情感参考为“{sentiment}”。线索标题为“{title}”[{reference_id}]。"
    )
    return overview, [{
        "text": f"原文主要可见内容：{excerpt}",
        "evidence_ids": [reference_id],
    }]


def _collection_overview(data: List[dict], scope_label: str) -> str:
    platforms = Counter(_clean(item.get("platform") or item.get("source") or "未知") for item in data)
    categories = Counter(_clean(item.get("content_category") or "其他") for item in data)
    sentiments = Counter(_clean(item.get("sentiment_label") or "中性") for item in data)
    return (
        f"程序对{scope_label}的{len(data)}条线索进行汇总。"
        f"来源构成为：{_format_counts(platforms)}；"
        f"内容分类为：{_format_counts(categories)}；"
        f"情感参考为：{_format_counts(sentiments)}。"
    )


def _theme_points(evidence: List[dict]) -> List[Dict]:
    points = []
    for theme_name, keywords in THEME_RULES:
        refs = []
        hits = []
        for item in evidence:
            text = f"{item.get('title', '')} {item.get('content_excerpt', '')}"
            item_hits = [keyword for keyword in keywords if keyword in text]
            if item_hits:
                refs.append(str(item.get("reference_id")))
                hits.extend(item_hits)
        refs = _unique(refs)[:4]
        hits = _unique(hits)[:5]
        if refs:
            points.append({
                "text": f"{theme_name}：相关样本出现“{'、'.join(hits)}”等内容。",
                "evidence_ids": refs,
            })
        if len(points) >= 4:
            break
    return points


def _representative_points(evidence: List[dict]) -> List[Dict]:
    return [
        {
            "text": (
                f"{_short(item.get('platform') or item.get('source') or '未知来源', 24)}线索："
                f"{_short(item.get('title') or item.get('content_excerpt') or '未命名内容', 100)}。"
            ),
            "evidence_ids": [str(item.get("reference_id"))],
        }
        for item in evidence[:4]
    ]


def _fallback_evidence(data: List[dict]) -> List[Dict]:
    result = []
    for index, item in enumerate(data, 1):
        result.append({
            "reference_id": f"S{index}",
            "title": _short(item.get("title") or "未命名内容", 120),
            "platform": _clean(item.get("platform") or item.get("source") or "未知"),
            "source": _clean(item.get("source") or "未知"),
            "pub_time": _clean(item.get("pub_time")),
            "time_basis": _clean(item.get("time_basis") or "unknown"),
            "url": _clean(item.get("url")),
            "content_excerpt": _short(item.get("content"), 180),
            "content_category": _clean(item.get("content_category") or "其他"),
            "sentiment_label": _clean(item.get("sentiment_label") or "中性"),
        })
    return result


def _extractive_excerpt(value, limit: int = 260) -> str:
    text = _clean(value)
    if not text:
        return "原页面没有提供可用正文，请打开原文核对"
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
    selected = []
    length = 0
    for sentence in sentences or [text]:
        if selected and length + len(sentence) > limit:
            break
        selected.append(sentence)
        length += len(sentence)
        if len(selected) >= 2:
            break
    excerpt = "".join(selected) or text
    return _short(excerpt, limit)


def _topic_hint(meta: dict) -> str:
    topic = _clean(meta.get("topic"))
    if topic:
        return topic
    return "、".join(_query_keywords(meta))


def _query_keywords(meta: dict) -> List[str]:
    values = meta.get("keywords") or []
    if not isinstance(values, list):
        values = re.split(r"[,，;；]", str(values))
    return [_clean(value) for value in values if _clean(value)][:10]


def _format_counts(counter: Counter) -> str:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return "、".join(f"{name}{count}条" for name, count in items) or "无"


def _short(value, limit: int) -> str:
    text = _clean(value).strip(" ，,；;。")
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique(values: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _reference_sort_key(reference_id: str) -> int:
    match = re.search(r"\d+", str(reference_id or ""))
    return int(match.group()) if match else 10**9
