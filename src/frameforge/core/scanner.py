from __future__ import annotations

import os
import re
import shutil
from pathlib import Path


def parse_libraryfolders(text: str) -> list[Path]:
    """Parse Steam's quoted library path entries without executing anything."""
    libraries: list[Path] = []
    for match in re.finditer(r'"path"\s*"((?:\\\\.|[^"])*)"', text, re.I):
        raw = match.group(1).replace("\\\\", "\\").replace('\\"', '"')
        candidate = Path(raw)
        if candidate not in libraries:
            libraries.append(candidate)
    return libraries


def steam_libraryfolders_files() -> list[Path]:
    candidates = []
    program_files = os.environ.get("PROGRAMFILES(X86)") or os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Steam" / "steamapps" / "libraryfolders.vdf")
    candidates.extend([Path.home() / ".steam" / "steam" / "steamapps" / "libraryfolders.vdf", Path.home() / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf"])
    return [path for path in candidates if path.is_file()]


def detect_skyrim_installs() -> list[Path]:
    installs = []
    for vdf in steam_libraryfolders_files():
        try:
            library_text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        library_roots = [vdf.parent.parent, *parse_libraryfolders(library_text)]
        for root in library_roots:
            manifest = root / "steamapps" / "appmanifest_489830.acf"
            if manifest.is_file():
                try:
                    text = manifest.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                match = re.search(r'"installdir"\s*"([^"]+)"', text, re.I)
                if match:
                    game_dir = root / "steamapps" / "common" / match.group(1)
                    if game_dir.is_dir() and game_dir not in installs:
                        installs.append(game_dir)
    return installs


def system_snapshot(home: Path | None = None) -> dict[str, str]:
    import platform

    home = home or Path.home()
    result = {"cpu": platform.processor() or platform.machine(), "logical_processors": str(os.cpu_count() or "unknown")}
    try:
        usage = shutil.disk_usage(home)
        result["disk_free_gb"] = f"{usage.free / 1024**3:.1f}"
        result["disk_total_gb"] = f"{usage.total / 1024**3:.1f}"
    except OSError:
        result["disk_free_gb"] = "unknown"
        result["disk_total_gb"] = "unknown"
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        memory = MemoryStatus()
        memory.dwLength = ctypes.sizeof(memory)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result["ram_total_gb"] = f"{memory.ullTotalPhys / 1024**3:.1f}"
                result["ram_available_gb"] = f"{memory.ullAvailPhys / 1024**3:.1f}"
        except (AttributeError, OSError):
            pass
    return result
