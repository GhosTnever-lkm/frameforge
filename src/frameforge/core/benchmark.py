from __future__ import annotations

import csv
import io
import math
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 5_000_000
FRAME_TIME_COLUMN = "frame_time_ms"
FRAME_TIME_BUCKET_EDGES_MS = (8.33, 16.67, 33.33, 50.0, 100.0)


@dataclass(frozen=True)
class Benchmark:
    name: str
    sample_count: int
    average_fps: float
    one_percent_low_fps: float
    p99_frame_time_ms: float
    median_frame_time_ms: float
    min_frame_time_ms: float
    max_frame_time_ms: float
    frame_time_buckets: tuple[int, ...]


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def analyze_frame_times(name: str, frame_times_ms: list[float]) -> Benchmark:
    if not frame_times_ms:
        raise ValueError("CSV must contain at least one frame time.")
    if len(frame_times_ms) > MAX_SAMPLES:
        raise ValueError(f"CSV contains more than {MAX_SAMPLES:,} frame samples.")
    if any(not math.isfinite(value) or value <= 0 or value > 10_000 for value in frame_times_ms):
        raise ValueError("Frame times must be finite values from 0 to 10,000 ms.")
    ordered = sorted(frame_times_ms)
    buckets = [0] * (len(FRAME_TIME_BUCKET_EDGES_MS) + 1)
    for value in ordered:
        buckets[bisect_right(FRAME_TIME_BUCKET_EDGES_MS, value)] += 1
    slow_count = max(1, math.ceil(len(ordered) * 0.01))
    slow_average = sum(ordered[-slow_count:]) / slow_count
    mean = sum(ordered) / len(ordered)
    return Benchmark(
        name=name,
        sample_count=len(ordered),
        average_fps=1000 / mean,
        one_percent_low_fps=1000 / slow_average,
        p99_frame_time_ms=_nearest_rank(ordered, 0.99),
        median_frame_time_ms=_nearest_rank(ordered, 0.5),
        min_frame_time_ms=ordered[0],
        max_frame_time_ms=ordered[-1],
        frame_time_buckets=tuple(buckets),
    )


def load_frame_time_csv(path: Path) -> Benchmark:
    source = Path(path)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError(f"CSV exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB safety limit.")
    text = source.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None or FRAME_TIME_COLUMN not in reader.fieldnames:
        raise ValueError(f"CSV must contain a '{FRAME_TIME_COLUMN}' column with frame durations in milliseconds.")
    samples: list[float] = []
    for line_number, row in enumerate(reader, start=2):
        raw = (row.get(FRAME_TIME_COLUMN) or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid frame time on CSV line {line_number}.") from exc
        if not math.isfinite(value) or value <= 0 or value > 10_000:
            raise ValueError(f"Frame time on CSV line {line_number} must be between 0 and 10,000 ms.")
        samples.append(value)
        if len(samples) > MAX_SAMPLES:
            raise ValueError(f"CSV contains more than {MAX_SAMPLES:,} frame samples.")
    return analyze_frame_times(source.name, samples)


def compare_benchmarks(before: Benchmark, after: Benchmark) -> str:
    fps_delta = after.average_fps - before.average_fps
    fps_percent = (fps_delta / before.average_fps * 100) if before.average_fps else 0.0
    low_delta = after.one_percent_low_fps - before.one_percent_low_fps
    p99_delta = after.p99_frame_time_ms - before.p99_frame_time_ms
    return (
        f"До: {before.name} ({before.sample_count:,} кадров)\n"
        f"  Средний FPS: {before.average_fps:.1f} · 1% low: {before.one_percent_low_fps:.1f} · p99 frametime: {before.p99_frame_time_ms:.2f} ms\n\n"
        f"После: {after.name} ({after.sample_count:,} кадров)\n"
        f"  Средний FPS: {after.average_fps:.1f} · 1% low: {after.one_percent_low_fps:.1f} · p99 frametime: {after.p99_frame_time_ms:.2f} ms\n\n"
        f"Разница среднего FPS: {fps_delta:+.1f} ({fps_percent:+.1f}%)\n"
        f"Разница 1% low: {low_delta:+.1f} FPS\n"
        f"Разница p99 frametime: {p99_delta:+.2f} ms ({'хуже' if p99_delta > 0 else 'лучше' if p99_delta < 0 else 'без изменений'})\n\n"
        "Сравнение имеет смысл только при одинаковой сцене, разрешении, пресете и условиях запуска."
    )
