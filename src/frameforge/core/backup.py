from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from .safety import SafetyError, _is_reparse_or_link, validate_config_path


def _validate_backup_directory(backup_dir: Path, *, create: bool = False) -> Path:
    candidate = Path(backup_dir).expanduser()
    if candidate.name.casefold() != "backups":
        raise SafetyError("FrameForge backups must be stored in a directory named 'backups'.")
    probe = candidate
    while True:
        if probe.exists() and _is_reparse_or_link(probe):
            raise SafetyError("Symbolic links and junctions are not supported in backup paths.")
        if probe.parent == probe:
            break
        probe = probe.parent
    if create:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SafetyError("The FrameForge backup directory cannot be created safely.") from exc
        probe = candidate
        while True:
            if probe.exists() and _is_reparse_or_link(probe):
                raise SafetyError("Symbolic links and junctions are not supported in backup paths.")
            if probe.parent == probe:
                break
            probe = probe.parent
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SafetyError("The FrameForge backup directory is missing or cannot be resolved.") from exc
    if not resolved.is_dir():
        raise SafetyError("The FrameForge backup location is not a directory.")
    return resolved


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_byte_backup(config: Path, backup_dir: Path) -> Path:
    safe = validate_config_path(config)
    backup_dir = _validate_backup_directory(backup_dir, create=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"frameforge-{safe.stem.casefold()}-{timestamp}.ini.bak"
    original = safe.read_bytes()
    with backup.open("xb") as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    if sha256(backup.read_bytes()) != sha256(original):
        backup.unlink(missing_ok=True)
        raise OSError("Backup verification failed; the config was not changed.")
    return backup


def atomic_replace(path: Path, data: bytes) -> None:
    import shutil
    import tempfile

    fd, temporary = tempfile.mkstemp(prefix=".frameforge-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copystat(path, temporary, follow_symlinks=False)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def restore_from_backup(backup: Path, target: Path, expected_sha256: str | None = None) -> str:
    safe = validate_config_path(target)
    backup = Path(backup).expanduser()
    if backup.parent.name.casefold() != "backups":
        raise SafetyError("Choose a backup from the FrameForge backups directory.")
    safe_backup_dir = _validate_backup_directory(backup.parent)
    backup = safe_backup_dir / backup.name
    expected_prefix = f"frameforge-{safe.stem.casefold()}-"
    if not backup.name.casefold().startswith(expected_prefix) or not backup.name.casefold().endswith(".ini.bak"):
        raise SafetyError("The backup is missing or is not a FrameForge Skyrim backup.")
    if not backup.exists() or _is_reparse_or_link(backup) or not backup.is_file():
        raise SafetyError("The backup is missing or is not a regular file.")
    payload = backup.read_bytes()
    actual_sha256 = sha256(payload)
    if expected_sha256 is not None and actual_sha256.casefold() != expected_sha256.casefold():
        raise SafetyError("The backup no longer matches its saved SHA-256; restore was stopped.")
    from .apply import validate_ini_payload
    validate_ini_payload(payload, safe.name)
    atomic_replace(safe, payload)
    return actual_sha256
