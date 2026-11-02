"""
Тесты для services/metrics.py.

Покрывают:
- TIB/SOL/WASO/TST/SE, включая переход через полночь
- граничные случаи (TIB=0, отрицательный TST → clamp)
- флаги одной ночи
- агрегаты за период и тренд
"""
from __future__ import annotations

import math

import pytest

from bot.services.metrics import (
    SleepMetrics,
    aggregate,
    compute_metrics,
    compute_se,
    compute_tib,
    compute_tst,
    night_flags,
    trend,
)


# ------------------------- TIB -------------------------

class TestTIB:
    def test_regular_night(self) -> None:
        # 23:00 → 07:00 = 8 ч
        assert compute_tib("23:00", "07:00") == 480

    def test_midnight_cross(self) -> None:
        # 23:30 → 07:15 = 7 ч 45 мин
        assert compute_tib("23:30", "07:15") == 465

    def test_just_after_midnight(self) -> None:
        # 00:30 → 08:00 = 7 ч 30 мин
        assert compute_tib("00:30", "08:00") == 450

    def test_same_time_is_full_day(self) -> None:
        # final_wake == lights_out → считаем 24 ч (редкий, но валидный кейс)
        assert compute_tib("22:00", "22:00") == 24 * 60

    def test_before_midnight_wake(self) -> None:
        # 20:00 → 23:00 = 3 ч (подъём в тот же день, но fw > lo)
        assert compute_tib("20:00", "23:00") == 180

    def test_negative_input_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_tib("25:00", "07:00")


# ------------------------- TST -------------------------

class TestTST:
    def test_standard(self) -> None:
        # TIB=480, SOL=20, WASO=30 → TST=430
        assert compute_tst(480, 20, 30) == 430

    def test_clamped_to_zero(self) -> None:
        # TIB=30, SOL=20, WASO=30 → TST=-20 → clamp 0
        assert compute_tst(30, 20, 30) == 0

    def test_no_awakenings(self) -> None:
        assert compute_tst(480, 10, 0) == 470


# ------------------------- SE -------------------------

class TestSE:
    def test_standard(self) -> None:
        # 430/480 × 100 = 89.58
        assert math.isclose(compute_se(430, 480), 89.58, abs_tol=0.01)

    def test_zero_tib(self) -> None:
        assert compute_se(0, 0) == 0.0

    def test_perfect(self) -> None:
        assert compute_se(480, 480) == 100.0

    def test_low(self) -> None:
        # 300/480 = 62.5
        assert compute_se(300, 480) == 62.5


# ------------------------- compute_metrics -------------------------

class TestComputeMetrics:
    def test_full_night(self) -> None:
        m = compute_metrics(
            lights_out="23:00", final_wake="07:00", sol_min=20, waso_min=30
        )
        assert m.tib_min == 480
        assert m.tst_min == 430
        assert math.isclose(m.se_percent, 89.58, abs_tol=0.01)

    def test_midnight_cross(self) -> None:
        m = compute_metrics(
            lights_out="00:15", final_wake="08:45", sol_min=15, waso_min=10
        )
        assert m.tib_min == 510
        assert m.tst_min == 485

    def test_try_sleep_ignored(self) -> None:
        # compute_metrics не принимает try_sleep — это документированное поведение
        m = compute_metrics(
            lights_out="23:00", final_wake="07:00", sol_min=0, waso_min=0
        )
        assert m.tib_min == 480


# ------------------------- night_flags -------------------------

