from app.schemas.contracts import CriterionScoreIn, ScenarioCriterion

RUBRIC_VERSION = "1.0"
CRITERIA = (
    ScenarioCriterion.RELEVANCE,
    ScenarioCriterion.STRUCTURE,
    ScenarioCriterion.CLARITY,
    ScenarioCriterion.COMPOSURE,
    ScenarioCriterion.CONCISENESS,
    ScenarioCriterion.LANGUAGE_ACCURACY,
)
WEIGHTS = {
    ScenarioCriterion.RELEVANCE: 25,
    ScenarioCriterion.STRUCTURE: 20,
    ScenarioCriterion.CLARITY: 20,
    ScenarioCriterion.COMPOSURE: 15,
    ScenarioCriterion.CONCISENESS: 10,
    ScenarioCriterion.LANGUAGE_ACCURACY: 10,
}
BAND_DESCRIPTIONS = {
    ScenarioCriterion.RELEVANCE: (
        "Off-topic or ignores the question",
        "Partly on topic; mostly generic or tangential",
        "Answers the question but claims are generic or unsupported",
        "Directly answers with specific, relevant examples",
        "Precisely answers every question with concrete evidence tailored to the scenario task",
    ),
    ScenarioCriterion.STRUCTURE: (
        "No discernible order",
        "Ideas present but order confusing; key parts missing",
        "Basic order; elements missing or transitions unclear",
        "Clear flow with most elements present",
        "Consistently well-organised with a clear point, support, and result",
    ),
    ScenarioCriterion.CLARITY: (
        "Largely hard to understand or ambiguous",
        "Frequent vagueness or unexplained jargon",
        "Understandable with some vague or ambiguous statements",
        "Clear and precise with minor ambiguity",
        "Immediately understandable, precise and concrete throughout",
    ),
    ScenarioCriterion.COMPOSURE: (
        "Defensive, hostile, or abandons answers when challenged",
        "Visibly flustered: rambling, apologising, or self-contradicting",
        "Holds up but hedges or yields easily when pushed",
        "Stays professional and answers challenges directly",
        "Handles pushback confidently and reframes constructively",
    ),
    ScenarioCriterion.CONCISENESS: (
        "Extremely rambling, or answers too short to be useful",
        "Frequent repetition or padding, or too terse to convey the point",
        "Sometimes wordy or incomplete",
        "Efficient with minor padding",
        "Every sentence adds value; length matches the question",
    ),
    ScenarioCriterion.LANGUAGE_ACCURACY: (
        "Errors regularly impede understanding",
        "Frequent errors, limited vocabulary or inappropriate register",
        "Noticeable errors but meaning stays clear",
        "Occasional minor errors; appropriate vocabulary",
        "Accurate, varied, professional language",
    ),
}
RUBRIC_DESCRIPTIONS = BAND_DESCRIPTIONS


def compute_overall_score(criteria: list[CriterionScoreIn]) -> int:
    if len(criteria) != len(CRITERIA):
        raise ValueError("Exactly six criterion scores are required")
    scores = {item.criterion: item.score for item in criteria}
    if set(scores) != set(CRITERIA):
        raise ValueError("Each rubric criterion must appear exactly once")
    weighted_sum = sum(WEIGHTS[key] * scores[key] for key in CRITERIA)
    return (weighted_sum + 5) // 10


def weighted_points(score: int, criterion: ScenarioCriterion) -> float:
    if not 0 <= score <= 10:
        raise ValueError("Score must be between 0 and 10")
    return round(score * WEIGHTS[criterion] / 10, 1)
