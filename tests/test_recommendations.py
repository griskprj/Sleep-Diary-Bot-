"""
Тесты recommendations.py.

Проверяют:
- срабатывание рекомендаций на канонических входах
- отсутствие рекомендаций, не привязанных к данным
- приоритеты и дедуп
- отсутствие фармакологических советов (этический тест)
"""
from __future__ import annotations

from datetime import date

import pytest

from bot.services.analysis import AnalysisResult, DiaryFactors, Hypothesis
from bot.services.metrics import PeriodStats
from bot.services.questionnaires import PSQIInput, ScoreResult, score_ess, score_isi, score_psqi, score_stopbang
from bot.services.recommendations import AdviceResult, build_advice


def stats(
    *,
    n: int = 14,
    avg_se: float = 80.0,
    median_se: float = 80.0,
    avg_tst: float = 400.0,
) -> PeriodStats:
    return PeriodStats(
        n_nights=n,
        avg_tib_min=500.0,
        avg_sol_min=30.0,
        avg_waso_min=40.0,
        avg_tst_min=avg_tst,
        avg_se_percent=avg_se,
        median_se_percent=median_se,
        median_sol_min=30.0,
        median_tst_min=avg_tst,
    )


def empty_analysis() -> AnalysisResult:
    return AnalysisResult(hypotheses=[], flags=[])


def analysis_with(*flags: str) -> AnalysisResult:
    return AnalysisResult(hypotheses=[], flags=list(flags))


# ============================================================================
# osa_referral
# ============================================================================

class TestOSAReferral:
    def test_triggered_by_flag(self) -> None:
        sb = score_stopbang([True] * 5 + [False] * 3)
        ess = score_ess([2] * 8)
        res = build_advice(
            analysis=analysis_with("osa_risk_suspected"),
            stats=stats(),
            stopbang=sb,
            ess=ess,
        )
        codes = [r.code for r in res.recommendations]
        assert "osa_referral" in codes
        # приоритет 1 — первая
        assert res.recommendations[0].code == "osa_referral"

    def test_not_triggered_without_flag(self) -> None:
        sb = score_stopbang([True] * 5 + [False] * 3)
        res = build_advice(analysis=empty_analysis(), stats=stats(), stopbang=sb)
        assert "osa_referral" not in [r.code for r in res.recommendations]


# ============================================================================
# cbti_referral
# ============================================================================

class TestCBTIReferral:
    def test_triggered_by_chronic_flag(self) -> None:
        isi = score_isi([3] * 7)
        res = build_advice(
            analysis=analysis_with("chronic_insomnia_suspected"),
            stats=stats(),
            isi=isi,
        )
        assert "cbti_referral" in [r.code for r in res.recommendations]

    def test_no_flag_no_referral(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats())
        assert "cbti_referral" not in [r.code for r in res.recommendations]


# ============================================================================
# stimulus_control
# ============================================================================

class TestStimulusControl:
    def test_triggered_by_low_avg_se(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(avg_se=80.0))
        assert "stimulus_control" in [r.code for r in res.recommendations]

    def test_triggered_by_low_median_se(self) -> None:
        res = build_advice(
            analysis=empty_analysis(), stats=stats(avg_se=88.0, median_se=80.0)
        )
        assert "stimulus_control" in [r.code for r in res.recommendations]

    def test_not_triggered_by_good_se(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(avg_se=92.0, median_se=92.0))
        assert "stimulus_control" not in [r.code for r in res.recommendations]


# ============================================================================
# sleep_restriction
# ============================================================================

class TestSleepRestriction:
    def test_triggered(self) -> None:
        res = build_advice(
            analysis=analysis_with("behavioral_insomnia_suspected"),
            stats=stats(avg_tst=400.0),
        )
        assert "sleep_restriction" in [r.code for r in res.recommendations]

    def test_not_triggered_without_flag(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(avg_se=80.0))
        assert "sleep_restriction" not in [r.code for r in res.recommendations]


# ============================================================================
# circadian_anchor
# ============================================================================

class TestCircadianAnchor:
    def test_triggered_by_flag(self) -> None:
        res = build_advice(
            analysis=analysis_with("circadian_delay_suspected"), stats=stats(n=14)
        )
        assert "circadian_anchor" in [r.code for r in res.recommendations]

    def test_triggered_with_enough_data(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(n=7))
        assert "circadian_anchor" in [r.code for r in res.recommendations]

    def test_not_triggered_too_few_nights(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(n=3))
        assert "circadian_anchor" not in [r.code for r in res.recommendations]


# ============================================================================
# extend_sleep
# ============================================================================

class TestExtendSleep:
    def test_triggered_by_flag(self) -> None:
        res = build_advice(
            analysis=analysis_with("insufficient_sleep"), stats=stats(avg_tst=350.0)
        )
        assert "extend_sleep" in [r.code for r in res.recommendations]

    def test_no_flag_no_extend(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats())
        assert "extend_sleep" not in [r.code for r in res.recommendations]


# ============================================================================
# Гигиена — привязка к факторам
# ============================================================================

