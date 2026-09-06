"""Public schemas must never leak hidden answers, generator inputs, or ownership."""

import uuid
from datetime import UTC, datetime

from math_tutor.adapters.db.models import PracticeSession, ProblemInstance
from math_tutor.api.schemas import PracticeSessionPublic, ProblemInstancePublic


def _problem() -> ProblemInstance:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    return ProblemInstance(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        template_id="fraction_add",
        template_version=1,
        skill_id="fractions.add",
        seed=42,
        position=0,
        parameters={"a": "1/2", "b": "1/3"},
        problem_text="1/2 + 1/3",
        expected_result={"value": "5/6"},
        format_constraints={"simplest_form": True},
        status="assigned",
        created_at=now,
        updated_at=now,
    )


def test_problem_public_excludes_hidden_material() -> None:
    problem = _problem()
    assert problem.expected_result == {"value": "5/6"}

    dumped = ProblemInstancePublic.model_validate(problem).model_dump(mode="json")

    assert dumped["problem_text"] == "1/2 + 1/3"
    assert dumped["format_constraints"] == {"simplest_form": True}
    for hidden in ("expected_result", "parameters", "seed"):
        assert hidden not in dumped, f"{hidden} must not serialize into learner payloads"


def test_session_public_excludes_ownership() -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    session = PracticeSession(
        id=uuid.uuid4(),
        learner_id=uuid.uuid4(),
        status="open",
        created_at=now,
        updated_at=now,
    )

    dumped = PracticeSessionPublic.model_validate(session).model_dump(mode="json")

    assert dumped["status"] == "open"
    assert "learner_id" not in dumped
