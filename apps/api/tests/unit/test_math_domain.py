"""Exact arithmetic properties and hostile-input rejection, independent of HTTP/SQL."""

from fractions import Fraction
from math import gcd

import pytest
from hypothesis import given
from hypothesis import strategies as st

from math_tutor.domain.math import SKILLS, generate, parse_answer, verify


@given(st.integers(-(10**6), 10**6), st.integers(1, 10**6))
def test_fraction_parser_preserves_exact_value(n: int, d: int) -> None:
    result = parse_answer(f"{n}/{d}")
    assert result.value == Fraction(n, d)
    assert result.simplified == (gcd(n, d) == 1)


@given(
    st.sampled_from(SKILLS),
    st.integers(0, 2**31 - 1),
    st.sampled_from(["introductory", "standard", "challenge"]),
)
def test_generated_math_is_consistent(skill: str, seed: int, difficulty: str) -> None:
    problem = generate(skill, seed, difficulty)
    assert problem == generate(skill, seed, difficulty)
    parameters = problem.parameters
    if skill == "equations.linear":
        expected = Fraction(int(parameters["c"]) - int(parameters["b"]), int(parameters["a"]))
        assert int(parameters["a"]) * Fraction(problem.expected) + int(parameters["b"]) == int(
            parameters["c"]
        )
    elif skill.endswith("simplify") or skill.endswith("equivalent"):
        expected = Fraction(int(parameters["n"]), int(parameters["d"]))
    else:
        left = Fraction(int(parameters["a"]), int(parameters["b"]))
        right = Fraction(int(parameters["c"]), int(parameters["d"]))
        expected = {
            "fractions.add": left + right,
            "fractions.subtract": left - right,
            "fractions.multiply": left * right,
            "fractions.divide": left / right,
        }[skill]
    assert Fraction(problem.expected) == expected
    assert verify(problem.expected, str(expected)).answer_status == "correct"


@pytest.mark.parametrize(
    "text",
    [
        "1/0",
        "9" * 129,
        "1e999",
        "__import__('os').system('id')",
        "1+2",
        "2**1000",
        "nan",
        "∞",
        "1/2/3",
        "０.５",
    ],
)
def test_unsafe_or_unsupported_grammar_is_unverifiable(text: str) -> None:
    assert verify(text, "5/6").answer_status == "unverifiable"


def test_value_format_and_equation_grammar_are_separate() -> None:
    result = verify("10/12", "5/6")
    assert result.answer_status == "correct"
    assert result.format_status == "needs_simplification"
    assert verify("x = -0.5", "-1/2", equation=True).answer_status == "correct"
    assert verify("x = -0.5", "-1/2").answer_status == "unverifiable"
