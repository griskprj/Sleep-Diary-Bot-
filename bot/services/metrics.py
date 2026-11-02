"""
Расчёт метрик сна по Consensus Sleep Diary.

Все формулы задокументированы в docstring со ссылками:
    Carney C.E. et al., "The Consensus Sleep Diary", Sleep 2012;35(2):287–302.
    PMID 22294820 / DOI 10.5665/sleep.1642

Пороги:
    SE < 85%        — признак инсомнии (Riemann 2017, PMID 28875581)
    SOL > 30 мин    — удлинённая латентность (PMID 28875581, ICSD-3 PMID 25367475)
    WASO > 30 мин   — значимые пробуждения (PMID 28875581)
    TST < 7 ч       — недостаточная длительность (PMID 26039963)
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.constants import (
    SE_INSOMNIA_THRESHOLD,
    SOL_ELEVATED_MIN,
    TIB_TST_GAP_HOURS,
    TST_LOW_HOURS,
    WASO_ELEVATED_MIN,
)


@dataclass(frozen=True, slots=True)
class SleepMetrics:
    """Вычисленные метрики одной ночи. Все длительности — в минутах."""
    tib_min: int
    sol_min: int
    waso_min: int
    tst_min: int
    se_percent: float

    @property
    def tib_hours(self) -> float:
        return self.tib_min / 60.0

    @property
    def tst_hours(self) -> float:
        return self.tst_min / 60.0


def _to_minutes(hhmm: str) -> int:
    """'HH:MM' → минуты от полуночи."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def compute_tib(lights_out: str, final_wake: str) -> int:
    """
    Time In Bed (TIB) = final_wake − lights_out, с переходом через полночь.

    Пример: lights_out='23:30', final_wake='07:15' → 465 мин (7 ч 45 мин).
    Если final_wake <= lights_out — считаем, что подъём на следующий день.

    Источник: CSD (PMID 22294820).
    """
    lo = _to_minutes(lights_out)
    fw = _to_minutes(final_wake)
    if fw <= lo:
        fw += 24 * 60
    return fw - lo


def compute_tst(tib_min: int, sol_min: int, waso_min: int) -> int:
    """
    Total Sleep Time (TST) = TIB − SOL − WASO.

    Источник: CSD (PMID 22294820). Не может быть отрицательным.
    """
    return max(0, tib_min - sol_min - waso_min)


def compute_se(tst_min: int, tib_min: int) -> float:
    """
    Sleep Efficiency (SE) = TST / TIB × 100%.

    Если TIB = 0 — возвращаем 0.0 (защита от деления на ноль).
    Источник: CSD (PMID 22294820).
    """
    if tib_min <= 0:
        return 0.0
    return round(tst_min / tib_min * 100.0, 2)


def compute_metrics(
    *,
    lights_out: str,
    final_wake: str,
    sol_min: int,
    waso_min: int,
) -> SleepMetrics:
    """
    Полный расчёт метрик одной ночи.

    try_sleep не участвует в формулах (используется только для UX-валидации:
    try_sleep ≥ lights_out). Включён в CSD как поле, но TIB считается от
    lights_out — так в оригинальном CSD (PMID 22294820).
    """
    tib = compute_tib(lights_out, final_wake)
    tst = compute_tst(tib, sol_min, waso_min)
    se = compute_se(tst, tib)
    return SleepMetrics(tib_min=tib, sol_min=sol_min, waso_min=waso_min, tst_min=tst, se_percent=se)


# ---------------------------------------------------------------------------
# Флаги одной ночи (не диагнозы!)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NightFlags:
    low_se: bool
    elevated_sol: bool
    elevated_waso: bool
    low_tst: bool
    wide_tib_tst_gap: bool


def night_flags(m: SleepMetrics) -> NightFlags:
    """
    Флаги одной ночи. НЕ диагноз — только «обрати внимание».

    Пороги:
        low_se            — SE < 85%            (PMID 28875581)
        elevated_sol      — SOL > 30 мин        (PMID 28875581)
        elevated_waso     — WASO > 30 мин       (PMID 28875581)
        low_tst           — TST < 7 ч           (PMID 26039963)
        wide_tib_tst_gap  — TIB − TST > 1 ч     (поведенческая инсомния)
    """
    return NightFlags(
        low_se=m.se_percent < SE_INSOMNIA_THRESHOLD,
        elevated_sol=m.sol_min > SOL_ELEVATED_MIN,
        elevated_waso=m.waso_min > WASO_ELEVATED_MIN,
        low_tst=m.tst_hours < TST_LOW_HOURS,
        wide_tib_tst_gap=(m.tib_min - m.tst_min) > int(TIB_TST_GAP_HOURS * 60),
    )


# ---------------------------------------------------------------------------
# Агрегаты за период
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PeriodStats:
    n_nights: int
    avg_tib_min: float
    avg_sol_min: float
    avg_waso_min: float
    avg_tst_min: float
    avg_se_percent: float
    median_se_percent: float
    median_sol_min: float
    median_tst_min: float


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def aggregate(metrics_list: list[SleepMetrics]) -> PeriodStats:
    """Средние и медианы за период. Пустой список → все нули, n_nights=0."""
    n = len(metrics_list)
    if n == 0:
        return PeriodStats(0, 0, 0, 0, 0, 0, 0, 0, 0)

    tibs = [m.tib_min for m in metrics_list]
    sols = [m.sol_min for m in metrics_list]
    wasos = [m.waso_min for m in metrics_list]
    tsts = [m.tst_min for m in metrics_list]
    ses = [m.se_percent for m in metrics_list]

    return PeriodStats(
        n_nights=n,
        avg_tib_min=sum(tibs) / n,
        avg_sol_min=sum(sols) / n,
        avg_waso_min=sum(wasos) / n,
        avg_tst_min=sum(tsts) / n,
        avg_se_percent=round(sum(ses) / n, 2),
        median_se_percent=round(_median(ses), 2),
        median_sol_min=round(_median(sols), 2),
        median_tst_min=round(_median(tsts), 2),
    )


def trend(metrics_list: list[SleepMetrics], field: str) -> float:
    """
    Простой линейный тренд: наклон по МНК (единиц поля в сутки).

    field ∈ {'se_percent', 'sol_min', 'tst_min', 'waso_min'}.
    Возвращает 0.0 при n < 2.
    Положительный наклон = рост показателя со временем.
    """
    n = len(metrics_list)
    if n < 2:
        return 0.0
    xs = list(range(n))
    ys = [float(getattr(m, field)) for m in metrics_list]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    return round(num / den, 3) if den else 0.0