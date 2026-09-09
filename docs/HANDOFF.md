# Current handoff

T39 fixes setup permission expiring while the form is open. Opening the private
link now exchanges it once for a signed HttpOnly cookie valid for eight hours.
This browser can finish setup after a refresh or an API restart with the same
deployment secret. The form refreshes anonymous CSRF before submitting. Existing
accounts close setup, and the cookie cannot authenticate normal app requests.
The owner token is discarded after exchange. D014 records the contract.

T38 fixed Docker setup recovery and app updates during signup. `make start`
connects to the running Docker API on port 8000 and prints a fresh private setup
link, or the sign-in address if an administrator exists. First-account creation
uses the browser. The owner command can renew an expired link without restarting
Docker; it cannot reset an account. App updates wait until signup finishes before
offering a refresh.

The local deployment now uses the `shepherd-academy-universe` Compose project and
the retained database in the current checkout. The obsolete containers and their
unused network were removed. The current API and worker passed readiness, and
the public setup check now confirms an administrator exists. The owner command
returns only the app address. No live account was created or reset by the agent.

T39 checks passed: **194 backend unit tests**, **147 frontend component tests**,
**267 integration tests**, **66 desktop/mobile browser cases**, and the
disposable container setup check. Exact commands and changes are in
[TASKS](TASKS.md).

The app is a multi-subject AI tutor. Learners sign in with individual usernames
and passwords, choose a topic and work through a conversation. Photo reading
appears before feedback; clear readings continue automatically. Unreadable work
receives specific clarification advice. Assignments provide reference material
for distinct practice and explanations, never answers to the active task.
There is no fixed activity catalog or photo approval step in this workflow.

The administrator manages learner accounts and AI connections. Administrators
who want to study create a separate learner account. Saving a connection does
not test or activate it. Synthetic connection tests and active-model selection
require separate actions in Settings. Provider routing, audience and ownership
remain enforced by the backend.

Live model quality, physical phone camera/install/update behavior, manual
accessibility checks and browser-model device measurements remain unverified.
Use [ACCEPTANCE](ACCEPTANCE.md) for these gates,
[PROVIDER_STATUS](PROVIDER_STATUS.md) for provider evidence, and
[RUNBOOK](RUNBOOK.md) for operation and recovery. Passing synthetic tests does
not establish model quality or production readiness.

Continue with one bounded task at a time. Preserve private settings and learner
data, regenerate API clients from backend schemas when contracts change, and
run the applicable Make gates. The current implementation has no legacy startup
path or development-schema compatibility bridge. Historical task evidence stays
in TASKS and architecture decisions stay in [DECISIONS](DECISIONS.md).
