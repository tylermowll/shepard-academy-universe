# Implementation decisions

## D013 — Administrator-managed learner accounts (2026-09-08)

The maintainer replaces profile-only learners and the primary device-pairing
flow with one administrator managing distinct learner sign-ins. Each learner
has a unique username and a password set/reset by the administrator. A learner
sign-in grants access only to that learner's practice and history; it never
grants household settings or account management. Administrators see Learners,
Settings and Help. Practice and History require a learner sign-in; administrators
can test AI connections with synthetic examples in Settings.

Use the existing Argon2id hashing, opaque cookies, CSRF, origin checks, bounded
sessions and rate limits. Passwords are write-only and excluded from account
lists and exports. Password resets revoke existing learner sessions. Username
uniqueness is enforced on normalized, case-insensitive keys in SQLite and also
checked against the administrator's login name to avoid ambiguous sign-in.

Existing learner IDs and saved work are preserved by a forward migration.
Conflicting old names receive a deterministic numeric suffix, never a merge or
deletion. Existing profiles initially need an administrator to set a password;
the application must not invent, print or publish shared default credentials.
Previously authenticated learner sessions remain subject to their existing
expiry/revocation. Pending pairing requests are retired with the old pairing
endpoints. New learner access uses the common sign-in form.

This supersedes the primary account/pairing workflow in T03/T26. Phone camera
delegation remains a separate, limited capability and is addressed separately.
No external identity service, public signup or email recovery is added.

## D012 — Operator-selected audience for Meta-hosted inference (2026-09-07)

The maintainer explicitly rejected a hard-coded Meta age gate and
directed the application to use a disclaimer instead. The dedicated Meta adapter
remains cloud-only because it calls Meta's hosted Model API; a locally served
Llama model is configured through Ollama or vLLM. The Meta connection's audience
is otherwise selected and attested by the adult operator, then enforced by the
same backend learner/app-audience checks used for other providers.

Meta's hosted API has provider-specific age and data terms. The connection editor
must disclose that fact and require the existing terms acknowledgment, but this
app will not encode a blanket provider age rule. The operator is responsible for
the current agreement and jurisdiction; the app does not certify eligibility. A
connection configured for a restricted audience still rejects learners outside
that selection server-side, while a mixed connection can serve either app audience
and still requires explicit cloud authorization, successful probes and normal
learner ownership. No provider call occurs on save.

