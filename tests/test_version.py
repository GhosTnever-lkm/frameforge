from __future__ import annotations

import unittest
from pathlib import Path

from frameforge import __version__


class VersionTests(unittest.TestCase):
    def test_package_version_matches_release_version_file(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        self.assertEqual(__version__, (repository_root / "VERSION").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
