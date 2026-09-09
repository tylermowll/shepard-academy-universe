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
make start
```

`make start` connects to the standard Docker app if it is already running on
port 8000; otherwise it starts a native app with persistent settings and data.
On first run, open the private setup link printed in the terminal and choose
your administrator username and password in the browser. The link expires after
30 minutes if unopened. Once opened, this browser has eight hours to finish
setup, including after refreshes and app restarts. Run `make start` to renew an
unopened expired link; stop a native terminal run with Ctrl+C first. Docker can
keep running. App updates wait until signup finishes before offering a refresh.
Keep the link private. Existing accounts sign in at the printed app address.

For an existing installation, stop all app/worker writes and back up retained
data before upgrading. If startup reports an old database schema, run
`make migrate start` for a native app. For Docker, follow the
[container upgrade instructions](RUNBOOK.md#container-package).

Configuration/key entry below is for you to perform in your trusted local app,
not for a coding agent to read. Never paste private files or keys into chat.

## 2. Give the phone a reachable HTTPS address

The computer must stay awake. `localhost` on an iPhone means the iPhone itself.
Both desktop and phone must open the **same configured HTTPS address**.

HTTP localhost permits passwords of six characters; HTTPS requires twelve. If
you chose a shorter local password, after setting the HTTPS origin and stopping
the app, run `make admin` with your **existing login name** and a password of at
least twelve characters. This explicit reset signs out old adult sessions; it
does not delete learners or work. `make serve` refuses to start with a local-only
password, rather than silently making that account network-accessible.

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

In the signed-in adult app, open **Settings**:

1. Under **Connections**, select **Ollama**, **vLLM**, or your API type.
2. Enter the model server address and exact installed/approved model name.
   For Ollama on the same computer, use `http://127.0.0.1:11434` and the name
   from `ollama list`. For vLLM, use its serving address ending in `/v1`.
   It needs a different port from this app's default port 8000.
3. Enter the API key if the endpoint requires one. Saved keys are encrypted on
   the app server, never displayed again, and can be replaced or removed later.
4. Choose the correct processing boundary and allowed users. Enable photo input
   only if the installed model actually supports images; a checkbox cannot add
   that capability. Review the model/provider terms and save the connection.
5. Under **App permissions**, explicitly enable cloud processing if needed.
   A Meta-hosted connection is always cloud processing, but its allowed audience
   is selected by the adult operator. Read its provider-specific age/data notice
   and confirm the terms applying to your account. The app records that choice;
   it does not certify provider eligibility. Environment policy locks are shown
   and cannot be overridden by this page.
6. Under **Connection tests**, explicitly run **Test tutor** and **Test photo
   reader** as needed. Tests send sample data, not learner work, and API providers
   may charge. The tutor test
   uses two calls (activity generation and feedback); the photo test uses one and
   must correctly read the known synthetic fraction.
7. Under **Assign active connections**, choose the tested **Tutor connection**
   and **Photo reader connection**, acknowledge where work will go, and save.

Saving a connection alone makes no inference call and changes no active route.
Saved connections are available to both API and worker without restarting.
The app does not install models or start Ollama/vLLM. Start your model server
separately, reachable from the app computer. The iPhone never calls it directly.

The same image-capable model may handle both roles. A cloud tutor receives text
read from photos even when the photo reader is local. The default `demo` provider
is a mock; it does not teach or read handwriting. Tests are not evidence of
general model quality. See [provider verification](PROVIDER_STATUS.md) for
capability expiry, context limits and evaluation guidance.

File-managed connections remain an optional advanced deployment path and are
read-only in Settings; see [the public example](../config/providers.example.yaml).
Bedrock uses that path and workload credentials. Never expose a model server
publicly as a phone-access shortcut.

## 4. Launch with phone access and start practice

After configuring the private HTTPS gateway and setting `APP_PUBLIC_ORIGIN`
as in section 2, stop the local app with Ctrl+C and run:

```bash
make serve
```

This loads your existing private settings, builds the app and supervises one API
on `127.0.0.1:8000` and one worker behind the gateway. Ctrl+C stops the app/worker
and preserves data; it does not stop Tailscale Serve or Caddy. For computer-only
HTTP use `make start`.

Open your configured HTTPS address on the computer and sign in. Create a learner account
under **Learners**, then open **Practice**, select the
learner and enter a topic. **Tutor options** controls how much the tutor leads.
Choose **Start session**, then **Create practice activity**. No grade level or
skill catalog is required.

To study from homework, paste it or use the reference-photo option. The tutor
creates distinct practice rather than answering the original.

## 5. Use your iPhone

On the computer, choose **Attach photo → Take photo with phone**. Scan the QR with the iPhone's
Camera app, tap the link, and choose **Take or choose a photo**. Preview, crop or
rotate as needed, then tap **Send to computer**. The phone needs no tutor login.
If it is already signed in, leave it signed in: the QR link opens the photo page
independently of that login, including when the browser reuses an open tab.

For the entire tutor on the phone, open the same HTTPS address and sign in with
the learner username and password created by the administrator. The administrator
can reset that password and manage signed-in browsers in **Learners**. This
account sign-in is separate from sending a photo through the QR link.

The in-app **Help → Phone setup** page contains these two workflows and the HTTPS
setup steps. The adjacent phone help disclosures link directly to it.

Return to the computer. Within the normal polling interval, the photo's processing
status appears in session history. The app displays the full reading and any
necessary readability advice. A usable reading proceeds to guidance
automatically—do not wait for a confirmation control. If the model reports
essential unreadable content, automatic photo tutoring stops and asks for a
specific clarification. Incidental uncertainty does not block useful feedback.
You can ask why the reader rejected the photo in the same conversation; its
report remains available as explicitly uncertain context. Clarify the relevant
line or send a clearer section when needed. Model confidence is not
proof of accuracy; if you notice a wrong reading, point it out in the discussion
or submit a corrected response.

Read the guidance, revise on paper and send another photo, or discuss the concepts
in text. Request a next activity when ready; the tutor uses recent work and your
initiative setting. It explains and uses different relevant examples rather than
giving the current answer or finishing your homework.

Links last two hours and accept one photo. Keep the phone page open while an
upload is pending; its retry button resends the same photo without creating a
second operation. If you reload or close it, rescan the original QR to check its
receipt, or choose **New QR code** on the computer if it expired. A new link cancels
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
