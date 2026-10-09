from __future__ import annotations

import unittest

from frameforge.ui.main_window import MainWindow


class CsgoProfileTests(unittest.TestCase):
    def test_autoexec_adds_managed_menu_without_replacing_user_lines(self):
        result = MainWindow._build_csgo_managed_autoexec("// user config\nexec personal", True)
        self.assertIn("// user config", result)
        self.assertIn("exec personal", result)
        self.assertIn("exec frameforge_menu", result)
        self.assertIn("ff_menu", result)
        self.assertIn("toggleconsole", result)

    def test_autoexec_replaces_only_existing_managed_block(self):
        original = (
            "exec personal\n\n"
            "// >>> FrameForge managed CS:GO Legacy menu >>>\n"
            "exec frameforge_menu\nff_menu\n"
            "// <<< FrameForge managed CS:GO Legacy menu <<<\n\n"
            "exec user-last"
        )
        result = MainWindow._build_csgo_managed_autoexec(original, False)
        self.assertIn("exec personal", result)
        self.assertIn("exec user-last", result)
        self.assertNotIn("FrameForge managed", result)
        self.assertNotIn("ff_menu", result)
        self.assertNotIn("toggleconsole", result)

    def test_autoexec_toggle_can_reenable_single_managed_block(self):
        once = MainWindow._build_csgo_managed_autoexec("", True)
        twice = MainWindow._build_csgo_managed_autoexec(once, True)
        self.assertEqual(twice.count("// >>> FrameForge managed"), 1)
        self.assertEqual(twice.count("exec frameforge_menu"), 1)
        self.assertEqual(twice.count("ff_menu"), 1)


if __name__ == "__main__":
    unittest.main()
