# Operations runbook

## Native local host

Follow the README setup. `make start` loads private `.env`
settings through uv without executing shell content, creates only missing setup,
and runs one API and one worker. With no adult account, first start prints a
thirty-minute, one-use setup link; the account is created in the browser, not a
terminal prompt. Invalid form input does not stop the app. Subsequent starts
never reset credentials or reopen first-account creation. An old retained
database stops startup before building: stop all API/worker writes, back up data,
then explicitly run `make migrate start`. Ctrl+C stops both services and preserves
the persistent data. `make demo` is different: its temporary data is deleted when
it stops. `make start` supports loopback HTTP or a configured private HTTPS
gateway; `make dev` is loopback-only, and `make serve` requires the gateway.
`make dev-api` alone is a development API reload process;
`make dev-web` alone is a frontend development server. Use the combined same-origin
application for end-to-end practice. `/health/live` reports process liveness;
`/health/ready` returns unavailable if the database or recent worker heartbeat is
missing. It never makes paid health-check calls.

Keep the setup link private and keep startup output out of shared logs. The
browser removes the token from its address and exchanges it once for a setup
cookie. The cookie is HttpOnly, restricted to the setup API, and valid for eight
hours. It survives refreshes and API restarts with the same deployment secret.
Unsent passwords clear on reload. App updates defer their refresh button until
account creation finishes. The unopened link expires after thirty minutes;
Ctrl+C followed by `make start` issues a replacement for a native app.
No public API issues owner links, and setup cannot reset an existing account.

Passwords of 6–11 characters are accepted only with an HTTP loopback origin;
the administrator is then flagged local-only. HTTPS needs at least twelve
characters, with no composition rules. Before enabling the gateway, use the
existing login name with `make admin` to replace a short password. Startup and
backend session/login checks reject local-only credentials in network mode,
even if a service bypasses the native launcher. Recovery never requires deleting
the database or changing the session secret.

Migration `0013_local_password_policy` preserves existing accounts and marks newly
accepted short passwords. Downgrade refuses while any local-only password remains;
replace those passwords with at least twelve characters first. Otherwise dropping
the flag could allow older code to expose a short password over the network.

For unattended use, supervise the two commands independently with the host service
manager, with the same private settings and local data directory. Use a dedicated
unprivileged account, restrictive umask, encrypted local disk, restart limits,
and no raw access/payload logs. Stop both before migrations and backups. Do not
run multiple API workers or put SQLite on a network/cloud-sync filesystem.

## Private HTTPS and phones

For the iPhone QR camera workflow and a step-by-step Spark/vLLM setup, see
[PHONE_SETUP](PHONE_SETUP.md). `make serve` supervises the API/worker behind the
separately configured HTTPS gateway and preserves data on exit.

Set `APP_PUBLIC_ORIGIN=https://your-reviewed-hostname` to the exact browser origin.
The backend selects Secure cookies automatically and rejects other Host/Origin
values. Run Caddy on the host using `infra/gateway/Caddyfile` and set `TUTOR_HOST`
to that hostname. Keep API port 8000 loopback-only. Caddy terminates TLS and
forwards to that local port; Uvicorn ignores forwarded client headers.

For LAN-only names, add `tls internal` and install/trust the Caddy local CA on
each device using the OS-supported process. Never bypass certificate errors.
For public DNS, use an appropriate validated certificate challenge. A firewall
that allows only 443 needs TLS-ALPN validation or a separately configured DNS
challenge; HTTP-01 requires a deliberate port-80 exception. Do not expose model,
worker, database, or administration service ports as a workaround.

For full learner practice on a phone, sign in with that learner's credentials.
The camera-only QR companion instead delegates one upload without a learner login.
Record actual Safari/Chrome
camera, HEIC, background/reconnect, install/update, zoom, keyboard and screen-reader
results using ACCEPTANCE. An emulator does not replace these checks.

## Container package

The final image uses a digest-pinned Distroless Debian 13 runtime with no shell or
package manager (D007). Use the explicit Python/CLI commands below; rebuild for
dependency changes. The Dockerfile builds public assets and a locked Python environment using the same
managed Python runtime as native checks. Runtime UID/GID is 10001. Compose mounts
one host data directory into both services, makes root filesystems read-only,
drops capabilities, and binds only `127.0.0.1:8000`.
The explicit Compose project name is `shepherd-academy-universe`, so changing
the checkout directory does not silently choose another Docker project.

