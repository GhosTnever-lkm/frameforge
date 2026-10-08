from __future__ import annotations

import difflib
import re
from pathlib import Path

from .backup import atomic_replace, create_byte_backup, sha256
from .safety import validate_config_path

ALLOWED_VALUES = (1000, 3000, 5000, 7000)
SETTING_NAME = "fGrassStartFadeDistance"


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


def _setting_rows(text: str) -> list[tuple[int, re.Match[str]]]:
    section = ""
    rows = []
    for index, line in enumerate(text.splitlines()):
        heading = re.match(r"^\s*\[([^\]]+)\]", line)
        if heading:
            section = heading.group(1).strip().casefold()
        elif section == "grass":
            match = re.match(r"^\s*fGrassStartFadeDistance\s*=\s*([^;#\s]+)", line, re.I)
            if match:
                rows.append((index, match))
    return rows


def validate_ini_payload(data: bytes) -> None:
    text, _, _ = decode_ini(data)
    rows = _setting_rows(text)
    if len(rows) != 1:
        raise ValueError("The file must contain exactly one fGrassStartFadeDistance entry in [Grass].")


def read_grass_distance(path: Path) -> tuple[int, bytes]:
    safe = validate_config_path(path)
    data = safe.read_bytes()
    text, _, _ = decode_ini(data)
    rows = _setting_rows(text)
    if len(rows) != 1:
        raise ValueError("Expected exactly one fGrassStartFadeDistance entry in [Grass].")
    try:
        current = int(float(rows[0][1].group(1)))
    except ValueError as exc:
        raise ValueError("The grass distance value is not numeric.") from exc
    if current < 0 or current > 100000:
        raise ValueError("The grass distance value is outside the supported range.")
    return current, data


def build_tuned_bytes(original: bytes, target: int) -> bytes:
    if target not in ALLOWED_VALUES:
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
        if section == "grass" and re.match(r"^\s*fGrassStartFadeDistance\s*=", line, re.I):
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "\r" if line.endswith("\r") else ""
            body = line[:-len(newline)] if newline else line
            prefix = re.match(r"^(\s*fGrassStartFadeDistance\s*=\s*)", body, re.I).group(1)
            comment = re.search(r"(\s+[;#].*)$", body)
            output.append(f"{prefix}{target}{comment.group(1) if comment else ''}{newline}")
            count += 1
        else:
            output.append(line)
    if count != 1:
        raise ValueError("Expected exactly one fGrassStartFadeDistance entry in [Grass].")
    return (b"\xef\xbb\xbf" if has_bom else b"") + "".join(output).encode(encoding)


def make_diff(original: bytes, updated: bytes, name: str = "SkyrimPrefs.ini") -> str:
    before, _, _ = decode_ini(original)
    after, _, _ = decode_ini(updated)
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=name + " (before)", tofile=name + " (preview)"))


def apply_grass_distance(path: Path, target: int, backup_dir: Path, expected_original: bytes | None = None) -> tuple[Path, str]:
    safe = validate_config_path(path)
    current, original = read_grass_distance(safe)
    if expected_original is not None and original != expected_original:
        raise RuntimeError("The config changed after preview. Scan it again before applying.")
    if current == target:
        raise ValueError("The selected value is already active.")
    updated = build_tuned_bytes(original, target)
    backup = create_byte_backup(safe, backup_dir)
    if safe.read_bytes() != original:
        raise RuntimeError("The config changed after preview. Scan it again before applying.")
    atomic_replace(safe, updated)
    return backup, sha256(updated)
