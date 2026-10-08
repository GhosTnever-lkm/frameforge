import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameforge.core.apply import apply_grass_distance, apply_profile_setting, build_profile_bytes, build_tuned_bytes, make_diff, read_grass_distance, read_profile_setting
from frameforge.core.backup import create_byte_backup, restore_from_backup
from frameforge.core.benchmark import FRAME_TIME_BUCKET_EDGES_MS, analyze_frame_times, compare_benchmarks, load_frame_time_csv
from frameforge.core.benchmark_store import BenchmarkStore, MAX_HISTORY, SCHEMA_VERSION
from frameforge.core.safety import SafetyError, validate_config_path
from frameforge.core.scanner import parse_libraryfolders


class FrameForgeCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Documents" / "My Games" / "Skyrim Special Edition"
        self.root.mkdir(parents=True)
        self.config = self.root / "SkyrimPrefs.ini"
        self.original = b"[Display]\r\niShadowMapResolution=2048\r\n\r\n[Grass]\r\nfGrassStartFadeDistance=7000.0000 ; user comment\r\nOther=keep\r\n"
        self.config.write_bytes(self.original)
        self.skyrim_ini = self.root / "Skyrim.ini"
        self.skyrim_ini_original = b"[General]\r\nsSomeSetting=1\r\n[Grass]\r\niMinGrassSize=20 ; density\r\n"
        self.skyrim_ini.write_bytes(self.skyrim_ini_original)
        self.backups = Path(self.temp.name) / "backups"

    def tearDown(self):
        self.temp.cleanup()

    def test_scans_supported_parameter_read_only(self):
        current, raw = read_grass_distance(self.config)
        self.assertEqual(current, 7000)
        self.assertEqual(raw, self.original)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_preview_changes_only_target_line_and_preserves_crlf_and_comment(self):
        updated = build_tuned_bytes(self.original, 3000)
        self.assertEqual(updated.count(b"\r\n"), self.original.count(b"\r\n"))
        self.assertIn(b"fGrassStartFadeDistance=3000 ; user comment\r\n", updated)
        self.assertIn(b"iShadowMapResolution=2048\r\n", updated)
        self.assertIn(b"Other=keep\r\n", updated)
        self.assertIn("-fGrassStartFadeDistance=7000.0000 ; user comment\r\n", make_diff(self.original, updated))

    def test_density_profile_can_disable_grass_and_restore_skyrim_ini(self):
        current, data = read_profile_setting(self.skyrim_ini)
        self.assertEqual(current, 20)
        self.assertEqual(data, self.skyrim_ini_original)
        updated = build_profile_bytes(data, 0, "Skyrim.ini")
        self.assertIn(b"iMinGrassSize=0 ; density\r\n", updated)
        with self.assertRaises(ValueError):
            build_profile_bytes(data, -1, "Skyrim.ini")
        backup, _ = apply_profile_setting(self.skyrim_ini, 0, self.backups, expected_original=data)
        self.assertIn("frameforge-skyrim-", backup.name)
        self.assertIn(b"iMinGrassSize=0", self.skyrim_ini.read_bytes())
        restore_from_backup(backup, self.skyrim_ini)
        self.assertEqual(self.skyrim_ini.read_bytes(), self.skyrim_ini_original)

    def test_bom_is_preserved(self):
        original = b"\xef\xbb\xbf[Grass]\n fGrassStartFadeDistance=7000\n"
        self.assertTrue(build_tuned_bytes(original, 1000).startswith(b"\xef\xbb\xbf"))

    def test_rejects_unapproved_or_unknown_config_values(self):
        with self.assertRaises(ValueError):
            build_tuned_bytes(self.original, 0)
        no_setting = self.root / "not-used.ini"
        no_setting.write_text("[Grass]\nSomeOtherSetting=1\n", encoding="utf-8")
        with self.assertRaises(SafetyError):
            validate_config_path(no_setting)
        self.config.write_bytes(b"[Grass]\nOther=1\n")
        with self.assertRaises(ValueError):
            read_grass_distance(self.config)

    def test_refuses_duplicate_parameter(self):
        self.config.write_bytes(b"[Grass]\nfGrassStartFadeDistance=7000\nfGrassStartFadeDistance=5000\n")
        with self.assertRaises(ValueError):
            read_grass_distance(self.config)

    def test_creates_byte_exact_backup_applies_and_restores(self):
        backup = create_byte_backup(self.config, self.backups)
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).digest(), hashlib.sha256(self.original).digest())
        backup2, _ = apply_grass_distance(self.config, 3000, self.backups)
        self.assertEqual(backup2.read_bytes(), self.original)
        self.assertIn(b"fGrassStartFadeDistance=3000", self.config.read_bytes())
        restore_from_backup(backup2, self.config)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_rejects_backup_outside_backups_directory(self):
        forged = Path(self.temp.name) / "skyrimprefs-forged.ini.bak"
        forged.write_bytes(self.original)
        with self.assertRaises(SafetyError):
            restore_from_backup(forged, self.config)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_rejects_backup_changed_since_indexing(self):
        backup = create_byte_backup(self.config, self.backups)
        expected = hashlib.sha256(backup.read_bytes()).hexdigest()
        backup.write_bytes(self.original.replace(b"7000.0000", b"3000.0000"))
        with self.assertRaises(SafetyError):
            restore_from_backup(backup, self.config, expected)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_rejects_symlinked_backup(self):
        outside = Path(self.temp.name) / "outside.ini.bak"
        outside.write_bytes(self.original)
        self.backups.mkdir(parents=True)
        linked_backup = self.backups / "frameforge-skyrimprefs-linked.ini.bak"
        try:
            linked_backup.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable in this environment")
        with self.assertRaises(SafetyError):
            restore_from_backup(linked_backup, self.config)

    def test_create_backup_rejects_symlinked_backup_directory(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        linked_dir = Path(self.temp.name) / "backups"
        try:
            linked_dir.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable in this environment")
        with self.assertRaises(SafetyError):
            create_byte_backup(self.config, linked_dir)

    def test_backup_directory_reparse_guard_stops_before_creation(self):
        self.backups.mkdir()
        with patch("frameforge.core.backup._is_reparse_or_link", side_effect=lambda path: Path(path) == self.backups):
            with self.assertRaises(SafetyError):
                create_byte_backup(self.config, self.backups)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_benchmark_csv_calculates_fps_and_one_percent_low(self):
        path = Path(self.temp.name) / "run.csv"
        path.write_text("frame_time_ms\n" + "10\n" * 99 + "50\n", encoding="utf-8")
        run = load_frame_time_csv(path)
        self.assertEqual(run.sample_count, 100)
        self.assertAlmostEqual(run.average_fps, 1000 / 10.4)
        self.assertEqual(run.one_percent_low_fps, 20)
        self.assertEqual(run.p99_frame_time_ms, 10)

    def test_benchmark_exposes_frame_time_distribution_buckets(self):
        run = analyze_frame_times("distribution", [4, *FRAME_TIME_BUCKET_EDGES_MS])
        self.assertEqual(run.frame_time_buckets, (1, 1, 1, 1, 1, 1))
        self.assertEqual(sum(run.frame_time_buckets), run.sample_count)
        at_100ms = analyze_frame_times("100ms", [100.0])
        self.assertEqual(at_100ms.frame_time_buckets[-1], 1)

    def test_benchmark_rejects_wrong_header_and_invalid_values(self):
        path = Path(self.temp.name) / "bad.csv"
        path.write_text("fps\n60\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_frame_time_csv(path)
        path.write_text("frame_time_ms\n0\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_frame_time_csv(path)
        with self.assertRaises(ValueError):
            analyze_frame_times("bad", [float("nan")])

    def test_benchmark_comparison_reports_delta_and_conditions(self):
        before = analyze_frame_times("before", [20, 20, 20, 20])
        after = analyze_frame_times("after", [10, 10, 10, 10])
        report = compare_benchmarks(before, after)
        self.assertIn("+50.0 (+100.0%)", report)
        self.assertIn("одинаковой сцене", report)

    def test_benchmark_comparison_reports_distribution_and_different_sample_warning(self):
        before = analyze_frame_times("baseline.csv", [10.0] * 100)
        after = analyze_frame_times("variant.csv", [20.0] * 50)
        report = compare_benchmarks(before, after)
        self.assertIn("Baseline (A)", report)
        self.assertIn("Variant (B)", report)
        self.assertIn("отличается более чем на 5%", report)
        self.assertIn("16.667–33.333 мс", report)
        self.assertIn("A 0.0% → B 100.0%", report)

    def test_benchmark_comparison_does_not_warn_for_close_sample_sizes(self):
        before = analyze_frame_times("baseline.csv", [10.0] * 100)
        after = analyze_frame_times("variant.csv", [10.0] * 96)
        report = compare_benchmarks(before, after)
        self.assertNotIn("отличается более чем на 5%", report)

    def test_benchmark_history_roundtrip_omits_source_paths_and_raw_samples(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        run = analyze_frame_times("benchmark.csv", [10, 15, 25])
        store.save([run])
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.temp.name), raw)
        self.assertNotIn("frame_times", raw)
        self.assertEqual(store.load(), [run])

    def test_benchmark_history_rejects_corruption_and_inconsistent_buckets(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        path.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "прочитать"):
            store.load()
        run = analyze_frame_times("benchmark.csv", [10, 15, 25])
        store.save([run])
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        data["runs"][0]["frame_time_buckets"][0] += 1
        path.write_text(__import__("json").dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Сумма диапазонов"):
            store.load()

    def test_benchmark_history_rejects_unknown_schema_and_large_file(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        path.write_text('{"schema_version":99,"runs":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "не поддерживается"):
            store.load()
        with patch("frameforge.core.benchmark_store.MAX_STORE_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "2 МБ"):
                store.load()

    def test_benchmark_history_rejects_path_like_source_names(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        run = analyze_frame_times("safe.csv", [10])
        store.save([run])
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        data["runs"][0]["name"] = "C:\\Users\\secret\\private.csv"
        path.write_text(__import__("json").dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Имя замера"):
            store.load()

    def test_benchmark_history_write_is_atomic_and_keeps_previous_file(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        before = analyze_frame_times("before.csv", [10, 11])
        after = analyze_frame_times("after.csv", [9, 10])
        store.save([before])
        original = path.read_bytes()
        with patch("frameforge.core.benchmark_store.os.replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                store.save([before, after])
        self.assertEqual(path.read_bytes(), original)

    def test_benchmark_history_is_bounded_to_newest_hundred(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        runs = [analyze_frame_times(f"run-{index}.csv", [10]) for index in range(MAX_HISTORY + 3)]
        store.save(runs)
        loaded = store.load()
        self.assertEqual(len(loaded), MAX_HISTORY)
        self.assertEqual(loaded[0].name, "run-3.csv")
        self.assertEqual(loaded[-1].name, "run-102.csv")

    def test_refuses_stale_preview_without_modifying_config(self):
        preview_source = self.config.read_bytes()
        self.config.write_bytes(self.original.replace(b"7000.0000", b"5000.0000"))
        changed = self.config.read_bytes()
        with self.assertRaises(RuntimeError):
            apply_grass_distance(self.config, 3000, self.backups, expected_original=preview_source)
        self.assertEqual(self.config.read_bytes(), changed)

    def test_atomic_write_failure_leaves_original_file_intact(self):
        with patch("frameforge.core.backup.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                apply_grass_distance(self.config, 3000, self.backups)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_parses_escaped_steam_library_paths(self):
        paths = parse_libraryfolders('"libraryfolders" { "0" { "path" "C:\\\\Games\\\\Steam" } "1" { "path" "D:\\\\Steam Library" } }')
        self.assertEqual([str(path) for path in paths], [r"C:\Games\Steam", r"D:\Steam Library"])

    def test_rejects_symlinked_config_when_supported_by_host(self):
        outside = Path(self.temp.name) / "outside.ini"
        outside.write_bytes(self.original)
        link = self.root / "SkyrimPrefs.ini"
        link.unlink()
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable in this environment")
        with self.assertRaises(SafetyError):
            validate_config_path(link)
        self.assertEqual(outside.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
