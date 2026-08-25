"""逐条线索的基础分类、情感初判与人工审核数据处理。

机器结果只用于辅助筛选。人工保存审核结果后，保留机器初判，
同时将人工确认值作为报告统计使用的有效值。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
import threading
from typing import Dict, Iterable, List, Optional, Tuple


CONTENT_CATEGORIES: Tuple[str, ...] = (
    "政策与政务",
    "公共安全",
    "社会民生",
    "经济与产业",
    "科技与教育",
    "文化与体育",
    "交通与出行",
    "健康与医疗",
    "灾害与环境",
    "其他",
)
SENTIMENT_LABELS: Tuple[str, ...] = ("正面", "中性", "负面")


_CATEGORY_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "公共安全",
        (
            "公安", "警方", "警情", "案件", "犯罪", "诈骗", "违法", "拘留",
            "逮捕", "嫌疑人", "治安", "消防", "火灾", "伤亡", "应急处置",
        ),
    ),
    (
        "政策与政务",
        (
            "政策", "政府", "政务", "部门", "公告", "通知", "会议", "新闻发布会",
            "外交部", "移民管理", "出入境", "法规", "条例", "实施意见", "官方发布",
        ),
    ),
    (
        "灾害与环境",
        (
            "暴雨", "台风", "洪水", "地震", "灾害", "预警", "气象", "内涝",
            "生态", "环境", "污染", "高温", "大风", "降雪", "山火",
        ),
    ),
    (
        "交通与出行",
        (
            "交通", "道路", "高速", "地铁", "铁路", "航班", "机场", "车站",
            "出行", "拥堵", "停运", "公交", "列车", "延误",
        ),
    ),
    (
        "健康与医疗",
        (
            "医疗", "医院", "医生", "患者", "疾病", "健康", "药品", "疫苗",
            "公共卫生", "感染", "诊疗", "医保",
        ),
    ),
    (
        "科技与教育",
        (
            "科技", "科学", "数学", "研究", "科研", "高校", "大学", "教育",
            "学校", "教师", "学生", "算法", "人工智能", "AI", "芯片", "菲尔兹奖",
        ),
    ),
    (
        "经济与产业",
        (
            "经济", "产业", "企业", "市场", "金融", "消费", "就业", "投资",
            "贸易", "价格", "房产", "制造业", "营商",
        ),
    ),
    (
        "文化与体育",
        (
            "文化", "体育", "比赛", "赛事", "电影", "电视剧", "音乐", "演出",
            "明星", "文旅", "旅游", "博物馆", "艺术",
        ),
    ),
    (
        "社会民生",
        (
            "民生", "社区", "居民", "住房", "养老", "婚姻", "家庭", "儿童",
            "劳动者", "社会保障", "公共服务", "物业", "救助",
        ),
    ),
)

_POSITIVE_WORDS = {
    "好评", "支持", "点赞", "满意", "感谢", "欣慰", "祝贺", "恭喜", "认可",
    "成功", "突破", "恢复", "改善", "获奖", "致敬", "平安", "顺利", "骄傲",
    "感动", "优秀", "赞扬",
}
_NEGATIVE_WORDS = {
    "质疑", "不满", "失望", "愤怒", "谴责", "抗议", "担忧", "风险", "隐患",
    "事故", "伤亡", "死亡", "受伤", "诈骗", "犯罪", "谣言", "投诉", "失败",
    "崩溃", "造假", "违法", "污染", "延误", "停运", "尴尬", "破防", "争议",
    "批评", "可惜",
}


class _SentimentClassifier:
    def classify(self, text: str) -> Dict:
        normalized = _clean_text(text)
        positive_hits = sorted(word for word in _POSITIVE_WORDS if word in normalized)
        negative_hits = sorted(word for word in _NEGATIVE_WORDS if word in normalized)
        if len(positive_hits) > len(negative_hits):
            label = "正面"
            score = 0.7
        elif len(negative_hits) > len(positive_hits):
            label = "负面"
            score = 0.3
        else:
            label = "中性"
            score = 0.5
        hits = (positive_hits + negative_hits)[:6]
        basis = f"命中参考词：{'、'.join(hits)}" if hits else "未命中明显情感参考词"
        return {
            "label": label,
            "score": score,
            "method": "保守关键词规则",
            "basis": basis,
        }


_SENTIMENT_CLASSIFIER: Optional[_SentimentClassifier] = None
_SENTIMENT_LOCK = threading.Lock()


def classify_sentiment(text: str) -> Dict:
    global _SENTIMENT_CLASSIFIER
    if _SENTIMENT_CLASSIFIER is None:
        with _SENTIMENT_LOCK:
            if _SENTIMENT_CLASSIFIER is None:
                _SENTIMENT_CLASSIFIER = _SentimentClassifier()
    return _SENTIMENT_CLASSIFIER.classify(text)


def classify_content(record: Dict) -> Dict:
    text = _clean_text(
        " ".join(
            str(record.get(key) or "")
            for key in ("title", "content", "keyword", "source", "platform")
        )
    )
    ranked = []
    for order, (category, words) in enumerate(_CATEGORY_RULES):
        hits = [word for word in words if word.casefold() in text.casefold()]
        if hits:
            ranked.append((len(hits), -order, category, hits))
    if not ranked:
        return {
            "category": "其他",
            "basis": "未命中明显内容类别关键词",
            "uncertain": True,
        }

    ranked.sort(reverse=True)
    best_score, _, category, hits = ranked[0]
    tied = [item[2] for item in ranked if item[0] == best_score]
    uncertain = len(tied) > 1 or best_score == 1
    basis = f"命中参考词：{'、'.join(hits[:6])}"
    if len(tied) > 1:
        basis += f"；同时接近{'、'.join(tied[1:3])}"
    return {"category": category, "basis": basis, "uncertain": uncertain}


def annotate_record(record: Dict) -> Dict:
    """补齐机器初判和当前有效标签，不覆盖已存在的人工审核。"""
    annotated = deepcopy(record)
    content_result = classify_content(annotated)
    sentiment_result = classify_sentiment(
        f"{annotated.get('title') or ''}。{annotated.get('content') or ''}"
    )

    machine_category = _valid_category(
        annotated.get("machine_content_category")
    ) or content_result["category"]
    machine_sentiment = _valid_sentiment(
        annotated.get("machine_sentiment_label")
    ) or sentiment_result["label"]

    annotated["machine_content_category"] = machine_category
    annotated.setdefault("machine_content_category_basis", content_result["basis"])
    annotated.setdefault("machine_content_category_uncertain", content_result["uncertain"])
    annotated["machine_sentiment_label"] = machine_sentiment
    annotated.setdefault("machine_sentiment_score", sentiment_result["score"])
    annotated.setdefault("machine_sentiment_method", sentiment_result["method"])
    annotated.setdefault("machine_sentiment_basis", sentiment_result["basis"])

    human_review = annotated.get("human_review")
    if not isinstance(human_review, dict):
        human_review = {}
    reviewed_category = _valid_category(human_review.get("content_category"))
    reviewed_sentiment = _valid_sentiment(human_review.get("sentiment_label"))

    annotated["content_category"] = reviewed_category or machine_category
    annotated["content_category_source"] = "human_review" if reviewed_category else "machine"
    annotated["sentiment_label"] = reviewed_sentiment or machine_sentiment
    annotated["sentiment_source"] = "human_review" if reviewed_sentiment else "machine"
    annotated["analysis_reference_only"] = True
    return annotated


def annotate_records(records: Iterable[Dict]) -> List[Dict]:
    return [annotate_record(record) for record in records if isinstance(record, dict)]


def body_review_is_pending(record: Dict) -> bool:
    if not isinstance(record, dict) or record.get("body_fetch_status") != "failed":
        return False
    review = record.get("body_manual_review")
    return not (
        isinstance(review, dict)
        and str(review.get("reviewed_at") or "").strip()
    )


def apply_human_review(
    record: Dict,
    *,
    content_category: str,
    sentiment_label: str,
    note: str = "",
    reviewer: str = "",
    reviewed_at: str = "",
    body_verified: bool = False,
) -> Dict:
    annotated = annotate_record(record)
    category = _valid_category(content_category)
    sentiment = _valid_sentiment(sentiment_label)
    if not category:
        raise ValueError("请选择有效的内容分类")
    if not sentiment:
        raise ValueError("请选择有效的情感标签")

    timestamp = reviewed_at or datetime.now().isoformat(timespec="seconds")
    if body_review_is_pending(annotated) and body_verified is not True:
        raise ValueError("正文获取失败，请先打开原文完成人工核查，或取消保留该记录")
    if annotated.get("body_fetch_status") == "failed" and body_verified is True:
        annotated["body_manual_review"] = {
            "reviewed_at": timestamp,
            "reviewed_by": _clean_text(reviewer)[:64],
        }
    annotated["human_review"] = {
        "content_category": category,
        "sentiment_label": sentiment,
        "note": _clean_text(note)[:500],
        "reviewed_at": timestamp,
        "reviewed_by": _clean_text(reviewer)[:64],
        "category_changed": category != annotated["machine_content_category"],
        "sentiment_changed": sentiment != annotated["machine_sentiment_label"],
    }
    annotated["content_category"] = category
    annotated["content_category_source"] = "human_review"
    annotated["sentiment_label"] = sentiment
    annotated["sentiment_source"] = "human_review"
    annotated["analysis_reference_only"] = True
    return annotated


def effective_sentiment_label(record_extra: Dict, text: str) -> str:
    label = _valid_sentiment((record_extra or {}).get("sentiment_label"))
    if label:
        return label
    return classify_sentiment(text)["label"]


def effective_content_category(record_extra: Dict, record: Optional[Dict] = None) -> str:
    category = _valid_category((record_extra or {}).get("content_category"))
    if category:
        return category
    return classify_content(record or {})["category"]


def _valid_category(value) -> str:
    text = _clean_text(value)
    return text if text in CONTENT_CATEGORIES else ""


def _valid_sentiment(value) -> str:
    text = _clean_text(value)
    return text if text in SENTIMENT_LABELS else ""


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
