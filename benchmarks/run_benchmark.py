"""Reproducible performance and quality benchmark for the production engine."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import sys
import threading
import time

import numpy as np
import pandas as pd
import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import (
    CompatibilityScorer,
    evaluate_assignment_metrics,
    OptimizationConfig,
    RoomOptimizer,
    parse_student_survey,
    total_pair_score,
)


def balanced_random_rooms(
    n_students: int,
    capacity: int,
    seed: int,
) -> list[list[int]]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(n_students)
    n_rooms = int(np.ceil(n_students / capacity))
    return [chunk.tolist() for chunk in np.array_split(order, n_rooms)]


def rooms_from_result(assignments: pd.DataFrame) -> list[list[int]]:
    return [
        group["student_idx"].astype(int).tolist()
        for _, group in assignments.groupby("room_id")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="Data/MOCK_DATA-Women.csv")
    parser.add_argument("--students", type=int, choices=[1000, 5000], default=1000)
    parser.add_argument("--capacity", type=int, default=6)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="benchmarks/latest.json")
    args = parser.parse_args()

    raw = pd.read_csv(args.input)
    if args.students > len(raw):
        repeats = int(np.ceil(args.students / len(raw)))
        raw = pd.concat([raw] * repeats, ignore_index=True).iloc[: args.students]
    else:
        raw = raw.iloc[: args.students]

    process = psutil.Process()
    peak_rss = process.memory_info().rss
    stop_sampling = threading.Event()

    def sample_memory() -> None:
        nonlocal peak_rss
        while not stop_sampling.wait(0.05):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    try:
        parsed = parse_student_survey(raw, strict=True)
        scoring_started = time.perf_counter()
        scores = CompatibilityScorer().score(parsed.data)
        scoring_seconds = time.perf_counter() - scoring_started

        random_rooms = balanced_random_rooms(
            len(parsed.data),
            args.capacity,
            args.seed,
        )
        random_metrics = evaluate_assignment_metrics(random_rooms, scores.matrix)
        greedy = RoomOptimizer(
            OptimizationConfig(
                capacity=args.capacity,
                time_limit_seconds=max(30.0, args.time_limit),
                seed=args.seed,
                restarts=1,
                max_swap_iterations=0,
                cp_sat_neighborhood_rooms=0,
            )
        ).optimize(parsed.data, scores)
        greedy_rooms = rooms_from_result(greedy.assignments)

        optimizer = RoomOptimizer(
            OptimizationConfig(
                capacity=args.capacity,
                time_limit_seconds=args.time_limit,
                seed=args.seed,
            )
        )
        result = optimizer.optimize(parsed.data, scores)
        optimized_rooms = rooms_from_result(result.assignments)
    finally:
        stop_sampling.set()
        sampler.join(timeout=1)
        peak_rss = max(peak_rss, process.memory_info().rss)

    payload = {
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        },
        "parameters": vars(args),
        "scoring_seconds": scoring_seconds,
        "matrix_bytes": int(scores.matrix.nbytes),
        "peak_process_rss_bytes": int(peak_rss),
        "random_total_pair_score": total_pair_score(random_rooms, scores.matrix),
        "random_metrics": asdict(random_metrics),
        "greedy_total_pair_score": total_pair_score(greedy_rooms, scores.matrix),
        "greedy_metrics": asdict(greedy.metrics),
        "optimized_total_pair_score": total_pair_score(
            optimized_rooms,
            scores.matrix,
        ),
        "optimization": result.metadata(),
        "metrics": asdict(result.metrics),
        "acceptance": {
            "runtime_below_five_minutes": result.runtime_seconds < 300,
            "peak_rss_below_one_gib": peak_rss < 1024**3,
            "mean_not_worse_than_greedy": (
                result.metrics.mean_student_utility
                >= greedy.metrics.mean_student_utility
            ),
            "fairness_not_worse_than_greedy": (
                result.metrics.objective >= greedy.metrics.objective
            ),
            "total_score_not_worse_than_random": (
                total_pair_score(optimized_rooms, scores.matrix)
                >= total_pair_score(random_rooms, scores.matrix)
            ),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
