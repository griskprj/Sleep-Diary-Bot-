"""
Тесты опросников: ISI, ESS, STOP-BANG, PSQI (упрощённый).

Покрывают граничные случаи и интерпретации по первоисточникам.
"""
from __future__ import annotations

import pytest

from bot.services.questionnaires import (
    PSQIInput,
    score_ess,
    score_isi,
    score_psqi,
    score_stopbang,
)


# ============================================================================
# ISI
# ============================================================================

class TestISI:
    def test_zero(self) -> None:
        r = score_isi([0] * 7)
        assert r.score == 0
        assert r.interpretation == "none"
        assert "isi_clinical" not in r.flags

    def test_upper_none(self) -> None:
        # 7 = верхняя граница 'none'
        r = score_isi([1] * 7)
        assert r.score == 7
        assert r.interpretation == "none"

    def test_lower_subclinical(self) -> None:
        # 8 = нижняя граница 'subclinical'
        r = score_isi([1, 1, 1, 1, 1, 1, 2])  # сумма 8
        assert r.score == 8
        assert r.interpretation == "subclinical"

    def test_upper_subclinical(self) -> None:
        # 14 = верхняя граница 'subclinical'
        r = score_isi([2] * 7)
        assert r.score == 14
        assert r.interpretation == "subclinical"

    def test_lower_moderate(self) -> None:
        # 15 = нижняя граница 'moderate' + клинический флаг
        r = score_isi([2, 2, 2, 2, 2, 2, 3])  # сумма 15
        assert r.score == 15
        assert r.interpretation == "moderate"
        assert "isi_clinical" in r.flags

    def test_upper_moderate(self) -> None:
        # 21 = верхняя граница 'moderate'
        r = score_isi([3] * 7)
        assert r.score == 21
        assert r.interpretation == "moderate"

    def test_lower_severe(self) -> None:
        # 22 = нижняя граница 'severe'
        r = score_isi([3, 3, 3, 3, 3, 3, 4])
        assert r.score == 22
        assert r.interpretation == "severe"
        assert "isi_clinical" in r.flags

    def test_max(self) -> None:
        r = score_isi([4] * 7)
        assert r.score == 28
        assert r.interpretation == "severe"

    def test_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            score_isi([0] * 6)
        with pytest.raises(ValueError):
            score_isi([0] * 8)

    def test_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            score_isi([5, 0, 0, 0, 0, 0, 0])
        with pytest.raises(ValueError):
            score_isi([-1, 0, 0, 0, 0, 0, 0])


# ============================================================================
# ESS
# ============================================================================

class TestESS:
    def test_zero(self) -> None:
        r = score_ess([0] * 8)
        assert r.score == 0
        assert r.interpretation == "normal"
        assert r.flags == ()

    def test_upper_normal(self) -> None:
        # 10 = верхняя граница 'normal'
        r = score_ess([1, 1, 1, 1, 1, 1, 2, 2])  # сумма 10
        assert r.score == 10
        assert r.interpretation == "normal"

    def test_lower_borderline(self) -> None:
        # 11 = нижняя граница 'borderline'
        r = score_ess([1, 1, 1, 1, 1, 2, 2, 2])  # сумма 11
        assert r.score == 11
        assert r.interpretation == "borderline"
        assert "ess_borderline" in r.flags

    def test_upper_borderline(self) -> None:
        # 12 = верхняя граница 'borderline'
        r = score_ess([1, 1, 1, 2, 2, 2, 1, 2])  # сумма 12
        assert r.score == 12
        assert r.interpretation == "borderline"

    def test_lower_excessive(self) -> None:
        # 13 = нижняя граница 'excessive'
        r = score_ess([2, 2, 2, 2, 1, 1, 2, 1])  # сумма 13
        assert r.score == 13
        assert r.interpretation == "excessive"
        assert "ess_excessive" in r.flags

    def test_max(self) -> None:
        r = score_ess([3] * 8)
        assert r.score == 24
        assert r.interpretation == "excessive"

    def test_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            score_ess([0] * 7)

    def test_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            score_ess([4, 0, 0, 0, 0, 0, 0, 0])


# ============================================================================
# STOP-BANG
# ============================================================================

class TestStopBang:
    def test_all_no(self) -> None:
        r = score_stopbang([False] * 8)
        assert r.score == 0
        assert r.interpretation == "low"
        assert r.flags == ()

    def test_upper_low(self) -> None:
        # 2 = верхняя граница 'low'
        r = score_stopbang([True, True, False, False, False, False, False, False])
        assert r.score == 2
        assert r.interpretation == "low"
        # 2 < 3 — флага stopbang_risk нет
        assert "stopbang_risk" not in r.flags

    def test_lower_intermediate_has_risk_flag(self) -> None:
        # 3 = нижняя граница 'intermediate' + флаг риска
        r = score_stopbang([True, True, True, False, False, False, False, False])
        assert r.score == 3
        assert r.interpretation == "intermediate"
        assert "stopbang_risk" in r.flags
        assert "stopbang_intermediate" in r.flags

    def test_upper_intermediate(self) -> None:
        # 4 = верхняя граница 'intermediate'
        r = score_stopbang([True, True, True, True, False, False, False, False])
        assert r.score == 4
        assert r.interpretation == "intermediate"

    def test_lower_high(self) -> None:
        # 5 = нижняя граница 'high'
        r = score_stopbang([True, True, True, True, True, False, False, False])
        assert r.score == 5
        assert r.interpretation == "high"
        assert "stopbang_high" in r.flags
        assert "stopbang_risk" in r.flags

    def test_all_yes(self) -> None:
        r = score_stopbang([True] * 8)
        assert r.score == 8
        assert r.interpretation == "high"

    def test_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            score_stopbang([True] * 7)


# ============================================================================
# PSQI (упрощённый)
# ============================================================================

class TestPSQI:
    def test_all_zero(self) -> None:
        r = score_psqi(PSQIInput(0, 0, 0, 0, 0))
        assert r.score == 0
        assert r.interpretation == "good"

    def test_threshold_boundary(self) -> None:
        # raw=4 → 4*1.4=5.6 → round=6 > 5 → poor
        r = score_psqi(PSQIInput(1, 1, 1, 1, 0))
        assert r.score == 6
        assert r.interpretation == "poor"
        assert "psqi_poor" in r.flags

    def test_below_threshold(self) -> None:
        # raw=3 → 3*1.4=4.2 → round=4 <= 5 → good
        r = score_psqi(PSQIInput(1, 1, 1, 0, 0))
        assert r.score == 4
        assert r.interpretation == "good"

    def test_max(self) -> None:
        r = score_psqi(PSQIInput(3, 3, 3, 3, 3))
        assert r.score == 21
        assert r.interpretation == "poor"

    def test_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            score_psqi(PSQIInput(4, 0, 0, 0, 0))
        with pytest.raises(ValueError):
            score_psqi(PSQIInput(0, -1, 0, 0, 0))