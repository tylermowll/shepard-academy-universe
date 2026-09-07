# Operations runbook

## Native local host

Follow the README setup. Export settings locally; the application does not parse
`.env` automatically. Run one API and one worker under `make dev` for local use.
Ctrl+C stops both. `make dev-api` alone is a development API reload process;
`make dev-web` alone is a frontend development server. Use the combined same-origin
application for end-to-end practice. `/health/live` reports process liveness;
`/health/ready` returns unavailable if the database or recent worker heartbeat is
missing. It never makes paid health-check calls.

For unattended use, supervise the two commands independently with the host service
manager, with the same private settings and local data directory. Use a dedicated
unprivileged account, restrictive umask, encrypted local disk, restart limits,
and no raw access/payload logs. Stop both before migrations and backups. Do not
run multiple API workers or put SQLite on a network/cloud-sync filesystem.

## Private HTTPS and phones

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

Pair each phone browser from the adult workspace. Record actual Safari/Chrome
camera, HEIC, background/reconnect, install/update, zoom, keyboard and screen-reader
results using ACCEPTANCE. An emulator does not replace these checks.

## Container package

The Dockerfile builds public assets and a locked Python environment using the same
managed Python runtime as native checks. Runtime UID/GID is 10001. Compose mounts
one host data directory into both services, makes root filesystems read-only,
drops capabilities, and binds only `127.0.0.1:8000`.

From a fresh clone, after generating a private `.env`:

```bash
mkdir -p data
sudo chown 10001:10001 data
sudo chmod 700 data
docker compose -f infra/docker/compose.yaml build
docker compose -f infra/docker/compose.yaml run --rm api alembic upgrade head
docker compose -f infra/docker/compose.yaml run --rm api python -m math_tutor.cli admin
docker compose -f infra/docker/compose.yaml up -d
curl --fail http://127.0.0.1:8000/health/ready
make down
```

If the public origin is HTTPS, supply its Host header for the loopback readiness
probe or request readiness through the gateway. Do not change the configured
origin merely to pass a health check. `make down` retains the host data directory.
Do not use a destructive volume removal as a routine restart.

Compose reads operator `.env` itself. Set an absolute container path for
`PROVIDER_CONFIG` and add an explicit **read-only** mount of the reviewed private
provider YAML to both services. For host-local Ollama/vLLM, localhost inside the
container is not the host: use a private reachable interface or a reviewed Linux
host-gateway mapping, and block public model ports. No provider config or secrets
are baked into the image. Supply cloud credentials through workload identity or
an explicitly managed short-lived mechanism, not committed static keys.

CI's `scripts/container-smoke.sh` creates a disposable volume, migrates/seeds
synthetic data, and runs non-root API/worker readiness and built-UI checks. It also
scans the resulting image and generates a CycloneDX SBOM. Native host testing is
not container evidence; see TASKS for observed CI results.

## Retention, export and deletion

Photos default to 24 hours and are capped at 24; `PHOTO_RETENTION_HOURS` permits
shorter retention. History defaults to 30 days; `HISTORY_RETENTION_DAYS` is bounded
1–365. The worker sweeps every 60 seconds while running. Monitor readiness and
restart a failed worker; downtime delays physical expiry cleanup.

An adult export is an authenticated no-store download in the current request.
There is no persistent bearer export URL. Downloaded copies are outside server
revocation: the adult must delete them separately. Revocation prevents new device
requests. Learner deletion immediately revokes sessions and cancels work, purges
content, and records a content-free UUID tombstone. Late worker output is discarded.
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
Supply the **current** deletion ledger, even when restoring an old archive. If no
learner was ever deleted, explicitly create an empty private ledger. Never replace
a missing current ledger with an old empty one to bypass deletion preservation.
The restore authenticates before extraction, rejects unsafe archive paths, checks
hashes and SQLite integrity/foreign keys, reapplies all known deletions, checkpoints
the restored WAL, revokes sessions/pairings, and cancels pending jobs. Test a new
isolated restore directory before changing production paths. Re-pair devices after
cutover. Retention sweeps resume with the worker.

Operator configuration, certificate material, and session/provider secrets are
**not** in application archives. Recover them separately from your secret manager,
rotate session secrets where appropriate, and export the new database path. Keep
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
