from pathlib import Path
import tempfile
import unittest

from frameforge.core.presentmon_capture import build_presentmon_arguments


class PresentMonCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.exe = root / "PresentMon.exe"
        self.exe.write_bytes(b"tool fixture")
        self.output = root / "capture.csv"

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_bounded_targeted_capture_arguments(self):
        args = build_presentmon_arguments(self.exe, self.output, "csgo.exe", 120)
        self.assertEqual(args, [
            "--process_name", "csgo.exe",
            "--output_file", str(self.output),
            "--timed", "120",
            "--terminate_after_timed",
            "--no_console_stats",
        ])

    def test_rejects_missing_tool_and_invalid_process_name(self):
        with self.assertRaises(ValueError):
            build_presentmon_arguments(self.exe.parent / "missing.exe", self.output, "csgo.exe", 60)
        for name in ("csgo", "C:/games/csgo.exe", "csgo.exe --flag", "cmd.exe&calc.exe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_presentmon_arguments(self.exe, self.output, name, 60)

    def test_rejects_unbounded_or_invalid_duration_and_output(self):
        for duration in (0, 29, 600, True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                build_presentmon_arguments(self.exe, self.output, "game.exe", duration)
        with self.assertRaises(ValueError):
            build_presentmon_arguments(self.exe, self.output.with_suffix(".txt"), "game.exe", 60)


if __name__ == "__main__":
    unittest.main()
