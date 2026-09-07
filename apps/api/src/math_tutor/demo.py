"""Synthetic data only; refuse to seed an existing administrator database."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from math_tutor import auth
from math_tutor.adapters.db.models import Administrator, Learner, TutorProfileVersion
from math_tutor.api.profiles import ProfileSettings
from math_tutor.domain.math import SKILLS

DEMO_PASSWORD = "synthetic-demo-password-only"


def seed(engine: Engine) -> None:
    with Session(engine) as db:
        if (
            db.scalar(select(Administrator.id)) is not None
            or db.scalar(select(Learner.id)) is not None
        ):
            raise ValueError("Synthetic seed requires an empty database.")
        admin = auth.create_or_reset_admin(db, "demo", DEMO_PASSWORD)
        db.add_all(
            [
                Learner(alias="Orbit", eligibility="unknown"),
                Learner(alias="Delta", eligibility="minor"),
            ]
        )
        db.add(
            TutorProfileVersion(
                profile_id=uuid4(),
                version=1,
                author_id=admin.id,
                settings=ProfileSettings(
                    name="All supported skills", topics=list(SKILLS)
                ).model_dump(),
            )
        )
        db.commit()


def main() -> None:
    import os

    from math_tutor.adapters.db.engine import create_default_engine

    if not os.getenv("DATABASE_URL") or os.getenv("APP_MODE") != "demo":
        raise SystemExit(
            "Set an explicit DATABASE_URL and APP_MODE=demo; only an empty migrated database can be seeded."
        )
    engine = create_default_engine()
    try:
        seed(engine)
    finally:
        engine.dispose()
    print("Created synthetic demo aliases and administrator. See README for the public demo login.")


if __name__ == "__main__":
    main()
