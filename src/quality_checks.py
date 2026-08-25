"""统一的采集与报告检查清单。

本模块刻意不计算 0—100 分。每个检查项都给出可核对的实际值、
明确状态和下一步动作，网页、桌面端、命令行与 Word 报告共用同一结果。
"""

from collections import Counter
from datetime import datetime
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


CHECK_STATUS_LABELS = {
    "pass": "通过",
    "warning": "需复核",
    "fail": "未通过",
}

COLLECTION_STATUS_LABELS = {
    "ready_for_review": "可进入人工审核",
    "needs_attention": "需要补充或复核",
    "collection_failed": "采集失败",
}

_SOURCE_GROUPS = {"stable", "public_news", "social"}
_SOURCE_STRATEGY_ALIASES = {
    "hybrid": "all",
    "stable_first": "all",
    "stable-first": "all",
    "stablefirst": "all",
    "public_first": "all",
    "public": "stable",
}


def build_collection_assessment(raw_data: List[dict], meta: Optional[dict] = None) -> Dict:
    """根据实际记录和任务条件生成统一检查清单。"""
    data = [item for item in raw_data or [] if isinstance(item, dict)]
    meta = meta or {}
    total = len(data)
    real_count = sum(1 for item in data if item.get("data_type", "real") == "real")
    mock_count = sum(1 for item in data if item.get("data_type") == "mock")
    stable_count = sum(1 for item in data if item.get("source_group") == "stable")
    public_news_count = sum(1 for item in data if item.get("source_group") == "public_news")
    social_count = sum(1 for item in data if item.get("source_group") == "social")
    valid_url_count = sum(1 for item in data if is_valid_url(item.get("url", "")))
    valid_time_count = sum(1 for item in data if has_confirmed_pub_time(item))
    empty_content_count = sum(
        1
        for item in data
        if item.get("body_fetch_status") == "failed"
        or not str(item.get("content") or item.get("title") or "").strip()
    )

    selected_social = _unique_strings(meta.get("social_platforms") or meta.get("platforms") or [])
    selected_stable = _unique_strings(meta.get("stable_sources") or [])
    active_source_groups = _resolve_active_source_groups(meta)
    failures = [item for item in meta.get("failures", []) if isinstance(item, dict)]
    minimum_real = max(1, _safe_int(meta.get("min_real_results"), 3))

    platform_distribution = Counter(
        str(item.get("platform") or item.get("source") or "未知") for item in data
    )
    covered_social = [name for name in selected_social if platform_distribution.get(name, 0) > 0]
    duplicate_title_count = _duplicate_title_count(data)

    valid_url_rate = valid_url_count / total if total else 0.0
    valid_time_rate = valid_time_count / total if total else 0.0
    duplicate_rate = duplicate_title_count / total if total else 0.0

    checks = [_real_data_check(real_count, mock_count, minimum_real)]
    if active_source_groups is None or "social" in active_source_groups:
        checks.append(
            _platform_coverage_check(
                selected_social=selected_social,
                covered_social=covered_social,
                platform_distribution=platform_distribution,
                social_count=social_count,
            )
        )
    if active_source_groups is None or "stable" in active_source_groups:
        checks.append(_government_source_check(stable_count, selected_stable))
    checks.extend([
        _rate_check(
            check_id="source_links",
            label="原文链接",
            count=valid_url_count,
            total=total,
            pass_rate=0.8,
            fail_rate=0.5,
            warning_detail="部分结果不能直接返回原文，请在报告前补采或人工核对。",
            fail_detail="多数结果无法追溯原文，当前采集不能作为报告依据。",
        ),
        _publication_time_check(valid_time_count, total),
        _content_check(total, empty_content_count),
        _duplicate_check(total, duplicate_title_count, duplicate_rate),
        _failure_check(failures, real_count),
    ])

    critical_failed = any(
        item["status"] == "fail"
        for item in checks
        if item["id"] in {"real_data", "social_platforms", "source_links", "content_complete"}
    )
    assessment = _assessment_from_checks(checks, critical_failed=critical_failed)
    assessment["statistics"] = {
        "total": total,
        "real_count": real_count,
        "mock_count": mock_count,
        "stable_count": stable_count,
        "public_news_count": public_news_count,
        "social_count": social_count,
        "minimum_real_results": minimum_real,
        "valid_url_count": valid_url_count,
        "valid_time_count": valid_time_count,
        "empty_content_count": empty_content_count,
        "duplicate_title_count": duplicate_title_count,
        "valid_url_rate": round(valid_url_rate, 2),
        "valid_time_rate": round(valid_time_rate, 2),
        "title_duplicate_rate": round(duplicate_rate, 2),
        "selected_social_count": len(selected_social),
        "covered_social_count": len(covered_social),
        "selected_stable_count": len(selected_stable),
        "failure_count": len(failures),
        "platform_distribution": dict(platform_distribution),
    }
    assessment["checked_at"] = datetime.now().isoformat(timespec="seconds")
    return assessment


