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
    Benchmark, FrameTimingSummary, FRAME_BUDGET_FPS_PRESETS, FRAME_TIME_BUCKET_EDGES_MS, analyze_frame_times, compare_benchmarks,
    compare_benchmark_groups, export_comparison_csv, export_comparison_json, format_budget_threshold_label,
    export_group_comparison_csv, export_group_comparison_json, load_benchmark_csv,
    frame_budget_share, load_frame_time_csv, summarize_benchmark_group,
)
from frameforge.core.benchmark_store import BenchmarkStore, MAX_HISTORY, SCHEMA_VERSION
from frameforge.core.safety import SafetyError, get_documents_root, validate_config_path
from frameforge.core.scanner import parse_libraryfolders
from frameforge.core.settings_snapshot import read_allowed_setting_snapshot


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

    def test_presentmon_import_prefers_displayed_metric_and_skips_missing_values(self):
        path = Path(self.temp.name) / "presentmon.csv"
        path.write_text(
            "Application,MsBetweenPresents,FrameType,MsBetweenDisplayChange\n"
            "game.exe,16.0,Application,8.0\n"
            "game.exe,8.0,Intel XeSS-FG,8.0\n"
            "game.exe,NA,Application,NA\n",
            encoding="utf-8",
        )
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "displayed")
        self.assertEqual(run.sample_count, 2)
        self.assertTrue(any("сгенерированные кадры" in warning for warning in warnings))
        self.assertTrue(any("Пропущено некорректных" in warning for warning in warnings))

    def test_presentmon_optional_frame_counters_summarize_valid_rows_and_coverage(self):
        path = Path(self.temp.name) / "presentmon-counters.csv"
        path.write_text(
            "MsBetweenDisplayChange,FrameType,MsCPUBusy,MsGPUTime,MsGPUBusy\n"
            "16,Application,4,6,5\n"
            "16,Application,NA,8,0\n"
            "16,Unknown,999,999,999\n"
            "20,Application,0,4,2\n",
            encoding="utf-8",
        )
        run, _ = load_benchmark_csv(path)
        self.assertEqual(run.sample_count, 3)
        details = {item.metric_id: item for item in run.frame_timing}
        self.assertEqual(details["cpu_busy"], FrameTimingSummary("cpu_busy", 2, 2.0, 4.0))
        self.assertEqual(details["gpu_time"], FrameTimingSummary("gpu_time", 3, 6.0, 8.0))
        self.assertEqual(details["gpu_busy"], FrameTimingSummary("gpu_busy", 3, 2.0, 5.0))

    def test_presentmon_legacy_optional_counter_headers_are_supported(self):
        path = Path(self.temp.name) / "presentmon-old-counters.csv"
        path.write_text("MsBetweenPresents,CPUBusy,GPUTime,GPUBusy\n16,5,8,4\n", encoding="utf-8")
        run, _ = load_benchmark_csv(path)
        self.assertEqual({item.metric_id for item in run.frame_timing}, {"cpu_busy", "gpu_time", "gpu_busy"})

    def test_generic_csv_without_optional_counters_imports_without_diagnostics(self):
        path = Path(self.temp.name) / "generic-no-counters.csv"
        path.write_text("frame_time_ms\n16\n20\n", encoding="utf-8")
        run, _ = load_benchmark_csv(path)
        self.assertEqual(run.frame_timing, ())

    def test_generic_metric_has_priority_and_csv_headers_are_case_insensitive(self):
        path = Path(self.temp.name) / "metric-priority.csv"
        path.write_text(
            "FRaME_TiMe_Ms,msbetweendisplaychange,FRAMETYPE\n"
            "16.0,8.0,Application\n"
            "20.0,4.0,Intel_XEFG\n",
            encoding="utf-8",
        )
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "generic")
        self.assertEqual(run.sample_count, 2)
        self.assertEqual(run.median_frame_time_ms, 16.0)
        self.assertTrue(any("не отфильтрованы автоматически" in warning for warning in warnings))

    def test_presentmon_generated_frame_types_accept_official_underscore_values(self):
        path = Path(self.temp.name) / "presentmon-frame-types.csv"
        path.write_text(
            "MsBetweenDisplayChange,FrameType\n8.0,Intel_XEFG\n8.0,AMD_AFMF\n16.0,Application\n",
            encoding="utf-8",
        )
        run, _ = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "displayed")
        self.assertEqual(run.sample_count, 3)

    def test_generic_import_warns_if_generated_frame_types_cannot_be_filtered(self):
        path = Path(self.temp.name) / "generic-with-frame-types.csv"
        path.write_text("frame_time_ms,FrameType\n16.0,Application\n8.0,Intel_XEFG\n", encoding="utf-8")
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "generic")
        self.assertEqual(run.sample_count, 2)
        self.assertTrue(any("не отфильтрованы автоматически" in warning for warning in warnings))

    def test_presentmon_cpu_presented_filters_generated_frame_types(self):
        path = Path(self.temp.name) / "presentmon-cpu.csv"
        path.write_text(
            "MsBetweenPresents,FrameType\n16.0,Application\n8.0,AMD AFMF\n12.0,Unknown\n",
            encoding="utf-8",
        )
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "cpu-presented")
        self.assertEqual(run.sample_count, 1)
        self.assertTrue(any("исключены строки" in warning for warning in warnings))
        self.assertTrue(any("неподходящим FrameType: 2" in warning for warning in warnings))

    def test_presentmon_import_supports_semicolon_decimal_comma(self):
        path = Path(self.temp.name) / "regional.csv"
        path.write_text("MsBetweenDisplayChange;FrameType\n16,5;Application\n", encoding="utf-8")
        run, _ = load_benchmark_csv(path)
        self.assertEqual(run.sample_count, 1)
        self.assertEqual(run.median_frame_time_ms, 16.5)

    def test_presentmon_semicolon_delimiter_wins_over_comma_in_other_header_text(self):
        path = Path(self.temp.name) / "quoted-header.csv"
        path.write_text(
            'FrameType;MsBetweenDisplayChange;"note, with comma"\n'
            'Application;16.5;"ok, fine"\n',
            encoding="utf-8",
        )
        run, _ = load_benchmark_csv(path)
        self.assertEqual(run.metric_kind, "displayed")
        self.assertEqual(run.sample_count, 1)
        self.assertEqual(run.median_frame_time_ms, 16.5)

    def test_import_reports_fraction_of_rows_skipped_by_frame_type(self):
        path = Path(self.temp.name) / "frame-type-drop-rate.csv"
        path.write_text(
            "MsBetweenPresents,FrameType\n"
            + "16.0,Application\n"
            + "8.0,AMD_AFMF\n" * 3,
            encoding="utf-8",
        )
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.sample_count, 1)
        drop_warning = next(w for w in warnings if "неподходящим FrameType" in w)
        self.assertIn("3 из 4 строк (75.0%)", drop_warning)

    def test_import_reports_malformed_row_count_and_share(self):
        path = Path(self.temp.name) / "malformed.csv"
        path.write_text(
            "MsBetweenDisplayChange,FrameType\n"
            "16.0,Application\n"
            "8.0\n"
            "20.0,Application\n",
            encoding="utf-8",
        )
        run, warnings = load_benchmark_csv(path)
        self.assertEqual(run.sample_count, 2)
        malformed_warning = next(w for w in warnings if "неверным числом полей" in w)
        self.assertIn("1 из 3 строк (33.3%)", malformed_warning)

    def test_presentmon_import_rejects_file_over_size_limit(self):
        path = Path(self.temp.name) / "too-large.csv"
        path.write_text("MsBetweenDisplayChange\n16.0\n", encoding="utf-8")
        with patch("frameforge.core.benchmark.MAX_CSV_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "safety limit"):
                load_benchmark_csv(path)

    def test_import_rejects_ambiguous_comma_decimal_row_in_comma_delimited_csv(self):
        path = Path(self.temp.name) / "ambiguous-comma.csv"
        path.write_text("MsBetweenDisplayChange\n16,67\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "нет пригодных значений"):
            load_benchmark_csv(path)

    def test_benchmark_comparison_warns_when_metric_kinds_differ(self):
        before = analyze_frame_times("before", [16], metric_kind="cpu-presented")
        after = analyze_frame_times("after", [8], metric_kind="displayed")
        self.assertIn("Типы frametime различаются", compare_benchmarks(before, after))

    def test_benchmark_comparison_displays_optional_counters_without_bottleneck_claims(self):
        before = analyze_frame_times("before", [16, 20], frame_timing=(FrameTimingSummary("gpu_busy", 1, 0.0, 0.0),))
        after = analyze_frame_times("after", [16, 20])
        report = compare_benchmarks(before, after)
        self.assertIn("GPU busy: 0.00 / 0.00 мс; 1/2 (50.0%)", report)
        self.assertIn("CPU busy: отсутствует в CSV", report)
        self.assertIn("не определение причины", report)
        self.assertIn("не всех строк исходного CSV", report)
        self.assertIn("Нули показываются как записанные значения", report)
        self.assertNotIn("CPU bottleneck", report)

    def test_benchmark_comparison_shows_user_notes_without_causal_claim(self):
        before = analyze_frame_times("before", [16], change_note="Тени: высокие")
        after = analyze_frame_times("after", [15], change_note="Тени: средние")
        report = compare_benchmarks(before, after)
        self.assertIn("A: Тени: высокие", report)
        self.assertIn("B: Тени: средние", report)
        self.assertIn("не доказательство причины", report)

    def test_benchmark_comparison_shows_allowlisted_setting_snapshot_as_context(self):
        before = analyze_frame_times("before", [16], setting_key="fGrassStartFadeDistance", setting_value=7000)
        after = analyze_frame_times("after", [15], setting_key="iMinGrassSize", setting_value=60)
        report = compare_benchmarks(before, after)
        self.assertIn("fGrassStartFadeDistance=7000", report)
        self.assertIn("iMinGrassSize=60", report)
        self.assertIn("путь к INI не сохранён", report)
        self.assertIn("не доказывает причину", report)

    def test_benchmark_comparison_shows_manual_checklist_changes_as_context(self):
        before = analyze_frame_times("before.csv", [16], game="Counter-Strike 2", scene="Mirage", manual_changes=("cs2.shadows",))
        after = analyze_frame_times("after.csv", [15], game="Counter-Strike 2", scene="Mirage", manual_changes=("cs2.effects",))
        report = compare_benchmarks(before, after)
        self.assertIn("Отмеченные вручную пункты игрового чек-листа", report)
        self.assertIn("Качество теней", report)
        self.assertIn("Качество эффектов", report)
        self.assertIn("Только A: Качество теней", report)
        self.assertIn("Только B: Качество эффектов", report)
        self.assertIn("не доказательство причины", report)

    def test_benchmark_comparison_does_not_diff_checklists_across_games(self):
        before = analyze_frame_times("before.csv", [16], game="Counter-Strike 2", manual_changes=("cs2.shadows",))
        after = analyze_frame_times("after.csv", [15], game="Dota 2", manual_changes=("dota2.shadows",))
        report = compare_benchmarks(before, after)
        self.assertIn("CS2" if "CS2" in report else "Counter-Strike 2", report)
        self.assertIn("Dota 2", report)
        self.assertIn("Списки относятся к разным играм и не сопоставляются", report)
        self.assertNotIn("Только A:", report)
        self.assertNotIn("Только B:", report)

    def test_allowed_setting_snapshot_returns_only_key_and_value(self):
        self.skyrim_ini.write_bytes(self.skyrim_ini_original + b"[Grass]\nUnknownPersonalValue=secret\n")
        self.assertEqual(read_allowed_setting_snapshot(self.skyrim_ini), ("iMinGrassSize", 20))

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

    def test_repeated_benchmark_groups_use_median_and_iqr_of_csv_summaries(self):
        def run(name, times):
            base = analyze_frame_times(name, times, game="Counter-Strike 2", scene="Dust II / benchmark", metric_kind="displayed")
            return base
        group_a = [run("private-a.csv", [value] * 10) for value in (10, 20, 30)]
        group_b = [run("private-b.csv", [value] * 10) for value in (8, 10, 12)]
        summary = summarize_benchmark_group(group_a)
        self.assertAlmostEqual(summary["average_fps"]["median"], 1000 / 20)
        report = compare_benchmark_groups(group_a, group_b)
        self.assertIn("A — 3 CSV, B — 3 CSV", report)
        self.assertIn("межквартильный диапазон", report)
        self.assertIn("не тест статистической значимости", report)
        self.assertIn("1% low по CSV", report)
        self.assertIn("не pooled-показатели группы", report)
        self.assertIn("прогонах IQR особенно чувствителен", report)
        self.assertIn("№ | n_frames | average FPS | 1% low FPS | p99 frametime", report)
        self.assertIn("  1 | 10 | 100.00 | 100.00 | 10.00", report)
        self.assertIn("n_frames — число принятых кадров, не длительность", report)
        self.assertNotIn("private-a.csv", report)
        run_rows = [line for line in report.splitlines() if line.startswith("  ") and line.split("|")[0].strip().isdigit()]
        self.assertEqual(len(run_rows), 6)
        self.assertTrue(any(row.startswith("  2 | 10 | 50.00 | 50.00 | 20.00 | ") for row in run_rows))
        self.assertEqual(report, compare_benchmark_groups(group_a, group_b))

    def test_repeated_group_requires_three_runs_and_matching_context(self):
        runs = [analyze_frame_times(str(index), [10, 10], game="CS2", scene="map") for index in range(3)]
        with self.assertRaisesRegex(ValueError, "не менее трёх"):
            summarize_benchmark_group(runs[:2])
        mismatched = runs[:2] + [analyze_frame_times("other", [10, 10], game="CS2", scene="other map")]
        with self.assertRaisesRegex(ValueError, "одинаковые игру, сцену и тип"):
            summarize_benchmark_group(mismatched)
        with self.assertRaisesRegex(ValueError, "одновременно"):
            compare_benchmark_groups(runs, runs)
        with self.assertRaisesRegex(ValueError, "только один раз"):
            summarize_benchmark_group([runs[0], runs[0], runs[1]])

    def test_repeated_group_exports_omit_private_context_and_raw_data(self):
        counter = (FrameTimingSummary("gpu_busy", 3, 4.0, 8.0),)
        group_a = [analyze_frame_times(f"C:\\secret\\run-{i}.csv", [10, 11, 12], game="Private Game", scene="private save", change_note="local note", frame_timing=counter) for i in range(3)]
        group_b = [analyze_frame_times(f"D:\\secret\\run-{i}.csv", [8, 9, 10], game="Private Game", scene="private save", change_note="other note", frame_timing=counter) for i in range(3)]
        csv_export = export_group_comparison_csv(group_a, group_b)
        json_export = export_group_comparison_json(group_a, group_b)
        for payload in (csv_export, json_export):
            for private in ("secret", "run-0", "Private Game", "private save", "local note", "gpu_busy", "frame_timing", "\nframe_time_ms\n"):
                self.assertNotIn(private, payload)
        data = json.loads(json_export)
        self.assertEqual(data["baseline_a"]["run_count"], 3)
        self.assertEqual(data["causal_claim"], "not_established_by_repeated_runs")
        self.assertEqual(set(data["baseline_a"]["metrics"]["average_fps"]), {"median", "q1", "q3"})
        self.assertNotIn("per_run", json_export)
        self.assertNotIn("average_fps_by_run", json_export)

    def test_benchmark_export_contains_aggregates_without_names_or_raw_frames(self):
        before = analyze_frame_times("C:\\private\\before.csv", [10.0, 11.0, 12.0], game="Cyberpunk 2077", scene="Night City / save 42", frame_timing=(FrameTimingSummary("gpu_busy", 3, 1.0, 2.0),))
        before = Benchmark(**(before.__dict__ | {"change_note": "LOCAL_ONLY C:\\Users\\private\\settings.ini", "setting_key": "iMinGrassSize", "setting_value": 40, "manual_changes": ("cyberpunk.volumetrics",)}))
        after = analyze_frame_times("D:\\secret\\after.csv", [9.0, 10.0, 120.0], game="Cyberpunk 2077", scene="Night City / save 43", change_note="another local note", frame_timing=(FrameTimingSummary("cpu_busy", 2, 2.0, 3.0),))
        csv_export = export_comparison_csv(before, after)
        json_export = export_comparison_json(before, after)
        for export in (csv_export, json_export):
            self.assertNotIn("before.csv", export)
            self.assertNotIn("after.csv", export)
            self.assertNotIn("C:\\private", export)
            self.assertNotIn("D:\\secret", export)
            self.assertNotIn("Cyberpunk 2077", export)
            self.assertNotIn("Night City", export)
            self.assertNotIn("LOCAL_ONLY", export)
            self.assertNotIn("local note", export)
            self.assertNotIn("iMinGrassSize", export)
            self.assertNotIn("cyberpunk.volumetrics", export)
            self.assertNotIn("gpu_busy", export)
            self.assertNotIn("frame_timing", export)
            self.assertNotIn("LOCAL_ONLY", export)
            self.assertNotIn("\nframe_time_ms\n", export)
        self.assertIn("average_fps", csv_export)
        self.assertIn("frame_time_metric_kind", csv_export)
        self.assertIn("frame_time_bucket_5_share", csv_export)
        data = json.loads(json_export)
        self.assertEqual(data["schema_version"], 3)
        self.assertEqual(data["baseline_a"]["frame_time_metric_kind"], "generic")
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
        run = analyze_frame_times("benchmark.csv", [10, 15, 25], game="Counter-Strike 2", change_note="Тени: высокие → средние", manual_changes=("cs2.shadows",))
        store.save([run])
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.temp.name), raw)
        self.assertNotIn("frame_times", raw)
        self.assertIn("Тени: высокие", raw)
        self.assertIn("cs2.shadows", raw)
        self.assertEqual(store.load(), [run])

    def test_benchmark_history_v7_roundtrips_optional_frame_timing_summaries(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks.json")
        run = analyze_frame_times(
            "presentmon.csv", [10, 15, 25],
            frame_timing=(FrameTimingSummary("cpu_busy", 2, 2.0, 3.0), FrameTimingSummary("gpu_busy", 3, 0.0, 5.0)),
        )
        store.save([run])
        self.assertEqual(store.load(), [run])
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], 8)
        self.assertEqual(raw["runs"][0]["frame_timing"][1]["metric_id"], "gpu_busy")
        self.assertEqual(raw["runs"][0]["frame_budget_counts"], list(run.frame_budget_counts))

    def test_frame_budget_counts_follow_exact_inclusive_thresholds_without_raw_frames(self):
        exact_60_budget = 1000.0 / 60
        run = analyze_frame_times("budget.csv", [8.0, exact_60_budget, exact_60_budget + 0.001])
        self.assertEqual(len(run.frame_budget_counts), len(FRAME_BUDGET_FPS_PRESETS))
        self.assertEqual(run.frame_budget_counts[FRAME_BUDGET_FPS_PRESETS.index(60)], 2)
        self.assertEqual(run.frame_budget_counts[FRAME_BUDGET_FPS_PRESETS.index(120)], 1)
        self.assertEqual(frame_budget_share(run, 60), 200 / 3)
        self.assertEqual(tuple(sorted(run.frame_budget_counts, reverse=True)), run.frame_budget_counts)
        self.assertNotIn("frame_times_ms", run.__dict__)
        fastest = analyze_frame_times("fast.csv", [3.0] * 100)
        slowest = analyze_frame_times("slow.csv", [100.0] * 100)
        self.assertEqual(fastest.frame_budget_counts, (100,) * len(FRAME_BUDGET_FPS_PRESETS))
        self.assertEqual(slowest.frame_budget_counts, (0,) * len(FRAME_BUDGET_FPS_PRESETS))
        store = BenchmarkStore(Path(self.temp.name) / "equal-counts.json")
        store.save([fastest, slowest])
        self.assertEqual(store.load(), [fastest, slowest])
        with self.assertRaises(ValueError):
            frame_budget_share(run, 100)

    def test_frame_budget_threshold_label_shows_fraction_and_marks_decimal_approximate(self):
        label = format_budget_threshold_label(60)
        self.assertEqual(label, "≤ 1000/60 мс (≈ 16.666667 мс)")
        self.assertNotIn("≤ 16.667 мс", label)
        for fps in FRAME_BUDGET_FPS_PRESETS:
            self.assertIn(f"1000/{fps}", format_budget_threshold_label(fps))
        for fps in (0, -1, 100):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                format_budget_threshold_label(fps)

    def test_benchmark_history_rejects_invalid_frame_budget_counts(self):
        store = BenchmarkStore(Path(self.temp.name) / "invalid-budget.json")
        base = analyze_frame_times("run.csv", [10, 20, 30])
        invalid_counts = (
            (1,),
            tuple([True] + list(base.frame_budget_counts[1:])),
            tuple([4] + list(base.frame_budget_counts[1:])),
            tuple([0, 1] + list(base.frame_budget_counts[2:])),  # higher FPS cannot include more frames
        )
        for counts in invalid_counts:
            with self.subTest(counts=counts), self.assertRaisesRegex(ValueError, "Frame budget"):
                store.save([Benchmark(**(base.__dict__ | {"frame_budget_counts": counts}))])

    def test_benchmark_history_v7_migrates_frame_budget_as_unavailable(self):
        path = Path(self.temp.name) / "benchmarks-v7.json"
        run = analyze_frame_times("old.csv", [10, 12])
        row = run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets), "frame_timing": []}
        row.pop("frame_budget_counts")
        path.write_text(json.dumps({"schema_version": 7, "runs": [row]}), encoding="utf-8")
        store = BenchmarkStore(path)
        loaded = store.load()[0]
        self.assertIsNone(loaded.frame_budget_counts)
        report = compare_benchmarks(loaded, run, 60)
        self.assertIn("нет данных (замер импортирован в старой версии", report)
        self.assertNotIn("A: 0.0%", report)
        store.save([loaded])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 8)
        self.assertIsNone(store.load()[0].frame_budget_counts)

    def test_frame_budget_group_uses_median_of_per_csv_percentages(self):
        runs_a = [analyze_frame_times(f"a-{index}.csv", values) for index, values in enumerate(([10] * 10, [10] * 5 + [20] * 5, [20] * 10))]
        runs_a = [Benchmark(**(run.__dict__ | {"game": "Game", "scene": "Scene"})) for run in runs_a]
        summary = summarize_benchmark_group(runs_a, 60)
        self.assertEqual(summary["frame_budget_within_pct"]["median"], 50.0)
        group_report = compare_benchmark_groups(runs_a, runs_a[:0] + [
            Benchmark(**(analyze_frame_times(f"b-{i}.csv", values).__dict__ | {"game": "Game", "scene": "Scene"}))
            for i, values in enumerate(([12] * 10, [18] * 10, [10] * 5 + [20] * 5))
        ], 60)
        self.assertIn("Доля принятых кадров в бюджете 60 FPS", group_report)
        self.assertIn("в бюджете (%)", group_report)
        legacy_group_a = [Benchmark(**(run.__dict__ | {"frame_budget_counts": None})) for run in runs_a]
        mixed_group_a = [Benchmark(**(run.__dict__ | {"frame_budget_counts": None if index == 0 else run.frame_budget_counts})) for index, run in enumerate(runs_a)]
        mixed_group_b = [Benchmark(**run.__dict__) for run in runs_a]
        mixed_report = compare_benchmark_groups(mixed_group_a, mixed_group_b, 60)
        self.assertIn("группа A — 2/3 CSV; группа B — 3/3 CSV", mixed_report)
        self.assertIn("Сводка групп недоступна", mixed_report)
        json_export = json.loads(export_group_comparison_json(legacy_group_a, runs_a, 60))
        self.assertEqual(json_export["frame_budget_available"], {"baseline_a": False, "variant_b": True})
        self.assertEqual(json_export["frame_budget_available_run_count"], {"baseline_a": 0, "variant_b": 3})
        self.assertNotIn("frame_budget_within_pct", json_export["baseline_a"]["metrics"])
        csv_rows = list(csv.DictReader(io.StringIO(export_group_comparison_csv(legacy_group_a, runs_a, 60).lstrip("\ufeff"))))
        available = next(row for row in csv_rows if row["metric"] == "frame_budget_available")
        self.assertEqual((available["group_a_median"], available["group_b_median"]), ("0", "1"))

    def test_frame_budget_comparison_exports_include_target_but_not_source_names(self):
        before = analyze_frame_times("C:\\private\\before.csv", [10, 20])
        after = analyze_frame_times("D:\\secret\\after.csv", [8, 30])
        payload = json.loads(export_comparison_json(before, after, 60))
        self.assertEqual(payload["frame_budget_target_fps"], 60)
        self.assertEqual(payload["baseline_a"]["frame_budget_within_share"], 0.5)
        self.assertEqual(payload["variant_b"]["frame_budget_within_share"], 0.5)
        self.assertNotIn("before.csv", json.dumps(payload))
        self.assertIn("frame_budget_target_fps", export_comparison_csv(before, after, 60))

    def test_benchmark_history_v6_migrates_with_empty_frame_timing(self):
        path = Path(self.temp.name) / "benchmarks-v6.json"
        run = analyze_frame_times("v6.csv", [10, 12], game="Counter-Strike 2", manual_changes=("cs2.shadows",))
        row = {key: value for key, value in (run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets)}).items() if key != "frame_timing"}
        path.write_text(json.dumps({"schema_version": 6, "runs": [row]}), encoding="utf-8")
        store = BenchmarkStore(path)
        loaded = store.load()
        self.assertEqual(loaded[0].frame_timing, ())
        store.save(loaded)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 8)

    def test_benchmark_history_rejects_invalid_frame_timing_summaries(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks-invalid-timing.json")
        base = analyze_frame_times("run.csv", [10, 12])
        invalid_summaries = (
            (FrameTimingSummary("unknown", 1, 1.0, 1.0),),
            (FrameTimingSummary("cpu_busy", True, 1.0, 1.0),),
            (FrameTimingSummary("cpu_busy", 3, 1.0, 1.0),),
            (FrameTimingSummary("gpu_busy", 1, 2.0, 1.0),),
            (FrameTimingSummary("gpu_time", 0, 0.0, 0.0),),
        )
        for summaries in invalid_summaries:
            with self.subTest(summaries=summaries), self.assertRaises(ValueError):
                store.save([Benchmark(**(base.__dict__ | {"frame_timing": summaries}))])

    def test_benchmark_history_v1_migrates_legacy_rows_without_rewriting_until_save(self):
        path = Path(self.temp.name) / "benchmarks.json"
        legacy = analyze_frame_times("legacy.csv", [10, 12])
        document = {
            "schema_version": 1,
            "runs": [{key: value for key, value in (legacy.__dict__ | {"frame_time_buckets": list(legacy.frame_time_buckets)}).items() if key not in {"game", "scene", "metric_kind", "change_note", "setting_key", "setting_value", "manual_changes", "frame_timing"}}],
        }
        path.write_text(json.dumps(document), encoding="utf-8")
        store = BenchmarkStore(path)
        loaded = store.load()
        self.assertEqual((loaded[0].game, loaded[0].scene), ("", ""))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 1)
        store.save(loaded)
        legacy_after_save = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(legacy_after_save["schema_version"], SCHEMA_VERSION)
        self.assertIn("game", legacy_after_save["runs"][0])
        self.assertEqual(legacy_after_save["runs"][0]["metric_kind"], "generic")
        self.assertEqual(legacy_after_save["runs"][0]["change_note"], "")
        self.assertEqual(legacy_after_save["runs"][0]["setting_key"], "")
        self.assertIsNone(legacy_after_save["runs"][0]["setting_value"])
        self.assertEqual(legacy_after_save["runs"][0]["manual_changes"], [])
        tagged = Benchmark(**(loaded[0].__dict__ | {"game": "Skyrim", "scene": "Whiterun · High"}))
        store.save([tagged])
        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
        self.assertEqual((store.load()[0].game, store.load()[0].scene), ("Skyrim", "Whiterun · High"))

    def test_benchmark_history_v2_migrates_tagged_runs(self):
        path = Path(self.temp.name) / "benchmarks.json"
        run = analyze_frame_times("legacy.csv", [10, 12], game="Skyrim", scene="Whiterun")
        row = {key: value for key, value in (run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets)}).items() if key not in {"metric_kind", "change_note", "setting_key", "setting_value", "manual_changes", "frame_timing"}}
        path.write_text(json.dumps({"schema_version": 2, "runs": [row]}), encoding="utf-8")
        loaded = BenchmarkStore(path).load()
        self.assertEqual(loaded[0].metric_kind, "generic")
        self.assertEqual(loaded[0].change_note, "")
        self.assertEqual((loaded[0].game, loaded[0].scene), ("Skyrim", "Whiterun"))

    def test_benchmark_history_v3_migrates_metric_and_adds_empty_note(self):
        path = Path(self.temp.name) / "benchmarks.json"
        run = analyze_frame_times("legacy.csv", [10, 12], game="Skyrim", scene="Whiterun", metric_kind="displayed")
        row = {key: value for key, value in (run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets)}).items() if key not in {"change_note", "setting_key", "setting_value", "manual_changes", "frame_timing"}}
        row_with_note = row | {"name": "legacy-with-note.csv", "change_note": "preserve this local note"}
        path.write_text(json.dumps({"schema_version": 3, "runs": [row, row_with_note]}), encoding="utf-8")
        loaded = BenchmarkStore(path).load()
        self.assertEqual(loaded[0].metric_kind, "displayed")
        self.assertEqual(loaded[0].change_note, "")
        self.assertEqual(loaded[1].change_note, "preserve this local note")
        self.assertEqual((loaded[0].setting_key, loaded[0].setting_value), ("", None))

    def test_benchmark_history_rejects_invalid_change_note(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks.json")
        base = analyze_frame_times("run.csv", [10, 12])
        with self.assertRaisesRegex(ValueError, "Заметка к замеру"):
            store.save([Benchmark(**(base.__dict__ | {"change_note": "N" * 161}))])
        with self.assertRaisesRegex(ValueError, "Заметка к замеру"):
            store.save([Benchmark(**(base.__dict__ | {"change_note": "line 1\nline 2"}))])

    def test_benchmark_history_roundtrips_only_allowlisted_setting_pairs(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks.json")
        base = analyze_frame_times("run.csv", [10, 12], setting_key="iMinGrassSize", setting_value=60)
        store.save([base])
        self.assertEqual(store.load(), [base])
        for key, value in (("UnknownSetting", 5), ([], 5), ("iMinGrassSize", True), ("iMinGrassSize", -1), ("iMinGrassSize", 100_001), ("", 10)):
            with self.subTest(key=key, value=value):
                invalid = Benchmark(**(base.__dict__ | {"setting_key": key, "setting_value": value}))
                with self.assertRaisesRegex(ValueError, "Снимок настройки"):
                    store.save([invalid])

    def test_benchmark_history_v4_migrates_with_empty_setting_snapshot(self):
        path = Path(self.temp.name) / "benchmarks.json"
        run = analyze_frame_times("v4.csv", [10, 12], metric_kind="displayed", change_note="updated grass")
        row = {key: value for key, value in (run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets)}).items() if key not in {"setting_key", "setting_value", "manual_changes", "frame_timing"}}
        path.write_text(json.dumps({"schema_version": 4, "runs": [row]}), encoding="utf-8")
        loaded = BenchmarkStore(path).load()
        self.assertEqual(loaded[0].metric_kind, "displayed")
        self.assertEqual(loaded[0].change_note, "updated grass")
        self.assertEqual((loaded[0].setting_key, loaded[0].setting_value), ("", None))

    def test_benchmark_history_v5_migrates_with_empty_manual_checklist(self):
        path = Path(self.temp.name) / "benchmarks.json"
        run = analyze_frame_times("v5.csv", [10, 12], game="Counter-Strike 2", manual_changes=("cs2.shadows",))
        row = {key: value for key, value in (run.__dict__ | {"frame_time_buckets": list(run.frame_time_buckets)}).items() if key not in {"manual_changes", "frame_timing"}}
        path.write_text(json.dumps({"schema_version": 5, "runs": [row]}), encoding="utf-8")
        loaded = BenchmarkStore(path).load()
        self.assertEqual(loaded[0].game, "Counter-Strike 2")
        self.assertEqual(loaded[0].manual_changes, ())
        BenchmarkStore(path).save(loaded)
        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
        self.assertEqual(migrated["runs"][0]["manual_changes"], [])

    def test_benchmark_history_roundtrips_only_game_allowlisted_checklist_ids(self):
        store = BenchmarkStore(Path(self.temp.name) / "benchmarks.json")
        run = analyze_frame_times(
            "run.csv", [10, 12], game="Counter-Strike 2", manual_changes=("cs2.shadows", "cs2.effects")
        )
        store.save([run])
        self.assertEqual(store.load(), [run])
        for game, changes in (
            ("Counter-Strike 2", ("cs2.unknown",)),
            ("Counter-Strike 2", ("cs2.shadows", "cs2.shadows")),
            ("Dota 2", ("cs2.shadows",)),
            ("The Elder Scrolls V: Skyrim Special Edition", ("cs2.shadows",)),
        ):
            with self.subTest(game=game, changes=changes):
                invalid = Benchmark(**(run.__dict__ | {"game": game, "manual_changes": changes}))
                with self.assertRaisesRegex(ValueError, "чек-листа"):
                    store.save([invalid])

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
