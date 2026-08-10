"""Stable test environment applied before application modules are imported."""

import os


os.environ.setdefault("UNIMATE_DATABASE_URL", "sqlite:///./test_api.sqlite3")
os.environ.setdefault("UNIMATE_STORAGE_ROOT", "./.tmp-api-storage")
os.environ.setdefault("UNIMATE_INLINE_JOBS", "true")
os.environ.setdefault("UNIMATE_ADMIN_USERNAME", "admin")
os.environ.setdefault("UNIMATE_ADMIN_PASSWORD", "change-me-now")
