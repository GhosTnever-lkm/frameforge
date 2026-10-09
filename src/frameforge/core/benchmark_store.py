from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..catalog import GUIDE_CHECKLISTS
from .benchmark import Benchmark, FRAME_BUDGET_FPS_PRESETS, FRAME_TIME_BUCKET_EDGES_MS, MAX_CHANGE_NOTE_CHARS, MAX_SAMPLES, METRIC_KINDS, FrameTimingSummary, PRESENTMON_FRAME_TIMING_COLUMNS
from .profiles import TUNING_PROFILES

SCHEMA_VERSION = 8
LEGACY_SCHEMA_VERSION = 1
LABEL_SCHEMA_VERSION = 2
METRIC_SCHEMA_VERSION = 3
NOTE_SCHEMA_VERSION = 4
SETTING_SNAPSHOT_SCHEMA_VERSION = 5
FRAME_TIMING_SCHEMA_VERSION = 7
FRAME_BUDGET_SCHEMA_VERSION = 8
ALLOWED_SETTING_KEYS = frozenset(profile.setting for profile in TUNING_PROFILES)
MAX_HISTORY = 100
MAX_STORE_BYTES = 2 * 1024 * 1024
_FIELDS = {
    "name", "game", "scene", "metric_kind", "change_note", "setting_key", "setting_value", "manual_changes", "sample_count", "average_fps", "one_percent_low_fps",
    "p99_frame_time_ms", "median_frame_time_ms", "min_frame_time_ms", "frame_timing", "frame_budget_counts",
    "max_frame_time_ms", "frame_time_buckets",
}


