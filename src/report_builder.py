from collections import Counter
from datetime import datetime
import re
from typing import Dict, List, Optional

from src.models import AnalysisContext, DocumentContext
from src.quality_checks import (
    append_report_evidence_check,
    build_collection_assessment,
    has_confirmed_pub_time,
    is_valid_url,
)


MAX_EVIDENCE_CATALOG_COUNT = 256


def build_report_metadata(
    raw_data: List[dict],
    meta: Optional[dict],
    analysis_context: AnalysisContext,
    document_context: Optional[DocumentContext] = None,
) -> Dict:
    quality = build_data_quality_summary(raw_data, meta or {})
    topic_hint = analysis_context.task_topic or str((meta or {}).get("topic") or "")
    evidence_catalog = select_key_samples(
        raw_data,
        limit=MAX_EVIDENCE_CATALOG_COUNT,
        topic_hint=topic_hint,
    )
    key_samples = list(analysis_context.evidence_samples) or select_key_samples(
        raw_data,
        topic_hint=topic_hint,
    )
    timeline = build_timeline(raw_data)
    analysis = build_analysis_summary(analysis_context)
    sections = serialize_sections(document_context) if document_context else []
    grounding = build_grounding_summary(sections, evidence_catalog)
    quality = append_report_evidence_check(
        quality,
        grounding,
        meta=meta or {},
        template_id=document_context.template_id if document_context else "",
        raw_data=raw_data,
    )
    return {
        "quality": quality,
        "key_samples": key_samples,
        "evidence_catalog": evidence_catalog,
        "timeline": timeline,
        "analysis": analysis,
        "sections": sections,
        "grounding": grounding,
    }


def attach_report_metadata(
    document_context: DocumentContext,
    raw_data: List[dict],
    meta: Optional[dict],
    analysis_context: AnalysisContext,
) -> Dict:
    report_meta = build_report_metadata(raw_data, meta, analysis_context, document_context)
    document_context.metadata["report_quality"] = report_meta["quality"]
    document_context.metadata["key_samples"] = _traceability_samples(
        report_meta["key_samples"],
        report_meta["evidence_catalog"],
        report_meta["grounding"].get("cited_sample_ids") or [],
    )
    document_context.metadata["evidence_catalog"] = report_meta["evidence_catalog"]
    document_context.metadata["timeline"] = report_meta["timeline"]
    document_context.metadata["analysis_summary"] = report_meta["analysis"]
    document_context.metadata["grounding_summary"] = report_meta["grounding"]
    return report_meta


def _traceability_samples(
    key_samples: List[Dict],
    evidence_catalog: List[Dict],
    cited_sample_ids: List[str],
) -> List[Dict]:
    """Keep the compact list, then append any extra evidence cited in the report."""
    selected = list(key_samples or [])
    selected_ids = {
        str(sample.get("reference_id") or "")
        for sample in selected
        if isinstance(sample, dict)
    }
    by_id = {
        str(sample.get("reference_id") or ""): sample
        for sample in evidence_catalog or []
        if isinstance(sample, dict) and sample.get("reference_id")
    }
    for reference_id in sorted(set(cited_sample_ids or []), key=_reference_sort_key):
        if reference_id in selected_ids or reference_id not in by_id:
            continue
        selected.append(by_id[reference_id])
        selected_ids.add(reference_id)
    return selected


