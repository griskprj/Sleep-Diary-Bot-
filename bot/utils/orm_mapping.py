"""Преобразование ORM-строк в dataclass'ы сервисов."""
from __future__ import annotations

from bot.db.models import Questionnaire
from bot.services.questionnaires import ScoreResult

_LABELS = {
    "ISI": {
        "none": "нет клинически значимой инсомнии",
        "subclinical": "субклиническая инсомния",
        "moderate": "клиническая инсомния (умеренная)",
        "severe": "тяжёлая клиническая инсомния",
    },
    "PSQI": {"good": "хорошее качество сна", "poor": "плохое качество сна"},
    "ESS": {
        "normal": "норма",
        "borderline": "пограничная сонливость",
        "excessive": "избыточная сонливость",
    },
    "STOPBANG": {
        "low": "низкий риск ОАС",
        "intermediate": "промежуточный риск ОАС",
        "high": "высокий риск ОАС",
    },
}


def questionnaire_to_score_result(row: Questionnaire | None) -> ScoreResult | None:
    if row is None:
        return None
    label = _LABELS.get(row.type, {}).get(row.interpretation, row.interpretation)
    return ScoreResult(
        score=row.score,
        interpretation=row.interpretation,
        label=label,
        explanation="",
        flags=(),
        source="",
    )