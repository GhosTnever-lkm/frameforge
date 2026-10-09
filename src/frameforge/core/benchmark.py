from __future__ import annotations

import csv
import io
import math
import json
import statistics
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
FRAME_BUDGET_FPS_PRESETS = (30, 60, 90, 120, 144, 165, 240)


@dataclass(frozen=True)
class FrameTimingSummary:
    metric_id: str
    valid_count: int
    median_ms: float | None
    p95_ms: float | None


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
    frame_timing: tuple[FrameTimingSummary, ...] = ()
    # Counts only; raw per-frame samples are deliberately discarded after import.
    # None means this run predates frame-budget summaries.
    frame_budget_counts: tuple[int, ...] | None = None
    # A pinned reference stays in local history when older ordinary runs are evicted.
    is_reference: bool = False


def benchmark_import_fingerprint(run: Benchmark) -> tuple[object, ...] | None:
    """Return a conservative aggregate-only duplicate hint, or None for tiny runs.

    Equal fingerprints are only a probable duplicate: distinct captures can have
    identical aggregates. The caller must let the user keep either run.
    """
    if run.sample_count < 30:
        return None
    return (
        run.game,
        run.scene,
        run.metric_kind,
        run.sample_count,
        run.average_fps,
        run.one_percent_low_fps,
        run.p99_frame_time_ms,
        run.median_frame_time_ms,
        run.min_frame_time_ms,
        run.max_frame_time_ms,
        run.frame_time_buckets,
        run.frame_timing,
        run.frame_budget_counts,
        run.change_note,
        run.setting_key,
        run.setting_value,
        run.manual_changes,
    )


PRESENTMON_FRAME_TIMING_COLUMNS = {
    "cpu_busy": ("mscpubusy", "cpubusy"),
    "gpu_time": ("msgputime", "gputime"),
    "gpu_busy": ("msgpubusy", "gpubusy"),
}
FRAME_TIMING_LABELS = {
    "cpu_busy": "CPU busy",
    "gpu_time": "GPU time",
    "gpu_busy": "GPU busy",
}


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def frame_time_spread_ms(run: Benchmark) -> float:
    """Return p99 minus median as a descriptive within-run tail spread."""
    return max(0.0, run.p99_frame_time_ms - run.median_frame_time_ms)


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
    frame_timing: tuple[FrameTimingSummary, ...] = (),
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
    frame_budget_counts = tuple(bisect_right(ordered, 1000.0 / fps) for fps in FRAME_BUDGET_FPS_PRESETS)
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
        frame_timing=frame_timing,
        sample_count=len(ordered),
        average_fps=1000 / mean,
        one_percent_low_fps=1000 / slow_average,
        p99_frame_time_ms=_nearest_rank(ordered, 0.99),
        median_frame_time_ms=_nearest_rank(ordered, 0.5),
        min_frame_time_ms=ordered[0],
        max_frame_time_ms=ordered[-1],
        frame_time_buckets=tuple(buckets),
        frame_budget_counts=frame_budget_counts,
    )


def frame_budget_ms_from_fps(target_fps: int) -> float:
    """Return the exact threshold in milliseconds for a supported FPS preset."""
    if isinstance(target_fps, bool) or not isinstance(target_fps, int) or target_fps not in FRAME_BUDGET_FPS_PRESETS:
        raise ValueError("Выбери один из поддерживаемых бюджетов FPS.")
    return 1000.0 / target_fps


def format_budget_threshold_label(target_fps: int) -> str:
    """Show the exact FPS fraction and mark its finite decimal as approximate."""
    threshold_ms = frame_budget_ms_from_fps(target_fps)
    approx_ms = f"{threshold_ms:.6f}".rstrip("0").rstrip(".")
    return f"≤ 1000/{target_fps} мс (≈ {approx_ms} мс)"


