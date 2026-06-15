import unittest

import numpy as np
import pandas as pd

from engine.exact import solve_exact_total_score, total_pair_score
from engine.optimizer import OptimizationConfig, RoomOptimizer
from engine.scoring import CompatibilityScorer


def normalized_students(count: int = 24) -> pd.DataFrame:
    index = np.arange(count)
    return pd.DataFrame(
        {
            "student_idx": index,
            "student_id": [f"s-{value:03d}" for value in index],
            "student_name": [f"Student {value}" for value in index],
            "cleanliness": index % 2,
            "noise_tolerance": (index // 2) % 2,
            "study_habit": (index // 3) % 2,
            "sleep_window": index % 5,
            "wake_window": index % 4,
            "faculty": pd.NA,
            "major": pd.NA,
            "age": pd.NA,
            "residence": "sensitive",
            "ethnicity": "sensitive",
            "cultural_group": "sensitive",
        }
    )


class RoomOptimizerTests(unittest.TestCase):
    def test_assignment_is_complete_balanced_and_deterministic(self):
        students = normalized_students()
        scores = CompatibilityScorer().score(students)
        config = OptimizationConfig(
            capacity=6,
            time_limit_seconds=3,
            seed=7,
            restarts=1,
            max_swap_iterations=80,
            cp_sat_time_limit_seconds=1,
        )

        first = RoomOptimizer(config).optimize(students, scores)
        second = RoomOptimizer(config).optimize(students, scores)

        self.assertEqual(len(first.assignments), len(students))
        self.assertEqual(first.assignments["student_id"].nunique(), len(students))
        self.assertLessEqual(first.assignments.groupby("room_id").size().max(), 6)
        self.assertLessEqual(
            first.assignments.groupby("room_id").size().max()
            - first.assignments.groupby("room_id").size().min(),
            1,
        )
        self.assertEqual(
            first.assignments[["student_id", "room_id"]].to_dict("records"),
            second.assignments[["student_id", "room_id"]].to_dict("records"),
        )

    def test_exact_oracle_bounds_small_heuristic_total_score(self):
        students = normalized_students(8)
        scores = CompatibilityScorer().score(students)
        config = OptimizationConfig(
            capacity=2,
            time_limit_seconds=2,
            seed=11,
            restarts=1,
            max_swap_iterations=40,
            cp_sat_neighborhood_rooms=2,
            cp_sat_time_limit_seconds=0.5,
        )
        heuristic = RoomOptimizer(config).optimize(students, scores)
        heuristic_rooms = [
            group["student_idx"].astype(int).tolist()
            for _, group in heuristic.assignments.groupby("room_id")
        ]
        exact = solve_exact_total_score(
            scores.matrix,
            capacity=2,
            time_limit_seconds=5,
        )

        self.assertIn(exact.status, {"optimal", "feasible"})
        self.assertLessEqual(
            total_pair_score(heuristic_rooms, scores.matrix),
            exact.objective + 1e-9,
        )


if __name__ == "__main__":
    unittest.main()
