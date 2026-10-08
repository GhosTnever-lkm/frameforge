from __future__ import annotations

import os
import stat
from pathlib import Path

CONFIG_NAME = "SkyrimPrefs.ini"


class SafetyError(ValueError):
    pass


def _is_reparse_or_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SafetyError("A path component cannot be inspected.") from exc
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def validate_config_path(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.name.casefold() != CONFIG_NAME.casefold():
        raise SafetyError(f"Select {CONFIG_NAME} from the supported game folder.")
    if candidate.parent.name.casefold() != "skyrim special edition" or candidate.parent.parent.name.casefold() != "my games":
        raise SafetyError("The config must be inside Documents\\My Games\\Skyrim Special Edition.")
    probe = candidate
    while True:
        if probe.exists() and _is_reparse_or_link(probe):
            raise SafetyError("Symbolic links and junctions are not supported.")
        if probe.parent == probe:
            break
        probe = probe.parent
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SafetyError("The selected config does not exist or cannot be resolved.") from exc
    if not resolved.is_file() or resolved.name.casefold() != CONFIG_NAME.casefold():
        raise SafetyError("The selected config is not a regular SkyrimPrefs.ini file.")
    return resolved
