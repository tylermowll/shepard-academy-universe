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
                  reference material.
                </li>
                <li>
                  Write your response in the box, upload a photo, or use{" "}
                  <strong>Take photo with phone</strong>.
                </li>
                <li>
                  Read the feedback. Revise your response, ask a question, or
                  ask for a hint. Choose <strong>Next activity</strong> when you
                  are ready.
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
                  Choose <strong>Add yourself (adult)</strong>. Edit the name if
                  you want, then choose <strong>Add learner</strong>.
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
                  in the same terminal:
                </p>
                <pre>
                  <code>{"set -a\n. ./.env\nset +a\nmake serve"}</code>
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
                <code>
                  {
                    "make bootstrap\nmake setup\nset -a\n. ./.env\nset +a\nmake db\nmake migrate\nmake admin\nmake dev"
                  }
                </code>
              </pre>
              <p>
                <code>make admin</code> asks you to create your own sign-in name
                and password. Open <code>http://127.0.0.1:8000</code> on this
                computer, sign in, and add a learner.
              </p>
              <p>
                If you already have a private setup, keep your existing
                settings, account, and data. Do not repeat setup or migrate
                retained data while the app is running; use{" "}
                <code>docs/RUNBOOK.md</code> in your checkout.
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
                  The adult running the app configures an installed local model
                  or an approved API in their private provider file, using{" "}
                  <code>config/providers.example.yaml</code> as a reference. The
                  app does not install a model.
                </li>
                <li>
                  Set <code>PROVIDER_CONFIG</code> to that private file’s
                  absolute path in the local environment. Restart the app and
                  worker with those settings.
                </li>
                <li>
                  Open {link("settings", "Settings")}. Test the model for
                  tutoring and, if needed, reading photos. Tests send synthetic
                  material; API providers may charge.
                </li>
                <li>
                  Select the tutor and photo reader, review where your work will
                  be sent, and save. Return to {link("practice", "Practice")}.
                </li>
              </ol>
              <p>
                If only <strong>demo</strong> is listed, an actual model has not
                been enabled. Demo cannot teach or read handwriting.
              </p>
              <ContextHelp topic="Where do I enter an API key?">
                <p>
                  In the server environment or your secret manager, as described
                  in <code>docs/PROVIDER_STATUS.md</code> and{" "}
                  <code>docs/PHONE_SETUP.md</code>. The browser never asks for a
                  provider key. Keep keys and private configuration out of chat
                  and source control.
                </p>
              </ContextHelp>
              <ContextHelp topic="Why is a model unavailable for a learner?">
                <p>
                  The server checks the learner’s age category, the provider’s
                  allowed audience, image support, and whether cloud processing
                  was enabled by the adult. Check those settings and the failed
                  test message before choosing a model.
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
                  the terminal with the private environment exported to reset
                  the account password. This signs that adult out on their other
                  browsers.
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
