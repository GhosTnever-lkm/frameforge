import hashlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameforge.core.apply import apply_grass_distance, apply_profile_setting, build_profile_bytes, build_tuned_bytes, make_diff, read_grass_distance, read_profile_setting
from frameforge.core.backup import create_byte_backup, restore_from_backup
from frameforge.core.benchmark import (
    Benchmark, FRAME_TIME_BUCKET_EDGES_MS, analyze_frame_times, compare_benchmarks,
    export_comparison_csv, export_comparison_json, load_frame_time_csv,
)
from frameforge.core.benchmark_store import BenchmarkStore, MAX_HISTORY, SCHEMA_VERSION
from frameforge.core.safety import SafetyError, get_documents_root, validate_config_path
from frameforge.core.scanner import parse_libraryfolders


class FrameForgeCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.documents_root = Path(self.temp.name) / "Documents"
        self.root = self.documents_root / "My Games" / "Skyrim Special Edition"
        self.root.mkdir(parents=True)
        self.documents_root_patch = patch("frameforge.core.safety.get_documents_root", return_value=self.documents_root)
        self.documents_root_patch.start()
        self.config = self.root / "SkyrimPrefs.ini"
        self.original = b"[Display]\r\niShadowMapResolution=2048\r\n\r\n[Grass]\r\nfGrassStartFadeDistance=7000.0000 ; user comment\r\nOther=keep\r\n"
        self.config.write_bytes(self.original)
        self.skyrim_ini = self.root / "Skyrim.ini"
        self.skyrim_ini_original = b"[General]\r\nsSomeSetting=1\r\n[Grass]\r\niMinGrassSize=20 ; density\r\n"
        self.skyrim_ini.write_bytes(self.skyrim_ini_original)
        self.backups = Path(self.temp.name) / "backups"

    def tearDown(self):
        self.documents_root_patch.stop()
        self.temp.cleanup()

    def test_rejects_lookalike_config_outside_known_documents(self):
        outside = Path(self.temp.name) / "Elsewhere" / "My Games" / "Skyrim Special Edition" / "Skyrim.ini"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(self.skyrim_ini_original)
        with self.assertRaisesRegex(SafetyError, "current Documents"):
            validate_config_path(outside)

    def test_config_path_validation_returns_resolved_path(self):
        validated = validate_config_path(self.config)
        self.assertIsInstance(validated, Path)
        self.assertEqual(validated, self.config.resolve())

    def test_missing_config_is_reported_as_safety_error(self):
        self.config.unlink()
        with self.assertRaisesRegex(SafetyError, "current Documents"):
            validate_config_path(self.config)

    def test_accepts_a_redirected_documents_root(self):
        redirected = Path(self.temp.name) / "OneDrive" / "Documents"
        config = redirected / "My Games" / "Skyrim Special Edition" / "Skyrim.ini"
        config.parent.mkdir(parents=True)
        config.write_bytes(self.skyrim_ini_original)
        with patch("frameforge.core.safety.get_documents_root", return_value=redirected):
            self.assertEqual(validate_config_path(config), config.resolve())

    def test_rejects_symlinked_game_directory_under_documents(self):
        outside = Path(self.temp.name) / "External Skyrim"
        outside.mkdir()
        (outside / "SkyrimPrefs.ini").write_bytes(self.original)
        linked = self.documents_root / "My Games" / "Skyrim Special Edition"
        shutil.rmtree(linked)
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlink creation is unavailable in this environment")
        # resolve() follows the link before the explicit reparse-point scan,
        # so the earlier allowlist check may provide the rejection message.
        with self.assertRaises(SafetyError):
            validate_config_path(linked / "SkyrimPrefs.ini")

    def test_rejects_junction_reparse_point_in_game_directory(self):
        import stat
        from types import SimpleNamespace

        target = self.root / "SkyrimPrefs.ini"
        real_lstat = Path.lstat
        junction = self.documents_root / "My Games" / "Skyrim Special Edition"

        def lstat_with_junction(path):
            if path == junction:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return real_lstat(path)

        with patch.object(Path, "lstat", lstat_with_junction):
            with self.assertRaisesRegex(SafetyError, "Symbolic links and junctions"):
                validate_config_path(target)

    @unittest.skipUnless(os.name == "nt", "Windows junctions are only available on Windows")
    def test_rejects_real_windows_junction_under_documents(self):
        import _winapi

        target = Path(self.temp.name) / "External Skyrim"
        target.mkdir()
        (target / "SkyrimPrefs.ini").write_bytes(self.original)
        junction = self.documents_root / "My Games" / "Skyrim Special Edition"
        shutil.rmtree(junction)
        try:
            _winapi.CreateJunction(str(target), str(junction))
        except OSError as exc:
            self.skipTest(f"Windows junction creation unavailable: {exc}")
        try:
            # resolve() follows the junction first, so the public validator may
            # reject the resolved target at the allowlist check before it gets
            # to its explicit reparse-point diagnostic.
            with self.assertRaises(SafetyError):
                validate_config_path(junction / "SkyrimPrefs.ini")
        finally:
            junction.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows known-folder API is only available on Windows")
    def test_windows_documents_known_folder_is_resolvable(self):
        root = get_documents_root()
        self.assertTrue(root.is_absolute())
        self.assertTrue(root.is_dir())

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

    def test_restore_refuses_to_overwrite_edits_made_after_apply(self):
        backup, applied_hash = apply_profile_setting(self.config, 3000, self.backups, expected_original=self.original)
        edited = self.config.read_bytes().replace(b"Other=keep", b"Other=kept-by-user")
        self.config.write_bytes(edited)

        with self.assertRaisesRegex(SafetyError, "current config changed"):
            restore_from_backup(
                backup,
                self.config,
                expected_sha256=hashlib.sha256(self.original).hexdigest(),
                expected_current_sha256=applied_hash,
            )

        self.assertEqual(self.config.read_bytes(), edited)

    def test_restore_chain_accepts_each_expected_current_state(self):
        first_backup, first_applied_hash = apply_profile_setting(self.config, 3000, self.backups, expected_original=self.original)
        intermediate = self.config.read_bytes()
        second_backup, second_applied_hash = apply_profile_setting(self.config, 5000, self.backups, expected_original=intermediate)

        intermediate_hash = restore_from_backup(
            second_backup,
            self.config,
            expected_sha256=hashlib.sha256(intermediate).hexdigest(),
            expected_current_sha256=second_applied_hash,
        )
        self.assertEqual(intermediate_hash, first_applied_hash)
        original_hash = restore_from_backup(
            first_backup,
            self.config,
            expected_sha256=hashlib.sha256(self.original).hexdigest(),
            expected_current_sha256=intermediate_hash,
        )
        self.assertEqual(original_hash, hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_rechecks_current_file_after_preparing_replacement(self):
        backup, applied_hash = apply_profile_setting(self.config, 3000, self.backups, expected_original=self.original)
        edited = self.config.read_bytes().replace(b"Other=keep", b"Other=external-edit")
        real_copystat = shutil.copystat

        def edit_config_after_temp_is_ready(source, destination, **kwargs):
            result = real_copystat(source, destination, **kwargs)
            self.config.write_bytes(edited)
            return result

        with patch("frameforge.core.backup.shutil.copystat", side_effect=edit_config_after_temp_is_ready):
            with self.assertRaisesRegex(SafetyError, "changed before it could be replaced"):
                restore_from_backup(
                    backup,
                    self.config,
                    expected_sha256=hashlib.sha256(self.original).hexdigest(),
                    expected_current_sha256=applied_hash,
                )

        self.assertEqual(self.config.read_bytes(), edited)
        self.assertFalse(list(self.root.glob(".frameforge-*.tmp")))

    def test_apply_rechecks_config_after_preparing_replacement(self):
        edited = self.original.replace(b"Other=keep", b"Other=external-edit")
        real_copystat = shutil.copystat

        def edit_config_after_temp_is_ready(source, destination, **kwargs):
            result = real_copystat(source, destination, **kwargs)
            self.config.write_bytes(edited)
            return result

        with patch("frameforge.core.backup.shutil.copystat", side_effect=edit_config_after_temp_is_ready):
            with self.assertRaisesRegex(SafetyError, "current config changed"):
                apply_profile_setting(self.config, 3000, self.backups, expected_original=self.original)

        self.assertEqual(self.config.read_bytes(), edited)
        self.assertFalse(list(self.root.glob(".frameforge-*.tmp")))

    def test_atomic_replace_cleans_temp_file_on_keyboard_interrupt(self):
        from frameforge.core.backup import atomic_replace

        real_validate = validate_config_path

        def interrupt_after_validation(path, *, documents_root=None):
            validated = real_validate(path, documents_root=documents_root)
            raise KeyboardInterrupt

        with patch("frameforge.core.backup.validate_config_path", side_effect=interrupt_after_validation):
            with self.assertRaises(KeyboardInterrupt):
                atomic_replace(self.config, b"replacement")

        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob(".frameforge-*.tmp")))

    @unittest.skipUnless(os.name == "nt", "Windows junctions are only available on Windows")
    def test_atomic_replace_revalidates_path_after_hash_check(self):
        import _winapi
        from frameforge.core.backup import atomic_replace, sha256

        external = Path(self.temp.name) / "External game directory"
        external.mkdir()
        external_config = external / "SkyrimPrefs.ini"
        external_config.write_bytes(self.original)
        displaced = Path(self.temp.name) / "Displaced game directory"
        real_sha256 = sha256
        swapped = False

        def hash_then_swap(data):
            nonlocal swapped
            digest = real_sha256(data)
            if not swapped:
                shutil.move(str(self.root), str(displaced))
                _winapi.CreateJunction(str(external), str(self.root))
                swapped = True
            return digest

        try:
            with patch("frameforge.core.backup.sha256", side_effect=hash_then_swap):
                with self.assertRaises(SafetyError):
                    atomic_replace(self.config, b"replacement", expected_current_sha256=real_sha256(self.original))
            self.assertTrue(swapped)
            self.assertEqual(external_config.read_bytes(), self.original)
        finally:
            if self.root.exists():
                self.root.rmdir()
            if displaced.exists():
                shutil.move(str(displaced), str(self.root))

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

    def test_benchmark_export_contains_aggregates_without_names_or_raw_frames(self):
        before = analyze_frame_times("C:\\private\\before.csv", [10.0, 11.0, 12.0], game="Cyberpunk 2077", scene="Night City / save 42")
        after = analyze_frame_times("D:\\secret\\after.csv", [9.0, 10.0, 120.0], game="Cyberpunk 2077", scene="Night City / save 43")
        csv_export = export_comparison_csv(before, after)
        json_export = export_comparison_json(before, after)
        for export in (csv_export, json_export):
            self.assertNotIn("before.csv", export)
            self.assertNotIn("after.csv", export)
            self.assertNotIn("C:\\private", export)
            self.assertNotIn("D:\\secret", export)
            self.assertNotIn("Cyberpunk 2077", export)
            self.assertNotIn("Night City", export)
            self.assertNotIn("\nframe_time_ms\n", export)
        self.assertIn("average_fps", csv_export)
        self.assertIn("frame_time_bucket_5_share", csv_export)
        data = json.loads(json_export)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["baseline_a"]["frame_time_bucket_counts"], list(before.frame_time_buckets))
        self.assertEqual(data["variant_b"]["sample_count"], 3)
        self.assertEqual(data["causal_claim"], "not_established_by_two_runs")
        self.assertEqual(sum(data["baseline_a"]["frame_time_bucket_counts"]), data["baseline_a"]["sample_count"])
        self.assertEqual(sum(data["variant_b"]["frame_time_bucket_counts"]), data["variant_b"]["sample_count"])
        forbidden_keys = {"path", "source_path", "config_path", "backup_path", "hostname", "username", "user"}
        def walk_keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key.casefold()
                    yield from walk_keys(value)
            elif isinstance(node, list):
                for value in node:
                    yield from walk_keys(value)
        self.assertFalse(forbidden_keys.intersection(walk_keys(data)))

    def test_benchmark_csv_and_json_exports_agree_on_aggregate_metrics(self):
        before = analyze_frame_times("baseline.csv", [8.0, 10.0, 16.0, 40.0, 120.0])
        after = analyze_frame_times("variant.csv", [9.0, 11.0, 17.0, 50.0, 150.0])
        json_data = json.loads(export_comparison_json(before, after))
        csv_rows = list(csv.DictReader(io.StringIO(export_comparison_csv(before, after))))
        by_metric = {row["metric"]: row for row in csv_rows}
        for side, key in (("baseline_a", "baseline_a"), ("variant_b", "variant_b")):
            run = json_data[key]
            prefix = "baseline_a" if side == "baseline_a" else "variant_b"
            self.assertEqual(int(by_metric["sample_count"][prefix]), run["sample_count"])
            for metric in ("average_fps", "one_percent_low_fps", "median_frame_time_ms", "p99_frame_time_ms", "min_frame_time_ms", "max_frame_time_ms"):
                self.assertAlmostEqual(float(by_metric[metric][prefix]), run[metric])
            for index, count in enumerate(run["frame_time_bucket_counts"]):
                self.assertEqual(int(by_metric[f"frame_time_bucket_{index}"][prefix]), count)
                self.assertAlmostEqual(float(by_metric[f"frame_time_bucket_{index}_share"][prefix]), count / run["sample_count"])

    def test_benchmark_history_roundtrip_omits_source_paths_and_raw_samples(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        run = analyze_frame_times("benchmark.csv", [10, 15, 25])
        store.save([run])
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.temp.name), raw)
        self.assertNotIn("frame_times", raw)
        self.assertEqual(store.load(), [run])

    def test_benchmark_history_v1_migrates_legacy_rows_without_rewriting_until_save(self):
        path = Path(self.temp.name) / "benchmarks.json"
        legacy = analyze_frame_times("legacy.csv", [10, 12])
        document = {
            "schema_version": 1,
            "runs": [{key: value for key, value in (legacy.__dict__ | {"frame_time_buckets": list(legacy.frame_time_buckets)}).items() if key not in {"game", "scene"}}],
        }
        path.write_text(json.dumps(document), encoding="utf-8")
        store = BenchmarkStore(path)
        loaded = store.load()
        self.assertEqual((loaded[0].game, loaded[0].scene), ("", ""))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 1)
        store.save(loaded)
        legacy_after_save = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(legacy_after_save["schema_version"], 1)
        self.assertNotIn("game", legacy_after_save["runs"][0])
        self.assertNotIn("scene", legacy_after_save["runs"][0])
        tagged = Benchmark(**(loaded[0].__dict__ | {"game": "Skyrim", "scene": "Whiterun · High"}))
        store.save([tagged])
        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual((store.load()[0].game, store.load()[0].scene), ("Skyrim", "Whiterun · High"))

    def test_benchmark_history_rejects_malformed_v1_rows_and_boolean_version(self):
        path = Path(self.temp.name) / "benchmarks.json"
        store = BenchmarkStore(path)
        path.write_text(json.dumps({"schema_version": 1, "runs": [None]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "неверный набор полей"):
            store.load()
        path.write_text(json.dumps({"schema_version": True, "runs": []}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "не поддерживается"):
            store.load()

    def test_benchmark_comparison_warns_when_game_or_scene_tags_differ(self):
        before = analyze_frame_times("before.csv", [10, 11], game="Skyrim", scene="Whiterun")
        after = analyze_frame_times("after.csv", [10, 11], game="Skyrim", scene="Riverwood")
        self.assertIn("Метки игры или сцены различаются", compare_benchmarks(before, after))

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

    def test_benchmark_history_rejects_oversized_game_and_scene_labels(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks.json")
        base = analyze_frame_times("run.csv", [10, 12])
        with self.assertRaisesRegex(ValueError, "Метки игры или сцены"):
            store.save([Benchmark(**(base.__dict__ | {"game": "G" * 101}))])
        with self.assertRaisesRegex(ValueError, "Метки игры или сцены"):
            store.save([Benchmark(**(base.__dict__ | {"scene": "S" * 121}))])

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