def frame_budget_share(run: Benchmark, target_fps: int) -> float | None:
    """Return the percent of accepted frames at or below a preset frame budget."""
    frame_budget_ms_from_fps(target_fps)
    if run.frame_budget_counts is None:
        return None
    count = run.frame_budget_counts[FRAME_BUDGET_FPS_PRESETS.index(target_fps)]
    return 100.0 * count / run.sample_count


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
    timing_columns = {
        metric_id: next((lookup[alias] for alias in aliases if alias in lookup), None)
        for metric_id, aliases in PRESENTMON_FRAME_TIMING_COLUMNS.items()
    }
    timing_values = {metric_id: [] for metric_id, index in timing_columns.items() if index is not None}

    def parse_optional_duration(raw: str) -> float | None:
        raw = raw.strip()
        if not raw or raw.casefold() in {"na", "n/a", "-"}:
            return None
        try:
            parsed = float(raw)
        except ValueError:
            if delimiter != "," and raw.count(",") == 1 and "." not in raw:
                try:
                    parsed = float(raw.replace(",", "."))
                except ValueError:
                    return None
            else:
                return None
        if not math.isfinite(parsed) or parsed < 0 or parsed > 10_000:
            return None
        return parsed

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
            if metric_kind == "cpu-presented" and normalized_frame_type != "application":
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
        for metric_id, column_index in timing_columns.items():
            if column_index is None:
                continue
            optional_value = parse_optional_duration(row[column_index])
            if optional_value is not None:
                timing_values[metric_id].append(optional_value)
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
    frame_timing = tuple(
        FrameTimingSummary(
            metric_id=metric_id,
            valid_count=len(values),
            median_ms=statistics.median(values) if values else None,
            p95_ms=_nearest_rank(sorted(values), 0.95) if values else None,
        )
        for metric_id, values in timing_values.items()
    )
    return analyze_frame_times(source.name, samples, metric_kind=metric_kind, frame_timing=frame_timing), tuple(warnings)


def _format_frame_timing_run(run: Benchmark, label: str) -> list[str]:
    lines = [f"{label} (медиана / p95, доля строк с валидным значением):"]
    summaries = {item.metric_id: item for item in run.frame_timing}
    for metric_id, metric_label in FRAME_TIMING_LABELS.items():
        item = summaries.get(metric_id)
        if item is None:
            lines.append(f"  {metric_label}: отсутствует в CSV.")
            continue
        coverage = 100 * item.valid_count / run.sample_count
        if item.valid_count and item.median_ms is not None and item.p95_ms is not None:
            lines.append(
                f"  {metric_label}: {item.median_ms:.2f} / {item.p95_ms:.2f} мс; "
                f"{item.valid_count}/{run.sample_count} ({coverage:.1f}%)."
            )
        else:
            lines.append(f"  {metric_label}: нет валидных значений; 0/{run.sample_count} (0.0%).")
    return lines


def _format_frame_timing_comparison(before: Benchmark, after: Benchmark) -> str:
    if not before.frame_timing and not after.frame_timing:
        return ""
    lines = [
        "Дополнительные счётчики PresentMon (медиана / p95, coverage от принятых строк frametime):",
        *_format_frame_timing_run(before, "  A"),
        *_format_frame_timing_run(after, "  B"),
        "Coverage считается относительно строк, принятых для основной метрики frametime, а не всех строк исходного CSV. "
        "Нули показываются как записанные значения; их интерпретация зависит от источника. "
        "Это описательные значения, не определение причины или ресурса, ограничивающего производительность. "
        "GPU time и GPU busy — разные счётчики; их наличие и заполненность зависят от конфигурации PresentMon.",
        "",
    ]
    return "\n".join(lines)


