"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import router
from .config import settings
from .database import SessionLocal, create_schema
from .models import Admin
from .logging_config import configure_logging
from .security import hash_password


configure_logging()


def bootstrap_admin() -> None:
    with SessionLocal() as db:
        existing = db.scalar(select(Admin).where(Admin.username == settings.admin_username))
        if existing is None:
            db.add(
                Admin(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    must_change_password=True,
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    settings.validate_production()
    settings.ensure_directories()
    if settings.environment != "production":
        create_schema()
    bootstrap_admin()
    yield


app = FastAPI(
    title="UniMate University Room Allocation API",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(router)
