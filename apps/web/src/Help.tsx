import type { ReactNode } from "react";
import { followPage, pageUrl, type Page, type Navigate } from "./navigation";

export function ContextHelp({
  topic,
  children,
}: {
  topic: string;
  children: ReactNode;
}) {
  return (
    <details className="context-help">
      <summary>{topic}</summary>
      <div>{children}</div>
    </details>
  );
}

const topics = [
  ["practice", "Start practicing"],
  ["accounts", "Accounts & learners"],
  ["phone", "Phone setup"],
  ["setup", "Set up the app"],
  ["providers", "Connect an AI model"],
  ["troubleshooting", "Troubleshooting"],
  ["privacy", "Saved work & privacy"],
] as const;

export function HelpPage({
  topic,
  onNavigate,
}: {
  topic?: string;
  onNavigate: Navigate;
}) {
  const selected = topics.find(([id]) => id === topic) ?? topics[0];
  const link = (page: Page, label: string, help?: string) => (
    <a
      href={pageUrl(page, help)}
      onClick={(event) => followPage(event, onNavigate, page, help)}
    >
      {label}
    </a>
  );
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(
    window.location.hostname,
  );
  return (
    <section aria-label="Help">
      <div className="page-heading">
        <h1 tabIndex={-1}>Help</h1>
        <p>Choose what you want to do.</p>
      </div>
      <div className="help-layout">
        <nav className="help-topics" aria-label="Help topics">
          {topics.map(([id, title]) => (
            <a
              key={id}
              href={pageUrl("help", id)}
              aria-current={selected[0] === id ? "page" : undefined}
              onClick={(event) => followPage(event, onNavigate, "help", id)}
            >
              {title}
            </a>
          ))}
        </nav>
        <article className="help-article card" key={selected[0]}>
          <h2>{selected[1]}</h2>
          {selected[0] === "practice" && (
            <>
              <ol className="steps">
                <li>
                  Open {link("practice", "Practice")}. Choose a learner, or add
                  one in {link("learners", "Learners & devices")} if you are
                  signed in as an adult.
                </li>
                <li>
                  Enter a topic, such as “writing a persuasive paragraph.” Start
                  the session, then create an activity from your topic or
                  reference material. Choose Easier, Standard, or Harder to set
                  the level; you can change it during the session.
                </li>
                <li>
                  Write your work or question and choose <strong>Send</strong>.
                  Use <strong>Attach photo</strong> to upload work or choose{" "}
                  <strong>Take photo with phone</strong>.
                </li>
                <li>
                  Read the feedback. Revise your response, ask a question, or
                  ask for a hint from <strong>Help</strong>. Choose from{" "}
                  <strong>Next activity options</strong> when you are ready.
                </li>
              </ol>
              <p>
                {link("history", "History")} holds your saved sessions.
                Switching pages keeps your unsent work in this tab; reloading or
                closing it can lose unsent text and photos.
              </p>
              <ContextHelp topic="Can I use my homework?">
                <p>
                  Yes. Paste an assignment or photograph it as reference
                  material. The tutor creates different practice using the same
                  concepts. It does not complete your assignment. For reading
                  practice, include the passage you want to discuss.
                </p>
              </ContextHelp>
              <ContextHelp topic="Why is Start session unavailable?">
                <p>
                  The demo cannot accept personal work. A private app and an
                  enabled tutor are needed. Follow{" "}
                  {link("help", "Set up the app", "setup")}; an adult can check
                  the selected model in {link("settings", "Settings")}.
                </p>
              </ContextHelp>
            </>
          )}
          {selected[0] === "accounts" && (
            <>
              <h3>One adult sign-in, a profile for each student</h3>
              <p>
                The adult account manages learners, device access, and AI
                settings. Each learner profile holds one person’s practice and
                history. A profile can belong to a child or to the adult.
              </p>
              <h3>If you are both parent and student</h3>
              <ol className="steps">
                <li>
                  Sign in with your adult account and open{" "}
                  {link("learners", "Learners & devices")}.
                </li>
                <li>
                  Choose <strong>Create my practice profile</strong>. Edit the
                  prefilled name if you want, then choose{" "}
                  <strong>Add learner</strong>.
                </li>
                <li>
                  Choose <strong>Start practice</strong>. Your own profile is
                  selected, and your work stays separate from your children’s.
                </li>
              </ol>
              <p>
                You keep the same sign-in for managing the app and studying.
              </p>
              <h3>For a child</h3>
              <p>
                Add their learner profile and choose Under 18. Pair their
                browser from Learners & devices. It opens only their practice
                and history, without Settings, other learners, or an adult
                password. Pairing instructions are in{" "}
                {link("help", "Phone setup", "phone")}.
              </p>
              <p>
                Children use paired browser access; separate child usernames and
                passwords are not needed. The adult can sign out their devices
                at any time.
              </p>
            </>
          )}
          {selected[0] === "phone" && (
            <>
              {loopback && (
                <p className="notice">
                  <strong>This address works only on this computer.</strong>{" "}
                  Your phone cannot reach localhost or 127.0.0.1. Set up a
                  shared HTTPS address below, then open it on both devices.
                </p>
              )}
              <h3>Send a photo while you work on the computer</h3>
              <ol className="steps">
                <li>
                  Start an activity on the computer and choose{" "}
                  <strong>Take photo with phone</strong>.
                </li>
                <li>
                  Scan the QR code with the phone’s camera and open the link. No
                  sign-in or device pairing is needed for this photo.
                </li>
                <li>
                  Choose <strong>Take or choose a photo</strong>, check the
                  preview, and tap <strong>Send to computer</strong>.
                </li>
                <li>
                  Return to the computer to see the reading and feedback. If the
                  link expires, create another one.
                </li>
              </ol>
              <h3>Use the whole tutor on the phone</h3>
              <ol className="steps">
                <li>
                  Open the app’s shared HTTPS address on the phone. On the
                  sign-in page, tap <strong>Pair this device</strong>.
                </li>
                <li>
                  Copy the <strong>Pairing request ID</strong> shown on the
                  phone.
                </li>
                <li>
                  On the computer, sign in as an adult, open{" "}
                  {link("learners", "Learners & devices")}, and select the
                  learner.
                </li>
                <li>
                  Paste the ID into <strong>Pairing request ID</strong> and
                  choose <strong>Approve device</strong> within five minutes.
                  The phone finishes pairing automatically.
                </li>
              </ol>
              <ContextHelp topic="Set up a shared HTTPS address">
                <p>
                  The app must run in private mode first. If you started it with{" "}
                  <code>make demo</code>, follow{" "}
                  {link("help", "Set up the app", "setup")} before continuing.
                </p>
                <p>
                  One supported option is Tailscale on both devices, connected
                  to the same private network. Enable HTTPS for that network,
                  then run this on the computer:
                </p>
                <pre>
                  <code>
                    tailscale serve --bg --https=443 http://127.0.0.1:8000
                  </code>
                </pre>
                <p>
                  Set <code>APP_PUBLIC_ORIGIN</code> in your local{" "}
                  <code>.env</code> to the exact HTTPS address Tailscale
                  reports, without a trailing slash. Stop the app and restart it
                  with:
                </p>
                <pre>
                  <code>make serve</code>
                </pre>
                <p>
                  Open that HTTPS address on both devices and keep the computer
                  awake. Use private Tailscale Serve; public Funnel is
                  unnecessary.
                </p>
                <p>
                  See the official{" "}
                  <a
                    href="https://tailscale.com/docs/reference/tailscale-cli/serve"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Serve instructions
                  </a>{" "}
                  and{" "}
                  <a
                    href="https://tailscale.com/docs/how-to/set-up-https-certificates"
                    target="_blank"
                    rel="noreferrer"
                  >
                    HTTPS setup
                  </a>
                  . A LAN-only Caddy alternative is documented in{" "}
                  <code>docs/PHONE_SETUP.md</code> in your checkout.
                </p>
              </ContextHelp>
            </>
          )}
          {selected[0] === "setup" && (
            <>
              <p>
                <code>make demo</code> is a disposable preview. It deliberately
                blocks tutoring and personal photos. Follow these steps for a
                private workspace.
              </p>
              <h3>First setup on your computer</h3>
              <p>
                Stop the demo with Ctrl+C. In the project folder, after
                installing the prerequisites in README:
              </p>
              <pre>
                <code>{"make bootstrap\nmake start"}</code>
              </pre>
              <p>
                The first start prints a{" "}
                <strong>Create administrator account</strong> link. Open that
                link and choose your login and password here in the browser.
                Localhost needs at least six characters; phone or HTTPS access
                needs twelve. No uppercase or symbol rules apply. Invalid input
                stays on the form so you can correct it.
              </p>
              <p>
                The private setup link expires after thirty minutes. If it
                expires, stop with Ctrl+C and run <code>make start</code> for a
                new one. If you reload the form, reopen the unexpired link from
                the terminal. Existing accounts simply sign in at{" "}
                <code>http://127.0.0.1:8000</code>. Restarts keep your settings,
                account, and practice history.
              </p>
              <p>
                If you already have a private setup, keep your existing
                settings, account, and data. Use <code>make start</code> to
                restart. If startup says the database needs an upgrade, stop the
                app and worker, back up retained data, then run{" "}
                <code>make migrate start</code>. Never migrate while another
                copy is running.
              </p>
              <h3>Finish setup</h3>
              <p>
                The default model returns synthetic test responses.{" "}
                {link("help", "Connect an AI model", "providers")} for actual
                tutoring. To add your phone, follow{" "}
                {link("help", "Phone setup", "phone")}.
              </p>
            </>
          )}
          {selected[0] === "providers" && (
            <>
              <p>
                The tutor needs a model for activities and feedback. Reading
                handwriting also needs a model that accepts images. One
                image-capable model can do both jobs.
              </p>
              <ol className="steps">
                <li>
                  Open {link("settings", "Settings")} and use the{" "}
                  <strong>Connections</strong> step. Select Ollama, vLLM, or
                  your API type. Enter the server URL, exact model name, and an
                  API key if required, then save. Saving does not activate it.
                </li>
                <li>
                  Open <strong>App permissions</strong>. This is the global
                  safety switch for every connection, not another part of the
                  connection you just saved. Enable cloud processing only if you
                  intend to send work to a cloud provider.
                </li>
                <li>
                  Open <strong>Connection tests</strong> and test tutoring and,
                  if needed, photo reading. Tests send sample material, not
                  learner work; API providers may charge. The tutor test makes
                  two sample calls; the photo test makes one.
                </li>
                <li>
                  Open <strong>Assign active connections</strong>. Choose the
                  tutor and photo reader for future learner work, authorize the
                  destinations, and save. Return to{" "}
                  {link("practice", "Practice")}.
                </li>
              </ol>
              <p>
                A saved connection can be selected before it is ready; the
                assignment step then names each missing permission or test and
                links to the step that fixes it. Demo cannot teach or read
                handwriting. The app does not install or download models.
              </p>
              <ContextHelp topic="What is the model context limit?">
                <p>
                  It is the model server&apos;s documented total context window,
                  including input and output tokens—not the desired response
                  length and not memory reserved by this app. Enter the value
                  supported by the exact model/server combination. Million-token
                  windows are accepted; ordinary tutoring requests remain much
                  smaller and separately bounded.
                </p>
              </ContextHelp>
              <ContextHelp topic="Where do I enter an API key?">
                <p>
                  In the adult <strong>Add AI connection</strong> form in{" "}
                  {link("settings", "Settings")}. Saved keys are encrypted on
                  the app server and are never returned to the browser. Editing
                  lets you keep, replace, or remove a key. Keep keys out of chat
                  and source control; only enter them into your own trusted app.
                </p>
              </ContextHelp>
              <ContextHelp topic="What server URL and model name do I use?">
                <p>
                  For Ollama on this computer, the server URL is normally{" "}
                  <code>http://127.0.0.1:11434</code>. Use the exact installed
                  model name shown by <code>ollama list</code>. For vLLM, use
                  your serving address ending in <code>/v1</code> and the model
                  name it serves. Use a different port from this app, which
                  normally uses port 8000.
                </p>
                <p>
                  These addresses are reached from the app server, not from your
                  phone. If the model runs elsewhere, use its reachable private
                  address. A text-only model cannot read photos; enable photo
                  support only for an image-capable model and test it.
                </p>
              </ContextHelp>
              <ContextHelp topic="Can children use a Meta or Llama model?">
                <p>
                  For Meta&apos;s hosted API, choose the allowed users only
                  after checking the current age and data terms for your
                  account. The app records and enforces your selection, but does
                  not certify that a provider permits it. The hosted location is
                  fixed to cloud processing.
                </p>
                <p>
                  To serve a Meta/Llama model on your own computer or private
                  network, choose Ollama or vLLM as the connection type instead
                  and review that model&apos;s license and use policy.
                </p>
              </ContextHelp>
              <ContextHelp topic="Why is a setting managed by the server?">
                <p>
                  An operator can lock cloud access or audience policy in the
                  deployment environment. Settings shows those restrictions and
                  cannot bypass them. Connections from an operator-managed
                  provider file are read-only here; add a separate connection to
                  manage one in the app. Bedrock continues to use the
                  operator&apos;s workload credentials and provider file.
                </p>
              </ContextHelp>
              <ContextHelp topic="What happens to keys after a restore?">
                <p>
                  Keep your deployment secret backed up privately with your
                  operational settings. Saved API keys need that same secret to
                  be decrypted. If it changes or is lost, edit each affected
                  connection and enter its key again, then retest it. Never
                  paste your settings file into chat.
                </p>
              </ContextHelp>
              <ContextHelp topic="Why is a model unavailable for a learner?">
                <p>
                  The server checks the learner’s age category, the provider’s
                  allowed audience, image support, and whether cloud processing
                  was enabled by the adult. Check those settings and the failed
                  test message before choosing a model. Tests expire after seven
                  days. After editing a connection, retest it and save your
                  tutor/photo selections again to approve the changed settings
                  before new learner requests use them.
                </p>
              </ContextHelp>
            </>
          )}
          {selected[0] === "troubleshooting" && (
            <>
              <ContextHelp topic="The phone cannot open the app">
                <p>
                  Use the same HTTPS address on both devices. A localhost
                  address reaches only the device that opens it. Keep the
                  computer awake and check the private network connection.
                  Follow {link("help", "Phone setup", "phone")}.
                </p>
              </ContextHelp>
              <ContextHelp topic="The pairing request expired">
                <p>
                  On the phone, choose Pair this device again. Paste the new ID
                  into Learners & devices on the computer and approve it within
                  five minutes. Keep the original phone browser open.
                </p>
              </ContextHelp>
              <ContextHelp topic="An activity or photo is stuck">
                <p>
                  Check that the computer’s API and worker are running.
                  Reconnect and reopen the session in History. Use the retry
                  button on the failed request; it keeps the original
                  submission. If a provider test fails, check Settings and its
                  server configuration.
                </p>
              </ContextHelp>
              <ContextHelp topic="The tutor misread my handwriting">
                <p>
                  Check the displayed reading before using the feedback. Tell
                  the tutor what was misread, type your work, or retake a
                  well-lit photo. Include the whole response and separate lines
                  or steps.
                </p>
              </ContextHelp>
              <ContextHelp topic="My photo is rejected">
                <p>
                  Use JPEG, PNG, WebP, HEIC, or HEIF under 8 MiB and 25 million
                  pixels. Crop to the work or use a lower-resolution photo. PDFs
                  and screenshots containing unreadably small writing will need
                  a new image.
                </p>
              </ContextHelp>
              <ContextHelp topic="I forgot the adult password">
                <p>
                  The person running the app can run <code>make admin</code> in
                  the terminal and enter the existing login name to reset its
                  password. Saved settings load automatically. This signs that
                  adult out on other browsers without deleting learners or work.
                  This recovery step is separate from first-time browser setup.
                </p>
              </ContextHelp>
              <ContextHelp topic="My local password stops phone access">
                <p>
                  Passwords shorter than twelve characters are for HTTP
                  localhost only. After setting your HTTPS address and stopping
                  the app, run <code>make admin</code> with your existing login
                  name and a password of at least twelve characters, then
                  restart. Do not delete your database or change the session
                  secret.
                </p>
              </ContextHelp>
            </>
          )}
          {selected[0] === "privacy" && (
            <>
              <p>
                Submitted work is saved to the computer running the app. The
                adult who manages a learner can review their sessions, export
                them, or delete them in Learners & devices.
              </p>
              <p>
                Photos are removed after processing. Failed or unprocessed
                photos expire within 24 hours by default. Later review uses the
                saved text. Session history is kept for 30 days by default; the
                operator may change retention.
              </p>
              <p>
                Troubleshooting records keep the model, operation, outcome,
                timing, and available token counts. They do not copy your
                questions, answers, photos, or API keys. Submitted conversation
                content remains in session history under the retention rules
                above. The app does not make special copies of concerning
                messages or send safety alerts.
              </p>
              <p>
                Practice shows where text and photos are processed. A cloud
                model receives the selected content only after the adult enables
                that service. Provider retention and existing backups have their
                own rules.
              </p>
              <p>
                AI feedback can be wrong. It is guidance, not a verified grade.
                Ask for an explanation or correct a mistaken reading.
              </p>
              <p>
                Unsent drafts stay in this browser tab while you change pages.
                Reloading, signing out, switching learners, or closing the tab
                can lose them.
              </p>
            </>
          )}
        </article>
      </div>
    </section>
  );
}
