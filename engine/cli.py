"""Command-line interface for reproducible room assignment runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

from .optimizer import OptimizationConfig, RoomOptimizer
from .preprocessing import parse_student_survey
from .scoring import CompatibilityScorer, ScoringConfig


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".xlsx":
        return pd.read_excel(path)
    raise ValueError("Input must be a CSV or Excel workbook.")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def assign_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = _read_table(input_path)
    parsed = parse_student_survey(raw)
    validation_path = output_dir / "validation_report.csv"
    parsed.validation_report().to_csv(validation_path, index=False, encoding="utf-8-sig")
    if not parsed.is_valid:
        print(
            f"Validation failed with {parsed.error_count} error(s). "
            f"See {validation_path}.",
            file=sys.stderr,
        )
        return 2

    scoring_config = ScoringConfig()
    scorer = CompatibilityScorer(scoring_config)
    scores = scorer.score(parsed.data)
    optimizer = RoomOptimizer(
        OptimizationConfig(
            capacity=args.capacity,
            time_limit_seconds=args.time_limit,
            seed=args.seed,
            restarts=args.restarts,
        )
    )

    def progress(event: dict) -> None:
        print(
            f"[{event.get('phase')}] "
            f"minimum={event.get('min_student_utility', 0):.2f} "
            f"p10={event.get('p10_room_quality', 0):.2f} "
            f"mean={event.get('mean_student_utility', 0):.2f}"
        )

    result = optimizer.optimize(
        parsed.data,
        scores,
        progress_callback=progress if not args.quiet else None,
    )

    profile_fields = [
        field
        for field in (
            "student_idx",
            "faculty",
            "major",
            "age",
            "sleep_window",
            "wake_window",
            "noise_tolerance",
            "study_habit",
            "cleanliness",
        )
        if field in parsed.data.columns
    ]
    assignments = result.assignments.merge(
        parsed.data[profile_fields],
        on="student_idx",
        how="left",
    )
    assignments.to_csv(
        output_dir / "assignments.csv",
        index=False,
        encoding="utf-8-sig",
    )
    result.room_metrics.to_csv(
        output_dir / "room_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    result.student_metrics.to_csv(
        output_dir / "student_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    _write_json(output_dir / "run_metadata.json", result.metadata())

    print(
        f"Assigned {len(assignments)} students to "
        f"{assignments['room_id'].nunique()} rooms. Status: {result.status}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m engine",
        description="Validated, reproducible university room assignment.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    assign = subparsers.add_parser("assign", help="Validate and assign a survey file.")
    assign.add_argument("--input", required=True, help="Raw questionnaire CSV/XLSX.")
    assign.add_argument("--output-dir", default="results", help="Report directory.")
    assign.add_argument("--capacity", type=int, default=6)
    assign.add_argument("--time-limit", type=float, default=300.0)
    assign.add_argument("--seed", type=int, default=42)
    assign.add_argument("--restarts", type=int, default=3)
    assign.add_argument("--quiet", action="store_true")
    assign.set_defaults(handler=assign_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2
