# Computer tutor with an iPhone camera

Run the application on one desktop or laptop. The iPhone sends a photo to that
computer through an expiring QR link. A configured vision model reads it; the
computer shows the reading and then the tutor's guidance. Clear readings proceed
automatically. There is no approval or confirmation button.
No native iPhone app or public deployment is required.

Choose any subject/topic. The AI creates practice, discusses your written work,
and adapts follow-up activities. Photograph one response or source excerpt at a
time so it remains readable. Uploaded/pasted homework is reference-only: the
tutor generates distinct practice on related concepts rather than solving it.
AI feedback is not a verified grade, and actual model quality must be tested.

## 1. Prepare the computer once

Install the toolchain listed in README. In the checkout:

```bash
make bootstrap
make setup
set -a
. ./.env
set +a
make db
make migrate
make admin
```

If already set up, keep your existing `.env`, database and account; do not rerun
`make setup`. Stop API/worker writes and back up retained data before running
`make migrate`. T24 introduced `0009_phone_upload`; T25 adds the tutoring metadata
migration. This does not upgrade historical
pre-cutover schemas; the README's earlier migration warning still applies to those.
Configuration/key entry below is for you to perform locally, not for a
coding agent to read. Never paste the private files or keys into chat.

## 2. Give the phone a reachable HTTPS address

The computer must stay awake. `localhost` on an iPhone means the iPhone itself.
Both desktop and phone must open the **same configured HTTPS address**.

### Convenient private access: Tailscale

Install Tailscale on the computer and iPhone and join your private network.
Its Personal plan is currently free for eligible personal use. Enable HTTPS for
your tailnet, then run this on the computer to proxy the application privately:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
```

Use the exact HTTPS URL reported by Tailscale (without a trailing slash) as
`APP_PUBLIC_ORIGIN` in your local `.env`, for example
`https://your-computer.your-tailnet.ts.net`. This setting's name does not make the
application publicly accessible. Use **Serve**, which is private to your network;
Funnel is a different, public feature and is not needed. Keep Tailscale connected
on the iPhone. The API still binds only to computer loopback, and both devices
need access to the configured Tailscale host. Do not expose vLLM to the internet.