def build_data_quality_summary(raw_data: List[dict], meta: Dict) -> Dict:
    data = [item for item in raw_data or [] if isinstance(item, dict)]
    total = len(data)
    real_count = sum(1 for item in data if item.get("data_type", "real") == "real")
    mock_count = sum(1 for item in data if item.get("data_type") == "mock")
    stable_count = sum(1 for item in data if item.get("source_group") == "stable")
    public_news_count = sum(1 for item in data if item.get("source_group") == "public_news")
    social_count = sum(1 for item in data if item.get("source_group") == "social")
    valid_url_count = sum(1 for item in data if _is_valid_url(item.get("url", "")))
    valid_pub_time_count = sum(1 for item in data if _has_confirmed_pub_time(item))
    empty_content_count = sum(1 for item in data if not str(item.get("content") or "").strip())
    source_types = Counter(_normalized_source_type(item) for item in data)
    platforms = Counter(str(item.get("platform") or item.get("source") or "未知") for item in data)
    avg_content_length = round(
        sum(len(str(item.get("content") or "")) for item in data) / total,
        1,
    ) if total else 0

    valid_url_rate = round(valid_url_count / total, 2) if total else 0
    valid_pub_time_rate = round(valid_pub_time_count / total, 2) if total else 0
    official_media_count = source_types.get("official", 0) + source_types.get("media", 0)
    official_media_rate = round(official_media_count / total, 2) if total else 0

    assessment = build_collection_assessment(data, meta)
    return {
        **assessment,
        "total": total,
        "real_count": real_count,
        "mock_count": mock_count,
        "stable_count": stable_count,
        "public_news_count": public_news_count,
        "social_count": social_count,
        "valid_url_count": valid_url_count,
        "valid_pub_time_count": valid_pub_time_count,
        "empty_content_count": empty_content_count,
        "avg_content_length": avg_content_length,
        "valid_url_rate": valid_url_rate,
        "valid_pub_time_rate": valid_pub_time_rate,
        "official_media_count": official_media_count,
        "official_media_rate": official_media_rate,
        "platform_distribution": dict(platforms),
        "source_type_distribution": dict(source_types),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def select_key_samples(
    raw_data: List[dict],
    limit: int = 8,
    topic_hint: str = "",
) -> List[Dict]:
    seen = set()
    seen_titles = set()
    samples = []
    ranked_items = sorted(
        [item for item in raw_data or [] if isinstance(item, dict)],
        key=lambda item: (_topic_title_relevance(item, topic_hint), *_sample_rank(item)),
        reverse=True,
    )
    # 先从每个平台各取一条代表样本，避免高互动单一平台垄断正文证据；
    # 再按质量排序补足剩余名额。
    platform_best = {}
    for item in ranked_items:
        platform = _clean(item.get("platform") or item.get("source") or "未知")
        if platform not in platform_best and not _is_low_signal_sample(
            _clean(item.get("title")),
            _clean(item.get("content")),
        ):
            platform_best[platform] = item
    candidates = list(platform_best.values())
    candidates.extend(item for item in ranked_items if item not in candidates)

    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"))
        content = _clean(item.get("content"))
        if _is_low_signal_sample(title, content):
            continue
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        title_key = re.sub(r"\W+", "", title).casefold()[:80]
        if title_key and title_key in seen_titles:
            continue
        seen.add(key)
        if title_key:
            seen_titles.add(title_key)
        reference_id = f"S{len(samples) + 1}"
        samples.append({
            "reference_id": reference_id,
            "title": title[:120],
            "platform": _clean(item.get("platform") or item.get("source")),
            "source": _clean(item.get("source")),
            "source_type": _clean(item.get("source_type") or "unknown"),
            "source_group": _clean(item.get("source_group") or "unknown"),
            "pub_time": _clean(item.get("pub_time")),
            "time_basis": _clean(item.get("time_basis") or "unknown"),
            "url": _clean(item.get("url")),
            "author": _clean(item.get("author")),
            "heat_index": item.get("heat_index", 0),
            "like_count": _safe_int(item.get("like_count")),
            "comment_count": _safe_int(item.get("comment_count")),
            "repost_count": _safe_int(item.get("repost_count")),
            "view_count": _safe_int(item.get("view_count")),
            "content_excerpt": content[:120],
            "content_category": _clean(item.get("content_category") or "其他"),
            "content_category_source": _clean(item.get("content_category_source") or "machine"),
            "sentiment_label": _clean(item.get("sentiment_label") or "中性"),
            "sentiment_source": _clean(item.get("sentiment_source") or "machine"),
            "review_note": _clean((item.get("human_review") or {}).get("note")),
        })
        if len(samples) >= limit:
            break
    return samples


def build_timeline(raw_data: List[dict], limit: int = 12) -> List[Dict]:
    events = []
    seen = set()
    for item in raw_data or []:
        if not isinstance(item, dict) or not _has_confirmed_pub_time(item):
            continue
        if _is_low_signal_sample(_clean(item.get("title")), _clean(item.get("content"))):
            continue
        dt = _parse_pub_time(item.get("pub_time"))
        if not dt:
            continue
        key = (dt.isoformat(timespec="minutes"), _clean(item.get("title"))[:80])
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "time": dt.isoformat(timespec="minutes"),
            "date": dt.date().isoformat(),
            "display_time": _format_timeline_time(dt, item.get("pub_time")),
            "title": _clean(item.get("title"))[:120],
            "platform": _clean(item.get("platform") or item.get("source")),
            "source": _clean(item.get("source")),
            "url": _clean(item.get("url")),
            "source_type": _clean(item.get("source_type") or "unknown"),
        })
    events.sort(key=lambda item: item["time"])
    return events[:limit]


def build_analysis_summary(context: AnalysisContext) -> Dict:
    start, end = context.time_range
    return {
        "event_keyword": context.event_keyword,
        "total_posts": context.total_posts,
        "heat_index": context.heat_index,
        "time_range": {
            "start": start.isoformat(timespec="minutes") if start else "",
            "end": end.isoformat(timespec="minutes") if end else "",
        },
        "platform_dist": context.platform_dist,
        "sentiment_ratio": context.sentiment_ratio,
        "top_keywords": context.top_keywords[:10],
        "official_responses": context.official_responses[:5],
        "netizen_opinions": context.netizen_opinions[:5],
        "risk_points": context.risk_points[:5],
        "case_progress": context.case_progress,
        "main_event": context.main_event,
        "case_location": context.case_location,
        "case_type": context.case_type,
        "injury_count": context.injury_count,
        "task_topic": context.task_topic,
        "query_keywords": context.query_keywords,
        "confirmed_time_count": context.confirmed_time_count,
        "source_type_dist": context.source_type_dist,
        "content_category_dist": context.content_category_dist,
        "human_reviewed_count": context.human_reviewed_count,
        "data_limitations": context.data_limitations,
    }


