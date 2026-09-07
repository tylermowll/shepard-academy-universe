"""Adult-managed profile versions. Existing sessions keep immutable settings."""

import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from math_tutor.adapters.db.models import TutorProfileVersion
from math_tutor.api.access import Adult, Database, Principal
from math_tutor.domain.math import SKILLS, help_text

router = APIRouter(prefix="/api/v1", tags=["profiles"])


class Presentation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    font_scale: float = Field(default=1, ge=1, le=1.5)
    reduced_motion: bool = True
    compact_explanations: bool = False


class ProfileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=64)
    topics: list[str] = Field(default_factory=lambda: ["fractions.add"], min_length=1, max_length=7)
    difficulty: Literal["introductory", "standard", "challenge"] = "standard"
    teaching_style: Literal["guided", "direct", "worked_example"] = "guided"
    verbosity: Literal["brief", "standard", "detailed"] = "standard"
    hint_policy: Literal["progressive"] = "progressive"
    solution_policy: Literal["on_request", "after_two_attempts", "adult_only"] = (
        "after_two_attempts"
    )
    language: Literal["en"] = "en"
    session_problem_limit: int = Field(default=5, ge=1, le=20)
    question_pacing: Literal[1] = 1
    presentation: Presentation = Field(default_factory=Presentation)
    custom_instructions: str = Field(default="", max_length=2000)

    @field_validator("topics")
    @classmethod
    def supported(cls, values: list[str]) -> list[str]:
        if any(value not in SKILLS for value in values) or len(set(values)) != len(values):
            raise ValueError("Select distinct supported skills.")
        return values


class ProfileInput(ProfileSettings):
    profile_id: UUID | None = None


class ProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    profile_id: UUID
    version: int
    settings: ProfileSettings


class Preview(BaseModel):
    problem: str
    message: str
    source: str = "built-in explanation"


@router.get("/tutor-profiles", response_model=list[ProfilePublic])
def profiles(db: Database, actor: Principal) -> list[TutorProfileVersion]:
    # These objects contain teaching settings only; no author or infrastructure fields.
    return list(
        db.scalars(
            select(TutorProfileVersion).order_by(TutorProfileVersion.created_at.desc()).limit(100)
        )
    )


@router.post("/admin/tutor-profiles", response_model=ProfilePublic, status_code=201)
def save_profile(body: ProfileInput, db: Database, actor: Adult) -> TutorProfileVersion:
    if os.getenv("APP_MODE", "private") == "demo" and (
        body.custom_instructions or body.name not in {"Synthetic", "Guided practice"}
    ):
        raise HTTPException(403, "Demo accepts supplied synthetic profiles only.")
    profile_id = body.profile_id or uuid4()
    latest = db.scalar(
        select(func.max(TutorProfileVersion.version)).where(
            TutorProfileVersion.profile_id == profile_id
        )
    )
    if body.profile_id is not None and latest is None:
        raise HTTPException(404, "Profile not found.")
    assert actor.administrator_id is not None
    settings = ProfileSettings.model_validate(body.model_dump(exclude={"profile_id"}))
    row = TutorProfileVersion(
        profile_id=profile_id,
        version=(latest or 0) + 1,
        settings=settings.model_dump(),
        author_id=actor.administrator_id,
    )
    db.add(row)
    db.flush()
    return row


@router.post("/admin/tutor-profiles/preview", response_model=Preview)
def preview(body: ProfileSettings, actor: Adult) -> Preview:
    if os.getenv("APP_MODE", "private") == "demo" and body.custom_instructions:
        raise HTTPException(403, "Demo does not accept custom instructions.")
    level = {"guided": 1, "direct": 2, "worked_example": 3}[body.teaching_style]
    return Preview(
        problem="1/2 + 1/3", message=help_text("fractions.add", level, "1/2 + 1/3", "5/6")
    )


@router.get("/admin/tutor-profiles", response_model=list[ProfilePublic])
def admin_profiles(db: Database, actor: Adult) -> list[TutorProfileVersion]:
    return profiles(db, actor)
