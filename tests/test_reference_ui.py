from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from frameforge.core.benchmark import analyze_frame_times
from frameforge.core.benchmark_store import BenchmarkStore, MAX_HISTORY
from frameforge.ui.main_window import MainWindow


class ReferenceRunUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp.name)
        self.app_data_patch = patch("frameforge.ui.main_window.app_data_dir", return_value=self.data_path)
        self.app_data_patch.start()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.app_data_patch.stop()
        self.temp.cleanup()

    def test_pin_unpin_persists_and_keeps_group_and_pair_identity(self):
        self.window.benchmark_runs = [analyze_frame_times(f"run-{index}.csv", [10 + index]) for index in range(4)]
        self.window.benchmark_store.save(self.window.benchmark_runs)
        self.window._refresh_benchmark_history()
        original = self.window.benchmark_runs[2]
        self.window._benchmark_group_a.add(id(original))
        self.window.benchmark_before.setCurrentIndex(2)
        self.window.benchmark_after.setCurrentIndex(3)
        self.window._last_benchmark_comparison = ("pair", original, self.window.benchmark_runs[3])
        self.window.export_benchmark_button.setEnabled(True)

        self.window.benchmark_list.setCurrentRow(2)
        self.window.toggle_selected_reference()

        pinned = self.window.benchmark_runs[2]
        self.assertTrue(pinned.is_reference)
        self.assertTrue(self.window.benchmark_store.load()[2].is_reference)
        self.assertIn(id(pinned), self.window._benchmark_group_a)
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIs(self.window.benchmark_runs[self.window.benchmark_before.currentData()], pinned)

        self.window.benchmark_pair_search.setText("эталон")
        self.assertEqual(self.window.benchmark_pair_search_results.count(), 1)
        self.window.benchmark_pair_search_results.setCurrentRow(0)
        self.window._assign_pair_search_result_to_baseline()
        self.assertEqual(self.window.benchmark_before.currentData(), 2)

        self.window.benchmark_list.setCurrentRow(2)
        self.window.toggle_selected_reference()
        unpinned = self.window.benchmark_runs[2]
        self.assertFalse(unpinned.is_reference)
        self.assertFalse(self.window.benchmark_store.load()[2].is_reference)
        self.assertIn(id(unpinned), self.window._benchmark_group_a)

    def test_unpin_at_capacity_requires_confirmation_and_evicts_oldest_ordinary(self):
        runs = [analyze_frame_times(f"run-{index}.csv", [10 + index]) for index in range(MAX_HISTORY + 1)]
        runs[10] = replace(runs[10], is_reference=True)
        self.window.benchmark_runs = runs
        self.window.benchmark_store.save(runs)
        self.window._refresh_benchmark_history()
        self.window.benchmark_list.setCurrentRow(10)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as ask:
            self.window.toggle_selected_reference()
        ask.assert_called_once()
        self.assertTrue(self.window.benchmark_runs[10].is_reference)
        self.assertEqual(len(self.window.benchmark_store.load()), MAX_HISTORY + 1)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.toggle_selected_reference()
        self.assertEqual(sum(not run.is_reference for run in self.window.benchmark_runs), MAX_HISTORY)
        self.assertNotIn("run-0.csv", [run.name for run in self.window.benchmark_runs])
        self.assertNotIn(True, [run.is_reference for run in self.window.benchmark_runs])
        self.assertEqual(len(self.window.benchmark_store.load()), MAX_HISTORY)

    def test_unpin_oldest_reference_at_capacity_warns_it_will_be_removed(self):
        runs = [analyze_frame_times(f"run-{index}.csv", [10 + index]) for index in range(MAX_HISTORY + 1)]
        runs[0] = replace(runs[0], is_reference=True)
        self.window.benchmark_runs = runs
        self.window.benchmark_store.save(runs)
        self.window._refresh_benchmark_history()
        self.window.benchmark_list.setCurrentRow(0)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as ask:
            self.window.toggle_selected_reference()

        self.assertEqual(ask.call_args.args[1], "История заполнена")
        self.assertTrue(ask.call_args.args[2])
        self.assertEqual(self.window.benchmark_runs[0].name, "run-0.csv")
        self.assertTrue(self.window.benchmark_runs[0].is_reference)

    def test_previous_match_uses_nearest_earlier_run_and_requires_explicit_compare(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("other-game.csv", [11.0] * 4, game="Cyberpunk", scene="Riverwood"),
            analyze_frame_times("second.csv", [12.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("latest.csv", [13.0] * 4, game="Skyrim", scene="Riverwood"),
        ]
        self.window._refresh_benchmark_history()
        self.window.benchmark_before.setCurrentIndex(0)
        self.window.benchmark_after.setCurrentIndex(1)
        self.window.benchmark_report.setPlainText("previous report")
        self.window._last_benchmark_comparison = ("pair", self.window.benchmark_runs[0], self.window.benchmark_runs[1])
        self.window.export_benchmark_button.setEnabled(True)

        self.assertTrue(self.window.compare_with_previous_matching_run(3))

        self.assertEqual(self.window.benchmark_before.currentData(), 2)
        self.assertEqual(self.window.benchmark_after.currentData(), 3)
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIn("Нажми «Сравнить»", self.window.benchmark_report.toPlainText())
        self.assertIn("Нажми «Сравнить»", self.window.benchmark_pair_search_status.text())

    def test_previous_match_invalidates_active_group_export_too(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("second.csv", [11.0] * 4, game="Skyrim", scene="Riverwood"),
        ]
        self.window._refresh_benchmark_history()
        self.window._last_benchmark_comparison = ("groups", [], [])
        self.window.export_benchmark_button.setEnabled(True)

        self.assertTrue(self.window.compare_with_previous_matching_run(1))

        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIn("Пара A/B подобрана", self.window.benchmark_report.toPlainText())

    def test_previous_match_button_requires_exactly_one_history_selection(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("second.csv", [11.0] * 4, game="Skyrim", scene="Riverwood"),
        ]
        self.window._refresh_benchmark_history()
        self.assertFalse(self.window.compare_previous_matching_button.isEnabled())

        self.window.benchmark_list.item(0).setSelected(True)
        self.assertTrue(self.window.compare_previous_matching_button.isEnabled())
        self.window.benchmark_list.item(1).setSelected(True)
        self.assertFalse(self.window.compare_previous_matching_button.isEnabled())

    def test_previous_match_excludes_other_metric_kind(self):
        self.window.benchmark_runs = [
            analyze_frame_times("displayed.csv", [10.0] * 4, game="Skyrim", scene="Riverwood", metric_kind="displayed"),
            analyze_frame_times("presented.csv", [11.0] * 4, game="Skyrim", scene="Riverwood", metric_kind="cpu-presented"),
        ]
        self.window._refresh_benchmark_history()

        self.assertFalse(self.window.compare_with_previous_matching_run(1))
        self.assertEqual(self.window.benchmark_before.currentData(), 0)
        self.assertEqual(self.window.benchmark_after.currentData(), 1)
        self.assertIn("не найден", self.window.benchmark_pair_search_status.text())

    def test_previous_match_rejects_missing_game_or_scene_without_changing_pair(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("missing-scene.csv", [11.0] * 4, game="Skyrim"),
        ]
        self.window._refresh_benchmark_history()
        self.window.benchmark_before.setCurrentIndex(0)
        self.window.benchmark_after.setCurrentIndex(0)

        self.assertFalse(self.window.compare_with_previous_matching_run(1))
        self.assertEqual(self.window.benchmark_before.currentData(), 0)
        self.assertEqual(self.window.benchmark_after.currentData(), 0)
        self.assertIn("Нужны заполненные", self.window.benchmark_pair_search_status.text())

    def test_previous_match_rejects_invalid_and_first_run_indices(self):
        self.window.benchmark_runs = [analyze_frame_times("only.csv", [10.0] * 4, game="Skyrim", scene="Riverwood")]
        self.window._refresh_benchmark_history()
        self.window.benchmark_after.setCurrentIndex(0)

        self.assertFalse(self.window.compare_with_previous_matching_run(0))
        self.assertFalse(self.window.compare_with_previous_matching_run(True))
        self.assertFalse(self.window.compare_with_previous_matching_run(5))
        self.assertEqual(self.window.benchmark_before.currentData(), 0)
        self.assertEqual(self.window.benchmark_after.currentData(), 0)

    def test_previous_match_requires_exact_game_and_scene_labels(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 4, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("different-scene.csv", [11.0] * 4, game="Skyrim", scene="riverwood"),
        ]
        self.window._refresh_benchmark_history()

        self.assertFalse(self.window.compare_with_previous_matching_run(1))
        self.assertIn("не найден", self.window.benchmark_pair_search_status.text())


if __name__ == "__main__":
    unittest.main()
