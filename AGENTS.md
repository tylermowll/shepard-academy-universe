# Repository instructions

## Read order

Read this file, the nearest nested AGENTS.md for files being edited, the relevant
README sections, the current task in docs/TASKS.md, and its referenced sections of
docs/SPECIFICATION.md. Load only the applicable
.agents/skills/<name>/SKILL.md. When documents conflict, report the conflict;
do not silently pick whichever permits an easier implementation.

## Architecture

React/TypeScript/Vite PWA; Python/FastAPI modular monolith; SQLite on local disk;
one API process and one separate worker on the same host. See docs/DECISIONS.md
D004 for the approved database change and deployment limits. Exact math in domain code.
Adapters isolate Meta, Ollama, vLLM, Bedrock, and compatible endpoints.
The app has no autonomous external tools. Do not add frameworks, services,
or database engines without a documented need and architecture decision.

## Hard boundaries

- Never commit secrets, real learner data, private logs, or employer material.
- Coding agents must not open live .env files, private provider config, secrets,
  uploads, or private logs; use examples and synthetic fixtures instead.
- Never expose a provider key, hidden answer, or administrator data to learners.
- Never execute learner/model text or pass it to unsafe expression evaluators.
- Never silently send local/private work to a cloud provider.
- Enforce provider capability, audience, ownership, and retention in backend code.
- Photo interpretation must be confirmed before grading in version 1.
- Models cannot change verdicts, permissions, answer keys, or workflow state.
- No application/test paid inference, cloud provisioning, public deployment,
  destructive migration, Git push, or model download unless the maintainer has
  authorized that action.

## Work protocol

Implement one task at a time. Inspect git status first; preserve unrelated edits.
Name affected contracts and tests before editing. Prefer a working vertical slice.
Keep scope bounded; no unrelated refactors. Use real migrations and typed schemas.
Generated API clients are regenerated, not hand-edited. Do not loosen tests or
requirements to conceal a failure. Do not add empty production stubs as features.

This project is pre-production. Prefer a hard cutover to one current implementation;
do not add legacy compatibility shims or development-schema upgrade bridges unless
the maintainer requests them. Initial migrations may be corrected in place and
disposable development databases recreated (D005). Keep current-schema integrity,
rollback tests, and the private-data boundaries above.

## Commands

Treat the checked-in Makefile as the authority for implemented commands. Add a
planned target only when its phase has real behavior; never add a fake-success
placeholder. Run relevant targeted checks, then the required phase gates. Live
evaluations are separate and explicitly opt-in.

## Completion evidence

Report changed files, requirements satisfied, actual commands and outcomes,
remaining failures, and provider tests not run. Update docs/TASKS.md with evidence.
A screenshot or model self-assessment is not proof of correctness. Mark incomplete
work honestly and identify the next bounded action. Never fabricate test results.
