"""Transparent, versioned roommate compatibility scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable

import numpy as np
import pandas as pd


SCORING_VERSION = "compatibility-v1"
SCORING_FIELDS = (
    "cleanliness",
    "noise_tolerance",
    "study_habit",
    "sleep_window",
    "wake_window",
)


@dataclass(frozen=True)
class ScoringConfig:
    cleanliness_weight: float = 25.0
    noise_weight: float = 25.0
    study_weight: float = 25.0
    schedule_weight: float = 25.0
    version: str = SCORING_VERSION

    def __post_init__(self) -> None:
        weights = self.weights
        if any(weight < 0 for weight in weights.values()):
            raise ValueError("Compatibility weights cannot be negative.")
        if not np.isclose(sum(weights.values()), 100.0):
            raise ValueError("Compatibility weights must sum to 100.")

    @property
    def weights(self) -> dict[str, float]:
        return {
            "cleanliness": float(self.cleanliness_weight),
            "noise": float(self.noise_weight),
            "study": float(self.study_weight),
            "schedule": float(self.schedule_weight),
        }

    @classmethod
    def from_weights(cls, weights: dict[str, float]) -> "ScoringConfig":
        raw = {
            "cleanliness": float(weights.get("cleanliness", 25.0)),
            "noise": float(weights.get("noise", 25.0)),
            "study": float(weights.get("study", 25.0)),
            "schedule": float(weights.get("schedule", 25.0)),
        }
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("At least one compatibility weight must be positive.")
        normalized = {key: value * 100.0 / total for key, value in raw.items()}
        return cls(
            cleanliness_weight=normalized["cleanliness"],
            noise_weight=normalized["noise"],
            study_weight=normalized["study"],
            schedule_weight=normalized["schedule"],
            version=f"{SCORING_VERSION}-sensitivity",
        )

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CompatibilityScores:
    matrix: np.ndarray
    students: pd.DataFrame
    config: ScoringConfig

    def explain_pair(self, first: int, second: int) -> dict[str, float]:
        if first == second:
            return {
                "cleanliness": 0.0,
                "noise": 0.0,
                "study": 0.0,
                "schedule": 0.0,
                "total": 0.0,
            }
        a = self.students.iloc[int(first)]
        b = self.students.iloc[int(second)]
        contributions = _pair_contributions(a, b, self.config)
        contributions["total"] = float(sum(contributions.values()))
        return contributions

    def explain_room(self, student_indices: Iterable[int]) -> dict[str, float]:
        indices = [int(index) for index in student_indices]
        pairs = [
            self.explain_pair(indices[left], indices[right])
            for left in range(len(indices))
            for right in range(left + 1, len(indices))
        ]
        if not pairs:
            return {
                "cleanliness": 0.0,
                "noise": 0.0,
                "study": 0.0,
                "schedule": 0.0,
                "total": 0.0,
            }
        return {
            key: float(np.mean([pair[key] for pair in pairs]))
            for key in ("cleanliness", "noise", "study", "schedule", "total")
        }


def _pair_contributions(
    first: pd.Series,
    second: pd.Series,
    config: ScoringConfig,
) -> dict[str, float]:
    schedule_sleep = 1.0 - abs(
        int(first["sleep_window"]) - int(second["sleep_window"])
    ) / 4.0
    schedule_wake = 1.0 - abs(
        int(first["wake_window"]) - int(second["wake_window"])
    ) / 3.0
    return {
        "cleanliness": (
            config.cleanliness_weight
            if int(first["cleanliness"]) == int(second["cleanliness"])
            else 0.0
        ),
        "noise": (
            config.noise_weight
            if int(first["noise_tolerance"]) == int(second["noise_tolerance"])
            else 0.0
        ),
        "study": (
            config.study_weight
            if int(first["study_habit"]) == int(second["study_habit"])
            else 0.0
        ),
        "schedule": config.schedule_weight
        * max(0.0, (schedule_sleep + schedule_wake) / 2.0),
    }


class CompatibilityScorer:
    """Compute pair scores without using sensitive demographic attributes."""

    def __init__(
        self,
        config: ScoringConfig | None = None,
        *,
        chunk_size: int = 256,
    ):
        self.config = config or ScoringConfig()
        self.chunk_size = max(1, int(chunk_size))

    def score(self, students: pd.DataFrame) -> CompatibilityScores:
        missing = [field for field in SCORING_FIELDS if field not in students.columns]
        if missing:
            raise ValueError(
                "Normalized student data is missing scoring fields: "
                + ", ".join(missing)
            )
        if students[list(SCORING_FIELDS)].isna().any().any():
            raise ValueError("Scoring fields cannot contain missing values.")

        n_students = len(students)
        matrix = np.zeros((n_students, n_students), dtype=np.int16)
        cleanliness = students["cleanliness"].to_numpy(dtype=np.int8)
        noise = students["noise_tolerance"].to_numpy(dtype=np.int8)
        study = students["study_habit"].to_numpy(dtype=np.int8)
        sleep = students["sleep_window"].to_numpy(dtype=np.int8)
        wake = students["wake_window"].to_numpy(dtype=np.int8)
        config = self.config

        for start in range(0, n_students, self.chunk_size):
            stop = min(start + self.chunk_size, n_students)
            row_slice = slice(start, stop)
            scores = (
                (cleanliness[row_slice, None] == cleanliness[None, :])
                * config.cleanliness_weight
            ).astype(np.float32)
            scores += (
                (noise[row_slice, None] == noise[None, :]) * config.noise_weight
            )
            scores += (
                (study[row_slice, None] == study[None, :]) * config.study_weight
            )

            sleep_similarity = 1.0 - (
                np.abs(
                    sleep[row_slice, None].astype(np.int16)
                    - sleep[None, :].astype(np.int16)
                )
                / 4.0
            )
            wake_similarity = 1.0 - (
                np.abs(
                    wake[row_slice, None].astype(np.int16)
                    - wake[None, :].astype(np.int16)
                )
                / 3.0
            )
            scores += (
                np.maximum(0.0, (sleep_similarity + wake_similarity) / 2.0)
                * config.schedule_weight
            )
            matrix[row_slice] = np.rint(scores).astype(np.int16)

        np.fill_diagonal(matrix, 0)
        return CompatibilityScores(
            matrix=matrix,
            students=students.reset_index(drop=True),
            config=config,
        )


class CompatibilityEngine:
    """Compatibility wrapper for the pre-rebuild public API."""

    def __init__(self, weights: dict[str, float] | None = None):
        config = ScoringConfig.from_weights(weights) if weights else ScoringConfig()
        self.scorer = CompatibilityScorer(config)
        self.last_result: CompatibilityScores | None = None

    def compute_matrix(self, df_students: pd.DataFrame) -> np.ndarray:
        self.last_result = self.scorer.score(df_students)
        return self.last_result.matrix
