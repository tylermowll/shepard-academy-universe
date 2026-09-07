# Current handoff

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
