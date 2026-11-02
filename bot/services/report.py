"""
Текстовый отчёт для врача-сомнолога.

Формат:
    1. Шапка: период, число ночей, дисклеймер.
    2. Таблица CSD-метрик (последние 14 ночей).
    3. Сводка (средние/медианы/тренды).
    4. Опросники (последние результаты + даты).
    5. Гипотезы с обоснованием и источниками.
    6. Факторы (кофеин/алкоголь/экраны/стресс/активность).

Никакой диагностики: только данные + гипотезы + ссылки.

CSV — отдельно, как вложение в /report и /export.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from bot.db.models import Questionnaire, SleepEntry
from bot.services.analysis import AnalysisResult
from bot.services.metrics import PeriodStats, SleepMetrics, trend


def build_doctor_report(
    *,
    rows: Sequence[SleepEntry],
    stats: PeriodStats,
    metrics_list: list[SleepMetrics],
    analysis: AnalysisResult,
    questionnaires: dict[str, Questionnaire | None],
    days: int,
    today: date,
    factors_summary: str | None = None,
) -> str:
    """
    Формирует текстовый отчёт для врача (HTML для Telegram).

    Не содержит диагнозов; содержит ссылки на источники.
    """
    lines: list[str] = []
    lines.append("<b>Отчёт для врача-сомнолога</b>")
    lines.append(f"Период: последние {days} дн. (до {today.isoformat()})")
    lines.append(f"Ночей с записями: {len(rows)}")
    lines.append("")
    lines.append(
        "<i>Данные самонаблюдения по Consensus Sleep Diary (PMID 22294820). "
        "Гипотезы — не диагнозы; требуют клинической оценки.</i>"
    )
    lines.append("")

    # --- 1. Таблица метрик
    lines.append("<b>Метрики по ночам</b>")
    if rows:
        lines.append("<pre>")
        header = f"{'Дата':<10} {'TIB':>5} {'SOL':>4} {'WASO':>4} {'TST':>5} {'SE%':>5} Q"
        lines.append(header)
        for r in rows:
            lines.append(
                f"{r.entry_date.isoformat():<10} "
                f"{r.tib_min:>5} {r.sol_min:>4} {r.waso_min:>4} "
                f"{r.tst_min:>5} {r.se_percent:>5.1f} {r.quality}"
            )
        lines.append("</pre>")
    else:
        lines.append("Нет записей за период.")
    lines.append("")

    # --- 2. Сводка
    if stats.n_nights > 0:
        lines.append("<b>Сводка</b>")
        lines.append(
            f"Средние: TIB {stats.avg_tib_min / 60:.1f} ч · "
            f"SOL {stats.avg_sol_min:.0f} мин · "
            f"WASO {stats.avg_waso_min:.0f} мин · "
            f"TST {stats.avg_tst_min / 60:.1f} ч · "
            f"SE {stats.avg_se_percent:.1f}%"
        )
        lines.append(
            f"Медианы: TST {stats.median_tst_min / 60:.1f} ч · "
            f"SE {stats.median_se_percent:.1f}% · "
            f"SOL {stats.median_sol_min:.0f} мин"
        )
        if stats.n_nights >= 3 and metrics_list:
            lines.append(
                f"Тренды: SE {trend(metrics_list, 'se_percent'):+.2f} %/день · "
                f"TST {trend(metrics_list, 'tst_min') / 60:+.2f} ч/день"
            )
        lines.append("")

    # --- 3. Опросники
    lines.append("<b>Опросники</b>")
    any_q = False
    for qtype, label in (
        ("ISI", "ISI (0–28, ≥15 клинически значимо)"),
        ("PSQI", "PSQI упрощ. (0–21, >5 плохое качество)"),
        ("ESS", "ESS (0–24, >10 избыточная сонливость)"),
        ("STOPBANG", "STOP-BANG (0–8, ≥3 риск ОАС)"),
    ):
        row = questionnaires.get(qtype)
        if row is not None:
            any_q = True
            lines.append(
                f"  {label}: <b>{row.score}</b> "
                f"({row.interpretation}) — {row.created_at.date().isoformat()}"
            )
    if not any_q:
        lines.append("  Не пройдены.")
    lines.append("")

    # --- 4. Гипотезы
    lines.append("<b>Гипотезы и флаги</b>")
    if analysis.hypotheses:
        for h in analysis.hypotheses:
            lines.append(f"• <b>{h.title}</b> [{h.severity}]")
            lines.append(f"  Обоснование: {h.rationale}")
            lines.append(f"  Источник: {h.source}")
    else:
        lines.append("  Значимых гипотез по текущим данным нет.")
    lines.append("")

    # --- 5. Факторы
    if factors_summary:
        lines.append("<b>Факторы</b>")
        lines.append(factors_summary)
        lines.append("")

    lines.append(
        "<i>Дисклеймер: отчёт не является медицинским заключением. "
        "Обсудите данные с врачом-сомнологом.</i>"
    )

    return "\n".join(lines)


def format_factors_summary(rows: Sequence[SleepEntry]) -> str:
    """Сводка факторов для отчёта."""
    if not rows:
        return ""
    n = len(rows)
    caffeine = sum(1 for r in rows if r.caffeine_after_16)
    alcohol = sum(1 for r in rows if r.alcohol_evening)
    screen = sum(1 for r in rows if r.screen_before_bed)
    stress_avg = sum(r.stress_level for r in rows) / n
    activity_avg = sum(r.activity_level for r in rows) / n
    return (
        f"Кофеин после 16:00: {caffeine}/{n} ночей\n"
        f"Алкоголь вечером: {alcohol}/{n} ночей\n"
        f"Экран за 1 ч до сна: {screen}/{n} ночей\n"
        f"Средний стресс: {stress_avg:.1f}/5\n"
        f"Средняя активность: {activity_avg:.1f}/2"
    )