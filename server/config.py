"""Environment-backed application settings."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import quote_plus


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    explicit = os.getenv("UNIMATE_DATABASE_URL")
    if explicit:
        return explicit
    password = os.getenv("UNIMATE_DB_PASSWORD")
    if password is None:
        return "sqlite:///./unimate.sqlite3"
    user = quote_plus(os.getenv("UNIMATE_DB_USER", "unimate"))
    encoded_password = quote_plus(password)
    host = os.getenv("UNIMATE_DB_HOST", "db")
    name = quote_plus(os.getenv("UNIMATE_DB_NAME", "unimate"))
    return f"postgresql+psycopg://{user}:{encoded_password}@{host}:5432/{name}"


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("UNIMATE_ENVIRONMENT", "development")
    database_url: str = _database_url()
    redis_url: str = os.getenv("UNIMATE_REDIS_URL", "redis://localhost:6379/0")
    storage_root: Path = Path(os.getenv("UNIMATE_STORAGE_ROOT", "./storage"))
    admin_username: str = os.getenv("UNIMATE_ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("UNIMATE_ADMIN_PASSWORD", "change-me-now")
    secure_cookies: bool = _boolean("UNIMATE_SECURE_COOKIES", False)
    session_idle_minutes: int = int(os.getenv("UNIMATE_SESSION_IDLE_MINUTES", "30"))
    session_max_hours: int = int(os.getenv("UNIMATE_SESSION_MAX_HOURS", "8"))
    upload_limit_mb: int = int(os.getenv("UNIMATE_UPLOAD_LIMIT_MB", "25"))
    frontend_origin: str = os.getenv("UNIMATE_FRONTEND_ORIGIN", "http://localhost:5173")
    inline_jobs: bool = _boolean("UNIMATE_INLINE_JOBS", False)
    cp_sat_default: bool = _boolean("UNIMATE_CP_SAT_DEFAULT", False)

    @property
    def upload_root(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def artifact_root(self) -> Path:
        return self.storage_root / "artifacts"

    def ensure_directories(self) -> None:
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def validate_production(self) -> None:
        if self.environment == "production" and self.admin_password == "change-me-now":
            raise RuntimeError("Set UNIMATE_ADMIN_PASSWORD before production startup.")
        if self.environment == "production" and not self.secure_cookies:
            raise RuntimeError("Secure cookies must be enabled in production.")


settings = Settings()
