"""Isolated optimization job executed by the RQ worker."""

from __future__ import annotations

from dataclasses import asdict
import json
import time

import pandas as pd
from redis import Redis
from rq import Queue
from sqlalchemy import delete

from engine import CompatibilityScorer, OptimizationConfig, RoomOptimizer, ScoringConfig

from .config import settings
from .database import SessionLocal
from .exports import generate_run_artifacts
from .models import Assignment, AuditEvent, Dataset, OptimizationRun, RoomResult, utcnow


class RunCancelled(RuntimeError):
    pass


PROFILE_FIELDS = (
    "faculty",
    "major",
    "age",
    "sleep_window",
    "wake_window",
    "noise_tolerance",
    "study_habit",
    "cleanliness",
)


def enqueue_run(run_id: str) -> None:
    if settings.inline_jobs:
        execute_run(run_id)
        return
    connection = Redis.from_url(settings.redis_url)
    Queue("optimizations", connection=connection).enqueue(
        execute_run,
        run_id,
        job_id=run_id,
        job_timeout=7500,
        result_ttl=86400,
        failure_ttl=604800,
        on_failure=record_rq_failure,
        on_stopped=record_rq_stopped,
    )


def _record_external_termination(run_id: str, *, error_type: str) -> None:
    """Close database state when RQ terminates a job outside execute_run()."""
    with SessionLocal() as db:
        run = db.get(OptimizationRun, run_id)
        if run is None or run.status in {"succeeded", "failed", "cancelled"}:
            return
        cancelled = run.cancel_requested
        run.status = "cancelled" if cancelled else "failed"
        run.completed_at = utcnow()
        run.error_message = None if cancelled else "The optimization worker terminated unexpectedly."
        run.progress = {
            "phase": run.status,
            "message": "اجرای تخصیص لغو شد" if cancelled else "پردازشگر به‌طور غیرمنتظره متوقف شد",
        }
        db.add(
            AuditEvent(
                action="run_cancelled" if cancelled else "run_failed",
                entity_type="run",
                entity_id=run_id,
                details={"error_type": error_type},
            )
        )
        db.commit()


def record_rq_failure(job, connection, exc_type, exc_value, traceback) -> None:
    del connection, exc_value, traceback
    _record_external_termination(job.id, error_type=exc_type.__name__)


def record_rq_stopped(job, connection) -> None:
    del connection
    _record_external_termination(job.id, error_type="JobStopped")


def _optimization_config(payload: dict) -> OptimizationConfig:
    capacity_mix = None
    if payload.get("capacity_mode") == "mixed":
        capacity_mix = tuple(
            (int(entry["count"]), int(entry["capacity"]))
            for entry in payload.get("capacity_mix", [])
        )
    cp_sat_enabled = bool(payload.get("cp_sat_enabled", settings.cp_sat_default))
    return OptimizationConfig(
        capacity=int(payload.get("capacity") or 6),
        capacity_mix=capacity_mix,
        time_limit_seconds=float(payload.get("time_limit_seconds", 300)),
        seed=int(payload.get("seed", 42)),
        restarts=int(payload.get("restarts", 3)),
        cp_sat_neighborhood_rooms=4 if cp_sat_enabled else 0,
    )


def _scoring_config(payload: dict) -> ScoringConfig:
    if not payload.get("sensitivity_enabled"):
        return ScoringConfig()
    return ScoringConfig.from_weights(
        {
            "cleanliness": payload.get("cleanliness", 25),
            "noise": payload.get("noise", 25),
            "study": payload.get("study", 25),
            "schedule": payload.get("schedule", 25),
        }
    )