Sources: [Meta's official terms page](https://llama.developer.meta.com/legal/terms-of-service)
(authenticated access may be required), and Meta's separate
[Llama 4 license](https://github.com/meta-llama/llama-models/blob/main/models/llama4/LICENSE)
and [acceptable-use policy](https://github.com/meta-llama/llama-models/blob/main/models/llama4/USE_POLICY.md)
for locally hosted weights.

## D011 — Browser-first owner setup and loopback password policy (2026-09-07)

The maintainer supersedes D010's CLI-only first-account decision. `make start`
starts a private unclaimed app and prints a one-use, thirty-minute owner link.
The token stays in the URL fragment until captured in browser memory, is removed
from browser history, and is submitted only in the CSRF-protected setup body.
No public endpoint issues setup authority. Each fresh launcher run replaces it;
successful account creation permanently closes setup for that database. Concurrent
claims are serialized and cannot reset or create an additional administrator.

Password creation accepts six characters on HTTP loopback and twelve on HTTPS;
neither requires mixed character classes. This is a deliberate local convenience
tradeoff, not a claim that a six-character password is strong. Saved API usage
and administrative actions still require authentication and remain rate-limited.
A boolean on the administrator records when the password is local-only. Network
startup/login/session access must not accept such an account unchanged. The
existing explicit local reset can replace it with a network-eligible password;
there is no anonymous web reset or silent relaxation for phone access.

The setup page validates in context without terminating services. Existing
accounts and settings are never overwritten on restart. Deployment secrets,
provider-key encryption, learner access and non-loopback HTTPS rules are unchanged.

Design references: [MDN fragment behavior](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment)
explains why the token is not part of the initial HTTP request. Expiry, one-use
claims and random owner tokens apply the bearer-token principles in
[OWASP's token guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
by analogy to initial ownership, not as a password-recovery endpoint.

## D010 — Browser-managed AI connections and persistent local startup (2026-09-07)

The maintainer explicitly requires entering an API key or connecting Ollama/vLLM
through the adult Settings page. T26's route-selection-only UI was incomplete.
This supersedes the configuration contract's restriction to preconfigured routes,
not the restriction against learner-controlled destinations or credentials.

- Keep the existing single-host SQLite architecture and provider transports.
  Store browser-managed connection definitions and encrypted credentials in
  private database tables. File-managed connections remain read-only; the UI
  does not rewrite operator YAML or environment files.
- Credential inputs are write-only. The adult response exposes a configured/not
  configured status, never the saved value. Use the existing cryptography library
  with a purpose-derived key from the deployment session secret. Backups need the
  original deployment secret to recover saved credentials; changing that secret
  requires re-entering them. Encryption protects a database-only copy, not a
  compromised host that has both database and secret.
- Save, test and select are distinct actions. Saving sends no network request to
  the model and does not select it for learner work. Tests require explicit
  synthetic-call authorization, disclose possible cost and validate capabilities.
  Key/configuration changes invalidate probe and pending-operation fingerprints.
- Explicitly saved cloud and audience policy fills the previous terminal-only
  setup gap. Operator environment restrictions remain enforced and visible;
  the UI cannot lift a deployment restriction or enable live calls in demo mode.
- A local launcher may load private settings at application runtime without
  executing a shell file. Coding agents still must not inspect real operator
  settings, credentials or data. Missing settings may be generated exclusively;
  existing settings, accounts and data must not be replaced on restart.
- No model installation, cloud provisioning, secret-return endpoint, new service,
  or automatic local-to-cloud fallback is introduced. CLI-only adult bootstrap
  remains an intentional local security boundary, with a prompt on first start.

## D009 — AI tutoring is the primary product (2026-09-07)

The maintainer explicitly corrected the product scope and authorized implementing
and pushing the correction to `main`. The central experience is topic → generated
practice → handwritten/typed work → readable interpretation → specific guidance
→ revision/discussion → an appropriate next activity. It covers subjects beyond
math and does not require a grade-level selection or a deterministic verifier for
every topic. Prior catalog-first descriptions were an implementation mistake,
not a limitation the maintainer accepted.

- Uploaded or pasted assignments are **reference-only**. Generate distinct
  analogous practice and explain concepts; never solve the original assignment.
  Book excerpts may ground new comprehension questions. Do not invent unavailable
  passages or claim to have read an entire book from a title.
- Tutor responses guide the learner, discuss their reasoning, and offer relevant
  different examples. They do not provide the active task's final answer or a
  finished essay. Treat requests to bypass this rule as untrusted learner content.
- Tutor initiative is adjustable between learner-led, balanced, and tutor-led.
  Relevant recent work and conversation inform follow-ups; no mastery claim is
  inferred from a model's assessment.
- Show a photo's reading before its guidance and give concrete
  handwriting/organization feedback. The worker automatically continues clear
  readings; there is no manual approval or hidden browser acknowledgement gate.
  Routing requires clear quality, a confidence score of at least
  0.85, no reported ambiguity, and the current operation/version. This score is a
  routing heuristic from the model, **not calibrated evidence of 85% accuracy**.
  Unclear work stops for a cleaner photograph, organized rewriting, or a new typed
  submission. No silent guesses or corrections to the student's work.
- Model reasoning feedback is permitted but is not a verified grade. Exact
  checks may support tests and domain utilities; they do not gate
  AI tutoring. No fixed-template practice catalog or authored-hint fallback is
  offered in the tutor. Backend code still owns permissions, transitions and persistence.
- Reuse the current single-host architecture and private provider/phone pipeline.
  This is a product/workflow correction, not a new hosting service or framework.

This decision removes approval/confirmation from the primary learning workflow,
fixed-catalog restrictions on tutoring, and authored-hints-only requirements for
the primary AI workspace. The maintainer rejected the proposed implicit browser
acknowledgement as well: clear readings proceed in the worker, without approval.
Historical T00–T24 evidence describes those
earlier implementations, not completion evidence for this tutoring loop.

Schemas and input separation enforce software boundaries; they cannot guarantee
that every model response is factually correct or never reveals an answer.
Anti-cheating, false correction, helpfulness, and handwriting quality need human
review using the actual configured model. Tests must distinguish those open
quality gates from deterministic orchestration/security checks.

## D001 — Supported toolchain baseline (2026-09-06)

The maintainer requested the latest LTS tooling. Use the newest LTS line where
the project offers one, otherwise supported stable releases, with exact locks.
Do not install prereleases or disable checks to accommodate a newer package.

- Node 24.20.0 is the latest LTS; Node 26 is still Current. `.node-version` pins
  the verified runtime, and `package.json` restricts execution to Node 24.
- Python has a bugfix/security lifecycle, not a separate LTS edition. Python
  3.14.7 is the latest stable release. It replaces the original 3.13 baseline in
  `.python-version`, package constraints, Ruff, mypy, and the specification.
- pnpm 12.3.4 and the existing uv 0.12.10 are the current stable tools. Frontend
  package versions were checked against npm metadata; Python versions against
  PyPI. Dependencies stay locked, with install scripts requiring explicit review.
- TypeScript stays on 6.0.3 because current `typescript-eslint` 8.69.0 declares
  support for `>=4.8.4 <6.1.0`. TypeScript 7.0.2 is newer but outside that range.
- Vitest 5.0.0 was tried: component execution passed, but strict `tsc` reported
  conflicting `Assertion` declarations with jest-dom, missing `@vitest/expect`,
  missing `MarkOptions`, and incompatible Vite config declarations. Vitest
  4.1.11 supports Vite 8 and passes strict type checking without `skipLibCheck`,
  casts, or suppressed errors. Recheck this exception on the next tooling update.
- CI retains Ubuntu 24.04 LTS, the latest generally available Ubuntu runner.
  Ubuntu 26.04 LTS exists, but GitHub still labels that runner Public preview.
  Move after general availability and a successful hosted run.

Sources: [Node release table](https://nodejs.org/en/about/previous-releases),
[Python support lifecycle](https://devguide.python.org/versions/),
[Python downloads](https://www.python.org/downloads/),
[TypeScript ESLint support](https://typescript-eslint.io/users/dependency-versions/),
[Vitest package metadata](https://registry.npmjs.org/vitest),
[GitHub runner availability](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

### Compatibility exception — embedded SQLite 3.53.1 (T01, 2026-09-06)

Python 3.14.7 is the latest 3.14 patch and loads SQLite 3.53.1, while current
stable SQLite is 3.53.4 (both rechecked against the official release history
in T01). No reproducible newer Python runtime exists, and the 3.53.2–3.53.4
deltas are follow-up fixes for 3.53.0 regressions. T01 therefore pins the
supported floor at 3.53.1 (`MIN_SQLITE_VERSION`, enforced by `make db` and
covered by on-disk integration tests over exactly the relied-upon surface)
instead of switching drivers or toolchains to hide the gap. Recheck on the
next tooling update.

## D002 — Local T00 completion (2026-09-06)

The maintainer explicitly deferred pushing and hosted CI execution while doing
more work locally. T00 can complete when fresh locked installation, backend and
frontend checks/builds, the browser smoke tests, and commit checks pass locally,
and the matching CI workflow is configured. A hosted run remains unverified and
must be recorded later; it does not block T01. This does not waive any application,
authorization, migration, or release acceptance gate.

The maintainer subsequently authorized the initial commit and push to `main`.
That supersedes the push deferral for this publication; hosted CI still needs
an observed result. Later task pushes require their own authorization.

## D003 — T05 before the worker (2026-09-06)

The original roadmap puts the first deterministic practice workflow in T05 and
durable jobs in T06, while the full API specification assumes a job exists for
every submission. The bounded staging default is immediate deterministic checking
in T05; queued processing is introduced in T06. This was proposed during handoff
preparation and is an explicit implementation assumption, not a maintainer reply.

T05's typed submission endpoint returns `201 Created` with the persisted completed
result. Persist the attempt, deterministic evaluation, authored help, assistance
level, and applicable progress change in one transaction. Ownership checks,
idempotency-key/payload conflict handling, and stale-version rejection already
apply in T05. Do not defer these to the worker or add a fake job merely to return
`202`. A repeat request returns its saved result; a different payload under the
same key returns `409`.

T06 deliberately changes the submission transport to the specified `202` plus
operation polling and adds durable jobs, leases, retries, and recovery tests.
Regenerate API types and update frontend consumers/tests together at that point.
The final version-1 job, privacy, and correctness requirements remain unchanged.

T05 also uses one immutable built-in tutor-profile snapshot. T08 introduces the
profile editor and customization; a working session must not refer to a mutable
or nonexistent profile in the meantime.

## D004 — SQLite for the initial deployment (2026-09-06)

The maintainer approved changing the plans to SQLite before T01. This supersedes
the PostgreSQL-only architecture, PostgreSQL test-runtime prerequisite, and
Fargate/RDS hosting plan. No persisted application data exists to migrate today.
T01 will implement persistence; this decision does not claim that it exists.

The initial application serves one household on one host with modest write
traffic. SQLite removes the database service, credentials, and container runtime
from native setup. Use the same engine in development, integration tests, and
deployment. Retain SQLAlchemy 2, Alembic, relational constraints, and separate
public/private schemas; use Python's standard sqlite3 driver.

### Storage and connection contract

- Run one API process and, from T06, one separate worker on the same host. They
  share a private local directory containing the database and its WAL/SHM files.
  Do not use NFS, SMB, EFS, live cloud-sync folders, ephemeral container storage,
  or separate application hosts for that directory.
- Configure `journal_mode=WAL`, `foreign_keys=ON` on every connection,
  `busy_timeout=5000`, and `synchronous=FULL`; verify effective settings in T01.
  Initialize connection PRAGMAs outside transactions. Use an explicit SQLAlchemy
  transaction-control strategy, including transactional DDL and rollback tests;
  do not rely on sqlite3's legacy implicit behavior.
- Keep write transactions short. Lock contention has a bounded failure/retry
  path; never retry an external provider call as part of a database transaction.
- Generate one absolute database path under the private data directory so API,
  worker, migrations, and commands resolve the same file regardless of cwd.
  Restrict directory/file permissions and ignore/block database files in Git.
- Store UUIDs in a consistent text representation and normalize timestamps to
  UTC through a tested persistence adapter. Naive datetime input is rejected;
  reads return aware UTC values. Exact math remains bounded integer/rational
  domain code. Versioned JSON payloads use SQLAlchemy JSON serialized as text,
  with schema validation; relational ownership and integrity stay constrained.

SQLite has no separate LTS line. The official current stable release is 3.53.4.
The installed Python 3.14.7 runtime currently loads SQLite 3.53.1; it is **not**
evidence of the latest SQLite or of database integration passing. T01 must select
and document a reproducible Python runtime linked to the current stable SQLite,
check `sqlite3.sqlite_version` in setup/CI, and record any justified compatibility
exception under D001. Installing a newer sqlite3 CLI alone does not update the
library Python uses. Do not add an alternative driver merely to hide that gap.

### Migrations, worker, and recovery

T01 adds real Alembic migrations and temporary on-disk integration fixtures.
Test empty-database upgrade, current schema, foreign-key/check/unique enforcement,
rollback, persistence after reopening, UTC round trips, and hidden-answer
serialization. Use Alembic batch operations when SQLite cannot perform a schema
change directly. Preserve named constraints and existing data; validate foreign
keys after a rebuild. Stop API/worker writes before controlled migrations.

T06 claims a job inside a short `BEGIN IMMEDIATE` transaction: select an eligible
row, conditionally update its state/lease, and commit before inference. Claim,
heartbeat, and completion updates check state and lease tokens. There is no
`FOR UPDATE SKIP LOCKED`. Keep crash, competing-claim, expired-lease, duplicate
submission, and deletion-race tests (A08/A09/A17), using independent connections
or processes even though the supported deployment configures one worker.

T19 supplies consistent backups using SQLite's backup API, or a documented
quiesced procedure, and a tested restore covering retained objects, settings,
and deletion tombstones. Never copy just the main file from a live WAL database.
Restore verification includes integrity and foreign-key checks.

### Hosting and future changes

Native local setup needs Python and the frontend tools; Compose is optional
packaging for the gateway/API/worker, with a shared local data directory and no
database service. Phones continue to use the authenticated HTTPS API.

T20's reference hosting plan becomes one EC2 host with persistent encrypted EBS,
the same gateway/API/worker layout, and instance-role access to permitted AWS
services. There is no horizontal scaling or automatic failover in this design.
Move to PostgreSQL through a separate architecture decision and tested data
migration when multiple application hosts, sustained write contention, or
availability requirements justify it. Do not maintain two database engines now.

Sources: [SQLite use cases](https://sqlite.org/whentouse.html),
[WAL and same-host requirements](https://sqlite.org/wal.html),
[foreign keys](https://sqlite.org/foreignkeys.html),
[SQLAlchemy SQLite transactions](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver),
[Alembic batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html),
[SQLite backup API](https://sqlite.org/backup.html),
[SQLite release history](https://sqlite.org/changes.html),
[EBS volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes.html).

## D005 — Pre-production hard cutovers (2026-09-06)

The maintainer confirmed that nothing is in production and explicitly prefers
hard cutovers without legacy compatibility code. Maintain one current
implementation. Correct initial migrations in place and recreate disposable
development databases when needed; do not add upgrade bridges, dual schemas,
or fallback paths solely to preserve an earlier development state.

For the T01/T02 review, session identity/lifetime constraints belong directly in
migration 0002. The review-only 0003 migration and its legacy-data upgrade tests
are removed. This supersedes the review's existing-database preservation plan,
including the initial recommendation to retain an earlier database URL and
upgrade those files. Old development database revisions are unsupported.

Real migrations, named constraints, explicit transactions, rollback tests,
current-data persistence, and private-data protections still apply. Revisit
compatibility and migration guarantees before a production release or a promise
to retain user data.

## D006 — Finish the roadmap implementation, defer external evidence (2026-09-06)

The maintainer explicitly authorized implementing the remaining repository in one
pass, batching testing toward the end, using hard cutovers, and pushing main.
They selected MIT and deferred the checks needing their accounts or physical
devices. This overrides the normal one-task-at-a-time workflow for this execution;
it does not waive functional/security tests or permit invented live results.
T11/T17 phone evidence, T19 release acceptance, and T23 actual-device measurements
remain open until the final maintainer checklist is completed. No application
inference, model download, cloud provisioning or public deployment was performed.

The implemented API uses one typed submission command with `kind` for answers,
questions and hints; photos use a separately bounded raw-body endpoint. This
replaces the blueprint's separate hints/multipart route examples without retaining
unused compatibility endpoints. The generated OpenAPI is authoritative for wire
names. Every path retains ownership, CSRF, idempotency and confirmation semantics.
Exports are immediate authenticated no-store downloads rather than persistent
signed links: authority lasts only for the current request. Downloaded adult
copies cannot be revoked remotely and are documented separately.

The checked-in provider example now matches the strict implemented schema. Fixed
server budgets replace the blueprint's configurable `limits` sample: six calls,
90-second timeout, at most one image, and zero automatic schema repairs (within
the specified maximum of one). Region is an explicit field, capabilities are
explicit, and unsupported legacy sample fields are rejected. `make bootstrap`
installs tools; `make setup` remains the explicit private-settings creation step
so CI and clean installs never create or inspect operator secrets implicitly.

OpenAPI generation uses its own tiny tooling workspace with TypeScript 5.9.3 to
satisfy openapi-typescript 7.13.0's declared peer contract. Application code remains
on TypeScript 6.0.3 with strict checking. No relaxed peers or skipLibCheck are used.
WebLLM 0.2.84's distributed declarations reference missing prerelease packages and
browser-worker globals; the optional experiment loads its self-contained ESM
through a narrow runtime-checked adapter. This avoids importing broken declarations
or silently claiming compatibility. Real WebGPU device validation is still pending.

Backups use SQLite's backup API plus authenticated encrypted archives, with
separately managed configuration/secrets and a required current deletion ledger.
A restore regression exposed uncheckpointed post-restore WAL changes; restore
now closes/checkpoints before copying the validated restored file. The regression
proves deleted learners and revoked sessions do not return from old backups.

## D007 — Minimal immutable container runtime (2026-09-06)

Hosted run 34079742050 passed all source checks and built/smoke-tested the original
container, but its strict image scan reported 60 HIGH/CRITICAL Debian 12 package
findings plus two unused Python installer dependencies. The final image inherited
a second Python installation, package managers and system utilities that the app
did not use. Keeping those components adds maintenance and attack surface.

Use the digest-pinned `gcr.io/distroless/cc-debian13:nonroot` runtime, retaining only
the tested uv-managed Python, locked application virtualenv and built public UI.
The builder removes the standalone interpreter's installer code and bundled
ensurepip wheels; application dependencies remain intact in their separate venv.
No package metadata is stripped to conceal installed vulnerable code, and the
HIGH/CRITICAL scan still includes unfixed findings without suppressions. This is
packaging hardening, not a new application service or database engine.

The runtime has no shell/package manager and runs as numeric UID/GID 10001.
Operational commands use the explicit Python/CLI entrypoints; rebuild the image
for dependency changes. Container checks additionally exercise HEIF normalization,
cryptography, and absence of unused pip/setuptools. The registry index digest and
supported platforms were verified from public registry metadata on September 6.
See the [official Distroless documentation](https://github.com/GoogleContainerTools/distroless)
for maintained Debian 13 images, vector entrypoints and signed-image verification.

## D008 — Bounded provider I/O and destination validation (2026-09-07)

Review reproduced a live-transport deadline gap without invoking a real model: a
loopback server sending bytes every 0.4 seconds completed after 2.48 seconds despite
a one-second request timeout. The HTTP/SDK socket timeouts bound individual waits;
they do not bound the whole call. A slow response could occupy the sole worker
past its 120-second lease. This contradicts D006's fixed 90-second call budget.

Keep one API process and one persistent worker. Each live provider invocation now
runs in a short-lived spawned Python child, with no database connection, filesystem
queue, new service, or dependency. Spawn avoids inheriting active database handles
and thread locks from API probe threads. The parent includes startup, DNS, SDK
setup, and response handling in the request deadline, then terminates and reaps
the child (up to 2.1 seconds of cleanup). A child expiry timer also bounds a call
whose parent dies. Mock and deterministic work stay in process. Both worker jobs
and adult capability probes use this boundary; process-local failures become safe
typed errors. Stopping our child cannot cancel remote inference or guarantee that
the provider stops billing. Existing call budgets and lease comparisons remain.

Configured HTTP destinations reject metadata names, link-local and metadata IPs,
including mapped IPv6 addresses. Live HTTP calls resolve once, reject the entire
answer set if any address is forbidden, then connect only to the validated IPs.
The original Host and TLS server name are preserved. A second validated address
is tried only if connection setup failed before HTTP transmission; response/read
failures never trigger hidden retries. Redirects and environment proxies stay
disabled. Operators remain responsible for identifying which allowed host belongs
to their private network and selecting the corresponding data boundary.

Provider response envelopes validate every consumed nested field before access,
while ignoring unused vendor metadata. Malformed envelopes cannot terminate the
worker. The Bedrock schema is checked against the installed SDK, including optional
cache usage metadata, and the public provider statuses remain live-unverified.
