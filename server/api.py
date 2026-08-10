"""Authenticated FastAPI routes for the UniMate dashboard."""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import pandas as pd
from redis import Redis
from rq.job import Job
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from engine import CompatibilityScorer, ScoringConfig, parse_student_survey, select_active_room_capacities

from .config import settings
from .database import get_db
from .jobs import enqueue_run
from .models import Admin, AdminSession, Assignment, AuditEvent, Dataset, OptimizationRun, RoomResult, new_id, utcnow
from .schemas import (
    DatasetResponse,
    LoginRequest,
    PaginatedResponse,
    PasswordChangeRequest,
    RunCreateRequest,
    RunResponse,
    SessionResponse,
)
from .security import (
    SESSION_COOKIE,
    check_login_rate_limit,
    clear_login_failures,
    create_session,
    hash_password,
    record_audit,
    record_login_failure,
    require_csrf,
    require_session,
    verify_password,
)
from .storage import (
    finalize_staged_deletion,
    resolve_storage_key,
    rollback_staged_deletion,
    remove_dataset_files,
    stage_for_deletion,
    store_upload,
)


router = APIRouter(prefix="/api")
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def _run_response(run: OptimizationRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        dataset_filename=run.dataset.original_filename,
        student_count=run.dataset.row_count,
        status=run.status,
        configuration=run.configuration,
        scoring_configuration=run.scoring_configuration,
        progress=run.progress,
        metrics=run.metrics,
        metadata=run.metadata_json,
        artifacts=run.artifact_manifest,
        error_message=run.error_message,
        cancel_requested=run.cancel_requested,
        created_at=run.created_at,
        queued_at=run.queued_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        runtime_seconds=run.runtime_seconds,
    )


