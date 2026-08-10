"""Typed HTTP request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class SessionResponse(BaseModel):
    username: str
    must_change_password: bool
    csrf_token: str


class CapacityEntry(BaseModel):
    count: int = Field(ge=1, le=100_000)
    capacity: int = Field(ge=2, le=100)


class RunConfiguration(BaseModel):
    capacity_mode: Literal["uniform", "mixed"] = "uniform"
    capacity: int | None = Field(default=6, ge=2, le=100)
    capacity_mix: list[CapacityEntry] = Field(default_factory=list, max_length=100)
    time_limit_seconds: float = Field(default=300, gt=0, le=7200)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    restarts: int = Field(default=3, ge=1, le=20)
    cp_sat_enabled: bool = False

    @model_validator(mode="after")
    def validate_inventory(self) -> "RunConfiguration":
        if self.capacity_mode == "mixed" and not self.capacity_mix:
            raise ValueError("Mixed capacity mode requires at least one room type.")
        if self.capacity_mode == "uniform" and self.capacity is None:
            raise ValueError("Uniform capacity mode requires a capacity.")
        return self


class ScoringConfiguration(BaseModel):
    sensitivity_enabled: bool = False
    cleanliness: float = Field(default=25, ge=0, le=100)
    noise: float = Field(default=25, ge=0, le=100)
    study: float = Field(default=25, ge=0, le=100)
    schedule: float = Field(default=25, ge=0, le=100)

    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringConfiguration":
        if self.sensitivity_enabled and (
            self.cleanliness + self.noise + self.study + self.schedule <= 0
        ):
            raise ValueError("At least one scoring weight must be positive.")
        return self


class RunCreateRequest(BaseModel):
    dataset_id: str
    configuration: RunConfiguration
    scoring: ScoringConfiguration = Field(default_factory=ScoringConfiguration)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    row_count: int
    is_valid: bool
    error_count: int
    warning_count: int
    validation_issues: list[dict]
    created_at: datetime


class RunResponse(BaseModel):
    id: str
    dataset_id: str
    dataset_filename: str
    student_count: int
    status: str
    configuration: dict
    scoring_configuration: dict
    progress: dict
    metrics: dict | None
    metadata: dict | None
    artifacts: dict
    error_message: str | None
    cancel_requested: bool
    created_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    runtime_seconds: float | None


class PaginatedResponse(BaseModel):
    items: list[dict]
    total: int
    offset: int
    limit: int
