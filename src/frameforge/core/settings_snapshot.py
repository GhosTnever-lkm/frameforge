from __future__ import annotations

from pathlib import Path

from .apply import read_profile_setting
from .profiles import PROFILES_BY_CONFIG
from .safety import SafetyError, validate_config_path


def read_allowed_setting_snapshot(path: Path) -> tuple[str, int]:
    """Read one allowlisted Skyrim setting without returning or storing its path."""
    safe = validate_config_path(Path(path))
    profile = PROFILES_BY_CONFIG.get(safe.name.casefold())
    if profile is None:
        raise SafetyError("The selected Skyrim setting has no supported snapshot profile.")
    value, _ = read_profile_setting(safe)
    return profile.setting, value