def append_report_evidence_check(
    assessment: Dict,
    grounding: Optional[dict],
    *,
    meta: Optional[dict] = None,
    template_id: str = "",
    raw_data: Optional[List[dict]] = None,
) -> Dict:
    """把人工审核、模板匹配和正文引用加入同一份报告清单。"""
    grounding = grounding or {}
    result = dict(assessment or {})
    checks = [dict(item) for item in result.get("checks", [])]
    if meta is not None:
        checks.append(_manual_review_check(meta, len(raw_data or [])))
    if template_id:
        checks.append(_template_fit_check(template_id, meta or {}, raw_data or []))
    unknown_ids = grounding.get("unknown_sample_ids") or []
    cited_count = _safe_int(grounding.get("cited_sample_count"), 0)
    available_count = _safe_int(grounding.get("available_sample_count"), 0)

    if unknown_ids:
        report_check = _check(
            "report_citations",
            "报告引用",
            "fail",
            f"{len(unknown_ids)} 个引用无对应样本",
            f"修正未知样本编号：{'、'.join(str(item) for item in unknown_ids)}。",
        )
    elif available_count and cited_count:
        report_check = _check(
            "report_citations",
            "报告引用",
            "pass",
            f"{cited_count}/{available_count} 条重点样本已引用",
            "正文引用均能定位到重点样本和原文链接。",
        )
    else:
        report_check = _check(
            "report_citations",
            "报告引用",
            "warning",
            "没有可核对的正文引用",
            "报告正文缺少可追溯样本，请先检查可用数据和报告内容。",
        )
    checks.append(report_check)

    critical_failed = result.get("status_code") == "collection_failed"
    refreshed = dict(result)
    refreshed.update(_assessment_from_checks(checks, critical_failed=critical_failed))
    refreshed["statistics"] = dict(result.get("statistics") or {})
    refreshed["checked_at"] = datetime.now().isoformat(timespec="seconds")
    return refreshed


def is_valid_url(value) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def has_confirmed_pub_time(item: dict) -> bool:
    value = str(item.get("pub_time") or "").strip()
    if not value or value in {"-", "unknown", "未知"}:
        return False
    if item.get("time_basis") == "unknown":
        return False
    return not _is_suspicious_social_pub_time(item)


def _assessment_from_checks(checks: List[Dict], critical_failed: bool = False) -> Dict:
    attention = [item for item in checks if item.get("status") != "pass"]
    if critical_failed:
        code = "collection_failed"
        detail = "关键采集检查未通过，请先处理失败项后重新采集。"
    elif attention:
        code = "needs_attention"
        detail = f"数据可以继续查看，但有 {len(attention)} 项需要补充或人工复核。"
    else:
        code = "ready_for_review"
        detail = "所有自动检查均已通过，可以进入人工审核；系统不代替人工定稿。"
    return {
        "status_code": code,
        "status_label": COLLECTION_STATUS_LABELS[code],
        "status_detail": detail,
        "ready_for_review": code == "ready_for_review",
        "checks": checks,
        "action_items": [item["detail"] for item in attention if item.get("detail")],
    }


def _real_data_check(real_count: int, mock_count: int, minimum: int) -> Dict:
    if real_count == 0:
        status = "fail"
        detail = "未取得真实数据，请检查关键词、网络、来源或平台登录状态。"
    elif real_count < minimum or mock_count:
        status = "warning"
        parts = []
        if real_count < minimum:
            parts.append(f"还差 {minimum - real_count} 条达到本任务设置的数量")
        if mock_count:
            parts.append(f"排除 {mock_count} 条模拟数据后再生成报告")
        detail = "；".join(parts) + "。"
    else:
        status = "pass"
        detail = "真实记录数量达到本任务设置，且未混入模拟数据。"
    return _check(
        "real_data",
        "真实数据",
        status,
        f"{real_count}/{minimum} 条" + (f"，模拟 {mock_count} 条" if mock_count else ""),
        detail,
    )


