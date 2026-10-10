from __future__ import annotations

import unittest

from suda.desktop import LANGUAGE_REFERENCE, LESSONS, STARTER_SOURCE, STUDY_REPORT
from suda.desktop.runner import run_editor_source


class DesktopLearningTests(unittest.TestCase):
    def test_starter_program_runs_in_editor_runtime(self) -> None:
        result = run_editor_source(STARTER_SOURCE)
        self.assertIsNone(result.error)
        self.assertIn("هلا بيك في سُدى", result.output)
        self.assertIn("15", result.output)

    def test_every_lesson_example_compiles_and_runs(self) -> None:
        self.assertGreaterEqual(len(LESSONS), 8)
        for lesson in LESSONS:
            with self.subTest(lesson=lesson.title):
                result = run_editor_source(lesson.source)
                self.assertIsNone(result.error)

    def test_editor_runtime_enforces_instruction_budget(self) -> None:
        result = run_editor_source("طالما صحيح:\n    عدد = 1\n")
        self.assertIn("حد التعليمات", result.error or "")

    def test_report_states_scope_and_learning_value(self) -> None:
        self.assertIn("مو", STUDY_REPORT)
        self.assertIn("native machine code", STUDY_REPORT)
        self.assertIn("bytecode", STUDY_REPORT)

    def test_offline_reference_covers_runtime_and_limits(self) -> None:
        for feature in ("لا_شيء", "رتب", "توازن المكدس", "4096 بت", "sandbox"):
            with self.subTest(feature=feature):
                self.assertIn(feature, LANGUAGE_REFERENCE)


if __name__ == "__main__":
    unittest.main()
