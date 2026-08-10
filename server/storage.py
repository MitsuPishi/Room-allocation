"""Private upload and artifact storage helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import uuid

from .config import settings


def store_upload(dataset_id: str, filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    target_dir = settings.upload_root / dataset_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix}"
    target.write_bytes(content)
    return str(target.relative_to(settings.storage_root)), hashlib.sha256(content).hexdigest()


def resolve_storage_key(storage_key: str) -> Path:
    root = settings.storage_root.resolve()
    target = (settings.storage_root / storage_key).resolve()
    if root not in target.parents and target != root:
        raise ValueError("Invalid storage key.")
    return target


def run_artifact_dir(run_id: str) -> Path:
    target = settings.artifact_root / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def remove_dataset_files(dataset_id: str) -> None:
    target = (settings.upload_root / dataset_id).resolve()
    root = settings.upload_root.resolve()
    if root not in target.parents:
        raise ValueError("Invalid dataset storage path.")
    if target.exists():
        shutil.rmtree(target)


def remove_run_files(run_id: str) -> None:
    target = (settings.artifact_root / run_id).resolve()
    root = settings.artifact_root.resolve()
    if root not in target.parents:
        raise ValueError("Invalid artifact storage path.")
    if target.exists():
        shutil.rmtree(target)


def stage_for_deletion(paths: list[Path]) -> list[tuple[Path, Path]]:
    trash_root = settings.storage_root / ".trash" / str(uuid.uuid4())
    staged: list[tuple[Path, Path]] = []
    for index, source in enumerate(paths):
        if not source.exists():
            continue
        trash_root.mkdir(parents=True, exist_ok=True)
        target = trash_root / f"{index}-{source.name}"
        source.rename(target)
        staged.append((source, target))
    return staged


def rollback_staged_deletion(staged: list[tuple[Path, Path]]) -> None:
    for original, temporary in reversed(staged):
        original.parent.mkdir(parents=True, exist_ok=True)
        if temporary.exists():
            temporary.rename(original)


def finalize_staged_deletion(staged: list[tuple[Path, Path]]) -> None:
    trash_roots = {temporary.parent for _, temporary in staged}
    for trash_root in trash_roots:
        if trash_root.exists():
            shutil.rmtree(trash_root)
