from pathlib import Path
import unittest

import pandas as pd

from engine import parse_student_survey


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RepositoryDatasetTests(unittest.TestCase):
    def test_original_mock_cohorts_match_the_canonical_schema(self):
        for relative_path in (
            "Data/MOCK_DATA-Women.csv",
            "Data/MOCK_DATA-Men.csv",
        ):
            with self.subTest(dataset=relative_path):
                raw = pd.read_csv(PROJECT_ROOT / relative_path)
                result = parse_student_survey(raw)

                self.assertTrue(
                    result.is_valid,
                    result.validation_report().to_string(index=False),
                )
                self.assertEqual(len(result.data), 1000)
                self.assertEqual(result.data["student_id"].nunique(), 1000)


if __name__ == "__main__":
    unittest.main()
