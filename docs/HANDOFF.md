# Current handoff

The local administrator account exists. Open the app address and sign in;
first-account setup is finished. The `shepherd-academy-universe` Compose project
runs one API and one worker against the retained database in this checkout.

T40 fixes Settings failing immediately after signup. Rechecking the same session
no longer cancels pending requests. Responses from a previous identity are still
discarded. The component regression reproduces the request order, and browser
signup tests now require loaded Settings controls. Project checks passed with
**194 backend unit tests**, **152 frontend component tests**, **14 affected
desktop/mobile browser cases**, and container smoke. The fix is deployed locally;
HTTPS readiness and frontend build checks passed. Exact evidence is in
[TASKS](TASKS.md).

For a fresh installation, the private owner link exchanges once for an eight-hour
HttpOnly setup cookie. Setup survives refreshes and API restarts with the same
secret; the cookie grants no normal account access. App updates defer their
refresh action until signup finishes. `make start` connects to the standard
running Docker API and prints a setup link only when no administrator exists.
It cannot reset an account. D014 records the setup contract.

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
