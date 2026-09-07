# Current handoff

The current task is **T26: simplify navigation and guide setup**, building on
the T25 multi-subject AI tutoring loop. The maintainer authorized separate
Practice, History, Learners & devices, Settings, and Help pages, plain wording,
contextual help, and pushing the reviewed changes to `main`. See the T26 entry
in [TASKS](TASKS.md) for evidence. The product remains governed by
[D009](DECISIONS.md#d009--ai-tutoring-is-the-primary-product-2026-09-07).
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