def compare_benchmarks(before: Benchmark, after: Benchmark, target_fps: int = 60) -> str:
    fps_delta = after.average_fps - before.average_fps
    fps_percent = (fps_delta / before.average_fps * 100) if before.average_fps else 0.0
    low_delta = after.one_percent_low_fps - before.one_percent_low_fps
    p99_delta = after.p99_frame_time_ms - before.p99_frame_time_ms
    spread_before = frame_time_spread_ms(before)
    spread_after = frame_time_spread_ms(after)
    spread_delta = spread_after - spread_before
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
    budget_rows = []
    for label, run in (("A", before), ("B", after)):
        share = frame_budget_share(run, target_fps)
        if share is None:
            budget_rows.append(f"  {label}: нет данных (замер импортирован в старой версии FrameForge)")
        else:
            within = run.frame_budget_counts[FRAME_BUDGET_FPS_PRESETS.index(target_fps)]
            budget_rows.append(f"  {label}: {share:.1f}% ({within:,}/{run.sample_count:,} кадров)")
    return (
        "Сравниваются две выборки; это само по себе не доказывает эффект настройки.\n"
        f"Метрика A: {METRIC_LABELS.get(before.metric_kind, before.metric_kind)}\n"
        f"Метрика B: {METRIC_LABELS.get(after.metric_kind, after.metric_kind)}\n"
        + notes
        + settings
        + checklist
        + metric_warning
        + context_warning
        + _format_frame_timing_comparison(before, after)
        + f"Baseline (A): {before.name} ({before.sample_count:,} кадров)\n"
        f"  Средний FPS: {before.average_fps:.1f} · 1% low: {before.one_percent_low_fps:.1f} · p99 frametime: {before.p99_frame_time_ms:.2f} ms\n\n"
        f"Variant (B): {after.name} ({after.sample_count:,} кадров)\n"
        f"  Средний FPS: {after.average_fps:.1f} · 1% low: {after.one_percent_low_fps:.1f} · p99 frametime: {after.p99_frame_time_ms:.2f} ms\n\n"
        f"Разброс хвоста frametime (p99 − медиана): A {spread_before:.2f} → B {spread_after:.2f} ms ({spread_delta:+.2f} ms; меньше — уже хвост в этом прогоне)\n"
        "Это описательная характеристика одной выборки, а не статистический тест и не гарантия плавности.\n\n"
        + sample_warning
        + "Доли кадров по времени кадра (меньше = короче кадр):\n"
        + "\n".join(bucket_rows)
        + f"\n\nКадры в бюджете {target_fps} FPS ({format_budget_threshold_label(target_fps)}; доля принятых кадров):\n"
        + "\n".join(budget_rows)
        + f"\nFrame budget — не оценка воспринимаемой плавности и не подтверждение стабильных {target_fps} FPS.\n"
        + "\n\n"
        f"Разница среднего FPS: {fps_delta:+.1f} ({fps_percent:+.1f}%)\n"
        f"Разница 1% low: {low_delta:+.1f} FPS\n"
        f"Разница p99 frametime: {p99_delta:+.2f} ms ({'хуже' if p99_delta > 0 else 'лучше' if p99_delta < 0 else 'без изменений'})\n\n"
        "Разница между прогонами сама по себе не доказывает причину. Повтори оба варианта в одинаковой сцене, разрешении, пресете и условиях; при малом числе кадров результат менее устойчив."
    )


GROUP_METRICS = (
    ("average_fps", "Средний FPS по CSV", "FPS", True),
    ("one_percent_low_fps", "1% low по CSV", "FPS", True),
        ("p99_frame_time_ms", "p99 frametime по CSV", "мс", False),
)


