import tempfile
import unittest
from pathlib import Path

from engine.cli import main
from tests.test_preprocessing import raw_survey


class CliTests(unittest.TestCase):
    def test_assign_command_writes_reproducibility_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "survey.csv"
            output_path = root / "results"
            raw_survey().to_csv(input_path, index=False)

            exit_code = main(
                [
                    "assign",
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(output_path),
                    "--capacity",
                    "2",
                    "--time-limit",
                    "2",
                    "--restarts",
                    "1",
                    "--quiet",
                ]
            )

            self.assertEqual(exit_code, 0)
            for name in (
                "assignments.csv",
                "room_metrics.csv",
                "student_metrics.csv",
                "validation_report.csv",
                "run_metadata.json",
            ):
                self.assertTrue((output_path / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
