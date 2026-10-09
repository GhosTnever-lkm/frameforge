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


if __name__ == "__main__":
    unittest.main()
