from app.evaluation.rubric import (
    BAND_DESCRIPTIONS,
    CRITERIA,
    WEIGHTS,
    compute_overall_score,
    weighted_points,
)
from app.schemas.contracts import CriterionScoreIn


def scores(values: dict[str, int]) -> list[CriterionScoreIn]:
    return [
        CriterionScoreIn(
            criterion=criterion,
            score=values[criterion.value],
            rationale="",
            evidence_turn_ids=["trn_test"],
        )
        for criterion in CRITERIA
    ]


def test_rubric_weights_and_keys_are_consistent() -> None:
    assert sum(WEIGHTS.values()) == 100
    assert set(BAND_DESCRIPTIONS) == set(CRITERIA)


def test_backend_score_uses_half_up_rounding() -> None:
    assert (
        compute_overall_score(
            scores(
                {
                    "relevance": 7,
                    "structure": 6,
                    "clarity": 7,
                    "composure": 6,
                    "conciseness": 5,
                    "language_accuracy": 8,
                }
            )
        )
        == 66
    )
    assert (
        compute_overall_score(
            scores(
                {
                    "relevance": 7,
                    "structure": 7,
                    "clarity": 6,
                    "composure": 6,
                    "conciseness": 6,
                    "language_accuracy": 6,
                }
            )
        )
        == 65
    )


def test_backend_score_handles_extreme_scores() -> None:
    zeroes = {criterion.value: 0 for criterion in CRITERIA}
    tens = {criterion.value: 10 for criterion in CRITERIA}
    assert compute_overall_score(scores(zeroes)) == 0
    assert compute_overall_score(scores(tens)) == 100
    assert sum(weighted_points(10, key) for key in CRITERIA) == 100
