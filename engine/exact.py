"""Small-instance exact oracle used for research validation."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np
from ortools.sat.python import cp_model


@dataclass(frozen=True)
class ExactTotalScoreResult:
    rooms: list[list[int]]
    status: str
    objective: float | None
    best_bound: float | None
    runtime_seconds: float


def _target_sizes(n_students: int, capacity: int) -> list[int]:
    n_rooms = math.ceil(n_students / capacity)
    base = n_students // n_rooms
    remainder = n_students % n_rooms
    return [base + (room < remainder) for room in range(n_rooms)]


def total_pair_score(rooms: list[list[int]], matrix: np.ndarray) -> float:
    total = 0.0
    for room in rooms:
        for left in range(len(room)):
            for right in range(left + 1, len(room)):
                total += float(matrix[room[left], room[right]])
    return total


def solve_exact_total_score(
    matrix: np.ndarray,
    *,
    capacity: int,
    time_limit_seconds: float = 60.0,
) -> ExactTotalScoreResult:
    """Maximize total within-room pair score for small benchmark instances.

    This oracle does not implement the production fairness objective. It exists
    to quantify the total-score gap on small instances where an exact solve is
    computationally reasonable.
    """
    started = time.monotonic()
    matrix = np.asarray(matrix)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("matrix must be square")
    if len(matrix) > 60:
        raise ValueError("The exact oracle is limited to 60 students.")
    if capacity < 2:
        raise ValueError("capacity must be at least 2")

    n_students = len(matrix)
    sizes = _target_sizes(n_students, capacity)
    model = cp_model.CpModel()
    x = {
        (student, room): model.new_bool_var(f"x_{student}_{room}")
        for student in range(n_students)
        for room in range(len(sizes))
    }
    for student in range(n_students):
        model.add_exactly_one(x[student, room] for room in range(len(sizes)))
    for room, size in enumerate(sizes):
        model.add(sum(x[student, room] for student in range(n_students)) == size)

    objective_terms = []
    for first in range(n_students):
        for second in range(first + 1, n_students):
            score = int(matrix[first, second])
            for room in range(len(sizes)):
                together = model.new_bool_var(f"y_{first}_{second}_{room}")
                model.add(together <= x[first, room])
                model.add(together <= x[second, room])
                model.add(together >= x[first, room] + x[second, room] - 1)
                objective_terms.append(score * together)
    model.maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status).lower()
    runtime = time.monotonic() - started
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return ExactTotalScoreResult(
            rooms=[],
            status=status_name,
            objective=None,
            best_bound=None,
            runtime_seconds=runtime,
        )

    rooms = [
        [
            student
            for student in range(n_students)
            if solver.value(x[student, room])
        ]
        for room in range(len(sizes))
    ]
    return ExactTotalScoreResult(
        rooms=rooms,
        status=status_name,
        objective=float(solver.objective_value),
        best_bound=float(solver.best_objective_bound),
        runtime_seconds=runtime,
    )
