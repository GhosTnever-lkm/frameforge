from __future__ import annotations

import difflib
import re
from pathlib import Path

from .backup import atomic_replace, create_byte_backup, sha256
from .profiles import PROFILES_BY_CONFIG
from .safety import SafetyError, validate_config_path

_PREFS_PROFILE = PROFILES_BY_CONFIG["skyrimprefs.ini"]
ALLOWED_VALUES = _PREFS_PROFILE.values
SETTING_NAME = _PREFS_PROFILE.setting


def decode_ini(data: bytes) -> tuple[str, str, bool]:
    has_bom = data.startswith(b"\xef\xbb\xbf")
    payload = data[3:] if has_bom else data
    try:
        return payload.decode("utf-8"), "utf-8", has_bom
    except UnicodeDecodeError:
        try:
            return payload.decode("cp1252"), "cp1252", has_bom
        except UnicodeDecodeError as exc:
            raise ValueError("The INI is not valid UTF-8 or Windows-1252.") from exc


def _setting_rows(text: str, section_name: str, setting_name: str) -> list[tuple[int, re.Match[str]]]:
    section = ""
    rows = []
    for index, line in enumerate(text.splitlines()):
        heading = re.match(r"^\s*\[([^\]]+)\]", line)
        if heading:
            section = heading.group(1).strip().casefold()
        elif section == section_name.casefold():
            match = re.match(rf"^\s*{re.escape(setting_name)}\s*=\s*([^;#\s]+)", line, re.I)
            if match:
                rows.append((index, match))
    return rows


def validate_ini_payload(data: bytes, config_name: str = "SkyrimPrefs.ini") -> None:
    profile = PROFILES_BY_CONFIG.get(config_name.casefold())
    if profile is None:
        raise ValueError("The INI file is not supported by FrameForge.")
    text, _, _ = decode_ini(data)
    rows = _setting_rows(text, profile.section, profile.setting)
    if len(rows) != 1:
        raise ValueError(f"The file must contain exactly one {profile.setting} entry in [{profile.section}].")


def read_grass_distance(path: Path) -> tuple[int, bytes]:
    safe = validate_config_path(path)
    if safe.name.casefold() != _PREFS_PROFILE.config_name.casefold():
        raise SafetyError("The grass-distance profile requires SkyrimPrefs.ini.")
    return read_profile_setting(safe)


def read_profile_setting(path: Path) -> tuple[int, bytes]:
    safe = validate_config_path(path)
    profile = PROFILES_BY_CONFIG[safe.name.casefold()]
    data = safe.read_bytes()
    text, _, _ = decode_ini(data)
    rows = _setting_rows(text, profile.section, profile.setting)
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one {profile.setting} entry in [{profile.section}].")
    try:
        current = int(float(rows[0][1].group(1)))
    except ValueError as exc:
        raise ValueError(f"The {profile.setting} value is not numeric.") from exc
    if current < 0 or current > 100000:
        raise ValueError(f"The {profile.setting} value is outside the supported range.")
    return current, data


def build_tuned_bytes(original: bytes, target: int) -> bytes:
    return build_profile_bytes(original, target, _PREFS_PROFILE.config_name)


def build_profile_bytes(original: bytes, target: int, config_name: str) -> bytes:
    profile = PROFILES_BY_CONFIG.get(config_name.casefold())
    if profile is None:
        raise ValueError("Unsupported Skyrim INI profile.")
    if target not in profile.values:
        raise ValueError("Unsupported preset value.")
    text, encoding, has_bom = decode_ini(original)
    lines = text.splitlines(keepends=True)
    section = ""
    count = 0
    output = []
    for line in lines:
        heading = re.match(r"^\s*\[([^\]]+)\]", line)
        if heading:
            section = heading.group(1).strip().casefold()
        if section == profile.section.casefold() and re.match(rf"^\s*{re.escape(profile.setting)}\s*=", line, re.I):
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "\r" if line.endswith("\r") else ""
            body = line[:-len(newline)] if newline else line
            prefix = re.match(rf"^(\s*{re.escape(profile.setting)}\s*=\s*)", body, re.I).group(1)
            comment = re.search(r"(\s+[;#].*)$", body)
            output.append(f"{prefix}{target}{comment.group(1) if comment else ''}{newline}")
            count += 1
        else:
            output.append(line)
    if count != 1:
        raise ValueError(f"Expected exactly one {profile.setting} entry in [{profile.section}].")
    return (b"\xef\xbb\xbf" if has_bom else b"") + "".join(output).encode(encoding)


def make_diff(original: bytes, updated: bytes, name: str = "SkyrimPrefs.ini") -> str:
    before, _, _ = decode_ini(original)
    after, _, _ = decode_ini(updated)
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=name + " (before)", tofile=name + " (preview)"))


def apply_grass_distance(path: Path, target: int, backup_dir: Path, expected_original: bytes | None = None) -> tuple[Path, str]:
    safe = validate_config_path(path)
    if safe.name.casefold() != _PREFS_PROFILE.config_name.casefold():
        raise SafetyError("The grass-distance profile requires SkyrimPrefs.ini.")
    return apply_profile_setting(safe, target, backup_dir, expected_original)


def apply_profile_setting(path: Path, target: int, backup_dir: Path, expected_original: bytes | None = None) -> tuple[Path, str]:
    safe = validate_config_path(path)
    profile = PROFILES_BY_CONFIG[safe.name.casefold()]
    current, original = read_profile_setting(safe)
    if expected_original is not None and original != expected_original:
        raise RuntimeError("The config changed after preview. Scan it again before applying.")
    if current == target:
        raise ValueError("The selected value is already active.")
    updated = build_profile_bytes(original, target, profile.config_name)
    backup = create_byte_backup(safe, backup_dir)
    if safe.read_bytes() != original:
        raise RuntimeError("The config changed after preview. Scan it again before applying.")
    atomic_replace(safe, updated, expected_current_sha256=sha256(original))
    return backup, sha256(updated)
