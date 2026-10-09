import importlib.util
import os
import sys


_dll_directory_handles = []


def _register_qt_dll_directories():
    if getattr(sys, "frozen", False):
        package_root = sys._MEIPASS
        package_paths = (
            os.path.join(package_root, "PySide6"),
            os.path.join(package_root, "shiboken6"),
        )
    else:
        package_paths = []
        for package_name in ("PySide6", "shiboken6"):
            spec = importlib.util.find_spec(package_name)
            if spec is None:
                continue
            locations = spec.submodule_search_locations
            package_paths.extend(locations or ([os.path.dirname(spec.origin)] if spec.origin else []))

    for package_path in package_paths:
        if os.path.isdir(package_path):
            _dll_directory_handles.append(os.add_dll_directory(package_path))


_register_qt_dll_directories()

from frameforge.app import main


if __name__ == "__main__":
    main()
