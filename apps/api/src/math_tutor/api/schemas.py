"""Learner-facing schemas for the practice slice.

These public types are deliberately narrower than the persistence models:
they exclude the hidden expected answer, raw generator parameters, the seed,
and ownership identifiers. Anything not listed here never serializes into a
learner API response. Serialization tests prove the exclusion.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PracticeSessionPublic(BaseModel):
    """Session state safe to show the session owner."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


class ProblemInstancePublic(BaseModel):
    """Assigned-problem state safe to show the learner.

    Excludes ``expected_result``, ``parameters``, and ``seed``: the learner
    sees the problem text and its format requirements, never the answer key
    or the raw generator inputs.
    """

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    template_id: str
    template_version: int
    skill_id: str
    problem_text: str
    format_constraints: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime
