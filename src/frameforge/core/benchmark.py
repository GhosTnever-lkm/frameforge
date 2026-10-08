from __future__ import annotations

import csv
import io
import math
import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 5_000_000
FRAME_TIME_COLUMN = "frame_time_ms"
FRAME_TIME_BUCKET_EDGES_MS = (
    1000.0 / 120.0,
    1000.0 / 60.0,
    1000.0 / 30.0,
    1000.0 / 20.0,
    1000.0 / 10.0,
)


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
    game: str = ""
    scene: str = ""


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def analyze_frame_times(name: str, frame_times_ms: list[float], *, game: str = "", scene: str = "") -> Benchmark:
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
        game=game,
        scene=scene,
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
    sample_delta = abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count)
    sample_warning = "⚠ Число кадров отличается более чем на 5%; сравнение распределений менее надёжно.\n\n" if sample_delta > 0.05 else ""
    context_warning = ""
    if before.game != after.game or before.scene != after.scene:
        context_warning = "⚠ Метки игры или сцены различаются; эти прогоны могут быть несопоставимы.\n\n"
    elif not before.game or not before.scene:
        context_warning = "ℹ Игра или сцена не указаны; FrameForge не может проверить сопоставимость условий.\n\n"
    bucket_rows = []
    for label, a_count, b_count in zip(
        ("< 8.333 мс", "8.333–16.667 мс", "16.667–33.333 мс", "33.333–50 мс", "50–100 мс", "≥ 100 мс"),
        before.frame_time_buckets,
        after.frame_time_buckets,
    ):
        a_share = 100 * a_count / before.sample_count
        b_share = 100 * b_count / after.sample_count
        bucket_rows.append(f"  {label}: A {a_share:.1f}% → B {b_share:.1f}% ({b_share - a_share:+.1f} п.п.)")
    return (
        "Сравниваются две выборки; это само по себе не доказывает эффект настройки.\n"
        + context_warning
        + f"Baseline (A): {before.name} ({before.sample_count:,} кадров)\n"
        f"  Средний FPS: {before.average_fps:.1f} · 1% low: {before.one_percent_low_fps:.1f} · p99 frametime: {before.p99_frame_time_ms:.2f} ms\n\n"
        f"Variant (B): {after.name} ({after.sample_count:,} кадров)\n"
        f"  Средний FPS: {after.average_fps:.1f} · 1% low: {after.one_percent_low_fps:.1f} · p99 frametime: {after.p99_frame_time_ms:.2f} ms\n\n"
        + sample_warning
        + "Доли кадров по времени кадра (меньше = короче кадр):\n"
        + "\n".join(bucket_rows)
        + "\n\n"
        f"Разница среднего FPS: {fps_delta:+.1f} ({fps_percent:+.1f}%)\n"
        f"Разница 1% low: {low_delta:+.1f} FPS\n"
        f"Разница p99 frametime: {p99_delta:+.2f} ms ({'хуже' if p99_delta > 0 else 'лучше' if p99_delta < 0 else 'без изменений'})\n\n"
        "Разница между прогонами сама по себе не доказывает причину. Повтори оба варианта в одинаковой сцене, разрешении, пресете и условиях; при малом числе кадров результат менее устойчив."
    )


def export_comparison_csv(before: Benchmark, after: Benchmark) -> str:
    """Export aggregate-only comparison rows; never include file paths or raw frames."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("metric", "baseline_a", "variant_b", "delta_b_minus_a", "unit"))
    rows = (
        ("sample_count", before.sample_count, after.sample_count, after.sample_count - before.sample_count, "frames"),
        ("average_fps", before.average_fps, after.average_fps, after.average_fps - before.average_fps, "fps"),
        ("one_percent_low_fps", before.one_percent_low_fps, after.one_percent_low_fps, after.one_percent_low_fps - before.one_percent_low_fps, "fps"),
        ("median_frame_time_ms", before.median_frame_time_ms, after.median_frame_time_ms, after.median_frame_time_ms - before.median_frame_time_ms, "ms"),
        ("p99_frame_time_ms", before.p99_frame_time_ms, after.p99_frame_time_ms, after.p99_frame_time_ms - before.p99_frame_time_ms, "ms"),
        ("min_frame_time_ms", before.min_frame_time_ms, after.min_frame_time_ms, after.min_frame_time_ms - before.min_frame_time_ms, "ms"),
        ("max_frame_time_ms", before.max_frame_time_ms, after.max_frame_time_ms, after.max_frame_time_ms - before.max_frame_time_ms, "ms"),
    )
    writer.writerows(rows)
    for index, (a_count, b_count) in enumerate(zip(before.frame_time_buckets, after.frame_time_buckets)):
        a_share = a_count / before.sample_count
        b_share = b_count / after.sample_count
        writer.writerow((f"frame_time_bucket_{index}", a_count, b_count, b_count - a_count, "frames"))
        writer.writerow((f"frame_time_bucket_{index}_share", a_share, b_share, b_share - a_share, "fraction"))
    writer.writerow(("sample_count_delta_ratio", "", "", abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count), "fraction"))
    writer.writerow(("causal_claim", "", "", "not_established_by_two_runs", "note"))
    return output.getvalue()


def export_comparison_json(before: Benchmark, after: Benchmark) -> str:
    """Export machine-readable aggregate comparison without source names or paths."""
    return json.dumps(
        {
            "schema_version": 1,
            "baseline_a": {
                "sample_count": before.sample_count,
                "average_fps": before.average_fps,
                "one_percent_low_fps": before.one_percent_low_fps,
                "median_frame_time_ms": before.median_frame_time_ms,
                "p99_frame_time_ms": before.p99_frame_time_ms,
                "min_frame_time_ms": before.min_frame_time_ms,
                "max_frame_time_ms": before.max_frame_time_ms,
                "frame_time_bucket_counts": list(before.frame_time_buckets),
            },
            "variant_b": {
                "sample_count": after.sample_count,
                "average_fps": after.average_fps,
                "one_percent_low_fps": after.one_percent_low_fps,
                "median_frame_time_ms": after.median_frame_time_ms,
                "p99_frame_time_ms": after.p99_frame_time_ms,
                "min_frame_time_ms": after.min_frame_time_ms,
                "max_frame_time_ms": after.max_frame_time_ms,
                "frame_time_bucket_counts": list(after.frame_time_buckets),
            },
            "sample_count_delta_ratio": abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count),
            "causal_claim": "not_established_by_two_runs",
        },
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    ) + "\n"
