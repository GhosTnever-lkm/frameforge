from __future__ import annotations

import ctypes
import os
import stat
import uuid
from pathlib import Path

from .profiles import PROFILES_BY_CONFIG

CONFIG_NAMES = frozenset(PROFILES_BY_CONFIG)


class SafetyError(ValueError):
    pass


def get_documents_root() -> Path:
    """Resolve the user's Documents known folder, including Windows redirection."""
    if os.name != "nt":
        return Path.home() / "Documents"

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    folder_id = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")
    known_folder_id = GUID(
        folder_id.time_low,
        folder_id.time_mid,
        folder_id.time_hi_version,
        (ctypes.c_ubyte * 8)(*folder_id.bytes[8:]),
    )
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long

    com_result = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    com_unsigned = com_result & 0xFFFFFFFF
    rpc_e_changed_mode = 0x80010106
    if com_unsigned not in (0, 1, rpc_e_changed_mode):
        raise SafetyError("Windows не смогла подготовить COM для определения папки Documents.")
    initialized_here = com_unsigned in (0, 1)
    path_pointer = ctypes.c_void_p()
    try:
        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(known_folder_id), 0, None, ctypes.byref(path_pointer)
        )
        if result < 0:
            raise SafetyError("Windows не смогла определить текущую папку Documents.")
        if not path_pointer.value:
            raise SafetyError("Windows вернула пустой путь для папки Documents.")
        root = Path(ctypes.wstring_at(path_pointer.value))
    except OSError as exc:
        raise SafetyError("Windows не смогла определить текущую папку Documents.") from exc
    finally:
        try:
            if path_pointer.value:
                ole32.CoTaskMemFree(path_pointer)
        finally:
            if initialized_here:
                ole32.CoUninitialize()

    if not root.is_absolute() or not root.is_dir():
        raise SafetyError("Папка Documents не существует или не является каталогом.")
    return root


def _is_reparse_or_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SafetyError("Не удалось безопасно проверить компонент пути.") from exc
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _assert_no_reparse_under(path: Path, root: Path) -> None:
    """Check the lexical supported path, without inspecting Documents itself."""
    current = root
    for component in ("My Games", "Skyrim Special Edition", path.name):
        current = current / component
        if _is_reparse_or_link(current):
            raise SafetyError("Symbolic links and junctions are not supported.")


def validate_config_path(path: Path, *, documents_root: Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if candidate.name.casefold() not in CONFIG_NAMES:
        raise SafetyError("Select Skyrim.ini or SkyrimPrefs.ini from the supported game folder.")
    root = Path(documents_root).expanduser() if documents_root is not None else get_documents_root()
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        relative = Path(os.path.relpath(resolved, resolved_root))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SafetyError("Choose the INI from the current Documents\\My Games\\Skyrim Special Edition folder.") from exc
    expected_parts = ["my games", "skyrim special edition", candidate.name.casefold()]
    if [part.casefold() for part in relative.parts] != expected_parts:
        raise SafetyError("The config must be inside the current Documents\\My Games\\Skyrim Special Edition folder.")
    # Allow a redirected Documents known folder, but reject reparse points
    # below it before following them into the game configuration directory.
    _assert_no_reparse_under(candidate, root)
    if not resolved.is_file() or resolved.name.casefold() not in CONFIG_NAMES:
        raise SafetyError("The selected config is not a supported regular Skyrim INI file.")
    return resolved