From a fresh clone, after generating a private `.env`:

```bash
mkdir -p data
sudo chown 10001:10001 data
sudo chmod 700 data
docker compose -f infra/docker/compose.yaml build
docker compose -f infra/docker/compose.yaml run --rm api alembic upgrade head
docker compose -f infra/docker/compose.yaml up -d
make start
curl --fail http://127.0.0.1:8000/health/ready
```

If the public origin is HTTPS, supply its Host header for the loopback readiness
probe or request readiness through the gateway. Do not change the configured
origin merely to pass a health check. `make down` retains the host data directory.
Use `make down` when you want to stop the containers.

Open the private link printed by `make start` to choose the first administrator's
credentials in the browser. If it expires, run `make start` again while Docker
continues running. The direct operator command is
`docker compose -f infra/docker/compose.yaml exec -T api python -m math_tutor.owner_setup`.
The command uses the API's `SHEPHERD_OWNER_SOCKET` Unix socket inside its private
tmpfs directory. Directory permissions are 700; socket permissions are 600.
`make start` discovers the running API using public Docker metadata before
loading native settings or checking Node. It does not start another app.
Every new link replaces the previous unopened link. Browser permission already
granted lasts until its eight-hour expiry or account creation. Once an
administrator exists, the command returns the sign-in address. Explicit
`make dev`, `make serve` and
alternate `ENV_FILE` values select native startup.

For a container upgrade, stop both services, back up the mounted data directory,
then run:

```bash
docker compose -f infra/docker/compose.yaml build
docker compose -f infra/docker/compose.yaml run --rm api alembic upgrade head
docker compose -f infra/docker/compose.yaml up -d
```

Keep the same data mount and private settings. Verify readiness through the
configured origin after startup. For an administrator password reset, stop both
services and run
`docker compose -f infra/docker/compose.yaml run --rm api python -m math_tutor.cli admin`
with the existing username, then start the services again. The reset revokes
administrator sessions and preserves learner accounts and saved work.

Compose reads operator `.env` itself. Browser-managed AI connections are stored
in the shared private database and configured through adult Settings. For optional
file-managed connections, set an absolute container path for `PROVIDER_CONFIG`
and add an explicit **read-only** mount of the reviewed private provider YAML to
both services. For host-local Ollama/vLLM, localhost inside the
container is not the host: use a private reachable interface or a reviewed Linux
host-gateway mapping, and block public model ports. No provider config or secrets
are baked into the image. Supply cloud credentials through workload identity or
an explicitly managed short-lived mechanism, not committed static keys.

`scripts/container-smoke.sh` migrates a disposable database and checks the
non-root API, worker readiness and built UI. It creates a synthetic administrator
through the owner link, checks renewal and stale-link rejection, and verifies
that account creation closes setup. CI separately scans the image and generates
a CycloneDX SBOM. See TASKS for observed results.

## Retention, export and deletion

Confirmed photos become inaccessible when processing completes and are then
deleted. A crash or storage failure leaves a durable cleanup reference for the
next sweep. Failed/unprocessed photos default to 24 hours and are capped at 24;
`PHOTO_RETENTION_HOURS` permits shorter retention. History defaults to 30 days;
`HISTORY_RETENTION_DAYS` is bounded 1–365. The worker sweeps every 60 seconds while
running. Expired photos are rejected by both the image API and the worker before
inference, including when physical deletion is delayed. Monitor readiness;
downtime delays physical expiry cleanup.

Migration `0011_photo_deletion` adds a durable image-deletion queue. Apply it with
API/worker writes stopped before running this version. Learner deletion and
history expiry commit pending opaque image keys with the database purge; the
worker removes those files during its next sweep. Failed unlinks retain their
queue entries across restarts. Other cleanup and tutoring continue after a file
failure. Temporary database/storage errors in the worker loop retry after five
seconds; a failed sweep retries on its next 60-second interval. Existing job
leases and provider-call budgets still apply. `--once` exits unsuccessfully on
a sweep/database failure so scripts cannot mistake it for completed work.

Warnings report cleanup/storage categories without filenames, learner content,
SQL, or raw exception details. If they persist, check the private volume's mount,
space, ownership and write permissions. A running worker cannot repair a missing
or read-only volume by itself.