def _quartile(values: list[float], fraction: float) -> float:
    """Inclusive linear interpolation over per-run summary values."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _validate_benchmark_groups(group_a: list[Benchmark], group_b: list[Benchmark] | None = None) -> None:
    if len(group_a) < 3:
        raise ValueError("Для группы A нужно не менее трёх отдельных CSV-замеров.")
    if len({id(run) for run in group_a}) != len(group_a):
        raise ValueError("Каждый отдельный CSV-замер можно добавить в группу только один раз.")
    runs = list(group_a)
    if group_b is not None:
        if len(group_b) < 3:
            raise ValueError("Для группы B нужно не менее трёх отдельных CSV-замеров.")
        if len({id(run) for run in group_b}) != len(group_b):
            raise ValueError("Каждый отдельный CSV-замер можно добавить в группу только один раз.")
        if {id(run) for run in group_a}.intersection(id(run) for run in group_b):
            raise ValueError("Один и тот же замер не может входить одновременно в группы A и B.")
        runs.extend(group_b)
    context = {(run.game, run.scene, run.metric_kind) for run in runs}
    if len(context) != 1:
        raise ValueError("Все замеры A/B должны иметь одинаковые игру, сцену и тип frametime.")
    game, scene, _metric = next(iter(context))
    if not game or not scene:
        raise ValueError("Для сравнения повторов укажи одинаковые игру и сцену у каждого замера.")


def summarize_benchmark_group(runs: list[Benchmark], target_fps: int = 60) -> dict[str, dict[str, float]]:
    """Summarize repeated per-CSV aggregate metrics; never pool raw frame samples."""
    _validate_benchmark_groups(runs)
    summary: dict[str, dict[str, float]] = {}
    for key, _label, _unit, _higher_is_better in GROUP_METRICS:
        values = [float(getattr(run, key)) for run in runs]
        summary[key] = {
            "median": statistics.median(values),
            "q1": _quartile(values, 0.25),
            "q3": _quartile(values, 0.75),
        }
    budget_shares = [frame_budget_share(run, target_fps) for run in runs]
    if all(value is not None for value in budget_shares):
        values = [float(value) for value in budget_shares]
        summary["frame_budget_within_pct"] = {
            "median": statistics.median(values),
            "q1": _quartile(values, 0.25),
            "q3": _quartile(values, 0.75),
        }
    return summary


def compare_benchmark_groups(group_a: list[Benchmark], group_b: list[Benchmark], target_fps: int = 60) -> str:
    """Compare medians and run-to-run IQRs with an explicit descriptive-only caveat."""
    _validate_benchmark_groups(group_a, group_b)
    summary_a = summarize_benchmark_group(group_a, target_fps)
    summary_b = summarize_benchmark_group(group_b, target_fps)
    report = [
        f"Повторные замеры: A — {len(group_a)} CSV, B — {len(group_b)} CSV.",
        f"Условия по меткам: {group_a[0].game} · {group_a[0].scene} · {METRIC_LABELS.get(group_a[0].metric_kind, group_a[0].metric_kind)}.",
        "Фильтр списка влияет только на выбор участников; отчёт использует все замеры, назначенные в группы.",
        "Значения ниже — медианы показателей, рассчитанных отдельно для каждого CSV; это не pooled-показатели группы (включая 1% low и p99).",
        "Каждый CSV имеет одинаковый вес независимо от числа кадров/длительности; разброс и IQR описательные.",
        "При 3–4 прогонах IQR особенно чувствителен к одному замеру; рассматривай его вместе со всеми отдельными CSV.",
        "",
    ]
    if any(run.frame_timing for run in (*group_a, *group_b)):
        report.extend((
            "Дополнительные счётчики PresentMon — медиана/p95 и coverage от принятых строк frametime; "
            "это описательные значения, а не определение причины или ресурса, ограничивающего производительность.",
            "Coverage считается от строк, принятых для основной метрики, а не от всех строк исходного CSV. Нули сохраняются как записанные значения; их интерпретация зависит от источника.",
            "GPU time и GPU busy — разные счётчики; наличие и заполненность зависят от конфигурации PresentMon.",
            "",
        ))
    for key, label, unit, _higher_is_better in GROUP_METRICS:
        a = summary_a[key]
        b = summary_b[key]
        delta = b["median"] - a["median"]
        overlap = max(a["q1"], b["q1"]) <= min(a["q3"], b["q3"])
        report.extend((
            f"{label} ({unit}):",
            f"  A: медиана {a['median']:.2f}; межквартильный диапазон {a['q1']:.2f}–{a['q3']:.2f}",
            f"  B: медиана {b['median']:.2f}; межквартильный диапазон {b['q1']:.2f}–{b['q3']:.2f}",
            f"  Медиана B−A: {delta:+.2f} {unit}; диапазоны {'перекрываются' if overlap else 'не перекрываются'}.",
            "",
        ))
    budget_a = summary_a.get("frame_budget_within_pct")
    budget_b = summary_b.get("frame_budget_within_pct")
    available_a = sum(run.frame_budget_counts is not None for run in group_a)
    available_b = sum(run.frame_budget_counts is not None for run in group_b)
    report.extend((f"Доля принятых кадров в бюджете {target_fps} FPS ({format_budget_threshold_label(target_fps)}):",))
    report.append(f"Данные доступны: группа A — {available_a}/{len(group_a)} CSV; группа B — {available_b}/{len(group_b)} CSV.")
    if budget_a is None or budget_b is None:
        report.append("  Сводка групп недоступна: для неё нужны данные каждого CSV. Старые замеры не учитываются как 0%.")
    else:
        report.extend((
            f"  A: медиана {budget_a['median']:.2f}%; IQR {budget_a['q1']:.2f}–{budget_a['q3']:.2f}%",
            f"  B: медиана {budget_b['median']:.2f}%; IQR {budget_b['q1']:.2f}–{budget_b['q3']:.2f}%",
            f"  Медиана B−A: {budget_b['median'] - budget_a['median']:+.2f} п.п.",
        ))
    report.extend(("Ограничение: доля в frame budget не описывает воспринимаемую плавность; одиночный длинный кадр может теряться в общей доле.", ""))
    for group_label, group in (("A", group_a), ("B", group_b)):
        report.extend((
            f"Отдельные прогоны группы {group_label} (агрегаты CSV, порядок следует истории замеров):",
            "  № | n_frames | average FPS | 1% low FPS | p99 frametime (мс) | в бюджете (%)",
        ))
        for index, run in enumerate(group, start=1):
            share = frame_budget_share(run, target_fps)
            budget_text = "нет данных" if share is None else f"{share:.2f}"
            report.append(
                f"  {index} | {run.sample_count} | {run.average_fps:.2f} | "
                f"{run.one_percent_low_fps:.2f} | {run.p99_frame_time_ms:.2f} | {budget_text}"
            )
            report.extend(_format_frame_timing_run(run, f"  {group_label}{index}"))
        report.append("")
    report.append(
        "Это описательное сравнение выбранных повторов, не тест статистической значимости и не доказательство причинного эффекта. "
        "Номер строки следует порядку истории и не подтверждает хронологию захвата; n_frames — число принятых кадров, не длительность. "
        "FrameForge не хранит настройки окружения, температуру, фоновые процессы или исходные кадры. "
        "Повторяй A и B в сопоставимой сцене и чередуй порядок прогонов; не интерпретируй небольшие различия без учёта разброса."
    )
    return "\n".join(report)


def export_group_comparison_csv(group_a: list[Benchmark], group_b: list[Benchmark], target_fps: int = 60) -> str:
    _validate_benchmark_groups(group_a, group_b)
    summaries = (summarize_benchmark_group(group_a, target_fps), summarize_benchmark_group(group_b, target_fps))
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("metric", "group_a_median", "group_a_q1", "group_a_q3", "group_b_median", "group_b_q1", "group_b_q3", "median_b_minus_a", "unit"))
    for key, _label, unit, _higher_is_better in GROUP_METRICS:
        a, b = summaries
        writer.writerow((key, a[key]["median"], a[key]["q1"], a[key]["q3"], b[key]["median"], b[key]["q1"], b[key]["q3"], b[key]["median"] - a[key]["median"], unit))
    writer.writerow(("run_count", len(group_a), "", "", len(group_b), "", "", len(group_b) - len(group_a), "runs"))
    writer.writerow(("frame_budget_target_fps", target_fps, "", "", "", "", "", "", "fps"))
    budget_a = summaries[0].get("frame_budget_within_pct")
    budget_b = summaries[1].get("frame_budget_within_pct")
    writer.writerow(("frame_budget_available", int(budget_a is not None), "", "", int(budget_b is not None), "", "", "", "boolean"))
    writer.writerow(("frame_budget_available_runs", sum(run.frame_budget_counts is not None for run in group_a), "", "", sum(run.frame_budget_counts is not None for run in group_b), "", "", "", "runs"))
    if budget_a is not None and budget_b is not None:
        writer.writerow(("frame_budget_within_pct", budget_a["median"], budget_a["q1"], budget_a["q3"], budget_b["median"], budget_b["q1"], budget_b["q3"], budget_b["median"] - budget_a["median"], "percent"))
    writer.writerow(("causal_claim", "", "", "", "", "", "", "not_established_by_repeated_runs", "note"))
    return "\ufeff" + output.getvalue()


def export_group_comparison_json(group_a: list[Benchmark], group_b: list[Benchmark], target_fps: int = 60) -> str:
    _validate_benchmark_groups(group_a, group_b)
    summary_a = summarize_benchmark_group(group_a, target_fps)
    summary_b = summarize_benchmark_group(group_b, target_fps)
    return json.dumps({
        "schema_version": 2,
        "method": "median_and_inclusive_iqr_of_per_csv_summaries",
        "baseline_a": {"run_count": len(group_a), "metrics": summary_a},
        "variant_b": {"run_count": len(group_b), "metrics": summary_b},
        "frame_time_metric_kind": group_a[0].metric_kind,
        "frame_budget_target_fps": target_fps,
        "frame_budget_available": {"baseline_a": "frame_budget_within_pct" in summary_a, "variant_b": "frame_budget_within_pct" in summary_b},
        "frame_budget_available_run_count": {
            "baseline_a": sum(run.frame_budget_counts is not None for run in group_a),
            "variant_b": sum(run.frame_budget_counts is not None for run in group_b),
        },
        "causal_claim": "not_established_by_repeated_runs",
    }, ensure_ascii=False, indent=2)


def export_comparison_csv(before: Benchmark, after: Benchmark, target_fps: int = 60) -> str:
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
        ("p99_minus_median_frame_time_ms", frame_time_spread_ms(before), frame_time_spread_ms(after), frame_time_spread_ms(after) - frame_time_spread_ms(before), "ms"),
        ("min_frame_time_ms", before.min_frame_time_ms, after.min_frame_time_ms, after.min_frame_time_ms - before.min_frame_time_ms, "ms"),
        ("max_frame_time_ms", before.max_frame_time_ms, after.max_frame_time_ms, after.max_frame_time_ms - before.max_frame_time_ms, "ms"),
    )
    writer.writerows(rows)
    writer.writerow(("frame_budget_target_fps", target_fps, target_fps, 0, "fps"))
    for label, run in (("baseline_a", before), ("variant_b", after)):
        share = frame_budget_share(run, target_fps)
        value = "" if share is None else share / 100.0
        writer.writerow((f"{label}_frame_budget_within_share", value, value, "", "fraction"))
    for index, (a_count, b_count) in enumerate(zip(before.frame_time_buckets, after.frame_time_buckets)):
        a_share = a_count / before.sample_count
        b_share = b_count / after.sample_count
        writer.writerow((f"frame_time_bucket_{index}", a_count, b_count, b_count - a_count, "frames"))
        writer.writerow((f"frame_time_bucket_{index}_share", a_share, b_share, b_share - a_share, "fraction"))
    writer.writerow(("sample_count_delta_ratio", "", "", abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count), "fraction"))
    writer.writerow(("causal_claim", "", "", "not_established_by_two_runs", "note"))
    return output.getvalue()


def export_comparison_json(before: Benchmark, after: Benchmark, target_fps: int = 60) -> str:
    """Export machine-readable aggregate comparison without source names or paths."""
    return json.dumps(
        {
            "schema_version": 4,
            "frame_budget_target_fps": target_fps,
            "baseline_a": {
                "frame_time_metric_kind": before.metric_kind,
                "sample_count": before.sample_count,
                "average_fps": before.average_fps,
                "one_percent_low_fps": before.one_percent_low_fps,
                "median_frame_time_ms": before.median_frame_time_ms,
                "p99_frame_time_ms": before.p99_frame_time_ms,
                "p99_minus_median_frame_time_ms": frame_time_spread_ms(before),
                "min_frame_time_ms": before.min_frame_time_ms,
                "max_frame_time_ms": before.max_frame_time_ms,
                "frame_time_bucket_counts": list(before.frame_time_buckets),
                "frame_budget_within_share": None if frame_budget_share(before, target_fps) is None else frame_budget_share(before, target_fps) / 100.0,
            },
            "variant_b": {
                "frame_time_metric_kind": after.metric_kind,
                "sample_count": after.sample_count,
                "average_fps": after.average_fps,
                "one_percent_low_fps": after.one_percent_low_fps,
                "median_frame_time_ms": after.median_frame_time_ms,
                "p99_frame_time_ms": after.p99_frame_time_ms,
                "p99_minus_median_frame_time_ms": frame_time_spread_ms(after),
                "min_frame_time_ms": after.min_frame_time_ms,
                "max_frame_time_ms": after.max_frame_time_ms,
                "frame_time_bucket_counts": list(after.frame_time_buckets),
                "frame_budget_within_share": None if frame_budget_share(after, target_fps) is None else frame_budget_share(after, target_fps) / 100.0,
            },
            "sample_count_delta_ratio": abs(before.sample_count - after.sample_count) / max(before.sample_count, after.sample_count),
            "causal_claim": "not_established_by_two_runs",
        },
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    ) + "\n"
