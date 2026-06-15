"""Public API for the UniMate room assignment engine."""

from .exact import ExactTotalScoreResult, solve_exact_total_score, total_pair_score
from .optimizer import (
    ALGORITHM_VERSION,
    AssignmentMetrics,
    DormOptimizationEngine,
    evaluate_assignment_metrics,
    OptimizationConfig,
    OptimizationResult,
    RoomOptimizer,
)
from .preprocessing import (
    SCHEMA_VERSION,
    SurveyParseResult,
    SurveyValidationError,
    ValidationIssue,
    parse_student_survey,
    preprocess_student_data,
)
from .scoring import (
    SCORING_VERSION,
    CompatibilityEngine,
    CompatibilityScorer,
    CompatibilityScores,
    ScoringConfig,
)

__all__ = [
    "ALGORITHM_VERSION",
    "AssignmentMetrics",
    "CompatibilityEngine",
    "CompatibilityScorer",
    "CompatibilityScores",
    "DormOptimizationEngine",
    "ExactTotalScoreResult",
    "OptimizationConfig",
    "OptimizationResult",
    "RoomOptimizer",
    "SCHEMA_VERSION",
    "SCORING_VERSION",
    "ScoringConfig",
    "SurveyParseResult",
    "SurveyValidationError",
    "ValidationIssue",
    "parse_student_survey",
    "preprocess_student_data",
    "evaluate_assignment_metrics",
    "solve_exact_total_score",
    "total_pair_score",
]
