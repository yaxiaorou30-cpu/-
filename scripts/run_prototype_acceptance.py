#!/usr/bin/env python3
"""Run a read-only prototype acceptance pass without exposing account secrets."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import web_app
from src.crawler import NewsCrawler
from src.orchestrator import Orchestrator


TARGET_PLATFORMS = ["抖音", "小红书", "微博", "B站", "百度贴吧"]
SENSITIVE_RECORD_FIELDS = {
    "login_evidence",
    "auth_mode",
    "session_mode",
    "login_confirmed",
}


def configure_account(crawler: NewsCrawler, platform: str, account: dict) -> None:
    if not account:
        return
    crawler.set_account(
        platform,
        account.get("username", ""),
        account.get("password", ""),
        account.get("cookie", ""),
        account.get("note", ""),
        browser_session=account.get("browser_session", ""),
        browser_cookie=account.get("browser_cookie", ""),
        session_mode=account.get("session_mode", ""),
    )


def safe_failure_kinds(meta: dict) -> list[str]:
    return sorted({
        str(item.get("error") or "unknown failure")[:160]
        for item in (meta.get("failures") or [])
    })


def record_quality(records: list[dict], *, social: bool = False) -> dict:
    total = len(records)
    valid_urls = 0
    traceable = 0
    readable = 0
    authors = 0
    timed = 0
    for record in records:
        parsed = urlparse(str(record.get("url") or ""))
        has_url = parsed.scheme in ("http", "https") and bool(parsed.netloc)
        has_source = bool(record.get("source") or record.get("platform"))
        has_text = bool(record.get("title") or record.get("content"))
        has_author = bool(record.get("author") or record.get("source"))
        has_time = bool(record.get("pub_time") or record.get("crawl_time"))
        valid_urls += int(has_url)
        traceable += int(has_url and has_source)
        readable += int(has_text)
        authors += int(has_author)
        timed += int(has_time)
    denominator = total or 1
    result = {
        "record_count": total,
        "valid_url_rate": round(valid_urls / denominator, 2) if total else 0,
        "traceable_rate": round(traceable / denominator, 2) if total else 0,
        "readable_rate": round(readable / denominator, 2) if total else 0,
        "time_rate": round(timed / denominator, 2) if total else 0,
    }
    if social:
        result["author_rate"] = round(authors / denominator, 2) if total else 0
    return result


def sanitized_records(records: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in record.items() if key not in SENSITIVE_RECORD_FIELDS}
        for record in records
    ]


def run(args: argparse.Namespace) -> dict:
    started_at = datetime.now()
    run_id = started_at.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir or f"output/prototype-acceptance-{run_id}")
    output_dir.mkdir(parents=True, exist_ok=False)

    accounts = web_app.sanitize_accounts({}, include_saved=True)
    all_records = []
    platform_results = {}

    public_crawler = NewsCrawler(use_external_social_adapters=False)
    public_records = public_crawler.crawl(
        keywords=[args.keyword],
        max_results=2,
        stable_sources=["官方公开网页"],
        time_range="近一年",
        collect_level="最小采集",
        source_strategy="stable",
        min_real_results=1,
    )
    all_records.extend(public_records)
    public_result = {
        **record_quality(public_records),
        "failure_count": len(public_crawler.last_meta.get("failures") or []),
        "failure_kinds": safe_failure_kinds(public_crawler.last_meta),
        "support_claim": "A0/S2 prototype evidence only",
    }

    for platform in TARGET_PLATFORMS:
        account = accounts.get(platform) or {}
        crawler = NewsCrawler(use_external_social_adapters=True)
        configure_account(crawler, platform, account)
        records = crawler.crawl(
            keywords=[args.keyword],
            max_results=1,
            social_platforms=[platform],
            time_range="近一年",
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        all_records.extend(records)
        probe = (crawler.last_meta.get("social_auth") or {}).get(platform) or {}
        platform_results[platform] = {
            "account_session_ready": bool(account.get("browser_session") or account.get("cookie")),
            "login_confirmed": probe.get("login_confirmed"),
            **record_quality(records, social=True),
            "failure_count": len(crawler.last_meta.get("failures") or []),
            "failure_kinds": safe_failure_kinds(crawler.last_meta),
            "support_claim": "A1/S3 candidate evidence only",
        }

    writer = NewsCrawler()
    combined_records = sanitized_records(writer._deduplicate_results(all_records))
    data_path = output_dir / "acceptance_data.json"
    meta_path = output_dir / "acceptance_data_meta.json"
    report_path = output_dir / "acceptance_report.docx"
    summary_path = output_dir / "acceptance_summary.json"

    data_path.write_text(json.dumps(combined_records, ensure_ascii=False, indent=2), encoding="utf-8")
    aggregate_quality = record_quality(combined_records)
    meta_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "purpose": "prototype acceptance; not an S3 certification",
        "keyword_count": 1,
        "public": public_result,
        "platforms": platform_results,
        "aggregate_quality": aggregate_quality,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    report_generated = False
    report_preview_generated = False
    report_size = 0
    report_error = ""
    if combined_records:
        try:
            orchestrator = Orchestrator()
            preview = orchestrator.build_report_preview(str(data_path), "police_report")
            report_preview_generated = bool(preview)
            generated_path = orchestrator.generate_report(
                str(data_path),
                "police_report",
                str(report_path),
            )
            report_path = Path(generated_path)
            report_generated = report_path.exists() and report_path.stat().st_size > 0
            report_size = report_path.stat().st_size if report_generated else 0
        except Exception as exc:
            report_error = str(exc)[:240]

    passed_platforms = [
        platform for platform, result in platform_results.items()
        if result["login_confirmed"] is True
        and result["record_count"] > 0
        and result["traceable_rate"] == 1.0
        and result["readable_rate"] == 1.0
    ]
    blocked_platforms = [platform for platform in TARGET_PLATFORMS if platform not in passed_platforms]
    overall_status = "prototype_passed" if not blocked_platforms and public_records and report_generated else "partial"
    summary = {
        "generated_at": datetime.now().isoformat(),
        "duration_seconds": round((datetime.now() - started_at).total_seconds(), 2),
        "status": overall_status,
        "scope": "P0 prototype collection-analysis-report flow",
        "not_a_claim": "This run does not grant S3 status or prove business accuracy/recall.",
        "combined_record_count": len(combined_records),
        "aggregate_quality": aggregate_quality,
        "public": public_result,
        "platforms": platform_results,
        "passed_platforms": passed_platforms,
        "blocked_platforms": blocked_platforms,
        "report": {
            "preview_generated": report_preview_generated,
            "docx_generated": report_generated,
            "size_bytes": report_size,
            "error": report_error,
        },
        "requirements": {
            "FR-003": "partial" if blocked_platforms else "prototype evidence passed",
            "FR-005": "mechanism exercised; business taxonomy still needs client review",
            "FR-006": "mechanism exercised; no accuracy claim without a frozen labeled set",
            "FR-007": "mechanism exercised; factual quality still needs client review",
            "FR-008": "prototype evidence passed" if report_generated else "failed",
            "FR-011/NFR-005": "implemented separately as single-local-account authentication; verify with E2E-007",
            "NFR-008": (
                "public crawler and authorized-session access are separated; "
                "stop-on-verification/risk-control is implemented; "
                "formal S3 still requires three successful cross-time acceptance runs"
            ),
        },
        "artifacts": {
            "data": str(data_path),
            "meta": str(meta_path),
            "report": str(report_path) if report_generated else "",
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only P0 prototype acceptance flow.")
    parser.add_argument("--keyword", default="警方通报")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = run(args)
    safe_console = {
        "status": summary["status"],
        "combined_record_count": summary["combined_record_count"],
        "passed_platforms": summary["passed_platforms"],
        "blocked_platforms": summary["blocked_platforms"],
        "report": summary["report"],
        "artifacts": summary["artifacts"],
    }
    print("SAFE_ACCEPTANCE_RESULT=" + json.dumps(safe_console, ensure_ascii=False))


if __name__ == "__main__":
    main()
