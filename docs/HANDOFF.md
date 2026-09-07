# Current handoff

The current task is **T28: browser-first administrator setup**,
building on T27's in-app provider configuration and persistent startup. The
maintainer rejected terminal account creation and the uniform twelve-character
password requirement, then authorized wise refinements and another push to main.
See [D011](DECISIONS.md#d011--browser-first-owner-setup-and-loopback-password-policy-2026-09-07)
and the T28 entry in [TASKS](TASKS.md) for the current contracts and evidence.

T28 local gates passed: 159 unit, 103 component, 215 integration and 46 browser
tests, all hooks/check gates, and 63 mock-evaluation fixtures. Native browser tests
exercise first-account creation, inline correction, lost-response recovery and
restart with isolated synthetic state. Routine `make start` no longer prompts for
credentials: an unclaimed private app prints a thirty-minute owner link for web
setup; existing accounts just sign in. Six-character passwords are permitted only
on HTTP loopback. Before HTTPS/phone access, any local-only account must be reset
through `make admin` to twelve or more characters. With the app stopped, existing
installations upgrade with `make migrate start`; no operator data was touched by
the agent. Live-provider and physical-phone verification remain unrun.

T27 completed local setup and browser-managed AI connections,
building on the T26 navigation and T25 multi-subject AI tutoring loop. The
maintainer found that Settings could not accept API keys or configure Ollama/vLLM
and authorized closing that gap and related setup blockers, then pushing `main`
before providing verified local run instructions. See the T27 entry
in [TASKS](TASKS.md) for evidence. The product remains governed by
[D009](DECISIONS.md#d009--ai-tutoring-is-the-primary-product-2026-09-07).
Connection/credential persistence and safe first-run behavior are governed by
[D010](DECISIONS.md#d010--browser-managed-ai-connections-and-persistent-local-startup-2026-09-07).
T27 local gates passed: 145 unit, 80 component, 188 integration and 42 browser
tests, plus an isolated first-run/restart rehearsal. Current-schema upgrades use
`make migrate` with writes stopped; routine startup is `make start`. Actual model
quality and physical phone verification remain external acceptance gates.
The maintainer explicitly wants no fixed
templates and no photo approval step. Clear readings continue automatically;
unclear work receives concrete handwriting/organization advice. Uploaded/pasted
homework is reference-only for distinct analogous practice, never direct solving.
Guide, explain concepts, and give relevant different examples. Tutor initiative
is adjustable; no required subject catalog or school level.

The maintainer authorized implementing these changes and pushing reviewed public
work to `main`. That does not authorize inspecting private provider settings,
publishing unlicensed examples, paid inference, or public deployment.

The maintainer authorized completing the remaining repository implementations and
pushing main, selected MIT, and deferred device/account-dependent verification.
T03 is implemented; do not restart the old T03 prompt. The historical T01/T02 Spark
review and observed checks remain in [TASKS](TASKS.md).

Use [ACCEPTANCE](ACCEPTANCE.md) for the final maintainer checklist and exact test
mapping, [RUNBOOK](RUNBOOK.md) for operations, and [PROVIDER_STATUS](PROVIDER_STATUS.md)
for live verification. Finish those external gates before calling T11/T17/T19/T23
fully accepted. No live model quality or actual phone evidence has been invented.

For subsequent changes, return to one bounded task at a time, regenerate contracts
from backend schemas, and run applicable Make gates. Initial development schemas
have no compatibility bridge (D005). Keep learner data and operator configuration
outside agent access and Git.
