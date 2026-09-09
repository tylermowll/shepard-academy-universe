# Shepherd Academy Universe

A self-hosted AI tutor: choose a topic, receive an activity, work on paper, send
an iPhone photo, and get guidance on your actual work. Revise or discuss it, then
receive a next activity informed by the conversation. Use math, writing, reading,
history, social studies, science, or your own topic—no required grade level or
fixed-template catalog.

The AI reads the work automatically and shows its reading before the feedback.
Clear readings proceed without an approval step. Unclear handwriting or layout
gets specific improvement advice and a request for a cleaner submission.

Uploaded or pasted homework is **reference material, not a request for answers**.
The tutor generates different practice on related concepts and guides with
explanations and relevant examples. It does not complete the original assignment
or supply the active task's final answer. Tutor initiative is adjustable.

The T25 correction replaces the earlier math-checker-first experience. Evidence and
remaining release gates are recorded in [TASKS](docs/TASKS.md) and
[ACCEPTANCE](docs/ACCEPTANCE.md). Live model quality, real phone camera/install
checks, and browser model device measurements remain unverified. They require the
maintainer's devices/accounts and were explicitly deferred. This is not a claim
of production readiness or educational effectiveness.

## Run it on your computer

Prerequisites: Git, GNU Make, Node **24.20.0**, pnpm **12.3.4**, and uv
**0.12.10**. Python **3.14.7** is installed by uv if needed. See
[dependency decisions](docs/DEPENDENCIES.md).

For **computer practice with iPhone photo submission**, follow
[the phone setup guide](docs/PHONE_SETUP.md). It covers private HTTPS, local vLLM
or Spark API configuration, `make serve`, and the expiring **Take photo with phone**
QR link. The app runs on your desktop/laptop; the iPhone is its camera. A local
vLLM vision model can handle inference, or explicitly select an API provider.
No paid hosting, native phone app, or public deployment is required by this design.

```bash
make bootstrap
make start
```

