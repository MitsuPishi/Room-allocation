"""Validated adapters for the original university housing questionnaire."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd


SCHEMA_VERSION = "raw-survey-v1"


class SurveyValidationError(ValueError):
    """Raised when questionnaire data cannot be safely normalized."""

    def __init__(self, result: "SurveyParseResult"):
        self.result = result
        super().__init__(
            f"Survey validation failed with {result.error_count} error(s) "
            f"and {result.warning_count} warning(s)."
        )


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    field: str
    message: str
    row: int | None = None
    value: Any = None


@dataclass
class SurveyParseResult:
    data: pd.DataFrame
    issues: list[ValidationIssue]
    schema_version: str = SCHEMA_VERSION

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def validation_report(self) -> pd.DataFrame:
        columns = ["severity", "code", "row", "field", "value", "message"]
        records = [
            {
                "severity": issue.severity,
                "code": issue.code,
                "row": issue.row,
                "field": issue.field,
                "value": issue.value,
                "message": issue.message,
            }
            for issue in self.issues
        ]
        return pd.DataFrame(records, columns=columns)


def _normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u200c", " ").replace("\u200f", " ")
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_header(value: Any) -> str:
    text = _normalize_text(value).lower()
    return re.sub(r"[\s_\-؟?():/]+", "", text)


COLUMN_ALIASES = {
    "student_id": (
        "student_id",
        "student id",
        "id",
        "شماره دانشجویی",
        "کد دانشجویی",
    ),
    "student_name": ("student_name", "student name", "name", "نام", "نام و نام خانوادگی"),
    "faculty": ("faculty", "دانشکده"),
    "major": ("major", "رشته", "رشته تحصیلی"),
    "age": ("age", "سن"),
    "residence": (
        "residence",
        "province",
        "city",
        "استان",
        "شهر سکونت",
        "محل سکونت",
    ),
    "ethnicity": ("ethnicity", "قومیت"),
    "sleep_window": (
        "sleep_window",
        "sleep time",
        "sleep_time",
        "اغلب شب‌ها در چه بازه‌ی زمانی می‌خوابید؟",
    ),
    "wake_window": (
        "wake_window",
        "wake time",
        "wake_time",
        "اغلب صبح‌ها چه ساعتی بیدار می‌شوید؟",
    ),
    "noise_tolerance": (
        "noise_tolerance",
        "noise tolerance",
        "سطح تحمل سر و صدا در شما چه‌گونه است؟",
        "سطح تحمل سر و صدا در شما چگونه است؟",
    ),
    "study_habit": (
        "study_habit",
        "study_habits",
        "study habits",
        "عادات مطالعه شما به چه صورت است؟",
    ),
    "cleanliness": (
        "cleanliness",
        "شما در نظافت و سازماندهی جزو کدام دسته از افراد هستید؟",
    ),
    "cultural_group": ("cultural_group", "religion", "دین"),
}

REQUIRED_FIELDS = (
    "sleep_window",
    "wake_window",
    "noise_tolerance",
    "study_habit",
    "cleanliness",
)
OPTIONAL_PROFILE_FIELDS = ("faculty", "major", "age")
SENSITIVE_FIELDS = ("residence", "ethnicity", "cultural_group")


def _column_lookup(df: pd.DataFrame) -> dict[str, str]:
    normalized_to_original = {_normalize_header(column): column for column in df.columns}
    matches: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            original = normalized_to_original.get(_normalize_header(alias))
            if original is not None:
                matches[canonical] = original
                break
    return matches


def _looks_one_hot_encoded(df: pd.DataFrame) -> bool:
    headers = [_normalize_text(column).lower() for column in df.columns]
    prefixes = ("ethnicity_", "province_", "major_", "faculty_", "religion_")
    return len(headers) > 20 and sum(header.startswith(prefixes) for header in headers) >= 3


def _map_binary(value: Any, field: str) -> int | None:
    if isinstance(value, (int, np.integer, float, np.floating)) and not pd.isna(value):
        if float(value) in (0.0, 1.0):
            return int(value)

    text = _normalize_text(value).lower()
    if not text:
        return None

    mappings = {
        "noise_tolerance": (
            ("پر جنب و جوش", "علاقه مند", "علاقه‌مند", "energetic", "lively"),
            ("حساس", "آرام", "quiet", "sensitive"),
        ),
        "study_habit": (
            ("سکوت کامل", "quiet", "silence"),
            ("موسیقی", "سر و صدا", "music", "noise"),
        ),
        "cleanliness": (
            ("نظم طلبان", "نظم‌طلبان", "تمیزی", "tidy", "organized"),
            ("راحت طلبان", "راحت‌طلبان", "آشفته", "relaxed"),
        ),
    }
    positive, negative = mappings[field]
    if any(token in text for token in positive):
        return 1
    if any(token in text for token in negative):
        return 0
    return None


SLEEP_BUCKETS = {
    "10-11": 0,
    "10–11": 0,
    "11-oct": 0,
    "0": 0,
    "11-12": 1,
    "11–12": 1,
    "12-nov": 1,
    "1": 1,
    "12-1": 2,
    "12–1": 2,
    "1-dec": 2,
    "2": 2,
    "1-2": 3,
    "1–2": 3,
    "2-jan": 3,
    "3": 3,
    "2-3": 4,
    "2–3": 4,
    "3-feb": 4,
    "4": 4,
}

WAKE_BUCKETS = {
    "4-5": 0,
    "4–5": 0,
    "5-apr": 0,
    "0": 0,
    "5-6": 1,
    "5–6": 1,
    "6-may": 1,
    "1": 1,
    "6-7": 2,
    "6–7": 2,
    "7-jun": 2,
    "2": 2,
    "7-8": 3,
    "7–8": 3,
    "8-jul": 3,
    "3": 3,
}


def _map_schedule(value: Any, field: str) -> int | None:
    text = _normalize_text(value).lower().replace(" ", "")
    mapping = SLEEP_BUCKETS if field == "sleep_window" else WAKE_BUCKETS
    return mapping.get(text)


def _issue(
    issues: list[ValidationIssue],
    *,
    severity: str,
    code: str,
    field: str,
    message: str,
    row: int | None = None,
    value: Any = None,
) -> None:
    issues.append(
        ValidationIssue(
            severity=severity,
            code=code,
            field=field,
            message=message,
            row=row,
            value=value,
        )
    )


def parse_student_survey(
    df: pd.DataFrame,
    *,
    strict: bool = False,
) -> SurveyParseResult:
    """Normalize the raw questionnaire into the optimization data contract.

    Sensitive attributes are retained for authorized auditing, but the scoring
    engine deliberately ignores them.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    issues: list[ValidationIssue] = []
    if df.empty:
        _issue(
            issues,
            severity="error",
            code="empty_dataset",
            field="dataset",
            message="The uploaded questionnaire contains no student rows.",
        )
        result = SurveyParseResult(pd.DataFrame(), issues)
        if strict:
            raise SurveyValidationError(result)
        return result

    if _looks_one_hot_encoded(df):
        _issue(
            issues,
            severity="error",
            code="encoded_dataset_not_supported",
            field="dataset",
            message=(
                "One-hot encoded data is not accepted. Upload the original "
                "11-column questionnaire export."
            ),
        )
        result = SurveyParseResult(pd.DataFrame(), issues)
        if strict:
            raise SurveyValidationError(result)
        return result

    columns = _column_lookup(df)
    for field in REQUIRED_FIELDS:
        if field not in columns:
            _issue(
                issues,
                severity="error",
                code="missing_required_column",
                field=field,
                message=f"Required questionnaire column '{field}' was not found.",
            )

    if any(issue.severity == "error" for issue in issues):
        result = SurveyParseResult(pd.DataFrame(), issues)
        if strict:
            raise SurveyValidationError(result)
        return result

    normalized = pd.DataFrame(index=df.index)
    normalized["source_row"] = np.arange(len(df), dtype=np.int32)

    if "student_id" in columns:
        student_ids = df[columns["student_id"]].map(_normalize_text)
        missing_ids = student_ids.eq("")
        for row in np.flatnonzero(missing_ids.to_numpy()):
            _issue(
                issues,
                severity="error",
                code="missing_student_id",
                row=int(row),
                field="student_id",
                value=df.iloc[row][columns["student_id"]],
                message="Student identifier is blank.",
            )
        normalized["student_id"] = student_ids
    else:
        width = max(6, len(str(len(df))))
        normalized["student_id"] = [
            f"student-{position:0{width}d}" for position in range(1, len(df) + 1)
        ]
        _issue(
            issues,
            severity="warning",
            code="generated_student_ids",
            field="student_id",
            message=(
                "No student identifier column was present; deterministic row-based "
                "identifiers were generated for this dataset."
            ),
        )

    duplicate_ids = normalized["student_id"].duplicated(keep=False)
    for row in np.flatnonzero(duplicate_ids.to_numpy()):
        _issue(
            issues,
            severity="error",
            code="duplicate_student_id",
            row=int(row),
            field="student_id",
            value=normalized.iloc[row]["student_id"],
            message="Student identifiers must be unique.",
        )

    if "student_name" in columns:
        names = df[columns["student_name"]].map(_normalize_text)
        normalized["student_name"] = names.mask(names.eq(""), normalized["student_id"])
    else:
        normalized["student_name"] = normalized["student_id"]

    for field in OPTIONAL_PROFILE_FIELDS:
        if field not in columns:
            normalized[field] = pd.NA
            _issue(
                issues,
                severity="warning",
                code="missing_optional_column",
                field=field,
                message=f"Optional profile column '{field}' was not found.",
            )
            continue
        if field == "age":
            values = pd.to_numeric(df[columns[field]], errors="coerce").astype("Int64")
            invalid = df[columns[field]].notna() & values.isna()
            for row in np.flatnonzero(invalid.to_numpy()):
                _issue(
                    issues,
                    severity="warning",
                    code="invalid_optional_value",
                    row=int(row),
                    field=field,
                    value=df.iloc[row][columns[field]],
                    message="Age is not numeric and was left blank.",
                )
            normalized[field] = values
        else:
            values = df[columns[field]].map(_normalize_text)
            missing = values.eq("")
            for row in np.flatnonzero(missing.to_numpy()):
                _issue(
                    issues,
                    severity="warning",
                    code="missing_optional_value",
                    row=int(row),
                    field=field,
                    value=df.iloc[row][columns[field]],
                    message=f"Optional field '{field}' is blank.",
                )
            normalized[field] = values.mask(missing, pd.NA)

    for field in SENSITIVE_FIELDS:
        if field in columns:
            values = df[columns[field]].map(_normalize_text)
            normalized[field] = values.mask(values.eq(""), pd.NA)
        else:
            normalized[field] = pd.NA

    for field in ("sleep_window", "wake_window"):
        source = df[columns[field]]
        mapped = source.map(lambda value: _map_schedule(value, field))
        invalid = mapped.isna()
        for row in np.flatnonzero(invalid.to_numpy()):
            _issue(
                issues,
                severity="error",
                code="unknown_schedule_value",
                row=int(row),
                field=field,
                value=source.iloc[row],
                message=(
                    f"Unrecognized {field.replace('_', ' ')} category. "
                    "Update the documented category mapping before optimization."
                ),
            )
        normalized[field] = mapped.astype("Int8")

    for field in ("noise_tolerance", "study_habit", "cleanliness"):
        source = df[columns[field]]
        mapped = source.map(lambda value: _map_binary(value, field))
        invalid = mapped.isna()
        for row in np.flatnonzero(invalid.to_numpy()):
            _issue(
                issues,
                severity="error",
                code="unknown_behavior_value",
                row=int(row),
                field=field,
                value=source.iloc[row],
                message=(
                    f"Unrecognized {field.replace('_', ' ')} category. "
                    "No default value was assumed."
                ),
            )
        normalized[field] = mapped.astype("Int8")

    normalized = normalized.reset_index(drop=True)
    normalized.insert(0, "student_idx", np.arange(len(normalized), dtype=np.int32))
    result = SurveyParseResult(normalized, issues)
    if strict and not result.is_valid:
        raise SurveyValidationError(result)
    return result


def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible strict wrapper returning normalized students."""
    return parse_student_survey(df, strict=True).data
