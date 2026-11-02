"""
Персональные рекомендации по CBT-I и гигиене сна.

Принципы:
    - Только доказательные элементы (CBT-I — терапия 1-й линии, ACP 2016).
    - Никаких фармакологических советов (мелатонин, снотворные) — только
      «обсудите с врачом».
    - Каждая рекомендация привязана к конкретным данным пользователя;
      без данных — не выдаётся.
    - Тон нейтральный, клинический. Никаких «волшебных» эмодзи-советов.

Источники:
    CBT-I               — Qaseem A. et al., Ann Intern Med 2016. PMID 27136449
    Stimulus control    — Bootzin R.R., 1972; Riemann 2017. PMID 28875581
    Sleep restriction   — Spielman A.J., 1987; Riemann 2017. PMID 28875581
    Circadian anchor    — Watson 2015. PMID 26039963
    Кофеин              — Drake 2013. PMID 24235903
    Алкоголь            — Ebrahim 2013. PMID 23347102
    Гипервозбуждение    — Riemann 2010. PMID 19524464
    Свет и мелатонин    — Chang A.M. et al., PNAS 2015. PMID 25605877
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from bot.constants import (
    CAFFEINE_CUTOFF_HOUR,
    SCREEN_CUTOFF_MIN_BEFORE_BED,
    SE_INSOMNIA_THRESHOLD,
    SOL_ELEVATED_MIN,
    TST_LOW_HOURS,
    WASO_ELEVATED_MIN,
)
from bot.services.analysis import AnalysisResult, DiaryFactors
from bot.services.metrics import PeriodStats
from bot.services.questionnaires import ScoreResult


@dataclass(frozen=True, slots=True)
class Recommendation:
    """
    Одна рекомендация.

    code       — машинный код ('stimulus_control', 'sleep_restriction', ...)
    title      — краткий заголовок
    body       — 1–3 предложения, конкретно и по делу
    rationale  — «почему вам это» (метрики/данные)
    source     — PMID
    priority   — 1 (высокий) … 5 (низкий) — для сортировки
    """
    code: str
    title: str
    body: str
    rationale: str
    source: str
    priority: int


@dataclass(frozen=True, slots=True)
class AdviceResult:
    recommendations: list[Recommendation] = field(default_factory=list)
    disclaimer: str = (
        "Это не диагноз и не назначение. Рекомендации основаны на ваших "
        "записях и валидированных шкалах. Обсудите их с врачом."
    )


def build_advice(
    *,
    analysis: AnalysisResult,
    stats: PeriodStats,
    factors: DiaryFactors | None = None,
    isi: ScoreResult | None = None,
    psqi: ScoreResult | None = None,
    ess: ScoreResult | None = None,
    stopbang: ScoreResult | None = None,
) -> AdviceResult:
    """
    Собирает рекомендации на основе анализа и метрик.

    Возвращает AdviceResult, отсортированный по priority (1 → 5).
    Дубликаты по code устраняются (первая побеждает).
    """
    recs: list[Recommendation] = []
    codes = analysis.flags

    # --- Приоритет 1: срочные направления к врачу (не советы по гигиене)
    if "osa_risk_suspected" in codes:
        recs.append(_osa_referral(stopbang, ess))

    if "chronic_insomnia_suspected" in codes:
        recs.append(_cbti_referral(isi))

    # --- Приоритет 2: ключевые элементы CBT-I
    if stats.n_nights > 0:
        if (
            stats.avg_se_percent < SE_INSOMNIA_THRESHOLD
            or stats.median_se_percent < SE_INSOMNIA_THRESHOLD
        ):
            recs.append(_stimulus_control(stats))

        if "behavioral_insomnia_suspected" in codes:
            recs.append(_sleep_restriction(stats))

    # --- Приоритет 3: циркадный якорь (фиксированный подъём)
    if (
        "circadian_delay_suspected" in codes
        or stats.n_nights >= 7  # раз есть данные — фиксированный подъём полезен
    ):
        recs.append(_circadian_anchor(stats))

    # --- Приоритет 3: недостаточная длительность
    if "insufficient_sleep" in codes:
        recs.append(_extend_sleep(stats))

    # --- Приоритет 4: гигиена сна, привязанная к факторам
    if factors is not None:
        if factors.caffeine_ratio >= 0.5:
            recs.append(_caffeine(factors))
        if factors.alcohol_ratio >= 0.4:
            recs.append(_alcohol(factors))
        if factors.screen_ratio >= 0.7:
            recs.append(_screens(factors))
        if factors.avg_stress >= 4.0:
            recs.append(_stress(factors))

    # --- Приоритет 4: PSQI poor → общая гигиена + CBT-I
    if "psqi_poor" in codes:
        recs.append(_psqi_general(psqi))

    # --- Приоритет 5: релаксация (всем, у кого есть данные)
    if stats.n_nights >= 3:
        recs.append(_relaxation())

    # Дедуп по code
    seen: set[str] = set()
    unique: list[Recommendation] = []
    for r in recs:
        if r.code not in seen:
            seen.add(r.code)
            unique.append(r)

    unique.sort(key=lambda r: r.priority)
    return AdviceResult(recommendations=unique)


# ============================================================================
# Отдельные рекомендации
# ============================================================================

def _osa_referral(
    stopbang: ScoreResult | None, ess: ScoreResult | None
) -> Recommendation:
    parts = []
    if stopbang is not None:
        parts.append(f"STOP-BANG = {stopbang.score}")
    if ess is not None and ess.score > 10:
        parts.append(f"ESS = {ess.score}")
    why = ", ".join(parts) or "скрининг указал на риск"

    return Recommendation(
        code="osa_referral",
        title="Консультация сомнолога по поводу апноэ сна",
        body=(
            "Обсудите с врачом-сомнологом целесообразность полисомнографии (ПСГ). "
            "При подтверждении ОАС есть эффективные методы лечения (СИПАП и др.); "
            "самолечение не рекомендуется."
        ),
        rationale=f"{why} — скрининговый порог риска ОАС превышен.",
        source="STOP-BANG (PMID 26378880), ESS (PMID 1798888)",
        priority=1,
    )


def _cbti_referral(isi: ScoreResult | None) -> Recommendation:
    isi_note = f"ISI = {isi.score} (≥15)" if isi is not None else "клинические критерии"
    return Recommendation(
        code="cbti_referral",
        title="Обсудить CBT-I со специалистом",
        body=(
            "CBT-I (когнитивно-поведенческая терапия инсомнии) — терапия первой "
            "линии при хронической инсомнии. Обсудите с врачом или психологом, "
            "прошедшим подготовку по CBT-I."
        ),
        rationale=f"{isi_note} в сочетании с устойчиво низкой SE и удлинённым SOL.",
        source="ACP 2016 (PMID 27136449), Riemann 2017 (PMID 28875581)",
        priority=1,
    )


def _stimulus_control(stats: PeriodStats) -> Recommendation:
    return Recommendation(
        code="stimulus_control",
        title="Контроль стимула",
        body=(
            "Если не спится более 20 минут — встаньте, уйдите в другую комнату, "
            "займитесь спокойным делом при тусклом свете. Возвращайтесь в постель "
            "только при сонливости. Кровать — только для сна."
        ),
        rationale=(
            f"Средняя SE ≈ {stats.avg_se_percent:.1f}% (<85%) — "
            f"признак того, что постель ассоциируется с бодрствованием."
        ),
        source="Riemann 2017 (PMID 28875581), CBT-I (PMID 27136449)",
        priority=2,
    )


def _sleep_restriction(stats: PeriodStats) -> Recommendation:
    suggested_window = round((stats.avg_tst_min + 30) / 60.0, 1)
    return Recommendation(
        code="sleep_restriction",
        title="Ограничение сна (sleep restriction)",
        body=(
            f"Сократите окно сна до ≈ {suggested_window} ч (средний TST + ~30 мин), "
            "фиксируйте время подъёма. По мере роста SE окно расширяется. "
            "Технику лучше осваивать под руководством специалиста по CBT-I."
        ),
        rationale=(
            f"Средний TST ≈ {stats.avg_tst_min / 60:.1f} ч при средней SE "
            f"≈ {stats.avg_se_percent:.1f}% — типичный паттерн «много времени "
            "в постели, мало сна»."
        ),
        source="Spielman 1987; Riemann 2017 (PMID 28875581), ACP 2016 (PMID 27136449)",
        priority=2,
    )


def _circadian_anchor(stats: PeriodStats) -> Recommendation:
    return Recommendation(
        code="circadian_anchor",
        title="Фиксированное время подъёма",
        body=(
            "Вставайте в одно и то же время (±30 мин) каждый день, включая "
            "выходные. Это укрепляет циркадный ритм и облегчает засыпание вечером."
        ),
        rationale=(
            f"За период {stats.n_nights} ночей — стабильный подъём помогает "
            "стабилизировать фазу сна."
        ),
        source="Watson 2015 (PMID 26039963), Riemann 2017 (PMID 28875581)",
        priority=3,
    )


def _extend_sleep(stats: PeriodStats) -> Recommendation:
    return Recommendation(
        code="extend_sleep",
        title="Увеличить продолжительность сна",
        body=(
            "Взрослым рекомендуется 7–9 ч сна. Сдвиньте отход ко сну на 15–30 мин "
            "раньше и сохраняйте фиксированное время подъёма. Резкое увеличение "
            "окна сна при низкой SE может ухудшить сон — двигайтесь постепенно."
        ),
        rationale=(
            f"Средний TST ≈ {stats.avg_tst_min / 60:.1f} ч (< {TST_LOW_HOURS:.0f} ч) "
            "на протяжении периода."
        ),
        source="Watson 2015 (PMID 26039963)",
        priority=3,
    )


def _caffeine(factors: DiaryFactors) -> Recommendation:
    return Recommendation(
        code="caffeine_cutoff",
        title="Кофеин — не позже 16:00",
        body=(
            f"Ограничьте кофе, чай, колу и энергетики после "
            f"{CAFFEINE_CUTOFF_HOUR:02d}:00. Период полувыведения кофеина ~5 ч; "
            "даже «вечерняя чашка» может удлинять засыпание."
        ),
        rationale=(
            f"Кофеин после 16:00 в {factors.caffeine_days}/{factors.n_nights} ночей."
        ),
        source="Drake 2013 (PMID 24235903)",
        priority=4,
    )


def _alcohol(factors: DiaryFactors) -> Recommendation:
    return Recommendation(
        code="alcohol_reduction",
        title="Алкоголь вечером — под вопросом",
        body=(
            "Алкоголь уменьшает REM-сон и фрагментирует вторую половину ночи. "
            "Если используете его как «снотворное» — обсудите с врачом альтернативы."
        ),
        rationale=(
            f"Алкоголь вечером в {factors.alcohol_days}/{factors.n_nights} ночей."
        ),
        source="Ebrahim 2013 (PMID 23347102)",
        priority=4,
    )


def _screens(factors: DiaryFactors) -> Recommendation:
    return Recommendation(
        code="screen_cutoff",
        title="Экраны — за 1 час до сна",
        body=(
            f"Откладывайте телефон/ноутбук/ТВ за ≥ "
            f"{SCREEN_CUTOFF_MIN_BEFORE_BED} мин до сна. Яркий свет вечером "
            "подавляет выработку мелатонина и сдвигает фазу сна. "
            "Речь о естественной выработке гормона, а не о приёме добавок."
        ),
        rationale=(
            f"Экран за 1 ч до сна в {factors.screen_days}/{factors.n_nights} ночей."
        ),
        source="Chang 2015 (PMID 25605877)",
        priority=4,
    )


def _stress(factors: DiaryFactors) -> Recommendation:
    return Recommendation(
        code="stress_management",
        title="Работа с гипервозбуждением",
        body=(
            "Гипервозбуждение — ключевой фактор инсомнии. Обсудите с врачом "
            "или психологом техники релаксации: прогрессивная мышечная релаксация, "
            "дыхание 4-7-8, «выгрузка мыслей» на бумагу за 1–2 ч до сна."
        ),
        rationale=f"Средний уровень стресса {factors.avg_stress:.1f}/5.",
        source="Riemann 2010 (PMID 19524464), CBT-I (PMID 27136449)",
        priority=4,
    )


def _psqi_general(psqi: ScoreResult | None) -> Recommendation:
    score = f" = {psqi.score}" if psqi is not None else ""
    return Recommendation(
        code="psqi_general",
        title="Системная работа над качеством сна",
        body=(
            "Плохое субъективное качество сна по PSQI — повод обсудить с врачом "
            "комплексный план: CBT-I, гигиена сна, оценка сопутствующих состояний."
        ),
        rationale=f"Глобальный балл упрощённого PSQI{score} (>5).",
        source="PSQI (PMID 2748771), ACP 2016 (PMID 27136449)",
        priority=4,
    )


def _relaxation() -> Recommendation:
    return Recommendation(
        code="relaxation",
        title="Релаксация перед сном",
        body=(
            "10–15 минут спокойной активности перед сном: дыхательные упражнения, "
            "прогрессивная мышечная релаксация, чтение бумажной книги при тусклом "
            "свете. Это элемент CBT-I, а не «снотворное»."
        ),
        rationale="Полезно как базовая практика при любом профиле сна.",
        source="CBT-I (PMID 27136449)",
        priority=5,
    )