def _platform_coverage_check(
    selected_social: List[str],
    covered_social: List[str],
    platform_distribution: Counter,
    social_count: int,
) -> Dict:
    if selected_social:
        missing = [name for name in selected_social if name not in covered_social]
        if not covered_social:
            status = "fail"
            detail = "已选社交平台均未返回结果，请逐个平台检查登录状态和作业日志。"
        elif missing:
            status = "warning"
            detail = f"以下已选平台没有结果：{'、'.join(missing)}。"
        else:
            status = "pass"
            detail = "所有已选社交平台都返回了至少一条结果。"
        value = f"{len(covered_social)}/{len(selected_social)} 个已选平台有结果"
    else:
        covered_count = len([name for name, count in platform_distribution.items() if count > 0])
        status = "pass" if covered_count else "fail"
        value = f"{covered_count} 个平台有结果"
        detail = "当前数据包含可识别的平台来源。" if covered_count else "没有可识别的平台结果。"
    if social_count == 0 and status == "pass":
        status = "warning"
        detail = "当前没有社交平台样本，网民观点覆盖需要补充。"
    return _check("social_platforms", "社交平台覆盖", status, value, detail)


def _government_source_check(stable_count: int, selected_stable: List[str]) -> Dict:
    selected_note = f"（已选 {len(selected_stable)} 个官网）" if selected_stable else ""
    if stable_count:
        return _check(
            "government_sources",
            "政府官网",
            "pass",
            f"{stable_count} 条{selected_note}",
            "已取得政府官网公开信息，可用于事实核对。",
        )
    return _check(
        "government_sources",
        "政府官网",
        "warning",
        f"0 条{selected_note}",
        "未取得政府官网结果；报告中的事实性判断需补充权威来源或明确标注限制。",
    )


def _rate_check(
    check_id: str,
    label: str,
    count: int,
    total: int,
    pass_rate: float,
    fail_rate: float,
    warning_detail: str,
    fail_detail: str,
) -> Dict:
    rate = count / total if total else 0.0
    if total and rate >= pass_rate:
        status = "pass"
        detail = f"{count} 条记录可以直接核对{label}。"
    elif total and rate >= fail_rate:
        status = "warning"
        detail = warning_detail
    else:
        status = "fail"
        detail = fail_detail
    return _check(check_id, label, status, f"{count}/{total} 条有效", detail)


def _publication_time_check(count: int, total: int) -> Dict:
    rate = count / total if total else 0.0
    if total and rate >= 0.8:
        status = "pass"
        detail = "大部分记录具有可靠发布时间，可以生成时间线。"
    else:
        status = "warning"
        detail = "发布时间不完整，时间线和时效判断必须只使用已确认时间的记录。"
    return _check("publication_time", "可靠发布时间", status, f"{count}/{total} 条已确认", detail)


def _content_check(total: int, empty_count: int) -> Dict:
    valid_count = max(0, total - empty_count)
    if total == 0 or valid_count == 0:
        status = "fail"
        detail = "没有可供阅读和分析的正文；正文获取失败或内容为空的记录需要补采或人工核查。"
    elif empty_count:
        status = "warning"
        detail = f"有 {empty_count} 条记录正文获取失败或没有可用内容，请补采或进行人工核查。"
    else:
        status = "pass"
        detail = "未发现正文获取失败或标题、内容同时为空的记录。"
    return _check("content_complete", "内容完整", status, f"{valid_count}/{total} 条有内容", detail)


def _duplicate_check(total: int, duplicate_count: int, duplicate_rate: float) -> Dict:
    if duplicate_rate > 0.7:
        status = "fail"
        detail = "重复结果过多，请调整去重规则后重新整理数据。"
    elif duplicate_rate > 0.3:
        status = "warning"
        detail = "重复结果较多，生成报告前应先人工去重。"
    else:
        status = "pass"
        detail = "标题重复比例未超过提醒线。"
    return _check("duplicates", "重复结果", status, f"{duplicate_count}/{total} 条重复", detail)


def _failure_check(failures: List[dict], real_count: int) -> Dict:
    failure_count = len(failures)
    if not failure_count:
        status = "pass"
        detail = "本次任务没有记录到来源采集失败。"
    elif real_count:
        status = "warning"
        detail = "部分来源采集失败，请在作业日志中逐项处理后决定是否补采。"
    else:
        status = "fail"
        detail = "来源采集失败且没有真实结果，请先处理作业日志中的错误。"
    return _check("collection_failures", "采集失败", status, f"{failure_count} 个失败记录", detail)