Tailscale adds an external networking dependency; it does not host the app or
perform inference. See [Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates), and
[current Personal pricing](https://tailscale.com/pricing).

### Entirely local Wi-Fi

Use the existing [Caddy LAN setup](RUNBOOK.md#private-https-and-phones): a stable
LAN address/name, `tls internal`, and your local CA installed and trusted on the
computer and iPhone. Allow the gateway port on your private network. No domain
purchase, AWS, Cloudflare, or router port forwarding is required. Guests on an
isolated Wi-Fi network may not be able to reach the computer. Open the HTTPS app
successfully in Safari before trying its QR links; do not bypass certificate errors.

## 3. Configure actual tutoring and handwriting models

The default `demo` provider is a mock and intentionally does not read handwriting.
Use the existing adapter for either Spark or vLLM. Copy the public example to
the ignored private configuration **only if you do not already have one**:

```bash
cp -n config/providers.example.yaml config/providers.yaml
chmod 600 config/providers.yaml
```

Edit this file locally. Keep `routes` on `demo` initially; use the adult UI to
probe and select the live route. In `.env`, set `PROVIDER_CONFIG` to the **absolute
path** of this private YAML file. API and worker must receive the same settings.

### Spark 1.3 API

Under `providers.spark`, set the account-approved exact model ID (expected
`muse-spark-1.3`; verify against your Meta account documentation), confirm the
base URL, set `enabled: true`, and declare `capabilities.image_input: true` only
for an image-capable route. Fill `eligibility_record` with your reviewed intended
use/audience and provider data handling. The backend reads `META_API_KEY` from
its environment; the key never goes into the YAML or browser.

Set `APP_AUDIENCE=adult_only` and `ALLOW_CLOUD_INFERENCE=true` in your local `.env`.
For a key that lasts only in the current Bash terminal, after exporting `.env`:

```bash
read -r -s -p 'Meta API key: ' META_API_KEY
export META_API_KEY
```

This hides key entry and avoids putting the key in shell history. Repeat in a
new terminal, or use your own secret manager. Sending photos to Spark is cloud
processing and may incur your account's API charges. This does not require AWS
or Cloudflare hosting. The current app restricts Meta to adult learners.

The Meta image/structured-output contract still needs a live probe against your
account. `structured_output_mode: native` is the existing default. If the endpoint
does not support that wire schema, select the adapter's explicit `json_prompt`
mode under `capabilities.structured_output_mode` after reviewing the endpoint
documentation, and probe that exact configuration;
all returned JSON remains locally validated. A failed probe is a setup failure,
not evidence the model read the photo.

### Local vLLM

Under `providers.local_vllm`, set your exact served model name and reachable `/v1`
base URL, `enabled: true`, an appropriate `eligibility_record`, and
`capabilities.image_input: true`. Your installed model must actually accept images;
a text-only model cannot be made visual through this flag. Keep
`ALLOW_CLOUD_INFERENCE=false` for local-only processing. No model download or
inference-server installation is performed by this application.

Start vLLM separately. If it runs on another computer, allow private access from
the app host; the iPhone never calls vLLM directly. For container deployments,
use the host reachability guidance in RUNBOOK rather than container `localhost`.

## 4. Launch and enable vision

In the same terminal with your private environment exported:

```bash
set -a
. ./.env
set +a
make serve
```

This builds the PWA and supervises one API on `127.0.0.1:8000` and one worker.
It requires an HTTPS `APP_PUBLIC_ORIGIN` and the separately configured gateway.
Ctrl+C stops the app/worker and preserves your data; it does not stop Tailscale
Serve or Caddy. `make dev` remains the computer-only HTTP development command.

Open your HTTPS address on the computer and sign in:

1. Open **Learners & devices** and add/select your learner. For Spark, choose
   **18 or older** as the age group.
2. Open **Settings → Connection tests & provider details** and choose
   **Test photo reader** for
   `spark` or `local_vllm`. It must correctly transcribe the synthetic `1/2` image.
   This is a real model call, potentially billed for an API provider.
3. Select that provider as **Photo reader** and acknowledge where the photo is
   processed. Also test and select a real **Tutor**, then **Save AI settings**;
   a mock cannot teach.
   The same image-capable model may serve both routes. A cloud tutor receives
   extracted text even if vision
   runs locally. Selection is persisted; a prior selection overrides YAML routes.
4. Open **Practice**, select the learner, and enter a topic. **Tutor options**
   controls how much the tutor leads. Choose **Start session**, then
   **Create practice activity**. No grade level or skill catalog is required.
   To study from homework, paste it or use the reference-photo option; the tutor
   creates different practice instead of answering the original.

The [provider runbook](PROVIDER_STATUS.md) covers probe expiry (seven days), exact
configuration changes, model evaluation and safe error handling.

## 5. Use your iPhone

On the computer, choose **Take photo with phone**. Scan the QR with the iPhone's
Camera app, tap the link, and choose **Take or choose a photo**. Preview, crop or
rotate as needed, then tap **Send to computer**. The phone needs no tutor login.

For the entire tutor on the phone, open the same HTTPS address in its browser and
tap **Pair this device** on the sign-in page. Copy its request ID to
**Learners & devices → Pairing request ID** on the signed-in adult's computer.
Select the learner and choose **Approve device** within five minutes. Keep the
phone browser open; it signs in automatically. This learner pairing is separate
from sending a photo through the QR link.

The in-app **Help → Phone setup** page contains these two workflows and the HTTPS
setup steps. The adjacent phone help disclosures link directly to it.

Return to the computer. Within the normal polling interval, the photo's processing
status appears in session history. The app displays the full reading and any
handwriting/organization advice. A clear reading proceeds to guidance
automatically—do not wait for a confirmation control. If the model reports
ambiguity or low readability, tutoring stops and asks for specific improvements:
for example, separating steps, numbering paragraphs, or rewriting an unclear
symbol. Submit a cleaner photo or type a new response. Model confidence is not
proof of accuracy; if you notice a wrong reading, point it out in the discussion
or submit a corrected response.

Read the guidance, revise on paper and send another photo, or discuss the concepts
in text. Request a next activity when ready; the tutor uses recent work and your
initiative setting. It explains and uses different relevant examples rather than
giving the current answer or finishing your homework.

Links last five minutes and accept one photo. Keep the phone page open while an
upload is pending; its retry button resends the same photo without creating a
second operation. If you reload or close it, rescan the original QR to check its
receipt, or generate a new link on the computer if it expired. A new link cancels
the previous link. Logout/revocation, deletion, changed processing settings, or
finishing/changing the problem invalidates unused links. Links expose neither
history nor grading/admin actions; nevertheless, keep the QR private.

The photo selector sends the original to your computer for private normalization
before preview; the model receives only the submitted preview/crop. The current
limit is 8 MiB and 25 million decoded pixels (allowing 24 MP-class photos).
If the original is too large, use a lower-resolution camera image; 48 MP and RAW
originals are not supported. See Apple's [camera resolution settings](https://support.apple.com/guide/iphone/change-advanced-camera-settings-iphb362b394e/ios).
Submitted images are deleted after processing. Failed/unprocessed
photos expire within 24 hours; the worker must be running to perform cleanup.

## If something is unavailable

- No phone-photo button: check the worker, configured vision route, probe, learner
  eligibility, and the status message above the photo controls. Demo mode blocks
  uploads; use private mode. An active operation must finish or be canceled first.
- QR opens localhost or cannot connect: reopen the computer app at the configured
  HTTPS address. Check the phone's network/Tailscale connection and trusted certificate.
- Synthetic/unreadable message mentioning mock: select a real, successfully
  probed vision route. Mock tests do not measure handwriting quality.
- Photo accepted but reading fails: inspect the safe operation error and provider
  settings, then use the computer's operation retry. Cloud fallback is never automatic.
- Reading rejected: follow the legibility/organization advice and retake it.
  Do not repeatedly retry inference on a genuinely unreadable image.
- Generic or poor guidance: confirm a real tutor route is selected. The application
  does not limit you to fixed math templates, but models differ in subject,
  handwriting, and teaching quality. Evaluate the exact configured model.

Automated tests use original synthetic images. Actual Safari camera/HEIC, QR
scanning, and exact-model handwriting quality require separate checks on your
devices; consult the T24 evidence in TASKS for what was actually run.
