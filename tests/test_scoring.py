import unittest

import numpy as np
import pandas as pd

from engine.scoring import CompatibilityScorer, ScoringConfig


class CompatibilityScoringTests(unittest.TestCase):
    def setUp(self):
        self.students = pd.DataFrame(
            {
                "student_id": ["a", "b", "c"],
                "cleanliness": [1, 1, 0],
                "noise_tolerance": [0, 0, 1],
                "study_habit": [1, 1, 0],
                "sleep_window": [1, 1, 4],
                "wake_window": [2, 2, 0],
                "ethnicity": ["x", "y", "z"],
                "cultural_group": ["r1", "r2", "r3"],
                "residence": ["p1", "p2", "p3"],
            }
        )

    def test_score_is_symmetric_bounded_and_explainable(self):
        result = CompatibilityScorer().score(self.students)

        np.testing.assert_array_equal(result.matrix, result.matrix.T)
        self.assertGreaterEqual(result.matrix.min(), 0)
        self.assertLessEqual(result.matrix.max(), 100)
        self.assertEqual(result.matrix[0, 1], 100)
        explanation = result.explain_pair(0, 1)
        self.assertAlmostEqual(explanation["total"], 100.0)

    def test_sensitive_attributes_do_not_change_scores(self):
        first = CompatibilityScorer().score(self.students).matrix
        altered = self.students.copy()
        altered[["ethnicity", "cultural_group", "residence"]] = "changed"
        second = CompatibilityScorer().score(altered).matrix

        np.testing.assert_array_equal(first, second)

    def test_sensitivity_weights_are_normalized(self):
        config = ScoringConfig.from_weights(
            {"cleanliness": 10, "noise": 20, "study": 30, "schedule": 40}
        )

        self.assertAlmostEqual(sum(config.weights.values()), 100.0)
        self.assertIn("sensitivity", config.version)


if __name__ == "__main__":
    unittest.main()
