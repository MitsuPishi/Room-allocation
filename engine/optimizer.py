"""Scalable, fairness-first room assignment optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .scoring import CompatibilityScores, ScoringConfig


ALGORITHM_VERSION = "fair-room-search-v1"
ProgressCallback = Callable[[dict[str, float | int | str]], None]


@dataclass(frozen=True)
class OptimizationConfig:
    capacity: int = 6
    time_limit_seconds: float = 300.0
    seed: int = 42
    restarts: int = 3
    max_swap_iterations: int = 2_000
    candidate_pool_size: int = 48
    random_candidate_size: int = 24
    stagnation_limit: int = 150
    cp_sat_neighborhood_rooms: int = 4
    cp_sat_time_limit_seconds: float = 8.0
    algorithm_version: str = ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if self.capacity < 2:
            raise ValueError("Room capacity must be at least 2.")
        if self.time_limit_seconds <= 0:
            raise ValueError("Time limit must be positive.")
        if self.restarts < 1:
            raise ValueError("At least one search restart is required.")

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AssignmentMetrics:
    min_student_utility: float
    p10_room_quality: float
    mean_student_utility: float
    mean_room_quality: float
    room_quality_variance: float

    @property
    def objective(self) -> tuple[float, float, float, float]:
        return (
            self.min_student_utility,
            self.p10_room_quality,
            self.mean_student_utility,
            -self.room_quality_variance,
        )


@dataclass
class OptimizationResult:
    assignments: pd.DataFrame
    room_metrics: pd.DataFrame
    student_metrics: pd.DataFrame
    metrics: AssignmentMetrics
    status: str
    runtime_seconds: float
    config: OptimizationConfig
    scoring_config: ScoringConfig
    data_hash: str
    config_hash: str
    search_history: list[dict[str, float | int | str]]

    def metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "algorithm_version": self.config.algorithm_version,
            "scoring_version": self.scoring_config.version,
            "runtime_seconds": self.runtime_seconds,
            "seed": self.config.seed,
            "data_hash": self.data_hash,
            "config_hash": self.config_hash,
            "configuration": asdict(self.config),
            "scoring_configuration": asdict(self.scoring_config),
            "metrics": asdict(self.metrics),
            "search_history": self.search_history,
        }


@dataclass
class _RoomEvaluation:
    student_utilities: np.ndarray
    quality: float
    mean_utility: float

    @property
    def utility_sum(self) -> float:
        return float(self.student_utilities.sum())


def _data_fingerprint(students: pd.DataFrame) -> str:
    fields = [
        field
        for field in (
            "student_id",
            "sleep_window",
            "wake_window",
            "noise_tolerance",
            "study_habit",
            "cleanliness",
        )
        if field in students.columns
    ]
    hashed = pd.util.hash_pandas_object(students[fields], index=False).to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()


def _target_room_sizes(n_students: int, capacity: int) -> np.ndarray:
    n_rooms = int(math.ceil(n_students / capacity))
    base = n_students // n_rooms
    larger_rooms = n_students % n_rooms
    targets = np.full(n_rooms, base, dtype=np.int16)
    targets[:larger_rooms] += 1
    return targets


def _evaluate_room(members: Iterable[int], matrix: np.ndarray) -> _RoomEvaluation:
    indices = np.asarray(list(members), dtype=np.int32)
    if len(indices) <= 1:
        utilities = np.zeros(len(indices), dtype=np.float64)
    else:
        submatrix = matrix[np.ix_(indices, indices)].astype(np.float64)
        utilities = submatrix.sum(axis=1) / (len(indices) - 1)
    return _RoomEvaluation(
        student_utilities=utilities,
        quality=float(utilities.min()) if len(utilities) else 0.0,
        mean_utility=float(utilities.mean()) if len(utilities) else 0.0,
    )


def _lower_percentile(values: np.ndarray, percentile: float) -> float:
    if len(values) == 0:
        return 0.0
    index = int(math.floor((len(values) - 1) * percentile))
    return float(np.partition(values, index)[index])


def _metrics_from_evaluations(
    evaluations: list[_RoomEvaluation],
) -> AssignmentMetrics:
    qualities = np.asarray([evaluation.quality for evaluation in evaluations])
    utility_values = np.concatenate(
        [evaluation.student_utilities for evaluation in evaluations]
    )
    return AssignmentMetrics(
        min_student_utility=float(utility_values.min()),
        p10_room_quality=_lower_percentile(qualities, 0.10),
        mean_student_utility=float(utility_values.mean()),
        mean_room_quality=float(qualities.mean()),
        room_quality_variance=float(qualities.var()),
    )


def evaluate_assignment_metrics(
    rooms: Iterable[Iterable[int]],
    matrix: np.ndarray,
) -> AssignmentMetrics:
    """Evaluate any complete room partition with the production metrics."""
    evaluations = [_evaluate_room(room, matrix) for room in rooms]
    if not evaluations:
        raise ValueError("At least one room is required.")
    return _metrics_from_evaluations(evaluations)


def _objective_with_replacements(
    evaluations: list[_RoomEvaluation],
    replacements: dict[int, _RoomEvaluation],
) -> AssignmentMetrics:
    qualities = np.asarray(
        [
            replacements.get(room_index, evaluation).quality
            for room_index, evaluation in enumerate(evaluations)
        ],
        dtype=np.float64,
    )
    utility_sum = sum(
        replacements.get(room_index, evaluation).utility_sum
        for room_index, evaluation in enumerate(evaluations)
    )
    n_students = sum(len(evaluation.student_utilities) for evaluation in evaluations)
    return AssignmentMetrics(
        min_student_utility=float(qualities.min()),
        p10_room_quality=_lower_percentile(qualities, 0.10),
        mean_student_utility=float(utility_sum / n_students),
        mean_room_quality=float(qualities.mean()),
        room_quality_variance=float(qualities.var()),
    )


def _objective_key(metrics: AssignmentMetrics) -> tuple[float, float, float, float]:
    return tuple(round(value, 8) for value in metrics.objective)


def _initial_assignment(
    matrix: np.ndarray,
    targets: np.ndarray,
    rng: np.random.Generator,
) -> list[list[int]]:
    n_students = len(matrix)
    n_rooms = len(targets)
    neighbor_count = min(max(1, int(targets.max()) - 1), n_students - 1)

    if neighbor_count:
        top_indices = np.argpartition(
            matrix,
            kth=n_students - neighbor_count,
            axis=1,
        )[:, -neighbor_count:]
        top_scores = np.take_along_axis(matrix, top_indices, axis=1)
        placement_ease = top_scores.mean(axis=1)
    else:
        placement_ease = np.zeros(n_students)

    jitter = rng.uniform(0.0, 1e-6, size=n_students)
    order = np.lexsort((jitter, placement_ease))
    rooms: list[list[int]] = [[] for _ in range(n_rooms)]

    for room_index, student in enumerate(order[:n_rooms]):
        rooms[room_index].append(int(student))

    member_table = np.full(
        (n_rooms, int(targets.max())),
        -1,
        dtype=np.int32,
    )
    member_table[:, 0] = order[:n_rooms]
    counts = np.ones(n_rooms, dtype=np.int16)

    for student in order[n_rooms:]:
        safe_members = np.maximum(member_table, 0)
        pair_scores = matrix[int(student), safe_members].astype(np.float64)
        valid = member_table >= 0
        pair_scores[~valid] = np.nan
        candidate_min = np.nanmin(pair_scores, axis=1)
        candidate_mean = np.nanmean(pair_scores, axis=1)
        eligible = counts < targets
        candidate_min[~eligible] = -np.inf
        candidate_mean[~eligible] = -np.inf

        best_min = np.max(candidate_min)
        min_mask = np.isclose(candidate_min, best_min)
        best_mean = np.max(np.where(min_mask, candidate_mean, -np.inf))
        choices = np.flatnonzero(
            min_mask & np.isclose(candidate_mean, best_mean) & eligible
        )
        room_index = int(rng.choice(choices))
        slot = int(counts[room_index])
        rooms[room_index].append(int(student))
        member_table[room_index, slot] = int(student)
        counts[room_index] += 1

    return rooms


def _room_positions(rooms: list[list[int]], n_students: int) -> tuple[np.ndarray, np.ndarray]:
    room_of = np.empty(n_students, dtype=np.int32)
    position_of = np.empty(n_students, dtype=np.int16)
    for room_index, room in enumerate(rooms):
        for position, student in enumerate(room):
            room_of[student] = room_index
            position_of[student] = position
    return room_of, position_of


class RoomOptimizer:
    """Fairness-first hybrid optimizer for flexible-capacity rooms."""

    def __init__(self, config: OptimizationConfig | None = None):
        self.config = config or OptimizationConfig()

    def optimize(
        self,
        students: pd.DataFrame,
        scores: CompatibilityScores | np.ndarray,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> OptimizationResult:
        started = time.monotonic()
        deadline = started + self.config.time_limit_seconds
        score_result = (
            scores
            if isinstance(scores, CompatibilityScores)
            else CompatibilityScores(
                matrix=np.asarray(scores),
                students=students.reset_index(drop=True),
                config=ScoringConfig(),
            )
        )
        matrix = score_result.matrix
        if matrix.shape != (len(students), len(students)):
            raise ValueError("Compatibility matrix shape does not match student count.")
        if len(students) < 2:
            raise ValueError("At least two students are required for room assignment.")

        targets = _target_room_sizes(len(students), self.config.capacity)
        history: list[dict[str, float | int | str]] = []
        best_rooms: list[list[int]] | None = None
        best_evaluations: list[_RoomEvaluation] | None = None
        best_metrics: AssignmentMetrics | None = None

        for restart in range(self.config.restarts):
            if time.monotonic() >= deadline:
                break
            rng = np.random.default_rng(self.config.seed + restart)
            rooms = _initial_assignment(matrix, targets, rng)
            evaluations = [_evaluate_room(room, matrix) for room in rooms]
            metrics = _metrics_from_evaluations(evaluations)
            event = {
                "phase": "initial",
                "restart": restart + 1,
                "min_student_utility": metrics.min_student_utility,
                "p10_room_quality": metrics.p10_room_quality,
                "mean_student_utility": metrics.mean_student_utility,
            }
            history.append(event)
            if progress_callback:
                progress_callback(event)

            rooms, evaluations, metrics = self._swap_search(
                rooms,
                evaluations,
                metrics,
                matrix,
                rng,
                deadline,
                restart,
                history,
                progress_callback,
            )
            rooms, evaluations, metrics, cp_status = self._cp_sat_improvement(
                rooms,
                evaluations,
                metrics,
                matrix,
                deadline,
            )
            if cp_status:
                event = {
                    "phase": "cp_sat_neighborhood",
                    "restart": restart + 1,
                    "status": cp_status,
                    "min_student_utility": metrics.min_student_utility,
                    "p10_room_quality": metrics.p10_room_quality,
                    "mean_student_utility": metrics.mean_student_utility,
                }
                history.append(event)
                if progress_callback:
                    progress_callback(event)

            if best_metrics is None or _objective_key(metrics) > _objective_key(
                best_metrics
            ):
                best_rooms = [room.copy() for room in rooms]
                best_evaluations = evaluations
                best_metrics = metrics

        if best_rooms is None or best_evaluations is None or best_metrics is None:
            raise RuntimeError("The optimizer stopped before creating an assignment.")

        runtime = time.monotonic() - started
        assignments, room_metrics, student_metrics = self._build_outputs(
            students.reset_index(drop=True),
            score_result,
            best_rooms,
            best_evaluations,
        )
        return OptimizationResult(
            assignments=assignments,
            room_metrics=room_metrics,
            student_metrics=student_metrics,
            metrics=best_metrics,
            status="best_found",
            runtime_seconds=runtime,
            config=self.config,
            scoring_config=score_result.config,
            data_hash=_data_fingerprint(students),
            config_hash=hashlib.sha256(
                (
                    self.config.fingerprint()
                    + score_result.config.fingerprint()
                ).encode("ascii")
            ).hexdigest(),
            search_history=history,
        )

    def _swap_search(
        self,
        rooms: list[list[int]],
        evaluations: list[_RoomEvaluation],
        metrics: AssignmentMetrics,
        matrix: np.ndarray,
        rng: np.random.Generator,
        deadline: float,
        restart: int,
        history: list[dict[str, float | int | str]],
        progress_callback: ProgressCallback | None,
    ) -> tuple[list[list[int]], list[_RoomEvaluation], AssignmentMetrics]:
        room_of, position_of = _room_positions(rooms, len(matrix))
        stagnation = 0

        for iteration in range(self.config.max_swap_iterations):
            if time.monotonic() >= deadline or stagnation >= self.config.stagnation_limit:
                break

            quality_order = np.argsort(
                [evaluation.quality for evaluation in evaluations]
            )
            focus_count = min(8, len(quality_order))
            focus_room = int(quality_order[iteration % focus_count])
            focus_eval = evaluations[focus_room]
            focus_positions = np.argsort(focus_eval.student_utilities)

            best_move = None
            best_move_metrics = metrics
            for focus_position in focus_positions[: min(3, len(focus_positions))]:
                student = rooms[focus_room][int(focus_position)]
                pool_size = min(self.config.candidate_pool_size + 1, len(matrix))
                candidates = np.argpartition(matrix[student], -pool_size)[-pool_size:]
                candidates = candidates[room_of[candidates] != focus_room]

                random_size = min(self.config.random_candidate_size, len(matrix))
                random_candidates = rng.choice(
                    len(matrix),
                    size=random_size,
                    replace=False,
                )
                candidates = np.unique(np.concatenate([candidates, random_candidates]))

                for other in candidates:
                    other = int(other)
                    other_room = int(room_of[other])
                    if other_room == focus_room:
                        continue
                    other_position = int(position_of[other])
                    proposed_focus = rooms[focus_room].copy()
                    proposed_other = rooms[other_room].copy()
                    proposed_focus[int(focus_position)] = other
                    proposed_other[other_position] = student
                    focus_new = _evaluate_room(proposed_focus, matrix)
                    other_new = _evaluate_room(proposed_other, matrix)
                    proposed_metrics = _objective_with_replacements(
                        evaluations,
                        {focus_room: focus_new, other_room: other_new},
                    )
                    if _objective_key(proposed_metrics) > _objective_key(
                        best_move_metrics
                    ):
                        best_move_metrics = proposed_metrics
                        best_move = (
                            student,
                            other,
                            focus_room,
                            other_room,
                            int(focus_position),
                            other_position,
                            focus_new,
                            other_new,
                        )

            if best_move is None:
                stagnation += 1
                continue

            (
                student,
                other,
                focus_room,
                other_room,
                focus_position,
                other_position,
                focus_new,
                other_new,
            ) = best_move
            rooms[focus_room][focus_position] = other
            rooms[other_room][other_position] = student
            evaluations[focus_room] = focus_new
            evaluations[other_room] = other_new
            room_of[student], room_of[other] = other_room, focus_room
            position_of[student], position_of[other] = other_position, focus_position
            metrics = best_move_metrics
            stagnation = 0

            if iteration % 25 == 0:
                event = {
                    "phase": "swap_search",
                    "restart": restart + 1,
                    "iteration": iteration + 1,
                    "min_student_utility": metrics.min_student_utility,
                    "p10_room_quality": metrics.p10_room_quality,
                    "mean_student_utility": metrics.mean_student_utility,
                }
                history.append(event)
                if progress_callback:
                    progress_callback(event)

        return rooms, evaluations, metrics

    def _cp_sat_improvement(
        self,
        rooms: list[list[int]],
        evaluations: list[_RoomEvaluation],
        metrics: AssignmentMetrics,
        matrix: np.ndarray,
        deadline: float,
    ) -> tuple[
        list[list[int]],
        list[_RoomEvaluation],
        AssignmentMetrics,
        str | None,
    ]:
        remaining = deadline - time.monotonic()
        if remaining < 1.0 or self.config.cp_sat_neighborhood_rooms < 2:
            return rooms, evaluations, metrics, None

        try:
            from ortools.sat.python import cp_model
        except ImportError:
            return rooms, evaluations, metrics, "unavailable"

        room_count = min(self.config.cp_sat_neighborhood_rooms, len(rooms))
        selected_rooms = np.argsort(
            [evaluation.quality for evaluation in evaluations]
        )[:room_count].tolist()
        local_students = [
            student for room_index in selected_rooms for student in rooms[room_index]
        ]
        if len(local_students) > 40:
            return rooms, evaluations, metrics, "skipped_large_neighborhood"

        model = cp_model.CpModel()
        x = {}
        for local_index in range(len(local_students)):
            for local_room in range(room_count):
                x[local_index, local_room] = model.new_bool_var(
                    f"x_{local_index}_{local_room}"
                )
            model.add_exactly_one(x[local_index, room] for room in range(room_count))

        room_sizes = [len(rooms[index]) for index in selected_rooms]
        for local_room, room_size in enumerate(room_sizes):
            model.add(
                sum(x[student, local_room] for student in range(len(local_students)))
                == room_size
            )

        y = {}
        objective_terms = []
        utility_terms: dict[tuple[int, int], list] = {
            (student, room): []
            for student in range(len(local_students))
            for room in range(room_count)
        }
        for first in range(len(local_students)):
            for second in range(first + 1, len(local_students)):
                score = int(matrix[local_students[first], local_students[second]])
                for local_room in range(room_count):
                    together = model.new_bool_var(
                        f"y_{first}_{second}_{local_room}"
                    )
                    y[first, second, local_room] = together
                    model.add(together <= x[first, local_room])
                    model.add(together <= x[second, local_room])
                    model.add(
                        together
                        >= x[first, local_room] + x[second, local_room] - 1
                    )
                    objective_terms.append(score * together)
                    utility_terms[first, local_room].append(score * together)
                    utility_terms[second, local_room].append(score * together)

        floor_score = int(math.floor(metrics.min_student_utility))
        for student in range(len(local_students)):
            for local_room, room_size in enumerate(room_sizes):
                model.add(
                    sum(utility_terms[student, local_room])
                    >= floor_score * (room_size - 1) * x[student, local_room]
                )

        model.maximize(sum(objective_terms))
        for local_index, student in enumerate(local_students):
            original_room = next(
                room
                for room, room_index in enumerate(selected_rooms)
                if student in rooms[room_index]
            )
            model.add_hint(x[local_index, original_room], 1)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(
            self.config.cp_sat_time_limit_seconds,
            max(0.5, remaining - 0.2),
        )
        solver.parameters.num_search_workers = 4
        status = solver.solve(model)
        status_name = solver.status_name(status)
        if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            return rooms, evaluations, metrics, status_name.lower()

        proposed_rooms = [room.copy() for room in rooms]
        for local_room, room_index in enumerate(selected_rooms):
            proposed_rooms[room_index] = [
                local_students[student]
                for student in range(len(local_students))
                if solver.value(x[student, local_room])
            ]
        proposed_evaluations = evaluations.copy()
        for room_index in selected_rooms:
            proposed_evaluations[room_index] = _evaluate_room(
                proposed_rooms[room_index],
                matrix,
            )
        proposed_metrics = _metrics_from_evaluations(proposed_evaluations)
        if _objective_key(proposed_metrics) > _objective_key(metrics):
            return (
                proposed_rooms,
                proposed_evaluations,
                proposed_metrics,
                status_name.lower(),
            )
        return rooms, evaluations, metrics, f"{status_name.lower()}_no_improvement"

    def _build_outputs(
        self,
        students: pd.DataFrame,
        score_result: CompatibilityScores,
        rooms: list[list[int]],
        evaluations: list[_RoomEvaluation],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        assignment_records = []
        room_records = []
        student_records = []
        for room_index, (room, evaluation) in enumerate(
            zip(rooms, evaluations, strict=True),
            start=1,
        ):
            room_id = f"Room-{room_index:04d}"
            breakdown = score_result.explain_room(room)
            room_records.append(
                {
                    "room_id": room_id,
                    "room_size": len(room),
                    "room_quality": evaluation.quality,
                    "mean_student_utility": evaluation.mean_utility,
                    **{
                        f"{key}_contribution": value
                        for key, value in breakdown.items()
                        if key != "total"
                    },
                }
            )
            for position, (student_index, utility) in enumerate(
                zip(room, evaluation.student_utilities, strict=True),
                start=1,
            ):
                student = students.iloc[student_index]
                base = {
                    "room_id": room_id,
                    "bed": position,
                    "student_idx": int(student_index),
                    "student_id": student["student_id"],
                    "student_name": student.get("student_name", student["student_id"]),
                    "student_utility": float(utility),
                    "room_quality": evaluation.quality,
                }
                assignment_records.append(base)
                student_records.append(
                    {
                        "student_idx": int(student_index),
                        "student_id": student["student_id"],
                        "room_id": room_id,
                        "student_utility": float(utility),
                    }
                )
        return (
            pd.DataFrame(assignment_records).sort_values(["room_id", "bed"]),
            pd.DataFrame(room_records).sort_values("room_id"),
            pd.DataFrame(student_records).sort_values("student_idx"),
        )


class DormOptimizationEngine:
    """Compatibility adapter for callers using the old engine interface."""

    def __init__(
        self,
        df_students: pd.DataFrame,
        df_rooms: pd.DataFrame,
        matrix: np.ndarray,
    ):
        self.students = df_students
        self.rooms = df_rooms
        self.matrix = matrix
        self.progress_callback = None
        self.result: OptimizationResult | None = None

    def build_model(self) -> None:
        """Retained for compatibility; the hybrid search builds state in solve()."""

    def set_progress_callback(self, callback) -> None:
        self.progress_callback = callback

    def solve(self, time_limit_sec: int = 30):
        capacities = self.rooms["capacity"].dropna().astype(int).unique()
        if len(capacities) != 1:
            raise ValueError("The compatibility adapter requires uniform capacities.")
        optimizer = RoomOptimizer(
            OptimizationConfig(
                capacity=int(capacities[0]),
                time_limit_seconds=float(time_limit_sec),
            )
        )

        def adapt_progress(event: dict[str, float | int | str]) -> None:
            if not self.progress_callback:
                return
            try:
                self.progress_callback(event)
            except TypeError:
                self.progress_callback(
                    current_objective=event.get("mean_student_utility", 0.0),
                    best_bound=event.get("mean_student_utility", 0.0),
                    solution_count=len(event),
                    gap_percent=0.0,
                )

        self.result = optimizer.optimize(
            self.students,
            self.matrix,
            progress_callback=adapt_progress,
        )
        output = self.result.assignments.rename(columns={"room_id": "generated_room_id"})
        room_names = self.rooms.reset_index(drop=True).copy()
        room_names["generated_room_id"] = [
            f"Room-{index:04d}" for index in range(1, len(room_names) + 1)
        ]
        output = output.merge(
            room_names[["generated_room_id", "room_id", "room_name"]],
            on="generated_room_id",
            how="left",
        )
        return output, "BestFound"
