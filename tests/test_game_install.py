from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameforge.core.scanner import find_csgo_legacy_cfg


class CsgoLegacyInstallTests(unittest.TestCase):
    def test_finds_cfg_in_secondary_library_using_legacy_install_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            primary = base / "Steam"
            secondary = base / "Steam Library"
            libraryfolders = primary / "steamapps" / "libraryfolders.vdf"
            libraryfolders.parent.mkdir(parents=True)
            escaped_secondary = str(secondary).replace("\\", "\\\\")
            libraryfolders.write_text(
                f'"libraryfolders" {{ "0" {{ "path" "{primary}" }} '
                f'"1" {{ "path" "{escaped_secondary}" }} }}',
                encoding="utf-8",
            )

            manifest = secondary / "steamapps" / "appmanifest_4465480.acf"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '"AppState" { "appid" "4465480" "installdir" "csgo legacy" }',
                encoding="utf-8",
            )
            cfg = secondary / "steamapps" / "common" / "csgo legacy" / "csgo" / "cfg"
            cfg.mkdir(parents=True)

            with patch("frameforge.core.scanner.steam_libraryfolders_files", return_value=[libraryfolders]):
                self.assertEqual(find_csgo_legacy_cfg(), cfg)

    def test_ignores_manifest_install_directories_that_escape_steam_common(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary) / "Steam"
            vdf = library / "steamapps" / "libraryfolders.vdf"
            vdf.parent.mkdir(parents=True)
            vdf.write_text('"libraryfolders" {}', encoding="utf-8")
            manifest = library / "steamapps" / "appmanifest_4465480.acf"
            manifest.write_text(
                '"AppState" { "installdir" "..\\outside" }', encoding="utf-8"
            )
            outside_cfg = library / "steamapps" / "common" / "..\\outside" / "csgo" / "cfg"
            outside_cfg.mkdir(parents=True)

            with patch("frameforge.core.scanner.steam_libraryfolders_files", return_value=[vdf]):
                self.assertIsNone(find_csgo_legacy_cfg())


if __name__ == "__main__":
    unittest.main()
