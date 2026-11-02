"""
Форматирование результатов сервисов в тексты для Telegram (HTML).

Отделено от бизнес-логики: сервисы возвращают dataclass'ы,
здесь — только строки. Легко тестируется (без aiogram).

ВАЖНО: aiogram при ParseMode.HTML не экранирует автоматически.
Все данные из БД/вычислений (rationale, source, label, body, ...)
экранируются через html.escape(..., quote=False). В тексте
используются &lt; / &gt; вместо < / >.
"""
from __future__ import annotations

import html
from datetime import date

from bot.services.analysis import AnalysisResult
from bot.services.metrics import PeriodStats, SleepMetrics, night_flags, trend
from bot.services.questionnaires import ScoreResult
from bot.services.recommendations import AdviceResult


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _esc(value: object) -> str:
    """Экранирует строку для Telegram HTML (не трогает кавычки)."""
    return html.escape(str(value), quote=False)


def _arrow(x: float) -> str:
    if x > 0.05:
        return "↑ "
    if x < -0.05:
        return "↓ "
    return "→ "


# ---------------------------------------------------------------------------
# /stats — метрики
# ---------------------------------------------------------------------------

def format_period_stats(
    stats: PeriodStats,
    *,
    days: int,
    today: date,
    metrics_list: list[SleepMetrics],
) -> str:
    """Сводка за период: средние/медианы + тренды."""
    if stats.n_nights == 0:
        return (
            f"За последние {days} дн. нет записей.\n"
            "Заполните /diary хотя бы 3 ночи подряд."
        )

    lines = [
        f"<b>Статистика за {days} дн.</b> (до {_esc(today.isoformat())})",
        f"Ночей с записями: <b>{stats.n_nights}</b>",
        "",
        "<b>Средние:</b>",
        f"  TIB: {stats.avg_tib_min / 60:.1f} ч",
        f"  SOL: {stats.avg_sol_min:.0f} мин",
        f"  WASO: {stats.avg_waso_min:.0f} мин",
        f"  TST: {stats.avg_tst_min / 60:.1f} ч",
        f"  SE: {stats.avg_se_percent:.1f}%",
        "",
        "<b>Медианы:</b>",
        f"  TST: {stats.median_tst_min / 60:.1f} ч",
        f"  SE: {stats.median_se_percent:.1f}%",
        f"  SOL: {stats.median_sol_min:.0f} мин",
    ]

    # Тренды (только если данных достаточно)
    if stats.n_nights >= 3 and metrics_list:
        se_trend = trend(metrics_list, "se_percent")
        tst_trend = trend(metrics_list, "tst_min")
        lines.extend([
            "",
            "<b>Тренды (наклон по дням):</b>",
            f"  SE: {_arrow(se_trend)}{se_trend:+.2f} %/день",
            f"  TST: {_arrow(tst_trend)}{tst_trend / 60:+.2f} ч/день",
        ])

    # Флаги одной ночи: сколько было «плохих» по каждому критерию
    if metrics_list:
        flags = [night_flags(m) for m in metrics_list]
        low_se = sum(f.low_se for f in flags)
        high_sol = sum(f.elevated_sol for f in flags)
        high_waso = sum(f.elevated_waso for f in flags)
        low_tst = sum(f.low_tst for f in flags)
        lines.extend([
            "",
            f"<b>Ночей с отклонением (из {len(metrics_list)}):</b>",
            f"  SE &lt; 85%: {low_se}",
            f"  SOL &gt; 30: {high_sol}",
            f"  WASO &gt; 30: {high_waso}",
            f"  TST &lt; 7 ч: {low_tst}",
        ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /stats — гипотезы
# ---------------------------------------------------------------------------

def format_hypotheses(result: AnalysisResult) -> str:
    """Список гипотез с обоснованием и источниками."""
    if not result.hypotheses:
        return (
            "<b>Гипотезы</b>\n\n"
            "По текущим данным значимых гипотез нет. Это не значит «всё хорошо» — "
            "это значит «пока нет паттерна, требующего внимания». Продолжайте вести дневник."
        )

    severity_label = {"high": "‼", "attention": "⚠", "info": "ℹ"}
    lines = ["<b>Гипотезы (не диагнозы)</b>", ""]
    for h in result.hypotheses:
        mark = severity_label.get(h.severity, "•")
        lines.append(f"{mark} <b>{_esc(h.title)}</b>")
        lines.append(f"   Почему: {_esc(h.rationale)}")
        lines.append(f"   Что делать: {_esc(h.recommendation)}")
        lines.append(f"   Источник: <i>{_esc(h.source)}</i>")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# /stats — снимок опросников
# ---------------------------------------------------------------------------

def format_questionnaire_snapshot(
    isi: ScoreResult | None,
    psqi: ScoreResult | None,
    ess: ScoreResult | None,
    stopbang: ScoreResult | None,
) -> str:
    """Краткая сводка последних опросников."""
    parts: list[str] = []
    if isi is not None:
        parts.append(f"ISI: {isi.score} ({_esc(isi.label)})")
    if psqi is not None:
        parts.append(f"PSQI (упр.): {psqi.score} ({_esc(psqi.label)})")
    if ess is not None:
        parts.append(f"ESS: {ess.score} ({_esc(ess.label)})")
    if stopbang is not None:
        parts.append(f"STOP-BANG: {stopbang.score} ({_esc(stopbang.label)})")
    if not parts:
        return ""
    return "<b>Последние опросники</b>\n" + "\n".join(f"  • {p}" for p in parts)


# ---------------------------------------------------------------------------
# /advice
# ---------------------------------------------------------------------------

PRIORITY_LABEL = {1: "‼", 2: "⚠", 3: "•", 4: "•", 5: "·"}


def format_advice(advice: AdviceResult) -> str:
    """Рекомендации с приоритетами и источниками."""
    if not advice.recommendations:
        return (
            "<b>Рекомендации</b>\n\n"
            "Недостаточно данных для персональных рекомендаций. "
            "Заполните /diary хотя бы 3 ночи и пройдите /isi."
        )

    lines = ["<b>Рекомендации (по вашим данным)</b>", ""]
    for r in advice.recommendations:
        mark = PRIORITY_LABEL.get(r.priority, "•")
        lines.append(f"{mark} <b>{_esc(r.title)}</b>")
        lines.append(_esc(r.body))
        lines.append(f"<i>Почему: {_esc(r.rationale)}</i>")
        lines.append(f"<i>Источник: {_esc(r.source)}</i>")
        lines.append("")
    lines.append(f"<i>{_esc(advice.disclaimer)}</i>")
    return "\n".join(lines)