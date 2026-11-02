"""
Тесты форматирования. Без aiogram — проверяем чистые строки.
"""
from __future__ import annotations

from datetime import date

import pytest

from bot.services.analysis import AnalysisResult, Hypothesis
from bot.services.metrics import PeriodStats, SleepMetrics
from bot.services.presentation import (
    format_advice,
    format_hypotheses,
    format_period_stats,
    format_questionnaire_snapshot,
)
from bot.services.recommendations import AdviceResult, Recommendation
from bot.services.questionnaires import ScoreResult


def stats(n: int = 10, avg_se: float = 85.0, avg_tst: float = 430.0) -> PeriodStats:
    return PeriodStats(
        n_nights=n,
        avg_tib_min=500.0,
        avg_sol_min=20.0,
        avg_waso_min=30.0,
        avg_tst_min=avg_tst,
        avg_se_percent=avg_se,
        median_se_percent=avg_se,
        median_sol_min=20.0,
        median_tst_min=avg_tst,
    )


def m(se: float = 85.0, sol: int = 20, waso: int = 30, tst: int = 430) -> SleepMetrics:
    return SleepMetrics(tib_min=500, sol_min=sol, waso_min=waso, tst_min=tst, se_percent=se)


# ============================================================================
# format_period_stats
# ============================================================================

class TestFormatPeriodStats:
    def test_empty(self) -> None:
        s = PeriodStats(0, 0, 0, 0, 0, 0, 0, 0, 0)
        text = format_period_stats(s, days=14, today=date(2025, 1, 21), metrics_list=[])
        assert "нет записей" in text
        assert "/diary" in text

    def test_with_data(self) -> None:
        text = format_period_stats(
            stats(), days=14, today=date(2025, 1, 21), metrics_list=[m()] * 5
        )
        assert "14 дн" in text
        assert "TIB" in text
        assert "TST" in text
        assert "SE" in text

    def test_trends_when_enough_data(self) -> None:
        metrics = [m(se=80.0), m(se=85.0), m(se=90.0)]
        text = format_period_stats(
            stats(), days=14, today=date(2025, 1, 21), metrics_list=metrics
        )
        assert "Тренды" in text
        assert "%/день" in text

    def test_no_trends_when_too_few(self) -> None:
        text = format_period_stats(
            stats(n=2), days=14, today=date(2025, 1, 21), metrics_list=[m(), m()]
        )
        assert "Тренды" not in text


# ============================================================================
# format_hypotheses
# ============================================================================

class TestFormatHypotheses:
    def test_empty(self) -> None:
        text = format_hypotheses(AnalysisResult())
        assert "значимых гипотез нет" in text

    def test_one_hypothesis(self) -> None:
        h = Hypothesis(
            code="x", title="Возможна инсомния",
            rationale="SE < 85%", source="PMID 123",
            recommendation="К врачу", severity="high",
        )
        text = format_hypotheses(AnalysisResult(hypotheses=[h], flags=[]))
        assert "Возможна инсомния" in text
        assert "PMID 123" in text
        assert "К врачу" in text
        assert "‼" in text  # маркер high

    def test_severity_markers(self) -> None:
        hs = [
            Hypothesis("a", "A", "r", "s", "rec", "high"),
            Hypothesis("b", "B", "r", "s", "rec", "attention"),
            Hypothesis("c", "C", "r", "s", "rec", "info"),
        ]
        text = format_hypotheses(AnalysisResult(hypotheses=hs, flags=[]))
        assert "‼" in text and "⚠" in text and "ℹ" in text


# ============================================================================
# format_questionnaire_snapshot
# ============================================================================

class TestFormatQuestionnaireSnapshot:
    def test_empty(self) -> None:
        text = format_questionnaire_snapshot(None, None, None, None)
        assert text == ""

    def test_partial(self) -> None:
        isi = ScoreResult(score=15, interpretation="moderate", label="умеренная", explanation="", flags=(), source="")
        ess = ScoreResult(score=8, interpretation="normal", label="норма", explanation="", flags=(), source="")
        text = format_questionnaire_snapshot(isi, None, ess, None)
        assert "ISI: 15" in text
        assert "ESS: 8" in text
        assert "PSQI" not in text
        assert "STOP-BANG" not in text


# ============================================================================
# format_advice
# ============================================================================

class TestFormatAdvice:
    def test_empty(self) -> None:
        text = format_advice(AdviceResult())
        assert "Недостаточно данных" in text

    def test_with_recommendations(self) -> None:
        r = Recommendation(
            code="x", title="Контроль стимула",
            body="Вставайте, если не спится.",
            rationale="SE < 85%",
            source="PMID 123",
            priority=2,
        )
        text = format_advice(AdviceResult(recommendations=[r]))
        assert "Контроль стимула" in text
        assert "Вставайте" in text
        assert "PMID 123" in text
        assert "не диагноз" in text.lower()

    def test_priority_markers(self) -> None:
        rs = [
            Recommendation("a", "A", "b", "r", "s", 1),
            Recommendation("b", "B", "b", "r", "s", 3),
            Recommendation("c", "C", "b", "r", "s", 5),
        ]
        text = format_advice(AdviceResult(recommendations=rs))
        assert "‼" in text
        assert "•" in text
        assert "·" in text