def _json_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def execute_run(run_id: str) -> None:
    last_progress_update = 0.0
    try:
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is None:
                return
            if run.cancel_requested:
                run.status = "cancelled"
                run.completed_at = utcnow()
                db.commit()
                return
            dataset = db.get(Dataset, run.dataset_id)
            if dataset is None or not dataset.is_valid:
                raise ValueError("The run dataset is missing or invalid.")
            run.status = "running"
            run.started_at = utcnow()
            run.progress = {"phase": "preparing", "message": "آماده‌سازی داده‌ها"}
            db.add(
                AuditEvent(
                    action="run_started",
                    entity_type="run",
                    entity_id=run.id,
                    details={},
                )
            )
            db.commit()
            students = pd.DataFrame(dataset.normalized_students)
            configuration = dict(run.configuration)
            scoring_payload = dict(run.scoring_configuration)
            validation_issues = list(dataset.validation_issues)

        scoring_config = _scoring_config(scoring_payload)
        scores = CompatibilityScorer(scoring_config).score(students)

        def progress_callback(event: dict) -> None:
            nonlocal last_progress_update
            now = time.monotonic()
            if now - last_progress_update < 0.75 and event.get("phase") == "swap_search":
                return
            with SessionLocal() as progress_db:
                current = progress_db.get(OptimizationRun, run_id)
                if current is None or current.cancel_requested:
                    raise RunCancelled("Run cancellation requested.")
                current.progress = dict(event)
                progress_db.commit()
            last_progress_update = now

        result = RoomOptimizer(_optimization_config(configuration)).optimize(
            students,
            scores,
            progress_callback=progress_callback,
        )
        profile_fields = [field for field in PROFILE_FIELDS if field in students.columns]
        ledger = result.assignments.merge(
            students[["student_idx", *profile_fields]],
            on="student_idx",
            how="left",
        )
        metadata = result.metadata()
        validation = pd.DataFrame(validation_issues)
        student_export = ledger[
            [
                "student_idx",
                "student_id",
                "student_name",
                "room_id",
                "bed",
                "room_capacity",
                "student_utility",
                "room_quality",
                *profile_fields,
            ]
        ].sort_values("student_idx")

        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is None:
                return
            if run.cancel_requested:
                raise RunCancelled("Run cancellation requested.")
            db.execute(delete(Assignment).where(Assignment.run_id == run_id))
            db.execute(delete(RoomResult).where(RoomResult.run_id == run_id))
            for record in _json_records(ledger):
                profile = {field: record.get(field) for field in profile_fields}
                db.add(
                    Assignment(
                        run_id=run_id,
                        room_id=str(record["room_id"]),
                        bed=int(record["bed"]),
                        room_capacity=int(record["room_capacity"]),
                        student_idx=int(record["student_idx"]),
                        student_id=str(record["student_id"]),
                        student_name=str(record["student_name"]),
                        student_utility=float(record["student_utility"]),
                        room_quality=float(record["room_quality"]),
                        profile=profile,
                    )
                )
            contribution_fields = [
                column
                for column in result.room_metrics.columns
                if column.endswith("_contribution")
            ]
            for record in _json_records(result.room_metrics):
                db.add(
                    RoomResult(
                        run_id=run_id,
                        room_id=str(record["room_id"]),
                        room_size=int(record["room_size"]),
                        room_capacity=int(record["room_capacity"]),
                        room_quality=float(record["room_quality"]),
                        mean_student_utility=float(record["mean_student_utility"]),
                        contributions={field: record.get(field, 0) for field in contribution_fields},
                    )
                )
            run.metrics = asdict(result.metrics)
            run.metadata_json = metadata
            run.runtime_seconds = result.runtime_seconds
            run.progress = {"phase": "exports", "message": "ساخت خروجی‌های رسمی"}
            db.commit()

        manifest = generate_run_artifacts(
            run_id,
            ledger,
            result.room_metrics,
            student_export,
            validation,
            metadata,
        )
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is None:
                return
            run.status = "succeeded"
            run.completed_at = utcnow()
            run.progress = {"phase": "completed", "message": "تخصیص با موفقیت تکمیل شد"}
            run.artifact_manifest = manifest
            db.add(
                AuditEvent(
                    action="run_completed",
                    entity_type="run",
                    entity_id=run_id,
                    details={"status": "succeeded"},
                )
            )
            db.commit()
    except RunCancelled:
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is not None:
                run.status = "cancelled"
                run.completed_at = utcnow()
                run.progress = {"phase": "cancelled", "message": "اجرای تخصیص لغو شد"}
                db.add(
                    AuditEvent(
                        action="run_cancelled",
                        entity_type="run",
                        entity_id=run_id,
                        details={},
                    )
                )
                db.commit()
    except Exception as exc:
        error_type = type(exc).__name__
        with SessionLocal() as db:
            run = db.get(OptimizationRun, run_id)
            if run is not None:
                run.status = "failed"
                run.completed_at = utcnow()
                run.error_message = f"Optimization failed ({error_type})."
                run.progress = {"phase": "failed", "message": "اجرای تخصیص ناموفق بود"}
                db.add(
                    AuditEvent(
                        action="run_failed",
                        entity_type="run",
                        entity_id=run_id,
                        details={"error_type": error_type},
                    )
                )
                db.commit()
        raise RuntimeError(
            f"Optimization run {run_id} failed ({error_type})."
        ) from None
