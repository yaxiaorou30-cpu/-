"""Persistent, server-side monitoring plans for incremental collection."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.executors.pool import ThreadPoolExecutor as APSchedulerThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler


SUPPORTED_INTERVALS = (15, 30, 60)
MAX_ACTIVE_PLANS = 5
MAX_STORED_PLANS = 60
MAX_RUNS_PER_PLAN = 50
MAX_NEW_ITEMS_PER_PLAN = 1000
MAX_FINGERPRINTS_PER_PLAN = 10000
MONITOR_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(MONITOR_TIMEZONE)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MONITOR_TIMEZONE)
    return parsed.astimezone(MONITOR_TIMEZONE)


def _text_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def normalize_monitor_payload(payload: dict) -> dict:
    """Keep only collection conditions; never persist credentials or cookies."""
    payload = payload if isinstance(payload, dict) else {}
    raw_keywords = payload.get("keywords")
    if isinstance(raw_keywords, str):
        keywords = [item.strip() for item in raw_keywords.replace("，", ",").split(",")]
        keywords = [item for item in keywords if item]
    else:
        keywords = _text_list(raw_keywords)

    min_real_results = payload.get("min_real_results")
    try:
        min_real_results = (
            int(min_real_results) if min_real_results not in (None, "") else None
        )
    except (TypeError, ValueError):
        min_real_results = None

    return {
        "topic": str(payload.get("topic") or "").strip(),
        "keywords": keywords,
        "region": str(payload.get("region") or "").strip() or "全国",
        "source_strategy": str(payload.get("source_strategy") or "stable_first").strip(),
        "collect_level": str(payload.get("collect_level") or "最小采集").strip(),
        "time_range": str(payload.get("time_range") or "近一周").strip(),
        "stable_sources": _text_list(payload.get("stable_sources")),
        "social_platforms": _text_list(payload.get("social_platforms")),
        "use_system_proxy": bool(payload.get("use_system_proxy", False)),
        "enable_debug_snapshots": bool(payload.get("enable_debug_snapshots", False)),
        "min_real_results": min_real_results,
    }


def normalize_original_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    ignored_names = {
        "from",
        "refer_flag",
        "spm_id_from",
        "sharetoken",
    }
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if (
            lowered in ignored_names
            or lowered.startswith("utm_")
            or lowered.startswith("share_")
            or lowered.startswith("xsec_")
        ):
            continue
        query.append((key, value))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            path,
            urlencode(sorted(query)),
            "",
        )
    )


def record_fingerprint(record: dict) -> str:
    record = record if isinstance(record, dict) else {}
    normalized_url = normalize_original_url(record.get("url") or "")
    if normalized_url:
        basis = f"url:{normalized_url}"
    else:
        basis = "fallback:" + "\u241f".join(
            str(record.get(key) or "").strip().casefold()
            for key in ("platform", "source", "title", "pub_time")
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def safe_clue(record: dict, fingerprint: str, seen_at: str) -> dict:
    """Store an operational clue, not an unbounded copy of the raw collection."""
    return {
        "id": uuid.uuid4().hex[:12],
        "fingerprint": fingerprint,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
        "title": str(record.get("title") or "").strip()[:500],
        "content_excerpt": str(record.get("content") or "").strip()[:800],
        "url": str(record.get("url") or "").strip(),
        "platform": str(record.get("platform") or "").strip(),
        "source": str(record.get("source") or "").strip(),
        "author": str(record.get("author") or "").strip(),
        "pub_time": str(record.get("pub_time") or "").strip(),
        "keyword": str(record.get("keyword") or "").strip(),
    }


class MonitorManager:
    def __init__(
        self,
        state_file: Path,
        data_root: Path,
        crawl_runner,
        *,
        crawl_lock: threading.Lock | None = None,
        now_provider=None,
        scheduler_factory=None,
    ):
        self.state_file = Path(state_file)
        self.data_root = Path(data_root)
        self.crawl_runner = crawl_runner
        self.crawl_lock = crawl_lock or threading.Lock()
        self.now_provider = now_provider or _now
        self.scheduler_factory = scheduler_factory
        self._lock = threading.RLock()
        self._scheduler = None
        self._plans = {}
        self._load()

    def _time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            value = value.replace(tzinfo=MONITOR_TIMEZONE)
        return value.astimezone(MONITOR_TIMEZONE)

    def _time_iso(self) -> str:
        return self._time().isoformat(timespec="seconds")

    def _load(self):
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for plan in raw.get("plans", []) if isinstance(raw, dict) else []:
            if not isinstance(plan, dict) or not plan.get("id"):
                continue
            plan.setdefault("payload", {})
            plan["payload"] = normalize_monitor_payload(plan["payload"])
            plan.setdefault("runs", [])
            plan.setdefault("new_items", [])
            plan.setdefault("fingerprints", {})
            plan.setdefault("baseline_ready", False)
            plan.setdefault("consecutive_failures", 0)
            plan.setdefault("runtime_status", "waiting")
            if plan.get("status") == "active" and plan.get("runtime_status") == "running":
                plan["runtime_status"] = "waiting"
            self._plans[plan["id"]] = plan

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": self._time_iso(),
            "plans": list(self._plans.values()),
        }
        temporary = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.state_file)

    def start(self):
        with self._lock:
            if self._scheduler and self._scheduler.running:
                return
            if self.scheduler_factory:
                scheduler = self.scheduler_factory()
            else:
                scheduler = BackgroundScheduler(
                    timezone=MONITOR_TIMEZONE,
                    executors={"default": APSchedulerThreadPoolExecutor(max_workers=1)},
                    job_defaults={
                        "coalesce": True,
                        "max_instances": 1,
                        "misfire_grace_time": 5 * 60,
                    },
                )
            scheduler.add_listener(self._on_scheduler_event, EVENT_JOB_MISSED)
            self._scheduler = scheduler
            scheduler.start()
            for plan in self._plans.values():
                if plan.get("status") == "active":
                    self._schedule(plan, immediate=False)

    def shutdown(self):
        with self._lock:
            scheduler = self._scheduler
            self._scheduler = None
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)

    def _job_id(self, plan_id: str) -> str:
        return f"monitor:{plan_id}"

    def _schedule(self, plan: dict, *, immediate: bool):
        if not self._scheduler:
            return
        next_run = self._time() if immediate else _parse_time(plan.get("next_run_at"))
        if next_run is None:
            next_run = self._time() + timedelta(minutes=int(plan["interval_minutes"]))
        job = self._scheduler.add_job(
            self.run_plan,
            "interval",
            minutes=int(plan["interval_minutes"]),
            id=self._job_id(plan["id"]),
            args=[plan["id"]],
            replace_existing=True,
            next_run_time=next_run,
        )
        plan["next_run_at"] = job.next_run_time.astimezone(MONITOR_TIMEZONE).isoformat(
            timespec="seconds"
        )
        self._save()

    def _unschedule(self, plan_id: str):
        if not self._scheduler:
            return
        job = self._scheduler.get_job(self._job_id(plan_id))
        if job:
            self._scheduler.remove_job(job.id)

    def _sync_next_run(self, plan: dict):
        if not self._scheduler or plan.get("status") != "active":
            plan["next_run_at"] = None
            return
        job = self._scheduler.get_job(self._job_id(plan["id"]))
        plan["next_run_at"] = (
            job.next_run_time.astimezone(MONITOR_TIMEZONE).isoformat(timespec="seconds")
            if job and job.next_run_time
            else None
        )

    def _on_scheduler_event(self, event):
        job_id = str(getattr(event, "job_id", ""))
        if not job_id.startswith("monitor:"):
            return
        plan_id = job_id.split(":", 1)[1]
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return
            plan["runtime_status"] = "late"
            plan["last_message"] = "计划执行时间已错过，等待下一次调度"
            plan["updated_at"] = self._time_iso()
            self._sync_next_run(plan)
            self._save()

    def create_plan(self, payload: dict, interval_minutes: int) -> dict:
        try:
            interval_minutes = int(interval_minutes)
        except (TypeError, ValueError):
            raise ValueError("请选择 15、30 或 60 分钟的监测间隔") from None
        if interval_minutes not in SUPPORTED_INTERVALS:
            raise ValueError("请选择 15、30 或 60 分钟的监测间隔")

        safe_payload = normalize_monitor_payload(payload)
        if not safe_payload["keywords"]:
            raise ValueError("请填写至少一个监测关键词")
        if not safe_payload["stable_sources"] and not safe_payload["social_platforms"]:
            raise ValueError("请至少选择一个政府官网或社交平台")
        strategy = safe_payload["source_strategy"]
        if strategy not in {"stable_first", "stable", "social"}:
            raise ValueError("请选择有效的来源方式")
        if strategy == "stable" and not safe_payload["stable_sources"]:
            raise ValueError("只查政府官网时，请至少选择一个政府官网")
        if strategy == "social" and not safe_payload["social_platforms"]:
            raise ValueError("只查社交平台时，请至少选择一个社交平台")

        with self._lock:
            if len(self._plans) >= MAX_STORED_PLANS:
                raise ValueError(
                    f"本机已保留 {MAX_STORED_PLANS} 个监测计划；删除规则确认前不再自动覆盖旧计划"
                )
            active_count = sum(
                plan.get("status") == "active" for plan in self._plans.values()
            )
            if active_count >= MAX_ACTIVE_PLANS:
                raise ValueError(f"最多同时运行 {MAX_ACTIVE_PLANS} 个监测计划")
            created_at = self._time_iso()
            plan_id = uuid.uuid4().hex[:12]
            plan = {
                "id": plan_id,
                "status": "active",
                "runtime_status": "waiting",
                "interval_minutes": interval_minutes,
                "payload": safe_payload,
                "created_at": created_at,
                "updated_at": created_at,
                "last_started_at": None,
                "last_completed_at": None,
                "last_success_at": None,
                "next_run_at": None,
                "last_message": "监测计划已创建，首次运行将建立基线",
                "last_error": "",
                "consecutive_failures": 0,
                "total_runs": 0,
                "total_new": 0,
                "latest_new_count": 0,
                "baseline_ready": False,
                "fingerprints": {},
                "new_items": [],
                "runs": [],
            }
            self._plans[plan_id] = plan
            self._save()
            self._schedule(plan, immediate=True)
            return self._public_plan(plan, detail=True)

    def action(self, plan_id: str, action: str) -> dict:
        with self._lock:
            plan = self._plans.get(str(plan_id or ""))
            if not plan:
                raise KeyError("监测计划不存在")
            action = str(action or "").strip()
            if action == "pause":
                if plan.get("status") != "active":
                    raise ValueError("只有运行中的计划可以暂停")
                plan["status"] = "paused"
                plan["runtime_status"] = "paused"
                plan["last_message"] = "计划已暂停，不再自动采集"
                self._unschedule(plan["id"])
                plan["next_run_at"] = None
            elif action == "resume":
                if plan.get("status") == "active":
                    raise ValueError("计划已经在运行")
                active_count = sum(
                    item.get("status") == "active" for item in self._plans.values()
                )
                if active_count >= MAX_ACTIVE_PLANS:
                    raise ValueError(f"最多同时运行 {MAX_ACTIVE_PLANS} 个监测计划")
                plan["status"] = "active"
                plan["runtime_status"] = "waiting"
                plan["last_message"] = "计划已继续，正在安排下一次采集"
                self._schedule(plan, immediate=True)
            elif action == "stop":
                plan["status"] = "stopped"
                plan["runtime_status"] = "stopped"
                plan["last_message"] = "计划已停止；已有运行记录和新线索仍保留"
                self._unschedule(plan["id"])
                plan["next_run_at"] = None
            elif action == "run_now":
                if plan.get("status") == "stopped":
                    raise ValueError("已停止的计划请先重新启动")
                if plan.get("runtime_status") == "running":
                    raise ValueError("该计划正在采集，请等待本轮完成")
                if not self._scheduler:
                    raise RuntimeError("监测调度器尚未启动")
                self._scheduler.add_job(
                    self.run_plan,
                    "date",
                    run_date=self._time(),
                    id=f"monitor-once:{plan['id']}:{uuid.uuid4().hex[:8]}",
                    args=[plan["id"], True],
                )
                plan["last_message"] = "已安排立即运行"
            else:
                raise ValueError("不支持的监测操作")
            plan["updated_at"] = self._time_iso()
            self._sync_next_run(plan)
            self._save()
            return self._public_plan(plan, detail=True)

    def run_plan(self, plan_id: str, force: bool = False):
        started = self._time()
        started_at = started.isoformat(timespec="seconds")
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return
            if plan.get("status") != "active" and not force:
                return
            if plan.get("status") == "stopped":
                return
            if plan.get("runtime_status") == "running":
                return
            plan["runtime_status"] = "running"
            plan["last_started_at"] = started_at
            plan["last_message"] = "正在采集并比对新增线索"
            plan["updated_at"] = started_at
            self._sync_next_run(plan)
            self._save()
            payload = deepcopy(plan["payload"])

        plan_dir = self.data_root / plan_id
        plan_dir.mkdir(parents=True, exist_ok=True)
        output_path = plan_dir / "latest.json"
        meta_path = plan_dir / "latest_meta.json"

        try:
            with self.crawl_lock:
                result = self.crawl_runner(plan_id, payload, output_path, meta_path) or {}
            records = result.get("records") if isinstance(result, dict) else []
            meta = result.get("meta") if isinstance(result, dict) else {}
            records = records if isinstance(records, list) else []
            meta = meta if isinstance(meta, dict) else {}
            summary = meta.get("summary") if isinstance(meta.get("summary"), dict) else {}
            failures = meta.get("failures") if isinstance(meta.get("failures"), list) else []
            real_count = int(summary.get("real_count", len(records)) or 0)
            run_status = "failure" if failures and real_count == 0 else (
                "warning" if failures else "success"
            )
            self._finish_successful_call(
                plan_id,
                records,
                run_status,
                failures,
                started,
                started_at,
                real_count,
            )
        except Exception as exc:
            self._finish_failure(plan_id, str(exc), started, started_at)

    def _finish_successful_call(
        self,
        plan_id: str,
        records: list,
        run_status: str,
        failures: list,
        started: datetime,
        started_at: str,
        real_count: int,
    ):
        if run_status == "failure":
            message = self._failure_message(failures) or "所有已选来源均未取得可用结果"
            self._finish_failure(
                plan_id, message, started, started_at, failure_count=len(failures)
            )
            return

        completed = self._time()
        completed_at = completed.isoformat(timespec="seconds")
        seen_at = completed_at
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return
            fingerprints = plan.setdefault("fingerprints", {})
            baseline = not bool(plan.get("baseline_ready"))
            new_clues = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                fingerprint = record_fingerprint(record)
                known = fingerprints.get(fingerprint)
                if known:
                    known["last_seen_at"] = seen_at
                    for clue in plan.get("new_items", []):
                        if clue.get("fingerprint") == fingerprint:
                            clue["last_seen_at"] = seen_at
                            break
                else:
                    fingerprints[fingerprint] = {
                        "first_seen_at": seen_at,
                        "last_seen_at": seen_at,
                    }
                    if not baseline:
                        new_clues.append(safe_clue(record, fingerprint, seen_at))

            if len(fingerprints) > MAX_FINGERPRINTS_PER_PLAN:
                oldest = sorted(
                    fingerprints.items(), key=lambda item: item[1].get("last_seen_at", "")
                )[: len(fingerprints) - MAX_FINGERPRINTS_PER_PLAN]
                for fingerprint, _ in oldest:
                    fingerprints.pop(fingerprint, None)

            if baseline:
                plan["baseline_ready"] = True
                new_count = 0
                message = f"首次运行已建立基线，共识别 {len(fingerprints)} 条"
                display_status = "baseline"
            else:
                new_count = len(new_clues)
                message = f"本轮采集完成，发现 {new_count} 条新增线索"
                display_status = run_status
            if run_status == "warning":
                message += f"；另有 {len(failures)} 个来源失败，请查看运行记录"

            plan["new_items"] = (new_clues + plan.get("new_items", []))[
                :MAX_NEW_ITEMS_PER_PLAN
            ]
            plan["latest_new_count"] = new_count
            plan["total_new"] = int(plan.get("total_new") or 0) + new_count
            plan["total_runs"] = int(plan.get("total_runs") or 0) + 1
            plan["last_completed_at"] = completed_at
            plan["last_success_at"] = completed_at
            plan["consecutive_failures"] = 0
            plan["last_error"] = ""
            plan["runtime_status"] = "normal" if run_status == "success" else "warning"
            plan["last_message"] = message
            plan["updated_at"] = completed_at
            run = {
                "id": uuid.uuid4().hex[:12],
                "status": display_status,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": max(round((completed - started).total_seconds(), 2), 0),
                "records_found": real_count,
                "new_count": new_count,
                "failure_count": len(failures),
                "message": message,
            }
            plan["runs"] = [run] + plan.get("runs", [])[: MAX_RUNS_PER_PLAN - 1]
            self._sync_next_run(plan)
            self._save()

    def _finish_failure(
        self,
        plan_id: str,
        error: str,
        started: datetime,
        started_at: str,
        *,
        failure_count: int = 1,
    ):
        completed = self._time()
        completed_at = completed.isoformat(timespec="seconds")
        error = str(error or "未知采集错误").strip()[:1000]
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return
            consecutive = int(plan.get("consecutive_failures") or 0) + 1
            needs_attention = consecutive >= 3
            message = (
                f"已连续失败 {consecutive} 次，需要人工处理"
                if needs_attention
                else f"本轮采集失败（连续 {consecutive} 次）"
            )
            plan["latest_new_count"] = 0
            plan["total_runs"] = int(plan.get("total_runs") or 0) + 1
            plan["last_completed_at"] = completed_at
            plan["consecutive_failures"] = consecutive
            plan["last_error"] = error
            plan["runtime_status"] = "needs_attention" if needs_attention else "warning"
            plan["last_message"] = message
            plan["updated_at"] = completed_at
            run = {
                "id": uuid.uuid4().hex[:12],
                "status": "failure",
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": max(round((completed - started).total_seconds(), 2), 0),
                "records_found": 0,
                "new_count": 0,
                "failure_count": max(int(failure_count), 1),
                "message": f"{message}：{error}",
            }
            plan["runs"] = [run] + plan.get("runs", [])[: MAX_RUNS_PER_PLAN - 1]
            self._sync_next_run(plan)
            self._save()

    @staticmethod
    def _failure_message(failures: list) -> str:
        messages = []
        for failure in failures[:5]:
            if not isinstance(failure, dict):
                continue
            channel = str(failure.get("channel") or failure.get("platform") or "来源")
            error = str(failure.get("error") or failure.get("message") or "访问失败")
            messages.append(f"{channel}: {error}")
        return "；".join(messages)

    def _public_plan(self, plan: dict, *, detail: bool) -> dict:
        result = {
            key: deepcopy(value)
            for key, value in plan.items()
            if key not in {"fingerprints", "new_items", "runs"}
        }
        result["known_fingerprint_count"] = len(plan.get("fingerprints", {}))
        if detail:
            result["new_items"] = deepcopy(plan.get("new_items", []))
            result["runs"] = deepcopy(plan.get("runs", []))
        return result

    def list_plans(self) -> list[dict]:
        with self._lock:
            plans = sorted(
                self._plans.values(), key=lambda item: item.get("created_at", ""), reverse=True
            )
            return [self._public_plan(plan, detail=False) for plan in plans]

    def get_plan(self, plan_id: str) -> dict:
        with self._lock:
            plan = self._plans.get(str(plan_id or ""))
            if not plan:
                raise KeyError("监测计划不存在")
            return self._public_plan(plan, detail=True)
