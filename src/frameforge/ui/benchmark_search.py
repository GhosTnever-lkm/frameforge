"""Pure helpers for locating a run in the full benchmark history."""

from __future__ import annotations

from collections.abc import Sequence

from ..catalog import GUIDE_CHECKLIST_LABELS
from ..core.benchmark import Benchmark, METRIC_LABELS


def searchable_benchmark_text(run: Benchmark) -> str:
    manual = " ".join(GUIDE_CHECKLIST_LABELS.get(item, item) for item in run.manual_changes)
    setting = f"{run.setting_key} {run.setting_value}" if run.setting_key else ""
    return " ".join((run.name, run.game, run.scene, METRIC_LABELS.get(run.metric_kind, run.metric_kind), run.change_note, setting, manual)).casefold()


def matching_benchmark_indices(runs: Sequence[Benchmark], query: str) -> tuple[int, ...]:
    """Return original history indices matching a literal, case-insensitive substring."""
    needle = query.strip().casefold()
    if not needle:
        return ()
    return tuple(index for index, run in enumerate(runs) if needle in searchable_benchmark_text(run))
