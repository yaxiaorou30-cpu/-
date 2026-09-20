"""Validation and internal policy selection for one collection target."""

from __future__ import annotations

import re


MIN_TARGET_RESULT_COUNT = 1
MAX_TARGET_RESULT_COUNT = 5_000


def parse_target_result_count(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("目标采集数量必须是 1–5000 的整数")
    if isinstance(value, int):
        target = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        target = int(value.strip())
    else:
        raise ValueError("目标采集数量必须是 1–5000 的整数")
    if not MIN_TARGET_RESULT_COUNT <= target <= MAX_TARGET_RESULT_COUNT:
        raise ValueError("目标采集数量必须在 1–5000 之间")
    return target


def collection_level_for_target(target: object) -> str:
    count = parse_target_result_count(target)
    if count <= 10:
        return "最小采集"
    if count <= 20:
        return "快速采集"
    if count <= 50:
        return "标准采集"
    return "深度采集"


def normalize_collection_target(payload: dict) -> dict:
    normalized = dict(payload or {})
    target = parse_target_result_count(normalized.get("max_results"))
    normalized["max_results"] = target
    normalized["min_real_results"] = target
    normalized["collect_level"] = collection_level_for_target(target)
    return normalized
