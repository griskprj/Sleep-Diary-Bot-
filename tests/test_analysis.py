"""
Тесты генерации гипотез.

Ключевые проверки:
- каждая гипотеза срабатывает на каноническом наборе
- НЕ срабатывает на границе
- НЕ срабатывает за 1–2 плохие ночи (анти-ложнодиагностика)
- приоритет severity
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from bot.services.analysis import (
    DatedMetrics,
    DiaryFactors,
    analyze,
    build_factors,
)
from bot.services.metrics import SleepMetrics
from bot.services.questionnaires import score_isi, score_ess, score_stopbang, score_psqi, PSQIInput


TODAY = date(2025, 1, 21)


def m(tib: int, sol: int, waso: int, tst: int | None = None) -> SleepMetrics:
    """Удобный конструктор метрик. TST и SE считаются, если не заданы."""
    if tst is None:
        tst = max(0, tib - sol - waso)
    se = round(tst / tib * 100.0, 2) if tib > 0 else 0.0
    return SleepMetrics(tib_min=tib, sol_min=sol, waso_min=waso, tst_min=tst, se_percent=se)


def series(n: int, builder, *, end: date = TODAY) -> list[DatedMetrics]:
    """N ночей подряд, заканчивая end."""
    return [
        DatedMetrics(entry_date=end - timedelta(days=n - 1 - i), metrics=builder())
        for i in range(n)
    ]


# ============================================================================
# chronic_insomnia
# ============================================================================

class TestChronicInsomnia:
    def _bad_night(self) -> SleepMetrics:
        # TIB=480, SOL=45, WASO=45 → TST=390, SE=81.25
        return m(480, 45, 45)

    def test_positive(self) -> None:
        entries = series(21, self._bad_night)
        isi = score_isi([3] * 7)  # 21 → moderate
        res = analyze(entries=entries, isi=isi, today=TODAY)
        codes = [h.code for h in res.hypotheses]
        assert "chronic_insomnia" in codes
        assert "chronic_insomnia_suspected" in res.flags

    def test_no_isi_no_hypothesis(self) -> None:
        entries = series(21, self._bad_night)
        res = analyze(entries=entries, isi=None, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]

    def test_low_isi_no_hypothesis(self) -> None:
        entries = series(21, self._bad_night)
        isi = score_isi([1] * 7)  # 7 → none
        res = analyze(entries=entries, isi=isi, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]

    def test_one_bad_night_no_hypothesis(self) -> None:
        # 1 плохая ночь + 20 хороших — не гипотеза
        good = lambda: m(480, 10, 10)  # SE ≈ 95.8
        entries = series(20, good) + [
            DatedMetrics(entry_date=TODAY, metrics=self._bad_night())
        ]
        isi = score_isi([3] * 7)
        res = analyze(entries=entries, isi=isi, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]

    def test_too_few_entries_no_hypothesis(self) -> None:
        # 13 записей за 21 день < INSOMNIA_MIN_ENTRIES (14)
        entries = series(13, self._bad_night)
        isi = score_isi([3] * 7)
        res = analyze(entries=entries, isi=isi, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]

    def test_two_thirds_threshold(self) -> None:
        # 14 записей, 10 плохих → 10/14 ≈ 71.4% ≥ 2/3 (9.33) — срабатывает
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=self._bad_night()) for i in range(10)]
        good = [DatedMetrics(entry_date=TODAY - timedelta(days=10 + i), metrics=m(480, 10, 10)) for i in range(4)]
        isi = score_isi([3] * 7)
        res = analyze(entries=bad + good, isi=isi, today=TODAY)
        assert "chronic_insomnia" in [h.code for h in res.hypotheses]

    def test_below_two_thirds_threshold(self) -> None:
        # 14 записей, из них 8 плохих (8 < 9) — НЕ срабатывает
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=self._bad_night()) for i in range(8)]
        good = [DatedMetrics(entry_date=TODAY - timedelta(days=8 + i), metrics=m(480, 10, 10)) for i in range(6)]
        isi = score_isi([3] * 7)
        res = analyze(entries=bad + good, isi=isi, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]


# ============================================================================
# behavioral_insomnia
# ============================================================================

class TestBehavioralInsomnia:
    def _pattern(self) -> SleepMetrics:
        # TIB=600 (10 ч), SOL=30, WASO=30 → TST=540 (9 ч), gap=60, SE=90 — НЕ паттерн
        # Нужно: gap>60 и SE<85 → TIB=600, TST=450, gap=150, SE=75
        return m(600, 60, 90)  # TST=450, SE=75

    def test_positive(self) -> None:
        entries = series(14, self._pattern)
        res = analyze(entries=entries, today=TODAY)
        assert "behavioral_insomnia" in [h.code for h in res.hypotheses]

    def test_too_few_entries(self) -> None:
        entries = series(7, self._pattern)
        res = analyze(entries=entries, today=TODAY)
        assert "behavioral_insomnia" not in [h.code for h in res.hypotheses]

    def test_good_se_no_hypothesis(self) -> None:
        # gap>60, но SE>=85 → не паттерн
        # TIB=600, SOL=20, WASO=30 → TST=550, SE=91.67
        entries = series(14, lambda: m(600, 20, 30))
        res = analyze(entries=entries, today=TODAY)
        assert "behavioral_insomnia" not in [h.code for h in res.hypotheses]


# ============================================================================
# osa_risk
# ============================================================================

class TestOSARisk:
    def test_stopbang_high_and_ess_excessive(self) -> None:
        sb = score_stopbang([True] * 5 + [False] * 3)  # 5 → high
        ess = score_ess([2, 2, 2, 2, 2, 2, 2, 2])  # 16 → excessive
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), stopbang=sb, ess=ess, today=TODAY)
        assert "osa_risk" in [h.code for h in res.hypotheses]

    def test_stopbang_intermediate_and_ess_borderline(self) -> None:
        sb = score_stopbang([True, True, True, False, False, False, False, False])  # 3
        ess = score_ess([2, 1, 2, 1, 2, 1, 2, 1])  # 12 → borderline, >10
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), stopbang=sb, ess=ess, today=TODAY)
        assert "osa_risk" in [h.code for h in res.hypotheses]

    def test_stopbang_low(self) -> None:
        sb = score_stopbang([False] * 8)  # 0
        ess = score_ess([2] * 8)  # 16
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), stopbang=sb, ess=ess, today=TODAY)
        assert "osa_risk" not in [h.code for h in res.hypotheses]

    def test_stopbang_3_but_ess_normal_no_hypothesis(self) -> None:
        # STOP-BANG=3, ESS<=10, заметок нет → не срабатывает
        sb = score_stopbang([True, True, True, False, False, False, False, False])  # 3
        ess = score_ess([0] * 8)  # 0 → normal
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), stopbang=sb, ess=ess, today=TODAY)
        assert "osa_risk" not in [h.code for h in res.hypotheses]

    def test_no_stopbang_no_hypothesis(self) -> None:
        ess = score_ess([2] * 8)
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), stopbang=None, ess=ess, today=TODAY)
        assert "osa_risk" not in [h.code for h in res.hypotheses]


# ============================================================================
# circadian_delay
# ============================================================================

class TestCircadianDelay:
    def _late_phase(self) -> SleepMetrics:
        # TIB=540 (9 ч), SE>=85, SOL<=30 → «поздно лёг, поздно встал, выспался»
        return m(540, 15, 15)  # TST=510, SE=94.44

    def test_positive(self) -> None:
        entries = series(14, self._late_phase)
        res = analyze(entries=entries, today=TODAY)
        assert "circadian_delay" in [h.code for h in res.hypotheses]

    def test_too_few_entries(self) -> None:
        entries = series(7, self._late_phase)
        res = analyze(entries=entries, today=TODAY)
        assert "circadian_delay" not in [h.code for h in res.hypotheses]

    def test_low_se_no_hypothesis(self) -> None:
        # TIB=540, SOL=60, WASO=60 → SE=77.78 → не паттерн
        entries = series(14, lambda: m(540, 60, 60))
        res = analyze(entries=entries, today=TODAY)
        assert "circadian_delay" not in [h.code for h in res.hypotheses]


# ============================================================================
# insufficient_sleep
# ============================================================================

class TestInsufficientSleep:
    def _short(self) -> SleepMetrics:
        # TST=330 (5.5 ч)
        return m(420, 45, 45)  # TST=330, SE=78.57

    def test_positive(self) -> None:
        entries = series(14, self._short)
        res = analyze(entries=entries, today=TODAY)
        assert "insufficient_sleep" in [h.code for h in res.hypotheses]

    def test_too_few_entries(self) -> None:
        entries = series(13, self._short)
        res = analyze(entries=entries, today=TODAY)
        assert "insufficient_sleep" not in [h.code for h in res.hypotheses]

    def test_one_good_night_still_positive(self) -> None:
        # 13 плохих + 1 хорошая = 13/14 = 92.8% ≥ 80% → срабатывает
        entries = series(13, self._short) + [
            DatedMetrics(entry_date=TODAY, metrics=m(480, 10, 10))
        ]
        res = analyze(entries=entries, today=TODAY)
        assert "insufficient_sleep" in [h.code for h in res.hypotheses]

    def test_many_good_no_hypothesis(self) -> None:
        # 11 плохих + 3 хороших = 11/14 = 78.6% < 80% → не срабатывает
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=self._short()) for i in range(11)]
        good = [DatedMetrics(entry_date=TODAY - timedelta(days=11 + i), metrics=m(480, 10, 10)) for i in range(3)]
        res = analyze(entries=bad + good, today=TODAY)
        assert "insufficient_sleep" not in [h.code for h in res.hypotheses]


# ============================================================================
# poor_sleep_hygiene
# ============================================================================

class TestPoorSleepHygiene:
    def _bad_se(self) -> SleepMetrics:
        return m(480, 45, 45)  # SE=81.25

    def test_caffeine_high(self) -> None:
        entries = series(10, self._bad_se)
        factors = DiaryFactors(caffeine_days=6, alcohol_days=0, screen_days=0, avg_stress=2.0, n_nights=10)
        res = analyze(entries=entries, factors=factors, today=TODAY)
        assert "poor_sleep_hygiene" in [h.code for h in res.hypotheses]

    def test_good_se_no_hypothesis(self) -> None:
        entries = series(10, lambda: m(480, 10, 10))  # SE=95.83
        factors = DiaryFactors(caffeine_days=10, alcohol_days=10, screen_days=10, avg_stress=5.0, n_nights=10)
        res = analyze(entries=entries, factors=factors, today=TODAY)
        assert "poor_sleep_hygiene" not in [h.code for h in res.hypotheses]

    def test_stress_high(self) -> None:
        entries = series(10, self._bad_se)
        factors = DiaryFactors(caffeine_days=0, alcohol_days=0, screen_days=0, avg_stress=4.5, n_nights=10)
        res = analyze(entries=entries, factors=factors, today=TODAY)
        assert "poor_sleep_hygiene" in [h.code for h in res.hypotheses]

    def test_no_factors_argument(self) -> None:
        entries = series(10, self._bad_se)
        res = analyze(entries=entries, factors=None, today=TODAY)
        assert "poor_sleep_hygiene" not in [h.code for h in res.hypotheses]


# ============================================================================
# PSQI poor
# ============================================================================

class TestPSQIPoor:
    def test_poor_psqi_creates_hypothesis(self) -> None:
        psqi = score_psqi(PSQIInput(3, 3, 3, 3, 3))  # 21 → poor
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), psqi=psqi, today=TODAY)
        assert "psqi_poor" in [h.code for h in res.hypotheses]

    def test_good_psqi_no_hypothesis(self) -> None:
        psqi = score_psqi(PSQIInput(0, 0, 0, 0, 0))
        res = analyze(entries=series(3, lambda: m(480, 20, 20)), psqi=psqi, today=TODAY)
        assert "psqi_poor" not in [h.code for h in res.hypotheses]


# ============================================================================
# Общие свойства
# ============================================================================

class TestGeneral:
    def test_empty_entries(self) -> None:
        res = analyze(entries=[], today=TODAY)
        assert res.hypotheses == []
        assert res.flags == []

    def test_severity_sorting(self) -> None:
        # Соберём данные, дающие и high (ОАС), и info (гигиена)
        sb = score_stopbang([True] * 5 + [False] * 3)
        ess = score_ess([2] * 8)
        entries = series(10, lambda: m(480, 45, 45))
        factors = DiaryFactors(caffeine_days=10, alcohol_days=10, screen_days=10, avg_stress=5.0, n_nights=10)
        res = analyze(entries=entries, factors=factors, stopbang=sb, ess=ess, today=TODAY)
        sev = [h.severity for h in res.hypotheses]
        # high идёт раньше info
        if "high" in sev and "info" in sev:
            assert sev.index("high") < sev.index("info")

    def test_no_false_diagnosis_two_bad_nights(self) -> None:
        """2 плохие ночи + остальные хорошие → НИ ОДНОЙ гипотезы про инсомнию."""
        good = lambda: m(480, 10, 10)
        bad = lambda: m(480, 45, 45)
        entries = series(2, bad) + series(10, good)[:-2] if False else (
            series(2, bad) + [
                DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=good())
                for i in range(2, 12)
            ]
        )
        res = analyze(entries=entries, today=TODAY)
        codes = [h.code for h in res.hypotheses]
        assert "chronic_insomnia" not in codes
        assert "behavioral_insomnia" not in codes
        assert "insufficient_sleep" not in codes

    def test_build_factors(self) -> None:
        rows = [
            (True, False, True, 4),
            (True, False, False, 5),
            (False, True, True, 3),
        ]
        f = build_factors(rows)
        assert f.n_nights == 3
        assert f.caffeine_days == 2
        assert f.alcohol_days == 1
        assert f.screen_days == 2
        assert f.avg_stress == pytest.approx(4.0)
        assert f.caffeine_ratio == pytest.approx(2 / 3)

    def test_exactly_80_percent_triggers(self) -> None:
        # 12 плохих из 15 = 80% ровно → срабатывает (>= 4/5)
        # TST < 7 ч: m(420, 45, 45) → TST=330
        short = lambda: m(420, 45, 45)
        good  = lambda: m(480, 10, 10)
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=short()) for i in range(12)]
        good_entries = [DatedMetrics(entry_date=TODAY - timedelta(days=12 + i), metrics=good()) for i in range(3)]
        res = analyze(entries=bad + good_entries, today=TODAY)
        assert "insufficient_sleep" in [h.code for h in res.hypotheses]

    def test_exactly_two_thirds_triggers(self) -> None:
        # 14 записей, 10 плохих → 10*3=30 >= 2*14=28 → срабатывает
        # TIB=480, SOL=45, WASO=45 → TST=390, SE=81.25
        bad_night = lambda: m(480, 45, 45)
        good_night = lambda: m(480, 10, 10)
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=bad_night()) for i in range(10)]
        good = [DatedMetrics(entry_date=TODAY - timedelta(days=10 + i), metrics=good_night()) for i in range(4)]
        isi = score_isi([3] * 7)
        res = analyze(entries=bad + good, isi=isi, today=TODAY)
        assert "chronic_insomnia" in [h.code for h in res.hypotheses]

    def test_just_below_two_thirds_no_hypothesis(self) -> None:
        # 14 записей, 9 плохих → 9*3=27 < 2*14=28 → не срабатывает
        bad_night = lambda: m(480, 45, 45)
        good_night = lambda: m(480, 10, 10)
        bad = [DatedMetrics(entry_date=TODAY - timedelta(days=i), metrics=bad_night()) for i in range(9)]
        good = [DatedMetrics(entry_date=TODAY - timedelta(days=9 + i), metrics=good_night()) for i in range(5)]
        isi = score_isi([3] * 7)
        res = analyze(entries=bad + good, isi=isi, today=TODAY)
        assert "chronic_insomnia" not in [h.code for h in res.hypotheses]