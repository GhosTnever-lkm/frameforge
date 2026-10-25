from __future__ import annotations

import unittest
from pathlib import Path

from frameforge.core.csgo_profile import (
    build_csgo_profile_files,
    build_managed_autoexec,
    csgo_launch_arguments,
)


class CsgoProfileTests(unittest.TestCase):
    def build(self, folder: Path, **overrides: object) -> dict[Path, str]:
        options = {
            "fps_limit": 0,
            "dynamic_lights": False,
            "bloom": False,
            "blending": False,
            "red_crosshair": False,
            "startup_menu": False,
            "dark_sky": False,
            "hide_sky": False,
            "existing_autoexec": "",
        }
        options.update(overrides)
        return build_csgo_profile_files(folder, **options)  # type: ignore[arg-type]

    def test_launch_uses_borderless_window_for_interactive_overlay(self):
        self.assertEqual(
            csgo_launch_arguments(True),
            ["-applaunch", "4465480", "-windowed", "-noborder"],
        )

    def test_launch_can_preserve_existing_display_mode(self):
        self.assertEqual(csgo_launch_arguments(False), ["-applaunch", "4465480"])

    def test_autoexec_adds_managed_menu_without_replacing_user_lines(self):
        result = build_managed_autoexec("// user config\nexec personal", True)
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
        result = build_managed_autoexec(original, False)
        self.assertIn("exec personal", result)
        self.assertIn("exec user-last", result)
        self.assertNotIn("FrameForge managed", result)
        self.assertNotIn("ff_menu", result)
        self.assertNotIn("toggleconsole", result)

    def test_autoexec_toggle_can_reenable_single_managed_block(self):
        once = build_managed_autoexec("", True)
        twice = build_managed_autoexec(once, True)
        self.assertEqual(twice.count("// >>> FrameForge managed"), 1)
        self.assertEqual(twice.count("exec frameforge_menu"), 1)
        self.assertEqual(twice.count("ff_menu"), 1)

    def test_default_menu_does_not_reference_optional_cfg_files(self):
        folder = Path("cfg")
        files = self.build(folder)
        menu = files[folder / "frameforge_menu.cfg"]

        self.assertNotIn("alias ff_night", menu)
        self.assertNotIn("alias ff_accessibility", menu)
        self.assertNotIn("ff_night -", menu)
        self.assertNotIn("ff_accessibility -", menu)
        self.assertNotIn(folder / "frameforge_practice_sky.cfg", files)
        self.assertNotIn(folder / "frameforge_accessibility.cfg", files)
        self.assertIn('alias ff_perf "exec frameforge_fps"', menu)
        self.assertIn("ff_perf - apply FPS profile", menu)

    def test_enabled_options_generate_the_cfg_files_referenced_by_menu(self):
        folder = Path("cfg")
        files = self.build(
            folder,
            fps_limit=240,
            dynamic_lights=True,
            bloom=True,
            blending=True,
            red_crosshair=True,
            dark_sky=True,
            hide_sky=True,
        )
        menu = files[folder / "frameforge_menu.cfg"]
        fps = files[folder / "frameforge_fps.cfg"]
        sky = files[folder / "frameforge_practice_sky.cfg"]
        crosshair = files[folder / "frameforge_accessibility.cfg"]

        self.assertIn('alias ff_night "exec frameforge_practice_sky"', menu)
        self.assertIn('alias ff_accessibility "exec frameforge_accessibility"', menu)
        self.assertIn("ff_night - apply selected local-practice sky profile", menu)
        self.assertIn("ff_accessibility - red high-contrast crosshair", menu)
        self.assertIn("fps_max 240", fps)
        self.assertIn("r_dynamic 0", fps)
        self.assertIn("mat_disable_bloom 1", fps)
        self.assertIn("mat_disable_fancy_blending 1", fps)
        self.assertIn("sv_skyname sky_csgo_night02", sky)
        self.assertIn("r_drawskybox 0", sky)
        self.assertIn("cl_crosshaircolor_r 255", crosshair)

    def test_user_autoexec_is_included_only_when_content_remains(self):
        folder = Path("cfg")
        files = self.build(folder, existing_autoexec="exec personal", startup_menu=False)
        self.assertEqual(files[folder / "autoexec.cfg"], "exec personal")

        empty_files = self.build(folder, existing_autoexec="  \n", startup_menu=False)
        self.assertNotIn(folder / "autoexec.cfg", empty_files)


if __name__ == "__main__":
    unittest.main()
