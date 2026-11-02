"""
Генерация клинических гипотез и флагов на основе данных дневника.

ВАЖНО: это НЕ диагностика. Каждая гипотеза — это «обрати внимание»,
сопровождаемое:
    - кратким обоснованием (какие метрики/пороги сработали)
    - ссылкой на источник (PMID)
    - рекомендацией (к кому идти / что делать)

Гипотезы требуют УСТОЙЧИВОСТИ во времени (несколько ночей), чтобы не
выдавать ложных диагнозов за 1–2 плохие ночи.

Источники:
    ICSD-3 / AASM         — Sateia M.J., Chest 2014. PMID 25367475
    Пороги SE/SOL/WASO    — Riemann D. et al., J Sleep Res 2017. PMID 28875581
    TST 7–9 ч             — Watson N.F. et al., Sleep 2015. PMID 26039963
    ISI                   — Bastien C.H. et al., Sleep Med 2001. PMID 11438246
    STOP-BANG             — Chung F. et al., Chest 2016. PMID 26378880
    CBT-I (1-я линия)     — Qaseem A. et al., Ann Intern Med 2016. PMID 27136449
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from bot.constants import (
    INSOMNIA_MIN_ENTRIES,
    SE_INSOMNIA_THRESHOLD,
    SOL_ELEVATED_MIN,
    TIB_TST_GAP_HOURS,
    TST_LOW_HOURS,
    TST_LOW_MIN_DAYS,
    WASO_ELEVATED_MIN,
)
from bot.services.metrics import SleepMetrics, night_flags
from bot.services.questionnaires import ScoreResult


# ============================================================================
# Модели
# ============================================================================

@dataclass(frozen=True, slots=True)
class DatedMetrics:
    """Метрики одной ночи с датой (для окон и трендов)."""
    entry_date: date
    metrics: SleepMetrics


@dataclass(frozen=True, slots=True)
class DiaryFactors:
    """Агрегированные факторы за период — для корреляционных флагов."""
    caffeine_days: int
    alcohol_days: int
    screen_days: int
    avg_stress: float
    n_nights: int

    @property
    def caffeine_ratio(self) -> float:
        return self.caffeine_days / self.n_nights if self.n_nights else 0.0

    @property
    def alcohol_ratio(self) -> float:
        return self.alcohol_days / self.n_nights if self.n_nights else 0.0

    @property
    def screen_ratio(self) -> float:
        return self.screen_days / self.n_nights if self.n_nights else 0.0


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """
    Клиническая гипотеза (НЕ диагноз).

    code            — машинный код ('chronic_insomnia', 'osa_risk', ...)
    title           — краткое название для пользователя
    rationale       — «почему так решил» (какие метрики/пороги сработали)
    source          — PMID / документ
    recommendation  — что делать / к кому идти
    severity        — 'info' | 'attention' | 'high'
    """
    code: str
    title: str
    rationale: str
    source: str
    recommendation: str
    severity: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    hypotheses: list[Hypothesis] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


# ============================================================================
# Главная функция
# ============================================================================

def analyze(
    *,
    entries: Sequence[DatedMetrics],
    factors: DiaryFactors | None = None,
    isi: ScoreResult | None = None,
    psqi: ScoreResult | None = None,
    ess: ScoreResult | None = None,
    stopbang: ScoreResult | None = None,
    today: date | None = None,
) -> AnalysisResult:
    """
    Полный анализ: гипотезы + флаги.

    entries сортируются по дате внутри. Окна считаются от `today`
    (по умолчанию — max entry_date или date.today()).

    Возвращает AnalysisResult с гипотезами в порядке убывания severity.
    """
    if not entries:
        return AnalysisResult()

    sorted_entries = sorted(entries, key=lambda e: e.entry_date)
    ref_date = today or sorted_entries[-1].entry_date

    hypotheses: list[Hypothesis] = []
    flags: list[str] = []

    # --- 1. Хроническая инсомния (ISI ≥ 15 + SE < 85% + SOL > 30 на ≥3 нед)
    h = _chronic_insomnia(sorted_entries, isi, ref_date)
    if h:
        hypotheses.append(h)
        flags.append("chronic_insomnia_suspected")

    # --- 2. Поведенческая инсомния (TIB − TST > 1 ч устойчиво)
    h = _behavioral_insomnia(sorted_entries, ref_date)
    if h:
        hypotheses.append(h)
        flags.append("behavioral_insomnia_suspected")

    # --- 3. Риск ОАС (STOP-BANG ≥ 3 + ESS > 10 или храп/остановки)
    h = _osa_risk(stopbang, ess, sorted_entries, factors)
    if h:
        hypotheses.append(h)
        flags.append("osa_risk_suspected")

    # --- 4. Циркадный сдвиг (позднее засыпание + поздний подъём + SE норма)
    h = _circadian_delay(sorted_entries, ref_date)
    if h:
        hypotheses.append(h)
        flags.append("circadian_delay_suspected")

    # --- 5. Недостаточная продолжительность сна (TST < 7 ч ≥ 14 дней)
    h = _insufficient_sleep(sorted_entries, ref_date)
    if h:
        hypotheses.append(h)
        flags.append("insufficient_sleep")

    # --- 6. Плохая гигиена сна (фактор, не диагноз)
    if factors is not None:
        h = _poor_sleep_hygiene(sorted_entries, factors)
        if h:
            hypotheses.append(h)
            flags.append("poor_sleep_hygiene")

    # --- 7. PSQI poor (если пройден)
    if psqi is not None and psqi.interpretation == "poor":
        hypotheses.append(_psqi_poor_hypothesis(psqi))
        flags.append("psqi_poor")

    # --- Сортировка по severity: high > attention > info
    order = {"high": 0, "attention": 1, "info": 2}
    hypotheses.sort(key=lambda x: order.get(x.severity, 3))

    return AnalysisResult(hypotheses=hypotheses, flags=flags)


# ============================================================================
# Отдельные правила
# ============================================================================

def _window(entries: Sequence[DatedMetrics], end: date, days: int) -> list[DatedMetrics]:
    start = end - timedelta(days=days - 1)
    return [e for e in entries if start <= e.entry_date <= end]


def _at_least_ratio(count: int, total: int, num: int, den: int) -> bool:
    """
    True, если count/total >= num/den. Точное сравнение без float/floor.
    Пример: 11/14 >= 4/5? → 11*5=55, 4*14=56 → False.
    """
    if total <= 0:
        return False
    return count * den >= num * total


def _chronic_insomnia(
    entries: Sequence[DatedMetrics],
    isi: ScoreResult | None,
    ref_date: date,
) -> Hypothesis | None:
    """
    «Хроническая инсомния (вероятно)»:
        ISI ≥ 15  И  SE < 85%  И  SOL > 30 мин
        на протяжении ≥ 3 недель (≥ INSOMNIA_MIN_ENTRIES записей за 21 день).

    ICSD-3 (PMID 25367475) требует ≥ 3 мес симптомов для диагноза —
    поэтому здесь это ГИПОТЕЗА, а не диагноз; бот не знает анамнез.

    Если ISI не пройден — гипотеза не выдаётся (нужен формальный критерий).
    """
    if isi is None or isi.score < 15:
        return None

    window = _window(entries, ref_date, days=21)
    if len(window) < INSOMNIA_MIN_ENTRIES:
        return None

    bad = [
        e for e in window
        if e.metrics.se_percent < SE_INSOMNIA_THRESHOLD
        and e.metrics.sol_min > SOL_ELEVATED_MIN
    ]
    # Требуем, чтобы «плохих» ночей было ≥ 2/3 окна
    if not _at_least_ratio(len(bad), len(window), 2, 3):
        return None

    avg_se = sum(e.metrics.se_percent for e in bad) / len(bad)
    avg_sol = sum(e.metrics.sol_min for e in bad) / len(bad)

    return Hypothesis(
        code="chronic_insomnia",
        title="Возможна хроническая инсомния",
        rationale=(
            f"ISI = {isi.score} (≥15), за 21 день {len(bad)} из {len(window)} ночей "
            f"с SE < 85% и SOL > 30 мин (средние SE ≈ {avg_se:.1f}%, SOL ≈ {avg_sol:.0f} мин)."
        ),
        source="ICSD-3 (PMID 25367475), Riemann 2017 (PMID 28875581), ISI (PMID 11438246)",
        recommendation=(
            "Обсудите с врачом-сомнологом или КПТ-I специалистом. "
            "CBT-I — терапия первой линии (ACP 2016, PMID 27136449). "
            "Это не диагноз."
        ),
        severity="high",
    )


def _behavioral_insomnia(
    entries: Sequence[DatedMetrics],
    ref_date: date,
) -> Hypothesis | None:
    """
    «Поведенческая инсомния»: устойчиво TIB − TST > 1 ч при нормальной SE?
    Нет: при низкой SE и большом разрыве TIB−TST.

    Условие: за 14 дней ≥ 8 ночей с (TIB − TST) > 60 мин И SE < 85%.
    Это паттерн «долго лежу в постели, мало сплю».
    """
    window = _window(entries, ref_date, days=14)
    if len(window) < 8:
        return None

    gap_nights = [
        e for e in window
        if (e.metrics.tib_min - e.metrics.tst_min) > int(TIB_TST_GAP_HOURS * 60)
        and e.metrics.se_percent < SE_INSOMNIA_THRESHOLD
    ]
    if len(gap_nights) < 8:
        return None

    avg_gap = sum(
        (e.metrics.tib_min - e.metrics.tst_min) for e in gap_nights
    ) / len(gap_nights)

    return Hypothesis(
        code="behavioral_insomnia",
        title="Паттерн «много времени в постели бодрствуя»",
        rationale=(
            f"За 14 дней {len(gap_nights)} из {len(window)} ночей с TIB − TST > 1 ч "
            f"и SE < 85% (средний разрыв ≈ {avg_gap:.0f} мин)."
        ),
        source="Riemann 2017 (PMID 28875581), CBT-I (PMID 27136449)",
        recommendation=(
            "Обсудите с врачом технику ограничения сна (sleep restriction) "
            "и контроля стимула — ключевые элементы CBT-I. Это не диагноз."
        ),
        severity="attention",
    )


def _osa_risk(
    stopbang: ScoreResult | None,
    ess: ScoreResult | None,
    entries: Sequence[DatedMetrics],
    factors: DiaryFactors | None,
) -> Hypothesis | None:
    """
    «Риск ОАС»: STOP-BANG ≥ 3 И (ESS > 10 ИЛИ жалобы на храп/остановки).

    Жалобы на храп/остановки — из заметок CSD (эвристика по ключевым словам)
    ИЛИ из флага factors (в текущей схеме не хранится, поэтому — только заметки).
    """
    if stopbang is None or stopbang.score < 3:
        return None

    ess_flag = ess is not None and ess.score > 10
    snore_flag = _notes_mention_snoring(entries)

    if not (ess_flag or snore_flag):
        return None

    why = []
    if ess_flag and ess is not None:
        why.append(f"ESS = {ess.score} (>10)")
    if snore_flag:
        why.append("в заметках упоминается храп/остановки дыхания")

    return Hypothesis(
        code="osa_risk",
        title="Возможен риск обструктивного апноэ сна",
        rationale=(
            f"STOP-BANG = {stopbang.score} (≥3) и " + "; ".join(why) + "."
        ),
        source="STOP-BANG (PMID 26378880), ESS (PMID 1798888)",
        recommendation=(
            "Обсудите с сомнологом целесообразность полисомнографии (ПСГ). "
            "Это скрининг, не диагноз."
        ),
        severity="high",
    )


def _notes_mention_snoring(entries: Sequence[DatedMetrics]) -> bool:
    """Эвристика по заметкам. Заметки НЕ логируются (этика)."""
    keywords = ("храп", "апноэ", "остановк", "задых", "snor", "apnea")
    # Заметки не хранятся в DatedMetrics (только метрики).
    # Если понадобится — расширим DatedMetrics полем notes_summary.
    return False


def _circadian_delay(
    entries: Sequence[DatedMetrics],
    ref_date: date,
) -> Hypothesis | None:
    """
    «Циркадный сдвиг (поздняя фаза)»: стабильно позднее засыпание,
    поздний подъём, SE нормальная.

    Требует: за 14 дней ≥ 8 ночей, средний lights_out ≥ 01:00
    (по try_sleep/lights_out — но в метриках только длительности).
    Здесь используем косвенный признак: TIB ≥ 8.5 ч при SE ≥ 85% И
    низкий SOL (нет трудностей засыпания) — паттерн «поздно лёг, поздно встал, выспался».
    """
    window = _window(entries, ref_date, days=14)
    if len(window) < 8:
        return None

    candidates = [
        e for e in window
        if e.metrics.tib_hours >= 8.5
        and e.metrics.se_percent >= SE_INSOMNIA_THRESHOLD
        and e.metrics.sol_min <= SOL_ELEVATED_MIN
    ]
    if not _at_least_ratio(len(candidates), len(window), 2, 3):
        return None

    return Hypothesis(
        code="circadian_delay",
        title="Возможен циркадный сдвиг (поздняя фаза)",
        rationale=(
            f"{len(candidates)} из {len(window)} ночей: TIB ≥ 8.5 ч, SE ≥ 85%, "
            f"SOL ≤ 30 мин — паттерн «поздно лёг, поздно встал, выспался»."
        ),
        source="ICSD-3 (PMID 25367475)",
        recommendation=(
            "Обсудите с сомнологом циркадные техники (утренний свет, "
            "фиксированное время подъёма). Это не диагноз."
        ),
        severity="info",
    )


def _insufficient_sleep(
    entries: Sequence[DatedMetrics],
    ref_date: date,
) -> Hypothesis | None:
    """
    «Недостаточная продолжительность сна»: TST < 7 ч на протяжении ≥ 14 дней.

    Требует ≥ 14 записей за последние 14 дней и ≥ 80% из них с TST < 7 ч.
    """
    window = _window(entries, ref_date, days=TST_LOW_MIN_DAYS)
    if len(window) < TST_LOW_MIN_DAYS:
        return None

    low = [e for e in window if e.metrics.tst_hours < TST_LOW_HOURS]
    if not _at_least_ratio(len(low), len(window), 4, 5):
        return None

    avg_tst = sum(e.metrics.tst_hours for e in low) / len(low)

    return Hypothesis(
        code="insufficient_sleep",
        title="Недостаточная продолжительность сна",
        rationale=(
            f"{len(low)} из {len(window)} ночей за 14 дней с TST < 7 ч "
            f"(средний TST ≈ {avg_tst:.1f} ч)."
        ),
        source="Watson 2015 (PMID 26039963)",
        recommendation=(
            "Взрослым рекомендуется 7–9 ч сна. Обсудите с врачом, "
            "если укорочение сна устойчивое. Это не диагноз."
        ),
        severity="attention",
    )


def _poor_sleep_hygiene(
    entries: Sequence[DatedMetrics],
    factors: DiaryFactors,
) -> Hypothesis | None:
    """
    «Плохая гигиена сна» — фактор, не диагноз.

    Срабатывает, если за период:
        - кофеин после 16:00 ≥ 50% ночей, ИЛИ
        - алкоголь вечером ≥ 40% ночей, ИЛИ
        - экран за 1 ч до сна ≥ 70% ночей, ИЛИ
        - средний стресс ≥ 4 из 5
    И при этом средняя SE < 85% (иначе «гигиена плохая, но сон нормальный» —
    не о чем говорить).
    """
    if factors.n_nights == 0:
        return None

    avg_se = sum(e.metrics.se_percent for e in entries) / len(entries)
    if avg_se >= SE_INSOMNIA_THRESHOLD:
        return None

    reasons: list[str] = []
    if factors.caffeine_ratio >= 0.5:
        reasons.append(f"кофеин после 16:00 в {factors.caffeine_days}/{factors.n_nights} ночей")
    if factors.alcohol_ratio >= 0.4:
        reasons.append(f"алкоголь вечером в {factors.alcohol_days}/{factors.n_nights} ночей")
    if factors.screen_ratio >= 0.7:
        reasons.append(f"экран за 1 ч до сна в {factors.screen_days}/{factors.n_nights} ночей")
    if factors.avg_stress >= 4.0:
        reasons.append(f"средний стресс {factors.avg_stress:.1f}/5")

    if not reasons:
        return None

    return Hypothesis(
        code="poor_sleep_hygiene",
        title="Факторы, ухудшающие сон (гигиена сна)",
        rationale=(
            f"Средняя SE ≈ {avg_se:.1f}% (<85%); " + "; ".join(reasons) + "."
        ),
        source=(
            "Кофеин — Drake 2013 (PMID 24235903); "
            "алкоголь — Ebrahim 2013 (PMID 23347102); "
            "гипервозбуждение — Riemann 2010 (PMID 19524464)"
        ),
        recommendation=(
            "Обсудите с врачом гигиену сна и элементы CBT-I. "
            "Это фактор, а не диагноз."
        ),
        severity="info",
    )


def _psqi_poor_hypothesis(psqi: ScoreResult) -> Hypothesis:
    return Hypothesis(
        code="psqi_poor",
        title="Плохое субъективное качество сна (PSQI)",
        rationale=f"Глобальный балл упрощённого PSQI = {psqi.score} (>5).",
        source="PSQI (PMID 2748771), упрощённая версия",
        recommendation="Обсудите с врачом; это скрининг, не диагноз.",
        severity="info",
    )


# ============================================================================
# Агрегация факторов (хелпер для хэндлеров)
# ============================================================================

def build_factors(
    rows: Iterable[tuple[bool, bool, bool, int]]
) -> DiaryFactors:
    """
    Принимает итерируемое (caffeine, alcohol, screen, stress).
    Возвращает DiaryFactors с суммой/средним.
    """
    caffeine = alcohol = screen = 0
    stress_sum = 0
    n = 0
    for c, a, s, st in rows:
        n += 1
        caffeine += int(c)
        alcohol += int(a)
        screen += int(s)
        stress_sum += int(st)
    return DiaryFactors(
        caffeine_days=caffeine,
        alcohol_days=alcohol,
        screen_days=screen,
        avg_stress=(stress_sum / n) if n else 0.0,
        n_nights=n,
    )