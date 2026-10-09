from __future__ import annotations

import unittest
from dataclasses import replace

from frameforge.core.benchmark import analyze_frame_times
from frameforge.ui.benchmark_search import matching_benchmark_indices


class BenchmarkSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runs = [
            analyze_frame_times("same.csv", [10.0] * 4, game="Skyrim", scene="Riverwood", change_note="Night pass"),
            analyze_frame_times("same.csv", [11.0] * 4, game="Skyrim", scene="Whiterun", change_note="Day pass"),
            analyze_frame_times("other.csv", [12.0] * 4, game="Cyberpunk 2077", scene="Night City"),
        ]

    def test_empty_query_has_no_candidates_and_does_not_expand_to_all_history(self) -> None:
        self.assertEqual(matching_benchmark_indices(self.runs, "  "), ())

    def test_search_is_case_insensitive_and_returns_original_indices(self) -> None:
        self.assertEqual(matching_benchmark_indices(self.runs, "SAME.CSV"), (0, 1))
        self.assertEqual(matching_benchmark_indices(self.runs, "WHITERUN"), (1,))

    def test_search_treats_query_as_literal_substring(self) -> None:
        self.assertEqual(matching_benchmark_indices(self.runs, ".*"), ())

    def test_duplicate_names_remain_distinguishable_by_history_index(self) -> None:
        matches = matching_benchmark_indices(self.runs, "same")
        self.assertEqual(matches, (0, 1))
        self.assertNotEqual(matches[0], matches[1])

    def test_search_includes_checklist_labels_and_setting_snapshots(self) -> None:
        self.runs.extend((
            analyze_frame_times("cs2.csv", [10.0] * 4, game="Counter-Strike 2", manual_changes=("cs2.shadows",)),
            analyze_frame_times("skyrim.csv", [11.0] * 4, setting_key="iMinGrassSize", setting_value=40),
        ))
        self.assertEqual(matching_benchmark_indices(self.runs, "ТЕНЕЙ"), (3,))
        self.assertEqual(matching_benchmark_indices(self.runs, "iminGRASSsize"), (4,))

    def test_search_finds_pinned_reference_runs(self) -> None:
        self.runs[1] = replace(self.runs[1], is_reference=True)
        self.assertEqual(matching_benchmark_indices(self.runs, "эталон"), (1,))


if __name__ == "__main__":
    unittest.main()