class TestHygiene:
    def test_caffeine(self) -> None:
        f = DiaryFactors(caffeine_days=6, alcohol_days=0, screen_days=0, avg_stress=2.0, n_nights=10)
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=f)
        assert "caffeine_cutoff" in [r.code for r in res.recommendations]

    def test_no_caffeine_below_threshold(self) -> None:
        f = DiaryFactors(caffeine_days=4, alcohol_days=0, screen_days=0, avg_stress=2.0, n_nights=10)
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=f)
        assert "caffeine_cutoff" not in [r.code for r in res.recommendations]

    def test_alcohol(self) -> None:
        f = DiaryFactors(caffeine_days=0, alcohol_days=5, screen_days=0, avg_stress=2.0, n_nights=10)
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=f)
        assert "alcohol_reduction" in [r.code for r in res.recommendations]

    def test_screens(self) -> None:
        f = DiaryFactors(caffeine_days=0, alcohol_days=0, screen_days=8, avg_stress=2.0, n_nights=10)
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=f)
        assert "screen_cutoff" in [r.code for r in res.recommendations]

    def test_stress(self) -> None:
        f = DiaryFactors(caffeine_days=0, alcohol_days=0, screen_days=0, avg_stress=4.2, n_nights=10)
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=f)
        assert "stress_management" in [r.code for r in res.recommendations]

    def test_no_factors_no_hygiene(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(), factors=None)
        codes = [r.code for r in res.recommendations]
        assert "caffeine_cutoff" not in codes
        assert "alcohol_reduction" not in codes
        assert "screen_cutoff" not in codes
        assert "stress_management" not in codes


# ============================================================================
# PSQI poor
# ============================================================================

class TestPSQIGeneral:
    def test_triggered(self) -> None:
        psqi = score_psqi(PSQIInput(3, 3, 3, 3, 3))
        res = build_advice(
            analysis=analysis_with("psqi_poor"), stats=stats(), psqi=psqi
        )
        assert "psqi_general" in [r.code for r in res.recommendations]

    def test_not_triggered(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats())
        assert "psqi_general" not in [r.code for r in res.recommendations]


# ============================================================================
# relaxation
# ============================================================================

class TestRelaxation:
    def test_present_with_enough_data(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(n=3))
        assert "relaxation" in [r.code for r in res.recommendations]

    def test_absent_too_few_nights(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats(n=2))
        assert "relaxation" not in [r.code for r in res.recommendations]


# ============================================================================
# Общие свойства
# ============================================================================

class TestGeneral:
    def test_sorted_by_priority(self) -> None:
        sb = score_stopbang([True] * 5 + [False] * 3)
        ess = score_ess([2] * 8)
        isi = score_isi([3] * 7)
        f = DiaryFactors(caffeine_days=8, alcohol_days=6, screen_days=8, avg_stress=4.5, n_nights=10)
        res = build_advice(
            analysis=analysis_with(
                "osa_risk_suspected",
                "chronic_insomnia_suspected",
                "behavioral_insomnia_suspected",
                "insufficient_sleep",
                "psqi_poor",
            ),
            stats=stats(avg_se=75.0, avg_tst=350.0),
            factors=f,
            isi=isi,
            ess=ess,
            stopbang=sb,
        )
        priorities = [r.priority for r in res.recommendations]
        assert priorities == sorted(priorities)

    def test_no_duplicates(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats())
        codes = [r.code for r in res.recommendations]
        assert len(codes) == len(set(codes))

    def test_disclaimer_present(self) -> None:
        res = build_advice(analysis=empty_analysis(), stats=stats())
        assert res.disclaimer
        assert "не диагноз" in res.disclaimer.lower()

    def test_no_pharmacological_advice(self) -> None:
        """
        Этический тест: рекомендации не содержат назначений препаратов,
        дозировок и императивных фарм. советов.

        Важно: слово «мелатонин» может встречаться в физиологическом
        контексте («свет подавляет мелатонин») — это НЕ фарм. совет.
        Поэтому проверяем паттерны, а не отдельные слова.
        """
        import re

        # Паттерны, которые НЕ должны встречаться:
        forbidden_patterns = [
            # Прямые назначения препаратов
            r"\bпримите\s+(мелатонин|зопиклон|золпидем|бензодиазепин)",
            r"\bвыпейте\s+(мелатонин|зопиклон|золпидем|бензодиазепин)",
            r"\bпопробуйте\s+(мелатонин|зопиклон|золпидем|таблетк)",
            r"\bначните\s+принимать\s+(мелатонин|зопиклон|золпидем)",
            r"\bпринимайте\s+(мелатонин|зопиклон|золпидем|таблетк)",
            # Дозировки
            r"\bдозировк",
            r"\b\d+\s*мг\b",
            r"\b\d+\s*mg\b",
            # Прямые фарм. рекомендации
            r"\bпрепарат\s+(от|для)\s+сна\b",
            r"\bрекомендую\s+(принять|выпить|попробовать)\s+(мелатонин|таблетк)",
            r"\bследует\s+принять\s+(мелатонин|таблетк)",
        ]

        sb = score_stopbang([True] * 8)
        ess = score_ess([2] * 8)
        isi = score_isi([4] * 7)
        psqi = score_psqi(PSQIInput(3, 3, 3, 3, 3))
        f = DiaryFactors(caffeine_days=10, alcohol_days=10, screen_days=10, avg_stress=5.0, n_nights=10)
        res = build_advice(
            analysis=analysis_with(
                "osa_risk_suspected", "chronic_insomnia_suspected",
                "behavioral_insomnia_suspected", "insufficient_sleep",
                "circadian_delay_suspected", "psqi_poor", "poor_sleep_hygiene",
            ),
            stats=stats(avg_se=70.0, avg_tst=300.0),
            factors=f, isi=isi, psqi=psqi, ess=ess, stopbang=sb,
        )
        for r in res.recommendations:
            text = (r.title + " " + r.body + " " + r.rationale).lower()
            for pat in forbidden_patterns:
                assert not re.search(pat, text), (
                    f"Фарм. совет в {r.code}: найден паттерн {pat!r} в «{text}»"
                )