def _manual_review_check(meta: dict, current_total: int) -> Dict:
    review = meta.get("review") if isinstance(meta.get("review"), dict) else {}
    reviewed_at = str(review.get("reviewed_at") or "").strip()
    kept_total = _safe_int(review.get("kept_total"), -1)
    labels_confirmed = bool(review.get("labels_confirmed"))
    if reviewed_at and kept_total == current_total and labels_confirmed:
        return _check(
            "manual_review",
            "人工数据审核",
            "pass",
            f"已审核并保留 {kept_total} 条",
            "当前报告数据、内容分类和情感标签与最近一次保存的人工审核结果一致。",
        )
    return _check(
        "manual_review",
        "人工数据审核",
        "warning",
        "尚未保存当前数据的审核结果",
        "先到“数据审核”逐条核对原文、分类和情感标签并保存，再生成报告草稿。",
    )


def _template_fit_check(template_id: str, meta: dict, raw_data: List[dict]) -> Dict:
    template_names = {
        "event_report": "通用事件类",
        "police_report": "案件侦办类",
        "risk_report": "风险研判类",
    }
    label = template_names.get(template_id, template_id or "未知模板")
    if template_id == "event_report":
        return _check(
            "template_fit",
            "报告模板",
            "pass",
            label,
            "通用事件模板适用于当前任务；如需案件或风险专报，可人工切换后复核。",
        )

    topic = str(meta.get("topic") or "")
    sample_text = " ".join(
        f"{item.get('title', '')} {item.get('content', '')}"
        for item in raw_data[:20]
        if isinstance(item, dict)
    )
    haystack = f"{topic} {sample_text}"
    term_sets = {
        "police_report": (
            "案件", "公安", "警方", "民警", "嫌疑", "刑事", "治安", "侦办", "抓获", "立案",
        ),
        "risk_report": (
            "风险", "隐患", "谣言", "投诉", "质疑", "争议", "预警", "负面", "舆情危机",
        ),
    }
    matched = [term for term in term_sets.get(template_id, ()) if term in haystack]
    if matched:
        return _check(
            "template_fit",
            "报告模板",
            "pass",
            f"{label}（命中：{'、'.join(matched[:3])}）",
            "当前样本包含与所选模板相符的明确文本线索。",
        )
    return _check(
        "template_fit",
        "报告模板",
        "warning",
        f"{label}可能不匹配",
        "当前样本没有找到支持该专用模板的明确线索，建议改用“通用事件类”。",
    )


def _check(check_id: str, label: str, status: str, value: str, detail: str) -> Dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "status_label": CHECK_STATUS_LABELS[status],
        "value": value,
        "detail": detail,
    }


def _duplicate_title_count(data: List[dict]) -> int:
    titles = Counter()
    for item in data:
        title = re.sub(r"\s+", "", str(item.get("title") or "")).casefold()
        if title:
            titles[title] += 1
    return sum(count - 1 for count in titles.values() if count > 1)


def _is_suspicious_social_pub_time(item: dict) -> bool:
    social_platforms = {
        "微博", "知乎", "B站", "百度贴吧", "豆瓣", "小红书", "抖音",
        "快手", "今日头条", "微信公众平台",
    }
    platform = str(item.get("platform") or "")
    if item.get("source_group") != "social" and platform not in social_platforms:
        return False
    try:
        dt = datetime.fromisoformat(str(item.get("pub_time") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return dt.year <= datetime.now().year - 5


def _unique_strings(values) -> List[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _resolve_active_source_groups(meta: dict) -> Optional[set]:
    raw_groups = meta.get("active_source_groups")
    if isinstance(raw_groups, list) and raw_groups:
        groups = [str(value or "").strip().lower() for value in raw_groups]
        if groups and all(group in _SOURCE_GROUPS for group in groups):
            return set(groups)

    task_payload = meta.get("task_payload")
    payload_strategy = (
        task_payload.get("source_strategy") if isinstance(task_payload, dict) else ""
    )
    for value in (meta.get("source_strategy"), payload_strategy):
        strategy = str(value or "").strip().lower()
        strategy = _SOURCE_STRATEGY_ALIASES.get(strategy, strategy)
        if strategy == "all":
            return set(_SOURCE_GROUPS)
        if strategy in _SOURCE_GROUPS:
            return {strategy}
    return None


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
