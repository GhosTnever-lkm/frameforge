"""Build validated commands for timed PresentMon captures."""

from __future__ import annotations

import re
from pathlib import Path


CAPTURE_DURATIONS_SECONDS = (30, 60, 120, 300)
_PROCESS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}\.exe$", re.IGNORECASE)


def build_presentmon_arguments(
    executable: Path,
    output_file: Path,
    process_name: str,
    duration_seconds: int,
) -> list[str]:
    """Build an argv list without shell parsing or command-string interpolation."""
    tool = Path(executable)
    if not tool.is_file():
        raise ValueError("Выбери существующий PresentMon.exe из официальной сборки.")
    name = process_name.strip()
    if not _PROCESS_NAME.fullmatch(name):
        raise ValueError("Укажи имя процесса игры в формате game.exe, без пути и параметров запуска.")
    if isinstance(duration_seconds, bool) or duration_seconds not in CAPTURE_DURATIONS_SECONDS:
        raise ValueError("Продолжительность должна быть 30, 60, 120 или 300 секунд.")
    destination = Path(output_file)
    if destination.suffix.casefold() != ".csv":
        raise ValueError("Файл захвата должен иметь расширение .csv.")
    return [
        "--process_name", name,
        "--output_file", str(destination),
        "--timed", str(duration_seconds),
        "--terminate_after_timed",
        "--no_console_stats",
    ]
