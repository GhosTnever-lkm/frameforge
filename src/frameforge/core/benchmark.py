from __future__ import annotations

import csv
import io
import math
import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from ..catalog import GUIDE_CHECKLIST_LABELS

MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 5_000_000
MAX_CHANGE_NOTE_CHARS = 160
FRAME_TIME_COLUMN = "frame_time_ms"
METRIC_KINDS = {"generic", "cpu-presented", "displayed"}
METRIC_LABELS = {
    "generic": "Frametime (источник не указан)",
    "cpu-presented": "CPU presented (MsBetweenPresents)",
    "displayed": "Displayed (MsBetweenDisplayChange)",
}
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
    metric_kind: str = "generic"
    change_note: str = ""
    setting_key: str = ""
    setting_value: int | None = None
    manual_changes: tuple[str, ...] = ()


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def analyze_frame_times(
    name: str,
    frame_times_ms: list[float],
    *,
    game: str = "",
    scene: str = "",
    metric_kind: str = "generic",
    change_note: str = "",
    setting_key: str = "",
    setting_value: int | None = None,
    manual_changes: tuple[str, ...] = (),
) -> Benchmark:
    if not frame_times_ms:
        raise ValueError("CSV must contain at least one frame time.")
    if len(frame_times_ms) > MAX_SAMPLES:
        raise ValueError(f"CSV contains more than {MAX_SAMPLES:,} frame samples.")
    if any(not math.isfinite(value) or value <= 0 or value > 10_000 for value in frame_times_ms):
        raise ValueError("Frame times must be finite values from 0 to 10,000 ms.")
    if not isinstance(metric_kind, str) or metric_kind not in METRIC_KINDS:
        raise ValueError("Неизвестный тип метрики frametime.")
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
        metric_kind=metric_kind,
        change_note=change_note,
        setting_key=setting_key,
        setting_value=setting_value,
        manual_changes=manual_changes,
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


def load_benchmark_csv(path: Path) -> tuple[Benchmark, tuple[str, ...]]:
    """Import generic frame_time_ms or PresentMon per-frame CSV, retaining metric semantics."""
    source = Path(path)
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError(f"CSV exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB safety limit.")
    text = source.read_text(encoding="utf-8-sig")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    candidates = []
    for delimiter in (",", ";", "\t"):
        fields = next(csv.reader([first_line], delimiter=delimiter), [])
        normalized = {field.strip().casefold() for field in fields}
        if FRAME_TIME_COLUMN in normalized or "msbetweendisplaychange" in normalized or "msbetweenpresents" in normalized:
            candidates.append((delimiter, fields, normalized))
    if not candidates:
        raise ValueError("CSV must contain frame_time_ms, MsBetweenDisplayChange, or MsBetweenPresents.")
    delimiter, headers, normalized = candidates[0]
    lookup = {field.strip().casefold(): index for index, field in enumerate(headers)}
    if len(lookup) != len(headers):
        raise ValueError("CSV содержит повторяющиеся заголовки; нельзя безопасно выбрать колонку frametime.")
    if FRAME_TIME_COLUMN.casefold() in lookup:
        metric_kind, column = "generic", FRAME_TIME_COLUMN.casefold()
    elif "msbetweendisplaychange" in lookup:
        metric_kind, column = "displayed", "msbetweendisplaychange"
    else:
        metric_kind, column = "cpu-presented", "msbetweenpresents"
    frame_type_index = lookup.get("frametype")
    warnings: list[str] = []
    if metric_kind == "cpu-presented" and frame_type_index is not None:
        warnings.append("Для CPU presented исключены строки с FrameType, отличным от Application.")
    elif metric_kind == "displayed" and frame_type_index is None:
        warnings.append("В CSV нет FrameType: источник не позволяет отметить, какие отображённые кадры были сгенерированы.")
    elif metric_kind == "cpu-presented" and frame_type_index is None:
        warnings.append("В CSV нет FrameType: невозможно отметить generated-строки; при frame generation CPU-presented не равно displayed.")
    elif metric_kind == "displayed":
        warnings.append("Displayed intervals могут включать сгенерированные кадры; эта метрика отличается от CPU presented.")
    elif metric_kind == "cpu-presented":
        warnings.append("PresentMon не предоставил MsBetweenDisplayChange; импортирован CPU presented, он может отличаться от отображённого frametime.")
    samples: list[float] = []
    dropped_invalid = 0
    dropped_malformed = 0
    dropped_type = 0
    data_rows = 0
    saw_non_application = False
    for line_number, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter), start=1):
        if line_number == 1:
            continue
        data_rows += 1
        if len(row) != len(headers):
            dropped_malformed += 1
            continue
        if frame_type_index is not None:
            frame_type = row[frame_type_index].strip().casefold() if len(row) > frame_type_index else ""
            normalized_frame_type = frame_type.replace("-", "_").replace(" ", "_")
            if normalized_frame_type not in {"", "application"}:
                saw_non_application = True
            if metric_kind == "cpu-presented" and frame_type != "application":
                dropped_type += 1
                continue
            if metric_kind == "displayed" and normalized_frame_type not in {"application", "intel_xefg", "intel_xess_fg", "amd_afmf"}:
                dropped_type += 1
                continue
        raw = row[lookup[column]].strip()
        if not raw or raw.casefold() in {"na", "n/a", "-"}:
            dropped_invalid += 1
            continue
        try:
            value = float(raw)
        except ValueError:
            # Some regional spreadsheet exports use decimal comma with semicolon/tab separators.
            if delimiter != "," and raw.count(",") == 1 and "." not in raw:
                try:
                    value = float(raw.replace(",", "."))
                except ValueError:
                    dropped_invalid += 1
                    continue
            else:
                dropped_invalid += 1
                continue
        if not math.isfinite(value) or value <= 0 or value > 10_000:
            dropped_invalid += 1
            continue
        samples.append(value)
        if len(samples) > MAX_SAMPLES:
            raise ValueError(f"CSV contains more than {MAX_SAMPLES:,} frame samples.")
    if dropped_invalid:
        share = dropped_invalid / data_rows * 100 if data_rows else 0.0
        warnings.append(
            f"Пропущено некорректных, пустых или отсутствующих значений: {dropped_invalid} "
            f"из {data_rows} строк ({share:.1f}%)."
        )
    if dropped_malformed:
        share = dropped_malformed / data_rows * 100 if data_rows else 0.0
        warnings.append(
            f"Пропущено строк с неверным числом полей: {dropped_malformed} "
            f"из {data_rows} строк ({share:.1f}%)."
        )
    if dropped_type:
        share = dropped_type / data_rows * 100 if data_rows else 0.0
        warnings.append(
            f"Пропущено строк с неизвестным или неподходящим FrameType: {dropped_type} "
            f"из {data_rows} строк ({share:.1f}%)."
        )
    if metric_kind == "generic" and saw_non_application:
        warnings.append("В CSV есть не-Application FrameType, но generic-колонка frame_time_ms не позволяет определить их frametime; строки не отфильтрованы автоматически.")
    if not samples:
        raise ValueError("В выбранном столбце CSV нет пригодных значений frametime.")
    return analyze_frame_times(source.name, samples, metric_kind=metric_kind), tuple(warnings)


