import unittest

import pandas as pd

from engine.preprocessing import parse_student_survey


def raw_survey() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "دانشکده": ["فنی مهندسی", "علوم"],
            "رشته": ["کامپیوتر", "فیزیک"],
            "سن": [20, 21],
            "شهر سکونت": ["تهران", "کرج"],
            "قومیت": ["فارس", "ترک"],
            "اغلب شب‌ها در چه بازه‌ی زمانی می‌خوابید؟": ["11-Oct", "2-3"],
            "اغلب صبح‌ها چه ساعتی بیدار می‌شوید؟": ["5-Apr", "7-8"],
            "سطح تحمل سر و صدا در شما چه‌گونه است؟": [
                "علاقه مند به محیط های پر جنب و جوش",
                "حساس به سر و صدا و نیازمند به محیطی آرام",
            ],
            "عادات مطالعه شما به چه صورت است؟": [
                "نیاز به تمرکز در سکوت کامل",
                "امکان تمرکز با موسیقی یا سر و صدا",
            ],
            "شما در نظافت و سازماندهی جزو کدام دسته از افراد هستید؟": [
                "نظم طلبان: تمیزی مهم است",
                "راحت طلبان: محیط کمی آشفته",
            ],
            "دین": ["الف", "ب"],
        }
    )


class SurveyParsingTests(unittest.TestCase):
    def test_parses_raw_persian_schema_and_recovers_excel_ranges(self):
        result = parse_student_survey(raw_survey())

        self.assertTrue(result.is_valid)
        self.assertEqual(result.data["sleep_window"].tolist(), [0, 4])
        self.assertEqual(result.data["wake_window"].tolist(), [0, 3])
        self.assertEqual(result.data["noise_tolerance"].tolist(), [1, 0])
        self.assertEqual(result.data["study_habit"].tolist(), [1, 0])
        self.assertEqual(result.data["cleanliness"].tolist(), [1, 0])
        self.assertEqual(result.data["student_id"].nunique(), 2)

    def test_rejects_one_hot_encoded_input(self):
        encoded = pd.DataFrame(
            {
                "age": [20],
                "sleep_time": [1],
                "wake_time": [2],
                "noise_tolerance": [0],
                "study_habits": [1],
                "cleanliness": [1],
                "ethnicity_a": [1],
                "ethnicity_b": [0],
                "province_a": [1],
                "province_b": [0],
                "major_a": [1],
                "major_b": [0],
                "faculty_a": [1],
                "faculty_b": [0],
                **{f"extra_{index}": [0] for index in range(10)},
            }
        )

        result = parse_student_survey(encoded)

        self.assertFalse(result.is_valid)
        self.assertIn(
            "encoded_dataset_not_supported",
            result.validation_report()["code"].tolist(),
        )

    def test_unknown_required_value_is_an_error_not_an_imputation(self):
        survey = raw_survey()
        survey.iloc[0, survey.columns.get_loc("عادات مطالعه شما به چه صورت است؟")] = (
            "unknown category"
        )

        result = parse_student_survey(survey)

        self.assertFalse(result.is_valid)
        issue = result.validation_report().query("field == 'study_habit'").iloc[0]
        self.assertEqual(issue["severity"], "error")


if __name__ == "__main__":
    unittest.main()
