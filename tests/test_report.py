"""
Тесты services/report.py и utils/csv_export.py.

ORM-строки фабрикуем вручную (без БД) — это простые объекты с атрибутами.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from bot.services.analysis import AnalysisResult, Hypothesis
from bot.services.metrics import PeriodStats, SleepMetrics
from bot.services.report import build_doctor_report, format_factors_summary
from bot.utils.csv_export import entries_to_csv, questionnaires_to_csv


def fake_entry(
    *,
    entry_date: date = date(2025, 1, 15),
    tib: int = 480, sol: int = 20, waso: int = 30, tst: int = 430, se: float = 89.58,
    quality: int = 4,
    caffeine: bool = False, alcohol: bool = False, screen: bool = False,
    activity: int = 1, stress: int = 3,
    notes: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        entry_date=entry_date,
        lights_out="23:00", try_sleep="23:10", final_wake="07:00",
        tib_min=tib, sol_min=sol, waso_min=waso, tst_min=tst, se_percent=se,
        awakenings_count=2, quality=quality, notes=notes,
        caffeine_after_16=caffeine, alcohol_evening=alcohol,
        screen_before_bed=screen, activity_level=activity, stress_level=stress,
    )


def fake_q(
    qtype: str = "ISI", score: int = 15, interpretation: str = "moderate",
    when: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        type=qtype, score=score, interpretation=interpretation,
        created_at=when or datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc),
        answers_json={},
    )


def stats(n: int = 10) -> PeriodStats:
    return PeriodStats(
        n_nights=n,
        avg_tib_min=480.0, avg_sol_min=20.0, avg_waso_min=30.0,
        avg_tst_min=430.0, avg_se_percent=89.58,
        median_se_percent=89.58, median_sol_min=20.0, median_tst_min=430.0,
    )


def m(se: float = 89.58) -> SleepMetrics:
    return SleepMetrics(tib_min=480, sol_min=20, waso_min=30, tst_min=430, se_percent=se)


# ============================================================================
# build_doctor_report
# ============================================================================

class TestDoctorReport:
    def test_empty_rows(self) -> None:
        text = build_doctor_report(
            rows=[], stats=stats(0), metrics_list=[], analysis=AnalysisResult(),
            questionnaires={}, days=14, today=date(2025, 1, 21),
        )
        assert "Отчёт для врача" in text
        assert "Нет записей" in text
        assert "не является медицинским заключением" in text

    def test_with_rows(self) -> None:
        rows = [fake_entry(), fake_entry(entry_date=date(2025, 1, 16))]
        text = build_doctor_report(
            rows=rows, stats=stats(2), metrics_list=[m(), m()],
            analysis=AnalysisResult(), questionnaires={},
            days=14, today=date(2025, 1, 21),
        )
        assert "2025-01-15" in text
        assert "2025-01-16" in text
        assert "Сводка" in text
        assert "TIB" in text

    def test_with_questionnaires(self) -> None:
        qs = {
            "ISI": fake_q("ISI", 18, "moderate"),
            "ESS": fake_q("ESS", 12, "borderline"),
        }
        text = build_doctor_report(
            rows=[fake_entry()], stats=stats(1), metrics_list=[m()],
            analysis=AnalysisResult(), questionnaires=qs,
            days=14, today=date(2025, 1, 21),
        )
        assert "ISI" in text
        assert "18" in text
        assert "ESS" in text
        assert "12" in text

    def test_with_hypotheses(self) -> None:
        h = Hypothesis("x", "Возможна инсомния", "SE<85%", "PMID 1", "К врачу", "high")
        text = build_doctor_report(
            rows=[fake_entry()], stats=stats(1), metrics_list=[m()],
            analysis=AnalysisResult(hypotheses=[h], flags=["x"]),
            questionnaires={}, days=14, today=date(2025, 1, 21),
        )
        assert "Возможна инсомния" in text
        assert "PMID 1" in text
        assert "[high]" in text

    def test_no_hypotheses_message(self) -> None:
        text = build_doctor_report(
            rows=[fake_entry()], stats=stats(1), metrics_list=[m()],
            analysis=AnalysisResult(), questionnaires={},
            days=14, today=date(2025, 1, 21),
        )
        assert "Значимых гипотез" in text

    def test_factors_summary_included(self) -> None:
        text = build_doctor_report(
            rows=[fake_entry(caffeine=True, alcohol=True)],
            stats=stats(1), metrics_list=[m()],
            analysis=AnalysisResult(), questionnaires={},
            days=14, today=date(2025, 1, 21),
            factors_summary="Кофеин после 16:00: 1/1 ночей",
        )
        assert "Кофеин после 16:00: 1/1" in text


# ============================================================================
# format_factors_summary
# ============================================================================

class TestFactorsSummary:
    def test_empty(self) -> None:
        assert format_factors_summary([]) == ""

    def test_counts(self) -> None:
        rows = [
            fake_entry(caffeine=True, alcohol=False, screen=True, stress=4),
            fake_entry(caffeine=False, alcohol=True, screen=True, stress=2),
        ]
        text = format_factors_summary(rows)
        assert "Кофеин после 16:00: 1/2" in text
        assert "Алкоголь вечером: 1/2" in text
        assert "Экран за 1 ч до сна: 2/2" in text
        assert "Средний стресс: 3.0/5" in text


# ============================================================================
# CSV
# ============================================================================

class TestCSV:
    def test_entries_csv_header_and_rows(self) -> None:
        rows = [fake_entry(), fake_entry(entry_date=date(2025, 1, 16))]
        data = entries_to_csv(rows)
        text = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert "entry_date" in header
        assert "se_percent" in header
        data_rows = list(reader)
        assert len(data_rows) == 2

    def test_entries_csv_notes_omitted(self) -> None:
        """Заметки НЕ должны попадать в CSV (приватность)."""
        r = fake_entry(notes="секретная информация")
        text = entries_to_csv([r]).decode("utf-8-sig")
        assert "секретная" not in text

    def test_entries_csv_bom(self) -> None:
        data = entries_to_csv([fake_entry()])
        assert data[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM

    def test_questionnaires_csv(self) -> None:
        qs = [fake_q("ISI", 15, "moderate"), fake_q("ESS", 8, "normal")]
        text = questionnaires_to_csv(qs).decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert header == ["created_at", "type", "score", "interpretation"]
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0][1] == "ISI"