def compare_benchmarks(before: Benchmark, after: Benchmark) -> str:
    fps_delta = after.average_fps - before.average_fps
    fps_percent = (fps_delta / before.average_fps * 100) if before.average_fps else 0.0
    low_delta = after.one_percent_low_fps - before.one_percent_low_fps
    p99_delta = after.p99_frame_time_ms - before.p99_frame_time_ms
    sample_delta = abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count)
    sample_warning = "⚠ Число кадров отличается более чем на 5%; сравнение распределений менее надёжно.\n\n" if sample_delta > 0.05 else ""
    context_warning = ""
    metric_warning = ""
    notes = ""
    if before.change_note or after.change_note:
        notes = (
            "Заметки к прогонам (введены вручную; это контекст, не доказательство причины):\n"
            f"  A: {before.change_note or 'не указано'}\n"
            f"  B: {after.change_note or 'не указано'}\n\n"
        )
    settings = ""
    if before.setting_key or after.setting_key:
        settings = (
            "Снимок разрешённой настройки Skyrim (только контекст; путь к INI не сохранён):\n"
            f"  A: {before.setting_key + '=' + str(before.setting_value) if before.setting_key else 'не снят'}\n"
            f"  B: {after.setting_key + '=' + str(after.setting_value) if after.setting_key else 'не снят'}\n\n"
        )
    checklist = ""
    if before.manual_changes or after.manual_changes:
        before_items = set(before.manual_changes)
        after_items = set(after.manual_changes)

        def labels(items):
            return ", ".join(GUIDE_CHECKLIST_LABELS.get(item, item) for item in items) or "не отмечено"

        if before.game != after.game:
            checklist = (
                "Отмеченные вручную пункты игрового чек-листа (контекст, не доказательство причины):\n"
                f"  A — {before.game or 'игра не указана'}: {labels(before.manual_changes)}\n"
                f"  B — {after.game or 'игра не указана'}: {labels(after.manual_changes)}\n"
                "  Списки относятся к разным играм и не сопоставляются.\n\n"
            )
        else:
            only_a = before_items - after_items
            only_b = after_items - before_items
            checklist = (
                "Отмеченные вручную пункты игрового чек-листа (контекст, не доказательство причины):\n"
                f"  A: {labels(before.manual_changes)}\n"
                f"  B: {labels(after.manual_changes)}\n"
                f"  Только A: {labels(sorted(only_a))}\n"
                f"  Только B: {labels(sorted(only_b))}\n\n"
            )
    if before.metric_kind != after.metric_kind:
        metric_warning = (
            f"⚠ Типы frametime различаются: {METRIC_LABELS.get(before.metric_kind, before.metric_kind)} → "
            f"{METRIC_LABELS.get(after.metric_kind, after.metric_kind)}. Числа A/B не следует считать прямым сравнением.\n\n"
        )
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
        f"Метрика A: {METRIC_LABELS.get(before.metric_kind, before.metric_kind)}\n"
        f"Метрика B: {METRIC_LABELS.get(after.metric_kind, after.metric_kind)}\n"
        + notes
        + settings
        + checklist
        + metric_warning
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
    writer.writerow(("frame_time_metric_kind", before.metric_kind, after.metric_kind, "" if before.metric_kind == after.metric_kind else "different", "label"))
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
            "schema_version": 2,
            "baseline_a": {
                "frame_time_metric_kind": before.metric_kind,
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
                "frame_time_metric_kind": after.metric_kind,
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
