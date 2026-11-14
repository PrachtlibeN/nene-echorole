import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint

from app.core.errors import ErrorCode
from app.evaluation.rubric import (
    BAND_DESCRIPTIONS,
    CRITERIA,
    RUBRIC_VERSION,
    WEIGHTS,
    compute_overall_score,
    weighted_points,
)
from app.main import create_app
from app.models import Base
from app.schemas.contracts import (
    CriterionScoreIn,
    EndReason,
    EvaluationOut,
    EvaluationStatus,
    HealthOut,
    ScenarioCriterion,
    ScenarioListOut,
    ScenarioOut,
    SessionListOut,
    SessionOut,
    SessionStatus,
    SpeechStatusOut,
    StartSessionOut,
    TranscriptionOut,
    TurnListOut,
    TurnSource,
    TurnSubmitOut,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs" / "api-contracts" / "API_CONTRACTS.md"
EXAMPLES = ROOT / "docs" / "api-contracts" / "examples"


def test_openapi_matches_contract_endpoint_index_and_mock_handlers() -> None:
    contract_text = CONTRACT.read_text(encoding="utf-8")
    endpoint_rows = re.findall(
        r"^\|\s*\d+\s*\|\s*(GET|POST)\s*\|\s*`([^`]+)`",
        contract_text,
        flags=re.MULTILINE,
    )
    expected = {(method.lower(), f"/api/v1{path}") for method, path in endpoint_rows}

    client = TestClient(create_app())
    paths = client.get("/openapi.json").json()["paths"]
    actual = {
        (method, path)
        for path, operations in paths.items()
        for method in operations
        if method in {"get", "post"}
    }
    handlers_text = (ROOT / "frontend" / "src" / "mocks" / "handlers.ts").read_text(
        encoding="utf-8"
    )
    handlers = {
        (
            method,
            re.sub(r":([A-Za-z_]+)", r"{\1}", path.replace("*", "")),
        )
        for method, path in re.findall(
            r'\bhttp\.(get|post)\("([^"]+)"',
            handlers_text,
        )
    }

    assert len(expected) == 14
    assert actual == expected
    assert handlers == expected


def test_canonical_json_examples_validate_against_contract_schemas() -> None:
    models = {
        "health.json": HealthOut,
        "scenario-list.json": ScenarioListOut,
        "scenario.json": ScenarioOut,
        "session.json": SessionOut,
        "session-created.json": SessionOut,
        "session-ended.json": SessionOut,
        "session-list.json": SessionListOut,
        "session-start.json": StartSessionOut,
        "turn-list.json": TurnListOut,
        "turn-submit.json": TurnSubmitOut,
        "speech-status.json": SpeechStatusOut,
        "transcription.json": TranscriptionOut,
        "evaluation-pending.json": EvaluationOut,
        "evaluation-completed.json": EvaluationOut,
    }
    files = {path.name for path in EXAMPLES.glob("*.json")}

    assert files == set(models)
    for filename, model in models.items():
        payload = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
        model.model_validate(payload)


def test_error_enum_matches_contract_table() -> None:
    contract_text = CONTRACT.read_text(encoding="utf-8")
    error_section = contract_text.split("### 2.2 Error codes", maxsplit=1)[1].split(
        "### 2.3", maxsplit=1
    )[0]
    documented = set(
        re.findall(
            r"^\|\s*\d{3}\s*\|\s*`([A-Z][A-Z_]+)`\s*\|",
            error_section,
            re.MULTILINE,
        )
    )
    assert documented == {code.value for code in ErrorCode}


def test_database_constraints_and_rubric_match_contract() -> None:
    assert set(BAND_DESCRIPTIONS) == set(CRITERIA)
    assert sum(WEIGHTS.values()) == 100
    assert RUBRIC_VERSION == "1.0"
    assert (
        compute_overall_score(
            [
                CriterionScoreIn(
                    criterion=key,
                    score=score,
                    rationale="",
                    evidence_turn_ids=["trn1"],
                )
                for key, score in zip(
                    CRITERIA,
                    (7, 6, 7, 6, 5, 8),
                    strict=True,
                )
            ]
        )
        == 66
    )
    weighted_sum = sum(
        weighted_points(score, key) for score, key in zip((7, 6, 7, 6, 5, 8), CRITERIA, strict=True)
    )
    assert weighted_sum == 65.5

    constraints = {
        table.name: [
            str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        ]
        for table in Base.metadata.tables.values()
    }
    check_values = {
        table: [set(re.findall(r"'([^']+)'", check)) for check in table_checks]
        for table, table_checks in constraints.items()
    }
    expected_checks = {
        "sessions": [
            {item.value for item in SessionStatus},
            {item.value for item in EndReason},
        ],
        "turns": [
            {"interviewer", "candidate"},
            {item.value for item in TurnSource},
        ],
        "conversations": [{"roleplay", "evaluation"}],
        "evaluations": [{item.value for item in EvaluationStatus}],
        "evaluation_scores": [{item.value for item in ScenarioCriterion}],
    }
    for table, expected_sets in expected_checks.items():
        assert all(expected in check_values[table] for expected in expected_sets)
    assert set(Base.metadata.tables) == {
        "scenarios",
        "sessions",
        "turns",
        "conversations",
        "messages",
        "evaluations",
        "evaluation_scores",
    }


def test_module_import_boundaries_are_preserved() -> None:
    for path in (ROOT / "backend" / "app" / "speech").rglob("*.py"):
        imports = _imports(path)
        assert all(
            not name.startswith("app.")
            or name.startswith(("app.core.", "app.schemas.", "app.speech."))
            for name in imports
        )

    for module in ("roleplay", "evaluation"):
        files = (ROOT / "backend" / "app" / module).rglob("*.py")
        for path in files:
            imports = _imports(path)
            other_agent = "evaluation" if module == "roleplay" else "roleplay"
            assert not any(name.startswith(f"app.{other_agent}") for name in imports)
            if module == "roleplay" or path.name in {
                "coach.py",
                "prompts.py",
                "metrics.py",
                "rubric.py",
            }:
                assert not any(name.startswith(("sqlalchemy", "httpx")) for name in imports)


def test_application_code_contains_no_candidate_model_names() -> None:
    forbidden = re.compile(
        r"\b(?:llama(?:\d|[-_:])|mistral(?:[-_:])|qwen(?:[-_:])|"
        r"gemma(?:[-_:])|phi(?:[-_:])|deepseek(?:[-_:]))",
        flags=re.IGNORECASE,
    )
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        assert not forbidden.search(path.read_text(encoding="utf-8")), path


def _imports(path: Path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    names.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    return names