def _read_upload(filename: str, content: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(BytesIO(content))
    if suffix == ".xlsx":
        return pd.read_excel(BytesIO(content))
    raise ValueError("Only CSV and XLSX questionnaire files are accepted.")


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        if not settings.inline_jobs:
            Redis.from_url(settings.redis_url).ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service dependencies are unavailable.") from exc
    return {"status": "ready"}


@router.get("/config")
def public_configuration(auth=Depends(require_session)) -> dict[str, int]:
    return {"upload_limit_mb": settings.upload_limit_mb}


@router.post("/auth/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_key = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_key)
    admin = db.scalar(select(Admin).where(Admin.username == payload.username))
    if admin is None or not admin.is_active or not verify_password(admin.password_hash, payload.password):
        record_login_failure(client_key)
        record_audit(db, action="login_failed", entity_type="session", details={"client": client_key})
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    clear_login_failures(client_key)
    token, session = create_session(db, admin)
    record_audit(db, action="login_succeeded", entity_type="session", admin_id=admin.id)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        max_age=settings.session_max_hours * 3600,
        path="/",
    )
    return SessionResponse(
        username=admin.username,
        must_change_password=admin.must_change_password,
        csrf_token=session.csrf_token,
    )


@router.get("/auth/me", response_model=SessionResponse)
def me(auth: tuple[Admin, AdminSession] = Depends(require_session)):
    admin, session = auth
    return SessionResponse(
        username=admin.username,
        must_change_password=admin.must_change_password,
        csrf_token=session.csrf_token,
    )


@router.post("/auth/logout", status_code=204)
def logout(response: Response, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, session = auth
    session.revoked = True
    record_audit(db, action="logout", entity_type="session", admin_id=admin.id)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/auth/password", response_model=SessionResponse)
def change_password(payload: PasswordChangeRequest, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, session = auth
    if not verify_password(admin.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="The new password must be different.")
    admin.password_hash = hash_password(payload.new_password)
    admin.must_change_password = False
    record_audit(db, action="password_changed", entity_type="admin", admin_id=admin.id)
    db.commit()
    return SessionResponse(username=admin.username, must_change_password=False, csrf_token=session.csrf_token)


@router.post("/datasets", response_model=DatasetResponse, status_code=201)
async def upload_dataset(
    upload: UploadFile = File(...),
    auth: tuple[Admin, AdminSession] = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    admin, _ = auth
    filename = Path(upload.filename or "upload").name
    if Path(filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Only CSV and XLSX files are accepted.")
    content = await upload.read(settings.upload_limit_mb * 1024 * 1024 + 1)
    if len(content) > settings.upload_limit_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds the configured limit.")
    try:
        raw = _read_upload(filename, content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The questionnaire file could not be read.") from exc
    parsed = parse_student_survey(raw)
    dataset_id = new_id()
    storage_key, digest = store_upload(dataset_id, filename, content)
    issues = _records(parsed.validation_report())
    dataset = Dataset(
        id=dataset_id,
        original_filename=filename,
        content_type=upload.content_type or "application/octet-stream",
        sha256=digest,
        storage_key=storage_key,
        row_count=len(raw),
        is_valid=parsed.is_valid,
        error_count=parsed.error_count,
        warning_count=parsed.warning_count,
        validation_issues=issues,
        normalized_students=_records(parsed.data) if not parsed.data.empty else [],
    )
    db.add(dataset)
    record_audit(
        db,
        action="dataset_uploaded",
        entity_type="dataset",
        entity_id=dataset.id,
        admin_id=admin.id,
        details={"row_count": len(raw), "valid": parsed.is_valid, "sha256": digest},
    )
    record_audit(
        db,
        action="dataset_validated",
        entity_type="dataset",
        entity_id=dataset.id,
        admin_id=admin.id,
        details={
            "valid": parsed.is_valid,
            "error_count": parsed.error_count,
            "warning_count": parsed.warning_count,
        },
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        remove_dataset_files(dataset_id)
        raise
    db.refresh(dataset)
    return dataset


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, auth=Depends(require_session), db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


@router.post("/runs", response_model=RunResponse, status_code=201)
def create_run(payload: RunCreateRequest, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, _ = auth
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if not dataset.is_valid:
        raise HTTPException(status_code=409, detail="Dataset validation must pass before optimization.")
    configuration = payload.configuration.model_dump()
    if payload.configuration.capacity_mode == "mixed":
        mix = tuple((entry.count, entry.capacity) for entry in payload.configuration.capacity_mix)
        try:
            select_active_room_capacities(dataset.row_count, mix)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = OptimizationRun(
        dataset_id=dataset.id,
        status="draft",
        configuration=configuration,
        scoring_configuration=payload.scoring.model_dump(),
        progress={"phase": "draft", "message": "آماده شروع"},
    )
    db.add(run)
    db.flush()
    record_audit(db, action="run_created", entity_type="run", entity_id=run.id, admin_id=admin.id)
    db.commit()
    db.refresh(run)
    return _run_response(run)


@router.post("/runs/{run_id}/start", response_model=RunResponse)
def start_run(run_id: str, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, _ = auth
    run = db.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft runs can be started.")
    run.status = "queued"
    run.queued_at = utcnow()
    run.progress = {"phase": "queued", "message": "در صف پردازش"}
    record_audit(db, action="run_queued", entity_type="run", entity_id=run.id, admin_id=admin.id)
    db.commit()
    try:
        enqueue_run(run.id)
    except Exception as exc:
        if settings.inline_jobs:
            db.expire_all()
            refreshed = db.get(OptimizationRun, run_id)
            if refreshed is None:
                raise HTTPException(status_code=404, detail="Run not found.") from exc
            return _run_response(refreshed)
        run.status = "failed"
        run.error_message = "The optimization queue is unavailable."
        run.completed_at = utcnow()
        db.commit()
        raise HTTPException(status_code=503, detail="Optimization queue unavailable.") from exc
    db.refresh(run)
    return _run_response(run)


@router.get("/runs", response_model=list[RunResponse])
def list_runs(auth=Depends(require_session), db: Session = Depends(get_db)):
    runs = db.scalars(select(OptimizationRun).order_by(OptimizationRun.created_at.desc())).all()
    return [_run_response(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str, auth=Depends(require_session), db: Session = Depends(get_db)):
    run = db.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _run_response(run)


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_run(run_id: str, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, _ = auth
    run = db.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status in TERMINAL_STATUSES:
        return _run_response(run)
    run.cancel_requested = True
    if run.status in {"draft", "queued"}:
        if run.status == "queued" and not settings.inline_jobs:
            try:
                Job.fetch(run.id, connection=Redis.from_url(settings.redis_url)).cancel()
            except Exception:
                pass
        run.status = "cancelled"
        run.completed_at = utcnow()
        run.progress = {"phase": "cancelled", "message": "اجرای تخصیص لغو شد"}
    record_audit(db, action="run_cancel_requested", entity_type="run", entity_id=run.id, admin_id=admin.id)
    db.commit()
    db.refresh(run)
    return _run_response(run)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, auth=Depends(require_session)):
    async def stream():
        previous = None
        while True:
            from .database import SessionLocal

            with SessionLocal() as event_db:
                run = event_db.get(OptimizationRun, run_id)
                if run is None:
                    yield "event: error\ndata: {\"detail\":\"not_found\"}\n\n"
                    return
                payload = json.dumps(
                    {"status": run.status, "progress": run.progress, "error": run.error_message},
                    ensure_ascii=False,
                )
                if payload != previous:
                    yield f"event: progress\ndata: {payload}\n\n"
                    previous = payload
                if run.status in TERMINAL_STATUSES:
                    return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/runs/{run_id}/rooms", response_model=PaginatedResponse)
def list_rooms(
    run_id: str,
    query: str = "",
    min_quality: float | None = None,
    max_quality: float | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    auth=Depends(require_session),
    db: Session = Depends(get_db),
):
    conditions = [RoomResult.run_id == run_id]
    if query:
        conditions.append(RoomResult.room_id.ilike(f"%{query}%"))
    if min_quality is not None:
        conditions.append(RoomResult.room_quality >= min_quality)
    if max_quality is not None:
        conditions.append(RoomResult.room_quality <= max_quality)
    total = db.scalar(select(func.count()).select_from(RoomResult).where(*conditions)) or 0
    rows = db.scalars(
        select(RoomResult).where(*conditions).order_by(RoomResult.room_quality, RoomResult.room_id).offset(offset).limit(limit)
    ).all()
    items = [
        {
            "room_id": row.room_id,
            "room_size": row.room_size,
            "room_capacity": row.room_capacity,
            "room_quality": row.room_quality,
            "mean_student_utility": row.mean_student_utility,
            **row.contributions,
        }
        for row in rows
    ]
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/runs/{run_id}/analytics")
def run_analytics(run_id: str, auth=Depends(require_session), db: Session = Depends(get_db)):
    run = db.get(OptimizationRun, run_id)
    if run is None or run.status != "succeeded":
        raise HTTPException(status_code=404, detail="Completed run not found.")
    room_values = db.execute(
        select(RoomResult.room_id, RoomResult.room_quality, RoomResult.mean_student_utility)
        .where(RoomResult.run_id == run_id)
        .order_by(RoomResult.room_id)
    ).all()
    student_values = db.execute(
        select(Assignment.student_utility).where(Assignment.run_id == run_id)
    ).scalars().all()
    return {
        "rooms": [
            {"room_id": room_id, "room_quality": quality, "mean_student_utility": mean}
            for room_id, quality, mean in room_values
        ],
        "student_utilities": list(student_values),
        "search_history": (run.metadata_json or {}).get("search_history", []),
    }


@router.get("/runs/{run_id}/students", response_model=PaginatedResponse)
def list_students(
    run_id: str,
    query: str = "",
    room_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    auth=Depends(require_session),
    db: Session = Depends(get_db),
):
    conditions = [Assignment.run_id == run_id]
    if query:
        pattern = f"%{query}%"
        conditions.append(or_(Assignment.student_id.ilike(pattern), Assignment.student_name.ilike(pattern), Assignment.room_id.ilike(pattern)))
    if room_id:
        conditions.append(Assignment.room_id == room_id)
    total = db.scalar(select(func.count()).select_from(Assignment).where(*conditions)) or 0
    rows = db.scalars(
        select(Assignment).where(*conditions).order_by(Assignment.student_utility, Assignment.room_id, Assignment.bed).offset(offset).limit(limit)
    ).all()
    items = [
        {
            "room_id": row.room_id,
            "bed": row.bed,
            "room_capacity": row.room_capacity,
            "student_idx": row.student_idx,
            "student_id": row.student_id,
            "student_name": row.student_name,
            "student_utility": row.student_utility,
            "room_quality": row.room_quality,
            **row.profile,
        }
        for row in rows
    ]
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/runs/{run_id}/pair")
def explain_pair(run_id: str, first_idx: int, second_idx: int, auth=Depends(require_session), db: Session = Depends(get_db)):
    run = db.get(OptimizationRun, run_id)
    if run is None or run.status != "succeeded":
        raise HTTPException(status_code=404, detail="Completed run not found.")
    records = {int(record["student_idx"]): record for record in run.dataset.normalized_students}
    if first_idx not in records or second_idx not in records:
        raise HTTPException(status_code=404, detail="Student not found.")
    scoring_payload = run.scoring_configuration
    config = ScoringConfig()
    if scoring_payload.get("sensitivity_enabled"):
        config = ScoringConfig.from_weights(
            {key: scoring_payload.get(key, 25) for key in ("cleanliness", "noise", "study", "schedule")}
        )
    return CompatibilityScorer(config).explain_pair(records[first_idx], records[second_idx])


@router.get("/runs/{run_id}/artifacts/{filename}")
def download_artifact(run_id: str, filename: str, auth: tuple[Admin, AdminSession] = Depends(require_session), db: Session = Depends(get_db)):
    admin, _ = auth
    run = db.get(OptimizationRun, run_id)
    if run is None or filename not in run.artifact_manifest:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    storage_key = run.artifact_manifest[filename]["storage_key"]
    path = resolve_storage_key(storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file is unavailable.")
    record_audit(db, action="artifact_downloaded", entity_type="run", entity_id=run_id, admin_id=admin.id, details={"artifact": filename})
    db.commit()
    return FileResponse(path, filename=filename)


@router.get("/audit")
def list_audit_events(
    entity_id: str | None = Query(default=None, max_length=80),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    auth=Depends(require_session),
    db: Session = Depends(get_db),
):
    conditions = [AuditEvent.entity_id == entity_id] if entity_id else []
    total = db.scalar(
        select(func.count()).select_from(AuditEvent).where(*conditions)
    ) or 0
    events = db.scalars(
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "id": event.id,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "details": event.details,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, auth: tuple[Admin, AdminSession] = Depends(require_csrf), db: Session = Depends(get_db)):
    admin, _ = auth
    run = db.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Cancel the active run before deletion.")
    dataset = run.dataset
    other_run_count = db.scalar(
        select(func.count()).select_from(OptimizationRun).where(
            OptimizationRun.dataset_id == dataset.id,
            OptimizationRun.id != run.id,
        )
    ) or 0
    paths = [settings.artifact_root / run.id]
    delete_dataset = other_run_count == 0
    if delete_dataset:
        paths.append(settings.upload_root / dataset.id)
    staged = stage_for_deletion(paths)
    try:
        db.delete(run)
        if delete_dataset:
            db.delete(dataset)
        record_audit(
            db,
            action="run_deleted",
            entity_type="run",
            entity_id=run_id,
            admin_id=admin.id,
            details={"dataset_deleted": delete_dataset},
        )
        db.commit()
    except Exception:
        db.rollback()
        rollback_staged_deletion(staged)
        raise
    finalize_staged_deletion(staged)