`make start` connects to the standard Docker app if it is already running on
port 8000. Otherwise, it creates missing private settings, initializes a fresh
database, and starts the UI, API, and worker at <http://127.0.0.1:8000> by default.
See [the container instructions](docs/RUNBOOK.md#container-package) to install
with Docker.

On first run, open the private setup link printed in the terminal and choose
your administrator username and password in the browser. The link proves that
you control the installation. Open it within 30 minutes; this browser then has
eight hours to create the first administrator. After that, open the app address
and sign in.

To renew an expired link, run `make start`. Docker keeps running; for a native
app running in your terminal, stop it with Ctrl+C first. A new link replaces
the previous unopened link. Once opened, setup permission survives refreshes and
app restarts in that browser. Unsent passwords still clear on reload. App updates
wait until signup finishes before offering a refresh. Keep setup links private.

Localhost passwords need **6 characters**; phone/HTTPS passwords need **12**.
There are no uppercase/symbol rules. Short local passwords trade strength for
convenience and cannot be used unchanged after enabling network access. If you
later enable HTTPS, startup explains how to replace a local-only password with
`make admin`. That recovery command is not needed for browser-first setup.

The native launcher loads `.env` without executing it as a shell script and validates
setup before building. Existing settings, accounts and data are preserved.
Never share `.env` with coding agents.

Use `make start` again after Ctrl+C. It also supports a configured private HTTPS
gateway; `make dev` restricts the same persistent workflow to loopback HTTP.
`make demo` is a separate disposable preview. If a retained database
needs an upgrade, startup stops with instructions. Stop all app/worker writes,
back up retained data, then run `make migrate start`. `make admin` is an explicit
password-reset tool, not a routine restart step; resetting revokes sessions.

Sign in as administrator and open **Settings**. Choose a section:
**Connections** saves a model/server/key, **Data & privacy** controls the
installation-wide cloud and audience ceiling, **Connection tests** sends only
explicitly approved synthetic checks, and **Active models** chooses
what future learner work actually uses. A saved connection is not automatically
tested or activated. If a connection is not ready, its assignment shows the exact
requirement and links directly to it. Tests may incur your provider's charges.
The photo-reader test is one image-reading response; the tutor test separately
checks activity creation and feedback in two structured text responses. Passing
one role does not imply that the other response format works.
The **Model response limit** under Advanced connection options controls the
output budget for connection tests and all real practice calls, including photo reading
(16,384 tokens by default); the model
context limit is a separate budget. Match both limits to your provider. Each
tutor test request has up to 90 seconds, with at most two requests and no
automatic retry. Incomplete responses can still be billed by the provider.
Connection tests show the last result directly on the card and retain recent
diagnostics across reloads in SQLite: phase, safe code, HTTP status, duration,
requests started, thinking effort and output limit. Records contain no prompts, responses,
images or keys, are limited to 20 per connection (10 displayed), and expire
after seven days. A saved terms review remains checked when reopening an
unchanged connection.
Meta connections also offer **Thinking effort** under Advanced connection options:
Provider default (parameter omitted), Minimal, Low, Medium, High, or Xhigh.
[Meta's official reasoning cookbook](https://github.com/meta-models/meta-model-cookbook/blob/main/01_api_fundamentals/06_reasoning_tokens.ipynb)
currently documents Xhigh as equivalent to High and does not promise a fixed
default. Thinking consumes output tokens and can increase time and cost. The
setting applies to both tests and practice; save, retest and assign roles after
changing it. Other adapters keep their defaults, without unsupported parameters.
SQLite model-call records retain selected effort and reported reasoning-token
counts when supplied, never raw reasoning. Activity difficulty is separate.
For Meta-hosted inference, the cloud location is fixed but the allowed audience
is your explicit choice. The app shows a provider-terms disclaimer and records
your required acknowledgment; it does not certify that an account or agreement
permits a particular audience. To run a Meta/Llama model locally, configure it
through Ollama or vLLM instead.

Open **Learners** to add yourself or a child. Sign out, then sign in with the
learner account. Enter a topic, optionally add reference material, and choose
**Start session**. The first activity is created automatically.

The page tabs separate the workflow:

- **Practice**: one conversation containing work, photos, readings and replies.
  Use **Send** for work or questions, **Attach photo** for upload/phone QR,
  **Help** for suggestions and **Next activity options** to move on.
  **Session & material** holds reference material and session preferences.
- **History**: reopen or review a saved session.
- **Learners** (adult): manage learner accounts and passwords, sign out browsers, export saved work,
  revoke access, and delete learners.
- **Settings** (adult): add/edit AI connections and keys, review cloud/audience
  permissions, test connections, and separately assign the active tutor and photo
  reader. Connection tests use synthetic samples.
- **Help**: setup, phone connection, model configuration, troubleshooting, and
  privacy. Contextual disclosures explain controls without leaving the page.

Switching page tabs preserves unsent text, photo previews, and pending retry
requests in memory. Closing/reloading the tab or switching learners can lose
unsent work; submitted work is stored on the server. Learners see only Practice,
History, and Help.

The administrator manages learner accounts in **Learners**. Choose **Add learner
account**, enter a unique username and password, and select an age group. Each
learner signs in through the common sign-in page and sees only their own work.
Select an account to reset its password, manage its signed-in browsers, export
saved practice, or delete it. Password resets sign out that learner's browsers.

If the administrator also studies, create one distinct learner account for that
work, then sign in with that learner account. Administrator pages contain only
account management, AI settings and help.

A physical phone needs the shared private HTTPS address in the phone guide.
For full practice, sign in with the learner's credentials. **Take photo with
phone** opens a limited camera page without a learner login.

`make demo` starts a disposable preview at <http://127.0.0.1:8000>, with public
synthetic credentials `demo` / `synthetic-demo-password-only`. It blocks tutoring
and personal uploads; use the private setup above to practice. The UI links from
unavailable tutoring to setup help and Settings.

The default mock routes return explicitly synthetic fixtures and do not provide
real tutoring or read handwriting. Add actual **tutor and vision** connections in
Settings and follow [PROVIDER_STATUS](docs/PROVIDER_STATUS.md) before using them.
Keys entered in Settings are write-only and encrypted in the private database.
Preserve the deployment secret separately when backing up; changing it requires
re-entering saved API keys. Normal app setup does not require provider YAML.
Advanced operators can still use [providers.example.yaml](config/providers.example.yaml);
those connections are shown read-only. Explicit environment cloud/audience
restrictions remain enforced and are identified in Settings.
An unavailable model produces a visible error, not an authored-hint substitute.

Before a database upgrade, stop the API and worker and back up retained data.
Use `make migrate start` for a native installation; follow the container commands
in [RUNBOOK](docs/RUNBOOK.md#container-package) for Docker. The runbook also
covers private HTTPS, EC2/EBS, retention, encrypted backups, and restore rehearsals.

## Behavior and boundaries

- AI-generated activities and guidance across subjects; full written work and
  recent conversation inform feedback, revisions, and next activities.
- Paste an assignment or photograph one to generate distinct analogous practice.
  Supply a book excerpt for passage-specific comprehension questions. The app
  does not fetch books or pretend a title supplies the full text.
- Easier, Standard, and Harder activity difficulty, adjustable within a saved
  session, with direct Easier/Harder next-activity buttons. Learner-led, balanced,
  and tutor-led initiative; no grade-level gate.
- AI assessment is not a verified grade or a proof of mastery. Model confidence
  can be mistaken. Handwriting accuracy, factual correctness, and answer-leak
  resistance need evaluation with your actual model, not just passing mock tests.
- Owned session history, authenticated exports, and deletion with recovery tombstones.
- Durable jobs survive API reloads and worker crashes. Duplicate requests produce
  one visible result. A crash after a provider response may require a second
  billed request; total calls remain bounded.
- Choose or drag and drop JPG, PNG, WebP, HEIC, or HEIF photos (up to 8 MiB).
  HEIC/HEIF conversion happens on the server so browsers need no HEIC decoder.
  Photos are normalized to a bounded, high-quality JPEG with metadata removed.
  Photos are deleted after processing; failed/unprocessed photos expire within 24 hours.
  History defaults to 30 days. Retention runs in the worker.
- SQLite stores operational model identifiers, phases, safe errors, timing and
  available token counts without copying questions, answers, images or keys into
  logs. Submitted text is retained as session history. There is no separate
  concerning-message archive, safety classifier, or alert service.
- Service-worker caches contain public assets only. Offline does not mean the
  server or AI can be reached; no work is silently replayed to a cloud provider.

```mermaid
flowchart LR
  Browser[React PWA] --> API[FastAPI: auth, ownership, tutoring workflow]
  API --> DB[(Private local SQLite)]
  Worker[Separate worker] --> DB
  Worker --> Routes[Policy-checked provider adapters]
  API --> Photos[Private normalized photos]
  Worker --> Photos
```

Run one API process and one worker on the same host and local disk. No network
filesystem, horizontal scaling, autonomous model tools, or silent cloud fallback.
Provider keys and answer keys stay on the backend.
Live provider calls use a short-lived child process so DNS, SDK setup, and slow
responses cannot exceed the request deadline. See [D008](docs/DECISIONS.md#d008--bounded-provider-io-and-destination-validation-2026-09-07).

## Commands and verification

The [Makefile](Makefile) is authoritative.

| Command                                                                  | Purpose                                                                                                     |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| `make bootstrap`, `make hooks-install`                                   | Locked install and local commit checks                                                                      |
| `make check`                                                             | Locks, lint, format, strict types, unit/component tests, builds, generated contracts, secret scan, IaC lint |
| `make test-integration`                                                  | On-disk migration, authorization, recovery, provider-policy and retention checks                            |
| `make smoke` / `make test-e2e`                                           | Isolated API/worker and desktop/mobile Chromium workflows                                                   |
| `make eval-mock`                                                         | Original deterministic fixtures and mock vision contracts; no quality claim                                 |
| `make audit`, `make hooks-check`                                         | Locked dependency vulnerability audit and tracked-file checks                                               |
| `make contracts` / `make contracts-check`                                | Regenerate OpenAPI/TypeScript or reject drift                                                               |
| `make format`, `make lint`, `make typecheck`                             | Focused developer checks                                                                                    |
| `make demo`, `make seed-demo`                                            | Disposable supervisor, or explicit empty demo database seed                                                 |
| `make start`, `make dev`, `make worker`                                  | Persistent local setup/start, loopback-only start, or worker alone                                          |
| `make migrate`                                                           | Upgrade a retained database with all app/worker writes stopped                                              |
| `make serve`                                                             | API/worker behind your configured private HTTPS gateway; see PHONE_SETUP                                    |
| `make down`                                                              | Stop Compose services while retaining data; native services use Ctrl+C                                      |
| `make backup OUTPUT=...`, `make restore INPUT=... OUTPUT=... LEDGER=...` | Interactive encrypted backup/restore with writes stopped                                                    |
| `make eval-live PROVIDER=...`                                            | Explicit opt-in, at most three synthetic tutor calls; requires configured route                             |

Install the test browser with `pnpm exec playwright install --with-deps chromium`,
or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to an installed Chrome. Mobile
emulation does not certify actual Safari/Chrome phone behavior. Restricted tools
can use `UV_CACHE_DIR=/tmp/...` and `PNPM='pnpm --store-dir /tmp/...'`.

CI also builds and smoke-tests the non-root container, scans HIGH/CRITICAL image
vulnerabilities, and generates an SBOM. It does not provision, publish a service,
or invoke live inference. The task log distinguishes observed runs from configured
checks. Review public staged files; never blanket-add local configuration or data.

## Contributing and license

Read [AGENTS](AGENTS.md), the [specification](docs/SPECIFICATION.md), and the
[current handoff](docs/HANDOFF.md). Use original synthetic fixtures and record
actual outcomes. See [THREAT_MODEL](docs/THREAT_MODEL.md) for boundaries and
[evals/MANIFEST](evals/MANIFEST.md) for provenance. Implementation was AI-assisted;
software tests and human review provide the evidence, not model self-assessment.

[MIT licensed](LICENSE), as approved by the maintainer. Dependencies, model
weights, and third-party runtime artifacts retain their own licenses.
