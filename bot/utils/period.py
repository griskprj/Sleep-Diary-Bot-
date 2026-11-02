"""
Сборка входных данных для services.analysis из БД.

Преобразует ORM-строки SleepEntry в DatedMetrics/DiaryFactors.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from bot.db.models import SleepEntry
from bot.services.analysis import DatedMetrics, DiaryFactors, build_factors
from bot.services.metrics import SleepMetrics


def entries_to_dated(rows: Sequence[SleepEntry]) -> list[DatedMetrics]:
    """SleepEntry[] → DatedMetrics[] (для analysis)."""
    return [
        DatedMetrics(
            entry_date=r.entry_date,
            metrics=SleepMetrics(
                tib_min=r.tib_min,
                sol_min=r.sol_min,
                waso_min=r.waso_min,
                tst_min=r.tst_min,
                se_percent=r.se_percent,
            ),
        )
        for r in rows
    ]


def entries_to_factors(rows: Sequence[SleepEntry]) -> DiaryFactors:
    """SleepEntry[] → агрегированные факторы."""
    return build_factors(
        (r.caffeine_after_16, r.alcohol_evening, r.screen_before_bed, r.stress_level)
        for r in rows
    )


def metrics_only(dated: list[DatedMetrics]) -> list[SleepMetrics]:
    """DatedMetrics[] → SleepMetrics[] (для aggregate/trend)."""
    return [d.metrics for d in dated]