"""
Подсчёт и интерпретация скрининговых опросников.

Все функции — чистые (без I/O, без aiogram). Принимают список/словарь ответов,
возвращают dataclass с баллом, интерпретацией и текстовым пояснением.

Источники:
    ISI       — Bastien C.H. et al., Sleep Med 2001;2(4):297–307. PMID 11438246
    PSQI      — Buysse D.J. et al., Psychiatry Res 1989;28(2):193–213. PMID 2748771
    ESS       — Johns M.W., Sleep 1991;14(6):540–545. PMID 1798888
    STOP-BANG — Chung F. et al., Chest 2016;149(3):631–638. PMID 26378880
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from bot.constants import (
    ESS_BORDERLINE_MAX,
    ESS_EXCESSIVE_MIN,
    ESS_ITEMS_COUNT,
    ESS_MAX_SCORE,
    ESS_NORMAL_MAX,
    ISI_BANDS,
    ISI_CLINICAL_MIN,
    ISI_ITEMS_COUNT,
    ISI_MAX_SCORE,
    PSQI_MAX_GLOBAL,
    PSQI_POOR_THRESHOLD,
    STOPBANG_HIGH_MIN,
    STOPBANG_INTERMEDIATE_MAX,
    STOPBANG_ITEMS_COUNT,
    STOPBANG_LOW_MAX,
    STOPBANG_MAX_SCORE,
    STOPBANG_RISK_MIN,
)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """
    Результат опросника.

    score            — суммарный балл
    interpretation   — машинный код ('none', 'subclinical', 'moderate', ...)
    label            — человекочитаемая метка
    explanation      — 1–2 предложения для пользователя (без диагноза)
    flags            — машинные флаги для analysis.py (например, 'isi_clinical')
    source           — PMID для прозрачности
    """
    score: int
    interpretation: str
    label: str
    explanation: str
    flags: tuple[str, ...] = field(default_factory=tuple)
    source: str = ""


# ============================================================================
# ISI — Insomnia Severity Index
# ============================================================================

ISI_QUESTIONS: Final[tuple[str, ...]] = (
    "Трудности с засыпанием",
    "Трудности с поддержанием сна",
    "Проблема раннего пробуждения",
    "Неудовлетворённость текущим сном",
    "Влияние проблем со сном на дневное functioning",
    "Заметность проблем со сном для окружающих",
    "Беспокойство/огорчение из-за проблем со сном",
)


def score_isi(answers: list[int]) -> ScoreResult:
    """
    ISI: 7 пунктов, каждый 0–4, сумма 0–28.

    Интерпретация (PMID 11438246):
        0–7   — нет клинически значимой инсомнии
        8–14  — субклиническая инсомния
        15–21 — клиническая инсомния (умеренная)
        22–28 — тяжёлая клиническая инсомния

    Raises:
        ValueError: если длина != 7 или значения вне 0–4.
    """
    _validate_answers(answers, expected=ISI_ITEMS_COUNT, lo=0, hi=4, name="ISI")
    total = sum(answers)
    assert total <= ISI_MAX_SCORE

    for lo, hi, code in ISI_BANDS:
        if lo <= total <= hi:
            break
    else:  # pragma: no cover — покрыт диапазоном
        code = "severe"

    labels = {
        "none": "Нет клинически значимой инсомнии",
        "subclinical": "Субклиническая инсомния",
        "moderate": "Клиническая инсомния (умеренная)",
        "severe": "Тяжёлая клиническая инсомния",
    }
    explanations = {
        "none": "Симптомы инсомнии выражены минимально или отсутствуют.",
        "subclinical": "Есть отдельные симптомы, но они ниже клинического порога.",
        "moderate": (
            "Балл соответствует клинически значимой инсомнии. "
            "Это скрининг, не диагноз — обсудите с врачом."
        ),
        "severe": (
            "Выраженные симптомы инсомнии. Рекомендуется консультация специалиста "
            "по сну. Это скрининг, не диагноз."
        ),
    }
    flags: list[str] = []
    if total >= ISI_CLINICAL_MIN:
        flags.append("isi_clinical")

    return ScoreResult(
        score=total,
        interpretation=code,
        label=labels[code],
        explanation=explanations[code],
        flags=tuple(flags),
        source="PMID 11438246",
    )


# ============================================================================
# ESS — Epworth Sleepiness Scale
# ============================================================================

ESS_QUESTIONS: Final[tuple[str, ...]] = (
    "Сидя и читая",
    "Смотря телевизор",
    "Сидя пассивно в общественном месте (театр, собрание)",
    "В качестве пассажира в машине при часовой поездке без перерыва",
    "Лёжа отдохнуть днём, если есть возможность",
    "Сидя и разговаривая с кем-то",
    "Сидя спокойно после обеда без алкоголя",
    "В машине, остановившись на несколько минут в пробке",
)


def score_ess(answers: list[int]) -> ScoreResult:
    """
    ESS: 8 ситуаций, каждая 0–3, сумма 0–24.

    Интерпретация (PMID 1798888):
        0–10   — норма
        11–12  — пограничная дневная сонливость
        >12    — избыточная дневная сонливость

    Raises:
        ValueError: длина != 8 или значения вне 0–3.
    """
    _validate_answers(answers, expected=ESS_ITEMS_COUNT, lo=0, hi=3, name="ESS")
    total = sum(answers)
    assert total <= ESS_MAX_SCORE

    if total <= ESS_NORMAL_MAX:
        code = "normal"
        label = "Нормальная дневная сонливость"
        explanation = "Уровень дневной сонливости в пределах нормы."
        flags: tuple[str, ...] = ()
    elif total <= ESS_BORDERLINE_MAX:
        code = "borderline"
        label = "Пограничная дневная сонливость"
        explanation = (
            "Сонливость на границе нормы. Стоит обсудить с врачом, "
            "если она мешает днём."
        )
        flags = ("ess_borderline",)
    else:
        assert total >= ESS_EXCESSIVE_MIN
        code = "excessive"
        label = "Избыточная дневная сонливость"
        explanation = (
            "Избыточная дневная сонливость — повод для скрининга апноэ сна "
            "и консультации сомнолога. Это не диагноз."
        )
        flags = ("ess_excessive",)

    return ScoreResult(
        score=total,
        interpretation=code,
        label=label,
        explanation=explanation,
        flags=flags,
        source="PMID 1798888",
    )


# ============================================================================
# STOP-BANG
# ============================================================================

STOPBANG_QUESTIONS: Final[tuple[str, ...]] = (
    "Snoring: громко храпите (слышно за закрытой дверью)?",
    "Tired: чувствуете усталость/сонливость днём?",
    "Observed: кто-то наблюдал остановки дыхания во сне?",
    "Pressure: у вас повышенное артериальное давление?",
    "BMI: ИМТ > 35 кг/м²?",
    "Age: возраст > 50 лет?",
    "Neck: окружность шеи > 40 см?",
    "Gender: мужской пол?",
)


def score_stopbang(answers: list[bool]) -> ScoreResult:
    """
    STOP-BANG: 8 вопросов да/нет, сумма 0–8.

    Интерпретация (PMID 26378880):
        0–2 — низкий риск ОАС
        3–4 — промежуточный риск
        5–8 — высокий риск

    Raises:
        ValueError: длина != 8.
    """
    if len(answers) != STOPBANG_ITEMS_COUNT:
        raise ValueError(
            f"STOP-BANG ожидает {STOPBANG_ITEMS_COUNT} ответов, получено {len(answers)}"
        )
    total = sum(1 for a in answers if a)
    assert total <= STOPBANG_MAX_SCORE

    if total <= STOPBANG_LOW_MAX:
        code = "low"
        label = "Низкий риск апноэ сна"
        explanation = "По STOP-BANG риск обструктивного апноэ низкий."
        flags: tuple[str, ...] = ()
    elif total <= STOPBANG_INTERMEDIATE_MAX:
        code = "intermediate"
        label = "Промежуточный риск апноэ сна"
        explanation = (
            "Промежуточный риск апноэ сна. Обсудите с врачом целесообразность "
            "полисомнографии. Это скрининг, не диагноз."
        )
        flags = ("stopbang_intermediate",)
    else:
        assert total >= STOPBANG_HIGH_MIN
        code = "high"
        label = "Высокий риск апноэ сна"
        explanation = (
            "Высокий риск обструктивного апноэ сна. Рекомендуется консультация "
            "сомнолога и полисомнография. Это скрининг, не диагноз."
        )
        flags = ("stopbang_high",)

    if total >= STOPBANG_RISK_MIN:
        flags = flags + ("stopbang_risk",)

    return ScoreResult(
        score=total,
        interpretation=code,
        label=label,
        explanation=explanation,
        flags=flags,
        source="PMID 26378880",
    )


# ============================================================================
# PSQI — упрощённая версия
# ============================================================================

@dataclass(frozen=True, slots=True)
class PSQIInput:
    """
    Упрощённый PSQI (5 из 7 компонентов).

    Опущены:
        - дневная дисфункция (компонент 7)
        - необходимость медикаментов для сна (компонент 6)

    Используются:
        C1 (качество)       — 0–3
        C2 (латентность)    — 0–3
        C3 (длительность)   — 0–3
        C4 (эффективность)  — 0–3
        C5 (нарушения сна)  — 0–3

    Глобальный балл = сумма 5 компонентов (0–15). Для сопоставимости
    с оригинальной шкалой (0–21) глобальный балл нормируется ×(21/15) = ×1.4.
    Порог «плохое качество» — нормированный балл > 5 (PMID 2748771).
    Явное упрощение документировано в docs/methodology.md.
    """
    c1_quality: int
    c2_latency: int
    c3_duration: int
    c4_efficiency: int
    c5_disturbances: int


PSQI_NORMALIZATION: Final[float] = PSQI_MAX_GLOBAL / 15.0  # 1.4


def score_psqi(inp: PSQIInput) -> ScoreResult:
    """
    PSQI (упрощённый). См. PSQIInput для состава компонентов.

    Каждый компонент 0–3. Сумма 0–15 → нормировка ×1.4 → 0–21.
    Глобальный балл > 5 = плохое качество сна (PMID 2748771).

    Raises:
        ValueError: если компонент вне 0–3.
    """
    for name, v in (
        ("c1_quality", inp.c1_quality),
        ("c2_latency", inp.c2_latency),
        ("c3_duration", inp.c3_duration),
        ("c4_efficiency", inp.c4_efficiency),
        ("c5_disturbances", inp.c5_disturbances),
    ):
        if not 0 <= v <= 3:
            raise ValueError(f"PSQI: {name} должен быть 0–3, получено {v}")

    raw = (
        inp.c1_quality + inp.c2_latency + inp.c3_duration
        + inp.c4_efficiency + inp.c5_disturbances
    )
    global_score = round(raw * PSQI_NORMALIZATION)

    if global_score <= PSQI_POOR_THRESHOLD:
        code = "good"
        label = "Хорошее качество сна (по упрощённому PSQI)"
        explanation = "Глобальный балл в пределах нормы."
        flags: tuple[str, ...] = ()
    else:
        code = "poor"
        label = "Плохое качество сна (по упрощённому PSQI)"
        explanation = (
            "Глобальный балл > 5 указывает на плохое качество сна. "
            "Это скрининг, не диагноз. Упрощённая версия — см. /about."
        )
        flags = ("psqi_poor",)

    return ScoreResult(
        score=global_score,
        interpretation=code,
        label=label,
        explanation=explanation,
        flags=flags,
        source="PMID 2748771 (упрощённая версия)",
    )


# ============================================================================
# Внутренние хелперы
# ============================================================================

def _validate_answers(
    answers: list[int], *, expected: int, lo: int, hi: int, name: str
) -> None:
    if len(answers) != expected:
        raise ValueError(f"{name}: ожидается {expected} ответов, получено {len(answers)}")
    for i, v in enumerate(answers, start=1):
        if not lo <= v <= hi:
            raise ValueError(f"{name}: ответ #{i} вне диапазона {lo}–{hi}: {v}")