def build_grounding_summary(sections: List[Dict], key_samples: List[Dict]) -> Dict:
    valid_ids = {
        str(sample.get("reference_id"))
        for sample in key_samples
        if sample.get("reference_id")
    }
    cited_ids = []
    citations_by_section = {}
    for section in sections or []:
        content = str(section.get("content") or "")
        ids = re.findall(r"\[(S\d+)\]", content)
        if ids:
            citations_by_section[section.get("id") or ""] = ids
            cited_ids.extend(ids)
    unique_cited = sorted(set(cited_ids), key=_reference_sort_key)
    return {
        "citation_count": len(cited_ids),
        "cited_sample_count": len(set(cited_ids) & valid_ids),
        "available_sample_count": len(valid_ids),
        "cited_sample_ids": unique_cited,
        "unknown_sample_ids": sorted(set(cited_ids) - valid_ids, key=_reference_sort_key),
        "citations_by_section": citations_by_section,
    }


def serialize_sections(document_context: DocumentContext) -> List[Dict]:
    if not document_context:
        return []
    order = document_context.metadata.get("section_order") or list(document_context.sections.keys())
    names = document_context.metadata.get("section_names", {})
    review = document_context.metadata.get("section_review", {})
    sections = []
    for section_id in order:
        if section_id not in document_context.sections:
            continue
        sections.append({
            "id": section_id,
            "name": names.get(section_id, "标题" if section_id == "title" else section_id),
            "content": document_context.sections.get(section_id, ""),
            "is_title": section_id == "title",
            "require_manual_review": bool(review.get(section_id)),
        })
    return sections


def _sample_rank(item: dict):
    heat = _safe_float(item.get("heat_index"))
    interaction = (
        _safe_int(item.get("like_count"))
        + _safe_int(item.get("comment_count")) * 2
        + _safe_int(item.get("repost_count")) * 1.5
        + min(_safe_int(item.get("view_count")) / 100, 1000)
    )
    content_len = len(str(item.get("content") or ""))
    has_url = 1 if _is_valid_url(item.get("url", "")) else 0
    has_time = 1 if _has_confirmed_pub_time(item) else 0
    return heat, interaction, content_len, has_url, has_time


def _is_low_signal_sample(title: str, content: str) -> bool:
    normalized_title = re.sub(r"\s+", "", title or "")
    generic_titles = {
        "猜你想搜", "相关推荐", "搜索结果", "更多内容", "热门推荐",
        "登录后查看更多", "暂无内容",
    }
    if normalized_title in generic_titles:
        return True
    return len((content or "").strip()) < 12 and len((title or "").strip()) < 12


def _reference_sort_key(reference_id: str):
    match = re.search(r"\d+", str(reference_id or ""))
    return int(match.group()) if match else 10**9


def _topic_title_relevance(item: dict, topic_hint: str) -> int:
    topic = re.sub(r"\s+", "", str(topic_hint or ""))
    if not topic:
        return 0
    title = re.sub(r"\s+", "", str(item.get("title") or ""))
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", topic)
    terms = set()
    for chunk in chinese_chunks:
        max_size = min(4, len(chunk))
        for size in range(2, max_size + 1):
            terms.update(chunk[index:index + size] for index in range(len(chunk) - size + 1))
    return sum(1 for term in terms if term in title)


def _normalized_source_type(item: dict) -> str:
    source_type = str(item.get("source_type") or "unknown").strip().lower()
    source_group = str(item.get("source_group") or "").strip().lower()
    source = _clean(item.get("source"))
    if source_group == "stable":
        return "official" if source_type == "official" else source_type
    if source_type == "official":
        official_markers = ("政府", "公安", "警方", "应急管理", "气象局", "人民政府", "发布")
        media_markers = ("新闻", "电视台", "日报", "晚报", "广播")
        if any(marker in source for marker in official_markers):
            return "official"
        if any(marker in source for marker in media_markers):
            return "media"
        return "public"
    return source_type


def _is_valid_url(url: str) -> bool:
    return is_valid_url(url)


def _has_confirmed_pub_time(item: dict) -> bool:
    return has_confirmed_pub_time(item)


def _parse_pub_time(value) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_timeline_time(dt: datetime, raw_value) -> str:
    raw_text = str(raw_value or "")
    if len(raw_text.strip()) <= 10:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M")


def _clean(value) -> str:
    text = str(value or "")
    text = (
        text.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\u2060", "")
        .replace("【", "")
        .replace("】", "")
    )
    return " ".join(text.split())


def _safe_int(value) -> int:
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("+", "")
        return int(float(value or 0))
    except Exception:
        return 0


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0
