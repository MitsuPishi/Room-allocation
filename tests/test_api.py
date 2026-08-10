import json
from io import BytesIO
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from server import jobs
from server.config import settings
from server.database import Base, engine
from server.main import app
from server.storage import run_artifact_dir
from tests.test_preprocessing import raw_survey


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    if settings.storage_root.exists():
        shutil.rmtree(settings.storage_root)
    settings.ensure_directories()
    yield
    Base.metadata.drop_all(bind=engine)
    if settings.storage_root.exists():
        shutil.rmtree(settings.storage_root)
    engine.dispose()
    Path("test_api.sqlite3").unlink(missing_ok=True)


@pytest.fixture()
def client(monkeypatch):
    def fake_artifacts(run_id, assignments, rooms, students, validation, metadata):
        del assignments, rooms, students, validation, metadata
        path = run_artifact_dir(run_id) / "assignments.csv"
        path.write_text("room_id,student_id\nRoom-0001,a\n", encoding="utf-8")
        content = path.read_bytes()
        import hashlib

        return {
            "assignments.csv": {
                "storage_key": str(path.relative_to(settings.storage_root)),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        }

    monkeypatch.setattr(jobs, "generate_run_artifacts", fake_artifacts)
    with TestClient(app) as value:
        yield value


def authenticate(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "change-me-now"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    blocked = client.get("/api/runs")
    assert blocked.status_code == 403
    changed = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "change-me-now",
            "new_password": "a-strong-university-password",
        },
    )
    assert changed.status_code == 200
    return {"X-CSRF-Token": csrf}


def upload_valid_dataset(client: TestClient, headers: dict[str, str]) -> dict:
    content = raw_survey().to_csv(index=False).encode("utf-8-sig")
    response = client.post(
        "/api/datasets",
        headers=headers,
        files={"upload": ("survey.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_valid"] is True
    return response.json()


def test_authentication_csrf_and_password_rotation(client: TestClient):
    assert client.get("/api/runs").status_code == 401
    headers = authenticate(client)
    assert client.get("/api/runs").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/runs").status_code == 401


def test_full_run_lifecycle_results_download_and_delete(client: TestClient):
    headers = authenticate(client)
    dataset = upload_valid_dataset(client, headers)
    insufficient = client.post(
        "/api/runs",
        headers=headers,
        json={
            "dataset_id": dataset["id"],
            "configuration": {
                "capacity_mode": "mixed",
                "capacity_mix": [],
                "time_limit_seconds": 1,
                "seed": 7,
                "restarts": 1,
            },
        },
    )
    assert insufficient.status_code == 422

    created = client.post(
        "/api/runs",
        headers=headers,
        json={
            "dataset_id": dataset["id"],
            "configuration": {
                "capacity_mode": "uniform",
                "capacity": 2,
                "time_limit_seconds": 1,
                "seed": 7,
                "restarts": 1,
                "cp_sat_enabled": False,
            },
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    started = client.post(f"/api/runs/{run_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "succeeded"
    assert client.get(f"/api/runs/{run_id}/rooms").json()["total"] == 1
    students = client.get(f"/api/runs/{run_id}/students").json()
    assert students["total"] == 2
    pair = client.get(
        f"/api/runs/{run_id}/pair",
        params={"first_idx": students["items"][0]["student_idx"], "second_idx": students["items"][1]["student_idx"]},
    )
    assert pair.status_code == 200
    assert "total" in pair.json()
    download = client.get(f"/api/runs/{run_id}/artifacts/assignments.csv")
    assert download.status_code == 200
    assert download.content.startswith(b"room_id")
    deleted = client.delete(f"/api/runs/{run_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    audit = client.get("/api/audit").json()["items"]
    assert any(event["action"] == "run_deleted" for event in audit)
    assert any(event["action"] == "dataset_validated" for event in audit)
    run_audit = client.get("/api/audit", params={"entity_id": run_id}).json()
    assert run_audit["total"] >= 4
    assert all(event["entity_id"] == run_id for event in run_audit["items"])


def test_draft_run_can_be_cancelled(client: TestClient):
    headers = authenticate(client)
    dataset = upload_valid_dataset(client, headers)
    created = client.post(
        "/api/runs",
        headers=headers,
        json={
            "dataset_id": dataset["id"],
            "configuration": {"capacity_mode": "uniform", "capacity": 2},
        },
    ).json()
    cancelled = client.post(f"/api/runs/{created['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_xlsx_upload_and_file_type_guard(client: TestClient):
    headers = authenticate(client)
    workbook = BytesIO()
    raw_survey().to_excel(workbook, index=False)
    uploaded = client.post(
        "/api/datasets",
        headers=headers,
        files={
            "upload": (
                "survey.xlsx",
                workbook.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["is_valid"] is True

    rejected = client.post(
        "/api/datasets",
        headers=headers,
        files={"upload": ("survey.txt", b"not a questionnaire", "text/plain")},
    )
    assert rejected.status_code == 415


def test_inline_export_failure_is_not_mislabeled_as_queue_failure(client: TestClient, monkeypatch):
    headers = authenticate(client)
    dataset = upload_valid_dataset(client, headers)

    def fail_export(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("simulated export failure")

    monkeypatch.setattr(jobs, "generate_run_artifacts", fail_export)
    run = client.post(
        "/api/runs",
        headers=headers,
        json={
            "dataset_id": dataset["id"],
            "configuration": {
                "capacity_mode": "uniform",
                "capacity": 2,
                "time_limit_seconds": 1,
                "seed": 7,
                "restarts": 1,
                "cp_sat_enabled": False,
            },
        },
    ).json()

    started = client.post(f"/api/runs/{run['id']}/start", headers=headers)

    assert started.status_code == 200
    assert started.json()["status"] == "failed"
    assert started.json()["error_message"] == "Optimization failed (RuntimeError)."
