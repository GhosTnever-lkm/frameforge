from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton

from frameforge.core.benchmark import analyze_frame_times
from frameforge.core.benchmark_store import BenchmarkStore, MAX_HISTORY
from frameforge.ui.main_window import MainWindow, ProbableDuplicateDialog, probable_duplicate_dialog_dimensions


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

    def test_probable_duplicate_dialog_defaults_to_skip_but_allows_explicit_add(self):
        dialog = ProbableDuplicateDialog([(2, 3, "capture.csv", "запись истории #4: capture.csv")], 3)
        self.assertEqual(dialog.positions_to_keep(), set())
        position, checkbox = dialog.choices[0]
        self.assertEqual(position, 2)
        self.assertFalse(checkbox.isChecked())
        checkbox.setChecked(True)
        self.assertEqual(dialog.positions_to_keep(), {2})
        self.assertIn("не доказывает", dialog.layout().itemAt(0).widget().text())

    def test_probable_duplicate_dialog_safe_default_keeps_unique_batch_action_distinct_from_cancel(self):
        dialog = ProbableDuplicateDialog([(1, 2, "repeat.csv", "запись истории #1: old.csv")], 2)
        dialog.choices[0][1].setChecked(True)
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        buttons["Добавить уникальные, пропустить совпадения"].click()
        self.assertEqual(dialog.result(), int(QDialog.DialogCode.Accepted))
        self.assertEqual(dialog.positions_to_keep(), set())

        cancel = ProbableDuplicateDialog([(1, 2, "repeat.csv", "запись истории #1: old.csv")], 2)
        buttons = {button.text(): button for button in cancel.findChildren(QPushButton)}
        buttons["Отменить весь импорт"].click()
        self.assertEqual(cancel.result(), int(QDialog.DialogCode.Rejected))

    def test_probable_duplicate_dialog_disambiguates_repeated_filenames_and_bounds_list_height(self):
        duplicates = [(index, index + 1, "capture.csv", f"запись истории #{index}: old.csv") for index in range(30)]
        dialog = ProbableDuplicateDialog(duplicates, 40)
        labels = [checkbox.text() for _, checkbox in dialog.choices]
        self.assertIn("CSV #1 — capture.csv", labels[0])
        self.assertIn("CSV #30 — capture.csv", labels[-1])
        self.assertLessEqual(dialog.duplicate_list.maximumHeight(), 340)
        self.assertEqual(dialog.duplicate_list.widget().layout().count(), 31)

    def test_probable_duplicate_dialog_fits_smaller_available_screen(self):
        width, height, scroll_min, scroll_max = probable_duplicate_dialog_dimensions(910, 512)
        self.assertLessEqual(width, 910 - 24)
        self.assertLessEqual(height, 512 - 24)
        self.assertLessEqual(scroll_max, height - 200)
        self.assertLessEqual(scroll_min, scroll_max)
        self.assertEqual((width, height, scroll_min, scroll_max), (720, 488, 140, 288))
        self.assertEqual(probable_duplicate_dialog_dimensions(600, 400), (576, 376, 140, 176))
        self.assertEqual(probable_duplicate_dialog_dimensions(400, 300), (376, 276, 76, 76))
        self.assertEqual(probable_duplicate_dialog_dimensions(320, 240), (296, 216, 48, 48))

    def test_import_skips_probable_duplicate_by_default_without_touching_history(self):
        existing = analyze_frame_times("original.csv", [16.0] * 40, game=self.window.benchmark_game.currentData() or "")
        self.window.benchmark_runs = [existing]
        self.window.benchmark_store.save([existing])
        with (
            patch("frameforge.ui.main_window.QFileDialog.getOpenFileNames", return_value=(["repeat.csv"], "CSV files (*.csv)")),
            patch("frameforge.ui.main_window.load_benchmark_csv", return_value=(analyze_frame_times("repeat.csv", [16.0] * 40), [])),
            patch.object(ProbableDuplicateDialog, "exec", return_value=QDialog.DialogCode.Accepted),
            patch.object(QMessageBox, "information") as info,
        ):
            self.window.import_benchmark()
        self.assertEqual(self.window.benchmark_runs, [existing])
        self.assertEqual(self.window.benchmark_store.load(), [existing])
        info.assert_called_once()

    def test_import_allows_user_to_keep_a_flagged_duplicate(self):
        existing = analyze_frame_times("original.csv", [16.0] * 40, game=self.window.benchmark_game.currentData() or "")
        self.window.benchmark_runs = [existing]
        self.window.benchmark_store.save([existing])

        def accept_and_check(dialog):
            self.assertFalse(dialog.choices[0][1].isChecked())
            dialog.choices[0][1].setChecked(True)
            return QDialog.DialogCode.Accepted

        with (
            patch("frameforge.ui.main_window.QFileDialog.getOpenFileNames", return_value=(["repeat.csv"], "CSV files (*.csv)")),
            patch("frameforge.ui.main_window.load_benchmark_csv", return_value=(analyze_frame_times("repeat.csv", [16.0] * 40), [])),
            patch.object(ProbableDuplicateDialog, "exec", accept_and_check),
            patch.object(QMessageBox, "information"),
        ):
            self.window.import_benchmark()
        self.assertEqual([run.name for run in self.window.benchmark_runs], ["original.csv", "repeat.csv"])

    def test_duplicate_in_batch_is_prompted_without_reordering_kept_runs(self):
        runs = [analyze_frame_times(name, [value] * 40) for name, value in (("first.csv", 16.0), ("middle.csv", 17.0), ("repeat.csv", 16.0))]

        def accept_and_check(dialog):
            self.assertEqual(len(dialog.choices), 1)
            self.assertIn("выбранный CSV #1: first.csv", " ".join(widget.text() for widget in dialog.findChildren(QLabel)))
            dialog.choices[0][1].setChecked(True)
            return QDialog.DialogCode.Accepted

        paths = ["first.csv", "middle.csv", "repeat.csv"]
        with (
            patch("frameforge.ui.main_window.QFileDialog.getOpenFileNames", return_value=(paths, "CSV files (*.csv)")),
            patch("frameforge.ui.main_window.load_benchmark_csv", side_effect=[(run, []) for run in runs]),
            patch.object(ProbableDuplicateDialog, "exec", accept_and_check),
            patch.object(QMessageBox, "information"),
        ):
            self.window.import_benchmark()
        self.assertEqual([run.name for run in self.window.benchmark_runs], ["first.csv", "middle.csv", "repeat.csv"])

    def test_continue_selected_with_no_checks_still_imports_unique_csvs(self):
        duplicate = analyze_frame_times("already.csv", [16.0] * 40, game=self.window.benchmark_game.currentData() or "")
        unique = analyze_frame_times("unique.csv", [17.0] * 40)
        self.window.benchmark_runs = [duplicate]
        self.window.benchmark_store.save([duplicate])
        paths = ["repeat.csv", "unique.csv"]
        with (
            patch("frameforge.ui.main_window.QFileDialog.getOpenFileNames", return_value=(paths, "CSV files (*.csv)")),
            patch("frameforge.ui.main_window.load_benchmark_csv", side_effect=[(duplicate, []), (unique, [])]),
            patch.object(ProbableDuplicateDialog, "exec", return_value=QDialog.DialogCode.Accepted),
            patch.object(QMessageBox, "information"),
        ):
            self.window.import_benchmark()
        self.assertEqual([run.name for run in self.window.benchmark_runs], ["already.csv", "unique.csv"])

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
        self.assertTrue(self.window.toggle_active_benchmark_baseline(2))
        self.assertIs(self.window._active_benchmark_baseline, self.window.benchmark_runs[2])
        self.window.toggle_selected_reference()
        unpinned = self.window.benchmark_runs[2]
        self.assertFalse(unpinned.is_reference)
        self.assertIsNone(self.window._active_benchmark_baseline)
        self.assertFalse(self.window.benchmark_store.load()[2].is_reference)
        self.assertIn(id(unpinned), self.window._benchmark_group_a)

    def test_active_baseline_shortcut_assigns_pair_and_requires_explicit_compare(self):
        runs = [
            analyze_frame_times("reference.csv", [11.0] * 8, game="Skyrim", scene="Forest"),
            analyze_frame_times("new.csv", [14.0] * 8, game="Skyrim", scene="Forest"),
        ]
        runs[0] = replace(runs[0], is_reference=True)
        self.window.benchmark_runs = runs
        self.window._refresh_benchmark_history()
        self.assertTrue(self.window.toggle_active_benchmark_baseline(0))
        self.window.benchmark_list.setCurrentRow(1)
        self.assertTrue(self.window.compare_active_baseline_button.isEnabled())
        self.window._last_benchmark_comparison = ("pair", runs[1], runs[0])
        self.window.export_benchmark_button.setEnabled(True)

        self.assertTrue(self.window.compare_selected_with_active_baseline())

        self.assertEqual(self.window.benchmark_before.currentData(), 0)
        self.assertEqual(self.window.benchmark_after.currentData(), 1)
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIn("Нажми «Сравнить»", self.window.benchmark_report.toPlainText())
        self.window.benchmark_list.setCurrentRow(0)
        self.assertFalse(self.window.compare_active_baseline_button.isEnabled())
        self.assertIn("уже является", self.window.compare_active_baseline_button.toolTip())

    def test_active_baseline_can_only_be_one_pinned_reference_and_is_session_state(self):
        runs = [
            replace(analyze_frame_times("first.csv", [11.0] * 4), is_reference=True),
            replace(analyze_frame_times("second.csv", [12.0] * 4), is_reference=True),
            analyze_frame_times("ordinary.csv", [13.0] * 4),
        ]
        self.window.benchmark_runs = runs
        self.window._refresh_benchmark_history()
        self.assertFalse(self.window.compare_active_baseline_button.isVisible())
        self.assertFalse(self.window.toggle_active_benchmark_baseline(2))
        self.assertTrue(self.window.toggle_active_benchmark_baseline(0))
        self.assertTrue(self.window.toggle_active_benchmark_baseline(1))
        self.assertIs(self.window._active_benchmark_baseline, runs[1])
        self.assertTrue(self.window.toggle_active_benchmark_baseline(1))
        self.assertIsNone(self.window._active_benchmark_baseline)

    def test_active_baseline_survives_batch_import_and_keeps_object_identity(self):
        reference = replace(analyze_frame_times("reference.csv", [11.0] * 40), is_reference=True)
        self.window.benchmark_runs = [reference]
        self.window.benchmark_store.save([reference])
        self.window._refresh_benchmark_history()
        self.window.toggle_active_benchmark_baseline(0)
        added = analyze_frame_times("added.csv", [15.0] * 40)
        with (
            patch("frameforge.ui.main_window.QFileDialog.getOpenFileNames", return_value=(["added.csv"], "CSV files (*.csv)")),
            patch("frameforge.ui.main_window.load_benchmark_csv", return_value=(added, [])),
            patch.object(QMessageBox, "information"),
        ):
            self.window.import_benchmark()
        self.assertIs(self.window._active_benchmark_baseline, reference)
        self.assertIs(self.window.benchmark_runs[0], reference)
        self.assertEqual(self.window._recent_benchmark_pairs, [])
        self.window.benchmark_list.setCurrentRow(1)
        self.assertTrue(self.window.compare_selected_with_active_baseline())
        self.assertEqual(self.window.benchmark_before.currentData(), 0)

    def test_failed_unpin_save_preserves_active_baseline(self):
        reference = replace(analyze_frame_times("reference.csv", [11.0] * 4), is_reference=True)
        self.window.benchmark_runs = [reference]
        self.window.benchmark_store.save([reference])
        self.window._refresh_benchmark_history()
        self.window.toggle_active_benchmark_baseline(0)
        self.window.benchmark_list.setCurrentRow(0)
        with patch.object(self.window.benchmark_store, "save", side_effect=OSError("disk full")), patch.object(QMessageBox, "warning"):
            self.window.toggle_selected_reference()
        self.assertIs(self.window._active_benchmark_baseline, reference)
        self.assertTrue(self.window.benchmark_runs[0].is_reference)
        self.assertTrue(self.window.benchmark_store.load()[0].is_reference)

    def test_recent_pair_list_deduplicates_caps_and_restores_without_reusing_report(self):
        self.window.benchmark_runs = [
            analyze_frame_times(f"run-{index}.csv", [10.0 + index] * 4)
            for index in range(12)
        ]
        self.window._refresh_benchmark_history()
        self.assertTrue(self.window.recent_pairs_list.isHidden())
        self.assertFalse(self.window.recent_pairs_toggle.isEnabled())
        for index in range(11):
            self.window.benchmark_before.setCurrentIndex(index)
            self.window.benchmark_after.setCurrentIndex(index + 1)
            self.window.compare_benchmark_selection()
        self.assertEqual(len(self.window._recent_benchmark_pairs), 10)
        self.assertIs(self.window._recent_benchmark_pairs[0][0], self.window.benchmark_runs[10])
        self.window.benchmark_before.setCurrentIndex(0)
        self.window.benchmark_after.setCurrentIndex(1)
        self.window.compare_benchmark_selection()
        self.window.compare_benchmark_selection()
        self.assertEqual(len(self.window._recent_benchmark_pairs), 10)
        self.assertIs(self.window._recent_benchmark_pairs[0][0], self.window.benchmark_runs[0])
        self.assertIs(self.window._recent_benchmark_pairs[0][1], self.window.benchmark_runs[1])
        self.assertEqual(self.window.benchmark_store.load(), [])
        self.window.recent_pairs_toggle.click()
        self.assertFalse(self.window.recent_pairs_list.isHidden())

        self.window._restore_recent_pair(self.window.recent_pairs_list.item(1))

        self.assertEqual(self.window.benchmark_before.currentData(), 10)
        self.assertEqual(self.window.benchmark_after.currentData(), 11)
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIn("Нажми «Сравнить»", self.window.benchmark_report.toPlainText())

    def test_swap_pair_invalidates_old_report_without_comparing_or_recording_until_explicit_action(self):
        runs = [
            analyze_frame_times("before.csv", [11.0] * 8),
            analyze_frame_times("after.csv", [14.0] * 8),
        ]
        self.window.benchmark_runs = runs
        self.window._refresh_benchmark_history()
        self.window.benchmark_before.setCurrentIndex(0)
        self.window.benchmark_after.setCurrentIndex(1)
        self.window.compare_benchmark_selection()
        old_report = self.window.benchmark_report.toPlainText()
        old_recent = list(self.window._recent_benchmark_pairs)
        self.assertTrue(self.window.export_benchmark_button.isEnabled())

        with patch.object(self.window, "_benchmark_pair_selection_changed", wraps=self.window._benchmark_pair_selection_changed) as changed:
            self.window.swap_benchmark_pair_button.click()
        changed.assert_not_called()

        self.assertEqual(self.window.benchmark_before.currentData(), 1)
        self.assertEqual(self.window.benchmark_after.currentData(), 0)
        self.assertIn("after.csv", self.window.benchmark_before.accessibleName())
        self.assertIn("before.csv", self.window.benchmark_after.accessibleName())
        self.assertIn("Baseline (A)", self.window.benchmark_before.accessibleDescription())
        self.assertIn("Variant (B)", self.window.benchmark_after.accessibleDescription())
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertTrue(self.window.benchmark_chart.isHidden())
        self.assertNotEqual(self.window.benchmark_report.toPlainText(), old_report)
        self.assertIn("Нажми «Сравнить»", self.window.benchmark_report.toPlainText())
        self.assertEqual(self.window._recent_benchmark_pairs, old_recent)

        self.window.compare_benchmark_selection()
        self.assertEqual(self.window._recent_benchmark_pairs[0], (runs[1], runs[0]))
        self.assertTrue(self.window.export_benchmark_button.isEnabled())

    def test_swap_pair_button_disables_for_one_run_same_selection_and_stale_indices(self):
        only_run = analyze_frame_times("only.csv", [12.0] * 8)
        self.window.benchmark_runs = [only_run]
        self.window._refresh_benchmark_history()
        self.assertFalse(self.window.swap_benchmark_pair_button.isEnabled())

        second = analyze_frame_times("second.csv", [15.0] * 8)
        self.window.benchmark_runs = [only_run, second]
        self.window._refresh_benchmark_history()
        self.window.benchmark_after.setCurrentIndex(0)
        self.assertFalse(self.window.swap_benchmark_pair_button.isEnabled())
        self.window.benchmark_after.setCurrentIndex(1)
        self.assertTrue(self.window.swap_benchmark_pair_button.isEnabled())

        self.window.benchmark_before.setCurrentIndex(1)
        self.window.benchmark_before.setItemData(1, True, Qt.ItemDataRole.UserRole)
        self.window._update_swap_benchmark_pair_button()
        self.assertFalse(self.window.swap_benchmark_pair_button.isEnabled())
        bool_before = self.window.benchmark_before.currentIndex()
        bool_after = self.window.benchmark_after.currentIndex()
        self.window.swap_benchmark_pair()
        self.assertEqual(self.window.benchmark_before.currentIndex(), bool_before)
        self.assertEqual(self.window.benchmark_after.currentIndex(), bool_after)

        self.window.benchmark_before.setItemData(1, 1, Qt.ItemDataRole.UserRole)
        self.window.benchmark_before.setCurrentIndex(0)
        before_index = self.window.benchmark_before.currentIndex()
        after_index = self.window.benchmark_after.currentIndex()
        self.window.benchmark_runs = [only_run]
        self.window._update_swap_benchmark_pair_button()
        self.assertFalse(self.window.swap_benchmark_pair_button.isEnabled())
        self.window.swap_benchmark_pair()
        self.assertEqual(self.window.benchmark_before.currentIndex(), before_index)
        self.assertEqual(self.window.benchmark_after.currentIndex(), after_index)

    def test_swap_clears_any_existing_report_mode_without_creating_a_recent_pair(self):
        runs = [
            analyze_frame_times("a.csv", [11.0] * 8),
            analyze_frame_times("b.csv", [14.0] * 8),
        ]
        self.window.benchmark_runs = runs
        self.window._refresh_benchmark_history()
        self.window._last_benchmark_comparison = ("groups", [], [])
        self.window.benchmark_report.setPlainText("Старый групповой отчёт")
        self.window.export_benchmark_button.setEnabled(True)
        self.window.swap_benchmark_pair()
        self.assertIsNone(self.window._last_benchmark_comparison)
        self.assertFalse(self.window.export_benchmark_button.isEnabled())
        self.assertIn("Поля A/B поменялись местами", self.window.benchmark_report.toPlainText())
        self.assertEqual(self.window._recent_benchmark_pairs, [])

    def test_copy_report_copies_exact_visible_text_and_disables_when_pair_changes(self):
        clipboard = QApplication.clipboard()
        previous_clipboard = clipboard.text()
        try:
            runs = [
                replace(analyze_frame_times("a.csv", [11.0] * 8), change_note="before settings"),
                replace(analyze_frame_times("b.csv", [14.0] * 8), change_note="after settings"),
            ]
            self.window.benchmark_runs = runs
            self.window._refresh_benchmark_history()
            self.window.benchmark_before.setCurrentIndex(0)
            self.window.benchmark_after.setCurrentIndex(1)
            self.assertFalse(self.window.copy_benchmark_report_button.isEnabled())
            clipboard.setText("untouched")
            self.window.copy_benchmark_report_button.click()
            self.assertEqual(clipboard.text(), "untouched")

            self.window.compare_benchmark_selection()
            visible_report = self.window.benchmark_report.toPlainText()
            self.assertIn("Baseline (A): a.csv", visible_report)
            self.assertIn("Variant (B): b.csv", visible_report)
            self.assertIn("before settings", visible_report)
            self.assertTrue(self.window.copy_benchmark_report_button.isEnabled())
            self.window.copy_benchmark_report_button.click()
            self.assertEqual(clipboard.text(), visible_report)

            self.window.benchmark_before.setCurrentIndex(1)
            self.assertFalse(self.window.copy_benchmark_report_button.isEnabled())
            self.window.copy_benchmark_report()
            self.assertEqual(clipboard.text(), visible_report)
        finally:
            clipboard.setText(previous_clipboard)

    def test_recent_pair_disables_after_history_eviction_and_unpin_relinks_identity(self):
        reference = replace(analyze_frame_times("reference.csv", [11.0] * 4), is_reference=True)
        ordinary = analyze_frame_times("ordinary.csv", [12.0] * 4)
        evicted = analyze_frame_times("evicted.csv", [13.0] * 4)
        self.window.benchmark_runs = [reference, ordinary, evicted]
        self.window.benchmark_store.save(self.window.benchmark_runs)
        self.window._refresh_benchmark_history()
        self.window._remember_recent_benchmark_pair(reference, ordinary)
        self.window.benchmark_list.setCurrentRow(0)
        self.window.toggle_selected_reference()
        updated_reference = self.window.benchmark_runs[0]
        self.assertIs(self.window._recent_benchmark_pairs[0][0], updated_reference)
        self.assertTrue(self.window.recent_pairs_list.item(0).flags() & Qt.ItemFlag.ItemIsEnabled)

        self.window.benchmark_runs = [ordinary]
        self.window._refresh_benchmark_history()
        stale = self.window.recent_pairs_list.item(0)
        self.assertFalse(stale.flags() & Qt.ItemFlag.ItemIsEnabled)
        self.assertIn("Недоступна", stale.text())
        self.assertIn("больше не находится", stale.toolTip())
        previous_pair = (self.window.benchmark_before.currentData(), self.window.benchmark_after.currentData())
        self.window._restore_recent_pair(stale)
        self.assertEqual((self.window.benchmark_before.currentData(), self.window.benchmark_after.currentData()), previous_pair)
        self.assertIn("больше недоступна", self.window.benchmark_pair_search_status.text())
        self.window.recent_pairs_toggle.setChecked(True)
        self.window.benchmark_runs = [ordinary]
        self.window._refresh_benchmark_history()
        self.assertFalse(self.window.recent_pairs_toggle.isEnabled())
        self.assertFalse(self.window.recent_pairs_toggle.isChecked())
        self.assertTrue(self.window.recent_pairs_list.isHidden())

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

    def test_same_label_history_matches_exact_game_scene_and_metric_including_reference(self):
        rows = [
            analyze_frame_times("first.csv", [10.0] * 40, game="Skyrim", scene="Riverwood", metric_kind="generic"),
            replace(analyze_frame_times("pinned.csv", [11.0] * 40, game="Skyrim", scene="Riverwood", metric_kind="generic"), is_reference=True),
            analyze_frame_times("wrong-scene.csv", [12.0] * 40, game="Skyrim", scene="Whiterun", metric_kind="generic"),
            analyze_frame_times("wrong-metric.csv", [13.0] * 40, game="Skyrim", scene="Riverwood", metric_kind="displayed"),
            analyze_frame_times("latest.csv", [14.0] * 40, game="Skyrim", scene="Riverwood", metric_kind="generic"),
        ]
        self.window.benchmark_runs = rows
        matches = self.window.same_label_history_rows(4)
        self.assertEqual([index for index, _run in matches], [0, 1, 4])
        self.assertTrue(matches[1][1].is_reference)
        self.assertEqual(self.window.same_label_history_rows(2), [(2, rows[2])])

    def test_same_label_history_rejects_missing_labels_and_invalid_indices(self):
        self.window.benchmark_runs = [analyze_frame_times("unlabelled.csv", [10.0] * 4)]
        self.assertEqual(self.window.same_label_history_rows(0), [])
        self.assertEqual(self.window.same_label_history_rows(-1), [])
        self.assertEqual(self.window.same_label_history_rows(True), [])
        self.assertEqual(self.window.same_label_history_rows(1), [])
        with patch.object(QMessageBox, "information") as info:
            self.assertFalse(self.window.show_same_label_history(0))
        self.assertIn("У выбранного замера", info.call_args.args[2])
        with patch.object(QMessageBox, "information") as stale:
            self.assertFalse(self.window.show_same_label_history(7))
        self.assertEqual(stale.call_args.args[1], "Выбор устарел")

    def test_same_label_history_view_discloses_history_order_and_does_not_export(self):
        self.window.benchmark_runs = [
            analyze_frame_times("first.csv", [10.0] * 40, game="Skyrim", scene="Riverwood"),
            analyze_frame_times("second.csv", [12.0] * 40, game="Skyrim", scene="Riverwood"),
        ]
        from PySide6.QtWidgets import QDialog
        dialogs = []
        original_init = QDialog.__init__

        def capture_dialog(dialog, *args, **kwargs):
            original_init(dialog, *args, **kwargs)
            dialogs.append(dialog)

        with patch("frameforge.ui.main_window.QDialog.__init__", capture_dialog), patch("frameforge.ui.main_window.QDialog.exec", return_value=0):
            self.assertTrue(self.window.show_same_label_history(1))
        dialog = dialogs[-1]
        from PySide6.QtWidgets import QLabel, QTextEdit
        labels = dialog.findChildren(QLabel)
        self.assertTrue(any("не время захвата" in label.text() for label in labels))
        text = dialog.findChild(QTextEdit).toPlainText()
        self.assertIn("#001", text)
        self.assertIn("#002 " + chr(0x2190) + " выбран", text)

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