def _validate_benchmark(value: object) -> Benchmark:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("Запись истории имеет неверный набор полей.")
    name = value["name"]
    game = value["game"]
    scene = value["scene"]
    metric_kind = value["metric_kind"]
    change_note = value["change_note"]
    setting_key = value["setting_key"]
    setting_value = value["setting_value"]
    manual_changes = value["manual_changes"]
    frame_timing = value["frame_timing"]
    frame_budget_counts = value["frame_budget_counts"]
    count = value["sample_count"]
    if not isinstance(name, str) or not name or len(name) > 255 or "/" in name or "\\" in name:
        raise ValueError("Имя замера в истории некорректно.")
    if not isinstance(game, str) or len(game) > 100 or not isinstance(scene, str) or len(scene) > 120:
        raise ValueError("Метки игры или сцены в истории некорректны.")
    if not isinstance(metric_kind, str) or metric_kind not in METRIC_KINDS:
        raise ValueError("Тип метрики в истории некорректен.")
    if (
        not isinstance(change_note, str)
        or len(change_note) > MAX_CHANGE_NOTE_CHARS
        or any(ord(character) < 32 for character in change_note)
    ):
        raise ValueError("Заметка к замеру в истории некорректна.")
    if not isinstance(setting_key, str):
        raise ValueError("Снимок настройки в истории некорректен.")
    if setting_key == "":
        if setting_value is not None:
            raise ValueError("Снимок настройки в истории некорректен.")
    elif (
        setting_key not in ALLOWED_SETTING_KEYS
        or isinstance(setting_value, bool)
        or not isinstance(setting_value, int)
        or not 0 <= setting_value <= 100_000
    ):
        raise ValueError("Снимок настройки в истории некорректен.")
    if (
        not isinstance(manual_changes, (list, tuple))
        or any(not isinstance(item, str) for item in manual_changes)
        or len(set(manual_changes)) != len(manual_changes)
        or not set(manual_changes).issubset({item_id for item_id, _ in GUIDE_CHECKLISTS.get(game, ())})
    ):
        raise ValueError("Отметки игрового чек-листа в истории некорректны.")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_SAMPLES:
        raise ValueError("Количество кадров в истории некорректно.")
    if not isinstance(frame_timing, (list, tuple)):
        raise ValueError("Дополнительные счётчики времени кадра в истории некорректны.")
    allowed_frame_timing = set(PRESENTMON_FRAME_TIMING_COLUMNS)
    summaries: list[FrameTimingSummary] = []
    seen_metrics: set[str] = set()
    for item in frame_timing:
        if not isinstance(item, dict) or set(item) != {"metric_id", "valid_count", "median_ms", "p95_ms"}:
            raise ValueError("Дополнительный счётчик времени кадра в истории некорректен.")
        metric_id = item["metric_id"]
        valid_count = item["valid_count"]
        median_ms = item["median_ms"]
        p95_ms = item["p95_ms"]
        if not isinstance(metric_id, str) or metric_id not in allowed_frame_timing or metric_id in seen_metrics:
            raise ValueError("Имя дополнительного счётчика времени кадра в истории некорректно.")
        if isinstance(valid_count, bool) or not isinstance(valid_count, int) or not 0 <= valid_count <= count:
            raise ValueError("Количество строк дополнительного счётчика в истории некорректно.")
        if valid_count == 0:
            if median_ms is not None or p95_ms is not None:
                raise ValueError("Пустой дополнительный счётчик не должен иметь числовые сводки.")
        elif (
            isinstance(median_ms, bool) or not isinstance(median_ms, (int, float)) or not math.isfinite(median_ms)
            or isinstance(p95_ms, bool) or not isinstance(p95_ms, (int, float)) or not math.isfinite(p95_ms)
            or not 0 <= median_ms <= p95_ms <= 10_000
        ):
            raise ValueError("Значения дополнительного счётчика времени кадра в истории некорректны.")
        seen_metrics.add(metric_id)
        summaries.append(FrameTimingSummary(metric_id, valid_count, median_ms, p95_ms))
    if frame_budget_counts is not None:
        if (
            not isinstance(frame_budget_counts, (list, tuple))
            or len(frame_budget_counts) != len(FRAME_BUDGET_FPS_PRESETS)
            or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= count for item in frame_budget_counts)
            or any(left < right for left, right in zip(frame_budget_counts, frame_budget_counts[1:]))
        ):
            raise ValueError("Счётчики Frame budget в истории некорректны.")
    numeric_fields = _FIELDS - {"name", "game", "scene", "metric_kind", "change_note", "setting_key", "setting_value", "manual_changes", "frame_timing", "frame_budget_counts", "sample_count", "frame_time_buckets"}
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
        game=game,
        scene=scene,
        metric_kind=metric_kind,
        change_note=change_note,
        setting_key=setting_key,
        setting_value=setting_value,
        manual_changes=tuple(manual_changes),
        sample_count=count,
        average_fps=float(value["average_fps"]),
        one_percent_low_fps=float(value["one_percent_low_fps"]),
        p99_frame_time_ms=float(value["p99_frame_time_ms"]),
        median_frame_time_ms=float(value["median_frame_time_ms"]),
        min_frame_time_ms=float(value["min_frame_time_ms"]),
        max_frame_time_ms=float(value["max_frame_time_ms"]),
        frame_time_buckets=tuple(buckets),
        frame_timing=tuple(summaries),
        frame_budget_counts=None if frame_budget_counts is None else tuple(frame_budget_counts),
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
        if not isinstance(document, dict) or set(document) != {"schema_version", "runs"}:
            raise ValueError("Версия или структура локальной истории бенчмарков не поддерживается.")
        version = document["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version not in tuple(range(LEGACY_SCHEMA_VERSION, SCHEMA_VERSION + 1)):
            raise ValueError("Версия или структура локальной истории бенчмарков не поддерживается.")
        rows = document["runs"]
        if not isinstance(rows, list) or len(rows) > MAX_HISTORY:
            raise ValueError("Список локальных замеров некорректен.")
        if version < SCHEMA_VERSION:
            migrated = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Запись истории имеет неверный набор полей.")
                base = dict(row)
                if version in (LEGACY_SCHEMA_VERSION, LABEL_SCHEMA_VERSION):
                    base["metric_kind"] = "generic"
                if version == LEGACY_SCHEMA_VERSION:
                    base.update({"game": "", "scene": ""})
                if version < SCHEMA_VERSION:
                    base.setdefault("change_note", "")
                    base.setdefault("setting_key", "")
                    base.setdefault("setting_value", None)
                    base.setdefault("manual_changes", [])
                if version < FRAME_TIMING_SCHEMA_VERSION:
                    base.setdefault("frame_timing", [])
                if version < FRAME_BUDGET_SCHEMA_VERSION:
                    # Old aggregates cannot be reprocessed: their raw frame times were never stored.
                    base["frame_budget_counts"] = None
                migrated.append(_validate_benchmark(base))
            return migrated
        return [_validate_benchmark(row) for row in rows]

    def save(self, runs: list[Benchmark]) -> None:
        clean = [_validate_benchmark(asdict(run) | {"frame_time_buckets": list(run.frame_time_buckets)}) for run in runs[-MAX_HISTORY:]]
        stored_runs = [
            asdict(run)
            | {"frame_time_buckets": list(run.frame_time_buckets)}
            | {"frame_budget_counts": None if run.frame_budget_counts is None else list(run.frame_budget_counts)}
            for run in clean
        ]
        document = {
            "schema_version": SCHEMA_VERSION,
            "runs": stored_runs,
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