An adult export is an authenticated no-store download in the current request.
There is no persistent bearer export URL. Downloaded copies are outside server
revocation: the adult must delete them separately. Revocation prevents new device
requests. Learner deletion immediately revokes sessions and cancels work, purges
database content, queues physical image deletion, and records a content-free UUID
tombstone. Late worker output is discarded.
The journal `data/deletions.jsonl` is fsynced before the deletion commit. Keep it
private and preserve its latest version during recovery. Content-free audit events
and tombstones are retained for recovery/accountability; no raw prompts or photos
are in provider-call logs.

## Encrypted backup and restore rehearsal

Stop API and worker writes. Backups use SQLite's backup API, then bundle referenced
photos, checksums, database and deletion ledger. AES-256-GCM encrypts the archive;
scrypt derives the key from a separately stored passphrase. It is entered through
a hidden prompt, never argv or a checked-in variable. Copying a live main SQLite
file without its WAL is not a backup procedure.

```bash
make backup OUTPUT=/private/backup/tutor-2026-09-06.enc
make restore INPUT=/private/backup/tutor-2026-09-06.enc OUTPUT=/private/restore-rehearsal LEDGER=/private/current/deletions.jsonl
```

Both targets acknowledge that you stopped writes. The destination must not exist.
They load the same private `.env` as `make start`, including a custom database
path, and refuse to run while the native launcher holds that database's lock.
Stop independently supervised services too; the lock cannot stop those writers.
Supply the **current** deletion ledger, even when restoring an old archive. If no
learner was ever deleted, explicitly create an empty private ledger. Never replace
a missing current ledger with an old empty one to bypass deletion preservation.
The restore authenticates before extraction, rejects unsafe archive paths, checks
hashes and SQLite integrity/foreign keys, reapplies all known deletions, checkpoints
the restored WAL, revokes sessions/pairings, and cancels pending jobs. Test a new
isolated restore directory before changing production paths. Re-pair devices after
cutover. Retention sweeps resume with the worker.

Browser-managed connections and their encrypted API-key values are included in
the database archive. Operator environment/YAML, certificates, and the deployment
session secret are **not** included. Recover those separately from your secret
manager. Saved API keys require the original session secret for decryption; if
you rotate it, replace the affected keys in adult Settings and retest connections.
Encryption does not protect against someone who has both the database and that
secret. Export the new database path after restore. Keep
encrypted backups for at most seven days by default and keep the passphrase in a
separate secure location. An adult must account for exported downloads and old
backup retention when fulfilling deletion requests.

Optional encrypted S3 transfer is an explicit operator CLI:

```bash
uv run --project apps/api --locked python -m math_tutor.cloud_archive put --bucket YOUR_PRIVATE_BUCKET --region YOUR_REGION --key YOUR_BACKUP_UUID --file /private/backup/tutor.enc
```

`get` requires a new output file; `delete` removes the current key. Transfers are
capped at 64 MiB, accept only the encrypted archive format, use TLS and role-based
SDK credentials, and never run from learner requests. Versioned S3 noncurrent
copies expire by lifecycle, rather than immediately on DeleteObject.

## EC2/EBS reference deployment

`infra/aws/household.json` is a CloudFormation template, validated by
`make infra-check`. It creates no resources until an operator explicitly applies
it. Select an exact reviewed Linux AMI, matching subnet/availability zone, VPC,
household/VPN client CIDR, existing secret ARN, budget and notification address.
The host uses IMDSv2, SSM administration, encrypted root disk, and a separate
retained encrypted gp3 data volume. There is no SSH ingress or public model port.
The role can read one supplied secret and transfer objects only under its private
backup bucket's `backups/` prefix. Bedrock permission is deliberately absent;
add narrowly scoped model/region permissions only if that route is selected.

Mount the attached EBS volume by filesystem UUID at the shared private data path.
Inspect the new device before formatting; never format an existing data volume.
Set UID/GID 10001 ownership for the container deployment. Require the mount before
starting services so a missing volume cannot silently write to ephemeral root
storage. On replacement, stop the old host, reattach the retained volume to one
host in the same availability zone, restore configuration, and verify integrity
and readiness before opening access. This design has downtime and no automatic
failover or cross-zone database replication.

The template retains the data volume and backup bucket on stack deletion;
retained resources continue to incur costs. Its 80% monthly budget notification
is an alert, not a hard spending cap. SSM/network/certificate access and the chosen
AMI are account-specific operator checks. No EC2 resources, secrets, DNS records,
S3 buckets, or Bedrock invocations were created during implementation.