class TestNightFlags:
    def test_good_night_no_flags(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=10, waso_min=10, tst_min=460, se_percent=95.83)
        f = night_flags(m)
        assert not f.low_se
        assert not f.elevated_sol
        assert not f.elevated_waso
        assert not f.low_tst
        assert not f.wide_tib_tst_gap

    def test_low_se(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=10, waso_min=10, tst_min=360, se_percent=75.0)
        f = night_flags(m)
        assert f.low_se

    def test_elevated_sol(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=45, waso_min=10, tst_min=425, se_percent=88.54)
        assert night_flags(m).elevated_sol

    def test_sol_boundary_30_not_flagged(self) -> None:
        # ровно 30 — не > 30
        m = SleepMetrics(tib_min=480, sol_min=30, waso_min=0, tst_min=450, se_percent=93.75)
        assert not night_flags(m).elevated_sol

    def test_elevated_waso(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=0, waso_min=45, tst_min=435, se_percent=90.63)
        assert night_flags(m).elevated_waso

    def test_low_tst(self) -> None:
        # 6 ч = 360 мин
        m = SleepMetrics(tib_min=480, sol_min=60, waso_min=60, tst_min=360, se_percent=75.0)
        assert night_flags(m).low_tst

    def test_wide_tib_tst_gap(self) -> None:
        # TIB=600, TST=420 → gap=180 > 60
        m = SleepMetrics(tib_min=600, sol_min=60, waso_min=120, tst_min=420, se_percent=70.0)
        assert night_flags(m).wide_tib_tst_gap

    def test_gap_boundary_60_not_flagged(self) -> None:
        # gap == 60 → не > 60
        m = SleepMetrics(tib_min=480, sol_min=30, waso_min=30, tst_min=420, se_percent=87.5)
        assert not night_flags(m).wide_tib_tst_gap


# ------------------------- aggregate -------------------------

class TestAggregate:
    def test_empty(self) -> None:
        s = aggregate([])
        assert s.n_nights == 0
        assert s.avg_se_percent == 0.0

    def test_single(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=20, waso_min=30, tst_min=430, se_percent=89.58)
        s = aggregate([m])
        assert s.n_nights == 1
        assert s.avg_tst_min == 430
        assert s.median_se_percent == 89.58

    def test_multiple(self) -> None:
        m1 = SleepMetrics(tib_min=480, sol_min=20, waso_min=30, tst_min=430, se_percent=89.58)
        m2 = SleepMetrics(tib_min=420, sol_min=10, waso_min=10, tst_min=400, se_percent=95.24)
        m3 = SleepMetrics(tib_min=510, sol_min=40, waso_min=50, tst_min=420, se_percent=82.35)
        s = aggregate([m1, m2, m3])
        assert s.n_nights == 3
        assert math.isclose(s.avg_tst_min, (430 + 400 + 420) / 3, abs_tol=0.01)
        assert s.median_tst_min == 420.0
        assert s.median_se_percent == 89.58  # медиана из 82.35, 89.58, 95.24


# ------------------------- trend -------------------------

class TestTrend:
    def test_insufficient_data(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=20, waso_min=30, tst_min=430, se_percent=89.58)
        assert trend([m], "se_percent") == 0.0
        assert trend([], "se_percent") == 0.0

    def test_flat(self) -> None:
        m = SleepMetrics(tib_min=480, sol_min=20, waso_min=30, tst_min=430, se_percent=89.58)
        assert trend([m, m, m], "se_percent") == 0.0

    def test_increasing(self) -> None:
        # SE растёт линейно 80→90→100, наклон = 10
        ms = [
            SleepMetrics(tib_min=500, sol_min=100, waso_min=0, tst_min=400, se_percent=80.0),
            SleepMetrics(tib_min=500, sol_min=50, waso_min=0, tst_min=450, se_percent=90.0),
            SleepMetrics(tib_min=500, sol_min=0, waso_min=0, tst_min=500, se_percent=100.0),
        ]
        assert trend(ms, "se_percent") == 10.0

    def test_decreasing(self) -> None:
        ms = [
            SleepMetrics(tib_min=500, sol_min=0, waso_min=0, tst_min=500, se_percent=100.0),
            SleepMetrics(tib_min=500, sol_min=50, waso_min=0, tst_min=450, se_percent=90.0),
            SleepMetrics(tib_min=500, sol_min=100, waso_min=0, tst_min=400, se_percent=80.0),
        ]
        assert trend(ms, "se_percent") == -10.0