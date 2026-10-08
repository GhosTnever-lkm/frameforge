from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .benchmark import Benchmark, FRAME_TIME_BUCKET_EDGES_MS, MAX_SAMPLES

SCHEMA_VERSION = 1
MAX_HISTORY = 100
MAX_STORE_BYTES = 2 * 1024 * 1024
_FIELDS = {
    "name", "sample_count", "average_fps", "one_percent_low_fps",
    "p99_frame_time_ms", "median_frame_time_ms", "min_frame_time_ms",
    "max_frame_time_ms", "frame_time_buckets",
}


def _validate_benchmark(value: object) -> Benchmark:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("Запись истории имеет неверный набор полей.")
    name = value["name"]
    count = value["sample_count"]
    if not isinstance(name, str) or not name or len(name) > 255 or "/" in name or "\\" in name:
        raise ValueError("Имя замера в истории некорректно.")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_SAMPLES:
        raise ValueError("Количество кадров в истории некорректно.")
    numeric_fields = _FIELDS - {"name", "sample_count", "frame_time_buckets"}
    for field in numeric_fields:
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item <= 0:
            raise ValueError(f"Поле {field} в истории некорректно.")
    buckets = value["frame_time_buckets"]
    if not isinstance(buckets, (list, tuple)) or len(buckets) != len(FRAME_TIME_BUCKET_EDGES_MS) + 1:
        raise ValueError("Распределение кадров в истории некорректно.")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in buckets):
        raise ValueError("Количество кадров в диапазонах некорректно.")
    if sum(buckets) != count:
        raise ValueError("Сумма диапазонов не совпадает с количеством кадров.")
    if value["min_frame_time_ms"] > 10_000 or value["max_frame_time_ms"] > 10_000:
        raise ValueError("Время кадра в истории превышает допустимые 10 000 мс.")
    if value["average_fps"] > 1000 or value["one_percent_low_fps"] > 1000:
        raise ValueError("FPS в истории превышает допустимые 1000.")
    if value["min_frame_time_ms"] > value["median_frame_time_ms"] or value["median_frame_time_ms"] > value["max_frame_time_ms"]:
        raise ValueError("Порядок времени кадров в истории некорректен.")
    if value["median_frame_time_ms"] > value["p99_frame_time_ms"] or value["p99_frame_time_ms"] > value["max_frame_time_ms"]:
        raise ValueError("Перцентили времени кадров в истории некорректны.")
    return Benchmark(
        name=name,
        sample_count=count,
        average_fps=float(value["average_fps"]),
        one_percent_low_fps=float(value["one_percent_low_fps"]),
        p99_frame_time_ms=float(value["p99_frame_time_ms"]),
        median_frame_time_ms=float(value["median_frame_time_ms"]),
        min_frame_time_ms=float(value["min_frame_time_ms"]),
        max_frame_time_ms=float(value["max_frame_time_ms"]),
        frame_time_buckets=tuple(buckets),
    )


class BenchmarkStore:
    """Versioned local history containing aggregate results only."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[Benchmark]:
        try:
            if not self.path.exists():
                return []
            if self.path.stat().st_size > MAX_STORE_BYTES:
                raise ValueError("Файл истории бенчмарков превышает безопасный размер 2 МБ.")
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Не удалось прочитать локальную историю бенчмарков.") from exc
        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION or set(document) != {"schema_version", "runs"}:
            raise ValueError("Версия или структура локальной истории бенчмарков не поддерживается.")
        rows = document["runs"]
        if not isinstance(rows, list) or len(rows) > MAX_HISTORY:
            raise ValueError("Список локальных замеров некорректен.")
        return [_validate_benchmark(row) for row in rows]

    def save(self, runs: list[Benchmark]) -> None:
        clean = [_validate_benchmark(asdict(run) | {"frame_time_buckets": list(run.frame_time_buckets)}) for run in runs[-MAX_HISTORY:]]
        document = {
            "schema_version": SCHEMA_VERSION,
            "runs": [asdict(run) | {"frame_time_buckets": list(run.frame_time_buckets)} for run in clean],
        }
        payload = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        if len(payload) > MAX_STORE_BYTES:
            raise ValueError("Локальная история бенчмарков превысила безопасный размер 2 МБ.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".benchmarks-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except OSError:
                pass
