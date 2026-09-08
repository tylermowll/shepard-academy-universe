import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Schema } from "./client";
import { ContextHelp } from "./Help";
import type { Navigate } from "./navigation";

type ConnectionInput = Schema<"ProviderConnectionInput">;
type Draft = Required<Omit<Schema<"ProviderConnectionCreate">, "api_key">> & {
  api_key: string;
};
type Props = {
  configuration: Schema<"ProvidersPublic">;
  onChanged: () => Promise<void>;
  onNavigate: Navigate;
  section: ProviderSettingsSection;
  onSectionChange: (
    section: ProviderSettingsSection,
    focusContent?: boolean,
  ) => void;
  act: (action: () => Promise<void>) => Promise<void>;
};

export type ProviderSettingsSection =
  "connections" | "policy" | "tests" | "roles";

const addresses: Record<ConnectionInput["adapter"], string> = {
  ollama: "http://127.0.0.1:11434",
  vllm: "http://127.0.0.1:8081/v1",
  compatible: "",
  meta: "https://api.meta.ai/v1",
};

function blankDraft(): Draft {
  return {
    id: "",
    adapter: "ollama",
    model: "",
    base_url: addresses.ollama,
    enabled: true,
    boundary: "local_network",
    audience: "mixed",
    eligibility_record: "",
    image_input: false,
    configured_context_limit: 32768,
    configured_output_limit: 16384,
    structured_output_mode: "native",
    reasoning_effort: "default",
    api_key_action: "keep",
    api_key: "",
  };
}

function inputFor(provider: Schema<"ProviderPublic">): ConnectionInput {
  return {
    adapter: provider.adapter as ConnectionInput["adapter"],
    model: provider.model,
    base_url: provider.base_url ?? "",
    enabled: provider.enabled,
    boundary: provider.boundary as ConnectionInput["boundary"],
    audience: provider.audience as ConnectionInput["audience"],
    eligibility_record: provider.eligibility_record,
    image_input: provider.image_input,
    configured_context_limit: provider.configured_context_limit,
    configured_output_limit: provider.configured_output_limit ?? 16384,
    structured_output_mode: provider.structured_output_mode,
    reasoning_effort: provider.reasoning_effort ?? "default",
    api_key_action: "keep",
  };
}

const knownSafeConnectionDetails = new Set([
  "Thinking effort is currently supported only for Meta connections.",
  "An enabled Meta connection needs an API key.",
  "A changed server or provider needs a replacement key, or explicitly remove the old key.",
  "Use the cloud boundary for a public Internet endpoint.",
  "Check the server URL, exact model name, audience, and eligibility. URLs cannot contain credentials, queries, or fragments; cloud URLs need HTTPS. Meta requires the cloud boundary.",
  "That connection ID is already in use. Choose another.",
  "Choose a replacement tutor or photo reader before deleting this connection.",
  "This connection is managed by the server configuration.",
]);

function saveError(cause: unknown, draft: Draft) {
  const prefix = draft.id.trim()
    ? `Could not save ${draft.id.trim()}. `
    : "Could not save this connection. ";
  if (cause instanceof ApiError) {
    if (cause.status === 401 || cause.status === 403)
      return `${prefix}Your administrator sign-in is no longer authorized. Sign in again, then retry.`;
    if (cause.status === 404)
      return `${prefix}This connection was deleted. Cancel this editor, choose Add AI connection, and add it again.`;
    if (cause.status === 409) {
      if (knownSafeConnectionDetails.has(cause.message))
        return `${prefix}${cause.message}`;
      return `${prefix}That name is already in use, or this connection is active. Refresh the saved connections and check its current state.`;
    }
    if (cause.status === 422) {
      if (knownSafeConnectionDetails.has(cause.message))
        return `${prefix}${cause.message}`;
      if (draft.configured_context_limit > 131_072)
        return `${prefix}The running API rejected the form. This version accepts context limits above 131,072, so stop and restart the app to make the page and API use the same version, then retry.`;
      return `${prefix}The running API rejected a form value. Re-enter the API key without spaces, check the server address and model name, then retry.`;
    }
  }
  // Unexpected server details must never echo a credential into the page.
  return `${prefix}The app server did not confirm the save. Refresh Saved connections before retrying.`;
}

function connectionActionError(
  cause: unknown,
  provider: Schema<"ProviderPublic">,
  remove: boolean,
) {
  const action = remove
    ? `delete ${provider.id}`
    : `${provider.enabled ? "disable" : "enable"} ${provider.id}`;
  if (cause instanceof ApiError) {
    if (cause.status === 401 || cause.status === 403)
      return `Could not ${action}. Your administrator sign-in is no longer authorized.`;
    if (cause.status === 404)
      return `Could not ${action}. That connection no longer exists; refresh Saved connections.`;
    if (knownSafeConnectionDetails.has(cause.message))
      return `Could not ${action}. ${cause.message}`;
  }
  return `Could not ${action}. Refresh Saved connections, check its current state, and retry.`;
}

const probeMessages = {
  unavailable:
    "The app cannot reach the model server. Check Server address, make sure the model server is running, and check network access from the app server.",
  timeout:
    "The model test timed out. Make sure the server and model are running. Try a smaller model or a faster server, then test again.",
  authentication:
    "The model server rejected the API key, or the saved key could not be unlocked. Edit this connection and replace the key, then test again.",
  invalid_request:
    "The model server rejected the request. Check Model name and Connection type, then check Structured output under Advanced connection options.",
  malformed_output:
    "The model did not return the tutor's required response format. Check Model name and Structured output under Advanced connection options, then test again.",
  context_limit:
    "The model context limit is too small for tutoring. In Advanced connection options, match Model context limit to the model server's supported size.",
  cloud_disabled:
    "Cloud requests are off. Review and save App permissions before testing this cloud connection.",
  audience_blocked:
    "This connection's Allowed users setting does not match who uses the app. Review both the connection and App permissions.",
  invalid_endpoint:
    "The server address is blocked or does not match its network setting. Check Server address and Where this model runs; hosted services need the cloud setting.",
  unsupported_modality:
    "This model does not support the selected test. For photos, use a vision-capable model and enable This model supports photo input.",
  throttled:
    "The model server is limiting requests. Wait before testing again, and check the provider's usage limits.",
  probe_reading_failed:
    "The model could not clearly read the test photo. Check that the selected model and server support images, then try the photo-reader test again.",
  output_limit:
    "The model reached the response token limit before finishing. Increase Model response limit under Advanced connection options. The provider may charge for this incomplete response.",
  incomplete_output:
    "The model stopped without a complete response. The provider may charge even though the test did not pass.",
  refusal:
    "The model declined the sample request. The test did not pass; no automatic retry was made.",
  adapter_failure:
    "The app could not process the model server's response. This is an adapter error; the provider may have completed and charged for the request.",
} as const;

function probeError(cause: unknown) {
  if (cause instanceof ApiError) {
    const step = cause.probeStep
      ? {
          generate: "Activity creation (step 1 of 2): ",
          review: "Tutor feedback (step 2 of 2): ",
          read: "Photo reading: ",
        }[cause.probeStep]
      : "";
    if (cause.code && Object.hasOwn(probeMessages, cause.code))
      return `${step}${probeMessages[cause.code as keyof typeof probeMessages]} (HTTP ${cause.status}; ${cause.code})`;
    if (cause.status === 401 || cause.status === 403)
      return "Your adult sign-in is no longer authorized. Sign in again before testing this connection.";
    if (cause.status === 409)
      return "The connection or app permissions changed during the test. Refresh connections, then test the current settings again.";
    if (cause.status === 429)
      return "Too many requests were made. Wait a minute before testing again.";
    return `${step}The app returned HTTP ${cause.status} without a recognized test result. No successful test was confirmed.`;
  }
  return "The browser did not receive a usable test result from the app. Refresh status before retrying; the provider may have completed and charged for the request. No successful test was confirmed.";
}

function RecentTests({ tests }: { tests: Schema<"ProbeResultPublic">[] }) {
  const latest = tests[0];
  if (!latest) return null;
  const describe = (test: Schema<"ProbeResultPublic">) =>
    test.status === "passed"
      ? "Passed."
      : test.status === "running"
        ? "No final result recorded yet. The test may still be running or was interrupted. Refresh status before retrying."
        : probeError(
            new ApiError(
              "",
              test.http_status ?? 422,
              test.code ?? undefined,
              test.step,
            ),
          );
  const metadata = (test: Schema<"ProbeResultPublic">) =>
    `${new Date(test.created_at).toLocaleString()} · ${test.stage === "tutor" ? "Tutor" : "Photo reader"} · ${(test.elapsed_ms / 1000).toFixed(1)} seconds · ${test.requests_started} request(s) started · ${test.output_limit.toLocaleString()} output-token limit · thinking: ${test.reasoning_effort === "default" || !test.reasoning_effort ? "provider default" : test.reasoning_effort}`;
  return (
    <section aria-label="Recent connection tests">
      <p className={latest.status === "failed" ? "error" : "notice"}>
        Last test: {describe(latest)}
      </p>
      <p className="fine">{metadata(latest)}</p>
      {latest.completion_reason && (
        <p className="fine">Model finish reason: {latest.completion_reason}</p>
      )}
      {tests.length > 1 && (
        <details>
          <summary>Earlier test results ({tests.length - 1})</summary>
          <ul>
            {tests.slice(1).map((test, index) => (
              <li key={`${test.created_at}-${index}`}>
                <p>{describe(test)}</p>
                <p className="fine">{metadata(test)}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function ProviderConnections({
  configuration,
  onChanged,
  onNavigate,
  section,
  onSectionChange,
  act,
}: Props) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState<Schema<"ProviderPublic"> | null>(null);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saveFailure, setSaveFailure] = useState("");
  const [errorSection, setErrorSection] =
    useState<ProviderSettingsSection | null>(null);
  const editor = useRef<HTMLFormElement>(null);
  const editorOpen = draft !== null;
  useEffect(() => {
    if (editorOpen && editor.current) {
      editor.current
        .querySelector<HTMLInputElement>(
          editing ? 'input[name="model"]' : 'input[name="connection-name"]',
        )
        ?.focus({ preventScroll: true });
      editor.current.scrollIntoView?.({ block: "start" });
    }
  }, [editing, editorOpen]);
  const { policy, providers } = configuration;
  const policyBlocks = (provider: Schema<"ProviderPublic">) =>
    (provider.boundary === "cloud" && !policy.allow_cloud_inference) ||
    (provider.audience === "adult_only" &&
      policy.app_audience !== "adult_only");
  const openSection = (next: ProviderSettingsSection) =>
    onSectionChange(next, true);
  const keyDestinationChanged = Boolean(
    editing?.key_configured &&
    draft &&
    (draft.adapter !== editing.adapter || draft.base_url !== editing.base_url),
  );
  const keyMustChange =
    keyDestinationChanged || Boolean(editing?.key_needs_replacement);
  const metaKeyMissing = Boolean(
    draft?.adapter === "meta" &&
    draft.enabled &&
    !(draft.api_key_action === "replace"
      ? draft.api_key.trim()
      : draft.api_key_action === "keep" &&
        editing?.key_configured &&
        !editing.key_needs_replacement),
  );
  const apiKeyFormatInvalid = Boolean(
    draft?.api_key_action === "replace" &&
    draft.api_key &&
    [...draft.api_key].some(
      (character) =>
        character.charCodeAt(0) < 33 || character.charCodeAt(0) > 126,
    ),
  );
  const change = <K extends keyof Draft>(
    field: K,
    value: Draft[K],
    termsChanged = false,
  ) => {
    setDraft((current) => (current ? { ...current, [field]: value } : null));
    if (termsChanged) setTerms(false);
    setError("");
    setSaveFailure("");
  };
  const cancel = () => {
    setDraft(null);
    setEditing(null);
    setTerms(false);
    setError("");
    setSaveFailure("");
  };
  const start = (provider?: Schema<"ProviderPublic">) => {
    if (
      draft &&
      !window.confirm(
        "Discard the unsaved connection entries and start another?",
      )
    )
      return;
    setEditing(provider ?? null);
    setDraft(
      provider
        ? {
            ...blankDraft(),
            ...inputFor(provider),
            id: provider.id,
            api_key: "",
          }
        : blankDraft(),
    );
    setTerms(Boolean(provider?.eligibility_record.trim()));
    setMessage("");
    setError("");
    setSaveFailure("");
  };
  const updateConnection = (
    provider: Schema<"ProviderPublic">,
    remove = false,
  ) => {
    if (
      remove &&
      !window.confirm(
        `Delete connection ${provider.id} and its saved API key? Saved practice is kept.`,
      )
    )
      return;
    void act(async () => {
      setBusy(true);
      setError("");
      try {
        await api(
          `/admin/providers/connections/${provider.id}`,
          remove ? "DELETE" : "PUT",
          remove
            ? undefined
            : ({
                ...inputFor(provider),
                enabled: !provider.enabled,
              } satisfies ConnectionInput),
        );
        if (remove && editing?.id === provider.id) cancel();
        await onChanged();
        setMessage(
          remove
            ? `${provider.id} and its saved API key were deleted.`
            : `${provider.id} ${provider.enabled ? "disabled" : "enabled"}. Test it before selecting it for practice.`,
        );
      } catch (cause) {
        setErrorSection("connections");
        setError(connectionActionError(cause, provider, remove));
      } finally {
        setBusy(false);
      }
    });
  };

  return (
    <section className="connection-setup">
      {section === "connections" && (
        <>
          <div className="section-heading">
            <div>
              <h2 id="settings-connections-heading" tabIndex={-1}>
                Connections
              </h2>
              <p>
                Save the address, model name, and API key for each AI service.
                This step does not call a model or choose what learners use.
              </p>
            </div>
            <button
              className="primary"
              disabled={policy.demo_mode || busy}
              onClick={() => start()}
            >
              Add AI connection
            </button>
          </div>
          {policy.demo_mode && (
            <p className="notice">
              This public demo cannot save live connections or API keys. Start a
              private installation to connect your models.{" "}
              <button onClick={() => onNavigate("help", "setup")}>
                Private setup help
              </button>
            </p>
          )}
          {!policy.demo_mode &&
            !providers.some(
              (provider) => provider.adapter !== "mock" && provider.enabled,
            ) && (
              <p className="notice">
                No live AI connection is enabled. Add your Ollama or vLLM
                server, or a hosted API connection.
              </p>
            )}
          {draft && (
            <form
              className="card connection-editor"
              ref={editor}
              aria-labelledby="connection-editor-heading"
              autoComplete="off"
              onSubmit={(event) => {
                event.preventDefault();
                if (!terms || busy || policy.demo_mode) return;
                const { id, api_key, ...values } = draft;
                const body = {
                  ...values,
                  eligibility_record: `Operator reviewed the model and provider terms for the ${draft.audience === "adult_only" ? "adult-only" : "mixed"} audience.`,
                  ...(draft.api_key_action === "replace" ? { api_key } : {}),
                } satisfies ConnectionInput;
                void act(async () => {
                  setBusy(true);
                  setSaveFailure("");
                  let saved = false;
                  try {
                    await api(
                      editing
                        ? `/admin/providers/connections/${editing.id}`
                        : "/admin/providers/connections",
                      editing ? "PUT" : "POST",
                      editing
                        ? body
                        : ({
                            ...body,
                            id,
                          } satisfies Schema<"ProviderConnectionCreate">),
                    );
                    saved = true;
                    const cloudNeedsPolicy =
                      draft.boundary === "cloud" &&
                      !policy.allow_cloud_inference;
                    const needsPolicy =
                      cloudNeedsPolicy ||
                      (draft.audience === "adult_only" &&
                        policy.app_audience !== "adult_only");
                    cancel();
                    await onChanged();
                    setMessage(
                      needsPolicy
                        ? `${id} saved. No model request was sent. ${cloudNeedsPolicy ? "Cloud AI is off" : "Its allowed users do not match the app audience"}, so review App permissions next.`
                        : `${id} saved. No model request was sent. Test the connection next.`,
                    );
                    openSection(needsPolicy ? "policy" : "tests");
                  } catch (cause) {
                    setSaveFailure(
                      saved
                        ? "The connection was saved, but the list could not refresh. Refresh connections to continue."
                        : saveError(cause, draft),
                    );
                  } finally {
                    setBusy(false);
                  }
                });
              }}
            >
              <h3 id="connection-editor-heading">
                {editing ? `Edit ${editing.id}` : "Add an AI connection"}
              </h3>
              <p className="fine">
                Saving stores the connection on your server. It does not call
                the model or change the providers used for practice. Leaving
                Settings discards unsaved entries, including the API key.
              </p>
              <fieldset disabled={busy}>
                <legend>Model and server</legend>
                <div className="grid">
                  <label>
                    Connection name
                    <input
                      value={draft.id}
                      name="connection-name"
                      onChange={(event) => change("id", event.target.value)}
                      pattern="[a-z0-9]([a-z0-9_]|-){0,63}"
                      title="Use 1–64 lowercase letters, numbers, hyphens or underscores. Start with a letter or number."
                      maxLength={64}
                      required
                      readOnly={Boolean(editing)}
                      autoComplete="off"
                      aria-describedby="connection-name-help"
                    />
                  </label>
                  <label>
                    Connection type
                    <select
                      value={draft.adapter}
                      onChange={(event) => {
                        const adapter = event.target.value as Draft["adapter"];
                        setDraft({
                          ...draft,
                          adapter,
                          base_url: addresses[adapter],
                          model: adapter === "meta" ? "muse-spark-1.3" : "",
                          boundary:
                            adapter === "meta" || adapter === "compatible"
                              ? "cloud"
                              : "local_network",
                          audience: "mixed",
                          api_key_action:
                            adapter === "meta" || adapter === "compatible"
                              ? "replace"
                              : "keep",
                          api_key: "",
                          image_input: adapter === "meta",
                          reasoning_effort: "default",
                          configured_context_limit:
                            adapter === "meta" ? 1_048_576 : 32768,
                        });
                        setTerms(false);
                      }}
                    >
                      <option value="ollama">Ollama</option>
                      <option value="vllm">vLLM</option>
                      <option value="compatible">OpenAI-compatible API</option>
                      <option value="meta">Meta hosted API</option>
                    </select>
                  </label>
                </div>
                <p className="fine" id="connection-name-help">
                  Use 1–64 lowercase letters, numbers, hyphens or underscores.
                  Start with a letter or number. For Spark 1.3, use spark-1-3
                  (no spaces or periods).
                </p>
                <label>
                  Server address
                  <input
                    type="url"
                    value={draft.base_url}
                    onChange={(event) =>
                      change("base_url", event.target.value, true)
                    }
                    required
                    maxLength={2048}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={
                      draft.adapter === "compatible"
                        ? "https://your-provider.example/v1"
                        : addresses[draft.adapter]
                    }
                    aria-describedby="server-address-help"
                  />
                </label>
                <p className="fine" id="server-address-help">
                  This address is reached by the app server. For Ollama on the
                  same computer, use http://127.0.0.1:11434. For vLLM, use the
                  address and port where you started its server.
                </p>
                <label>
                  Model name
                  <input
                    value={draft.model}
                    name="model"
                    onChange={(event) =>
                      change("model", event.target.value, true)
                    }
                    required
                    maxLength={256}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Exact model name from your server or API account"
                    aria-describedby="model-name-help"
                  />
                </label>
                <p className="fine" id="model-name-help">
                  Copy the installed or served model name exactly. Saving a
                  connection does not download or start a model.
                </p>
                {draft.adapter === "meta" && (
                  <div className="inline-help">
                    <p>
                      Meta&apos;s current direct API model is{" "}
                      <code>muse-spark-1.3</code>. Use a different ID only when
                      it appears in your Meta Model API account.
                    </p>
                    {draft.model !== "muse-spark-1.3" && (
                      <button
                        type="button"
                        onClick={() => change("model", "muse-spark-1.3", true)}
                      >
                        Use muse-spark-1.3
                      </button>
                    )}
                  </div>
                )}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={draft.image_input}
                    onChange={(event) =>
                      change("image_input", event.target.checked)
                    }
                  />
                  This model supports photo input
                </label>
                <ContextHelp topic="Can one model handle text and photos?">
                  <p>
                    Yes, if the model and its server support image input. Select
                    this option only when they do, then run both tests. A
                    text-only model can be your tutor while another model reads
                    photos.
                  </p>
                </ContextHelp>
              </fieldset>
              <fieldset disabled={busy}>
                <legend>API key</legend>
                {editing && (
                  <p className="fine">
                    {editing.key_needs_replacement
                      ? "The saved key can no longer be read after a server secret change. Replace or remove it."
                      : editing.key_configured
                        ? "An API key is saved on the server. Its value is never shown here."
                        : "No API key is saved."}
                  </p>
                )}
                <label>
                  API key action
                  <select
                    value={draft.api_key_action}
                    onChange={(event) => {
                      change(
                        "api_key_action",
                        event.target.value as Draft["api_key_action"],
                      );
                      setDraft((current) =>
                        current ? { ...current, api_key: "" } : null,
                      );
                    }}
                  >
                    <option value="keep">
                      {editing?.key_configured
                        ? "Keep saved key"
                        : "No API key"}
                    </option>
                    <option value="replace">
                      {editing?.key_configured
                        ? "Replace saved key"
                        : "Add an API key"}
                    </option>
                    {editing?.key_configured && (
                      <option value="remove">Remove saved key</option>
                    )}
                  </select>
                </label>
                {draft.api_key_action === "replace" && (
                  <label>
                    API key
                    <input
                      type="password"
                      value={draft.api_key}
                      onChange={(event) =>
                        change("api_key", event.target.value)
                      }
                      required
                      autoComplete="new-password"
                      maxLength={8192}
                      spellCheck={false}
                      aria-invalid={apiKeyFormatInvalid}
                      aria-describedby={
                        apiKeyFormatInvalid ? "api-key-format-error" : undefined
                      }
                    />
                  </label>
                )}
                {apiKeyFormatInvalid && (
                  <p className="field-error" id="api-key-format-error">
                    Remove spaces, line breaks, or non-ASCII characters from the
                    API key.
                  </p>
                )}
                {keyMustChange && draft.api_key_action === "keep" && (
                  <p className="notice">
                    Replace or remove the saved key before saving this changed
                    connection.
                  </p>
                )}
                {metaKeyMissing && (
                  <p className="notice">
                    An enabled Meta connection needs an API key.
                  </p>
                )}
                <p className="fine">
                  Local servers often need no key. Hosted APIs usually provide
                  one in your account. Enter it only in this password field; it
                  is never saved in browser storage.
                </p>
              </fieldset>
              <fieldset disabled={busy}>
                <legend>Users and data</legend>
                <div className="grid">
                  {draft.adapter === "meta" ? (
                    <div
                      role="group"
                      aria-labelledby="meta-location-label"
                      aria-describedby="meta-policy-help"
                    >
                      <p id="meta-location-label">
                        <strong>Where this model runs</strong>
                      </p>
                      <p>
                        Cloud service <span className="pill">Fixed</span>
                      </p>
                    </div>
                  ) : (
                    <label>
                      Where this model runs
                      <select
                        value={draft.boundary}
                        onChange={(event) =>
                          change(
                            "boundary",
                            event.target.value as Draft["boundary"],
                          )
                        }
                      >
                        <option value="local_network">
                          This computer or private network
                        </option>
                        <option value="cloud">Cloud service</option>
                      </select>
                    </label>
                  )}
                  <label>
                    Allowed users
                    <select
                      value={draft.audience}
                      aria-describedby={
                        draft.adapter === "meta"
                          ? "meta-policy-help"
                          : undefined
                      }
                      onChange={(event) =>
                        change(
                          "audience",
                          event.target.value as Draft["audience"],
                          true,
                        )
                      }
                    >
                      <option value="mixed">Adults and children</option>
                      <option value="adult_only">Adults only</option>
                    </select>
                  </label>
                </div>
                {draft.adapter === "meta" && (
                  <p className="notice" id="meta-policy-help">
                    Meta's hosted API has provider-specific age and data terms.
                    Confirm the current terms for your account and intended
                    users before enabling this connection. Your Allowed users
                    selection records your decision; it is not a certification
                    from this app. To serve a Meta or Llama model locally,
                    choose Ollama or vLLM instead.
                  </p>
                )}
                {draft.boundary === "cloud" &&
                  !policy.allow_cloud_inference && (
                    <p className="notice">
                      Cloud AI is off for the whole app. You may save without
                      sending anything, but enable it in App permissions before
                      testing.{" "}
                      <button
                        type="button"
                        onClick={() => openSection("policy")}
                      >
                        Open App permissions
                      </button>
                    </p>
                  )}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={terms}
                    onChange={(event) => setTerms(event.target.checked)}
                    required
                  />
                  I reviewed the model and provider terms for the users selected
                  above.
                </label>
                <p className="fine">
                  Your saved review stays checked when you reopen this
                  connection or adjust technical options. Changing the model,
                  server, connection type, or allowed users requires a fresh
                  review.
                </p>
              </fieldset>
              <details>
                <summary>Advanced connection options</summary>
                <fieldset disabled={busy}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={(event) =>
                        change("enabled", event.target.checked)
                      }
                    />
                    Connection enabled
                  </label>
                  <label>
                    Model context limit
                    <input
                      type="number"
                      min={2048}
                      max={2147483647}
                      step={1}
                      value={draft.configured_context_limit}
                      onChange={(event) =>
                        change(
                          "configured_context_limit",
                          Number(event.target.value),
                        )
                      }
                      required
                    />
                  </label>
                  <p className="fine">
                    Enter the model server&apos;s total context window in
                    tokens. Million-token windows are supported. This is a
                    budgeting limit, not a response length or a memory
                    allocation.
                  </p>
                  <label>
                    Model response limit
                    <input
                      type="number"
                      min={64}
                      max={131072}
                      step={1}
                      value={draft.configured_output_limit}
                      onChange={(event) =>
                        change(
                          "configured_output_limit",
                          Number(event.target.value),
                        )
                      }
                      required
                    />
                  </label>
                  <p className="fine">
                    Maximum output tokens for tutor tests and real practice,
                    including photo reading and reasoning where the provider
                    counts it. The photo test still sends only one small image.
                    Higher limits can increase time and cost; match your model's
                    supported output limit.
                  </p>
                  {draft.adapter === "meta" && (
                    <>
                      <label>
                        Thinking effort
                        <select
                          value={draft.reasoning_effort}
                          onChange={(event) =>
                            change(
                              "reasoning_effort",
                              event.target.value as Draft["reasoning_effort"],
                            )
                          }
                        >
                          <option value="default">Provider default</option>
                          <option value="minimal">Minimal</option>
                          <option value="low">Low</option>
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                          <option value="xhigh">
                            Xhigh (currently same as High)
                          </option>
                        </select>
                      </label>
                      <p className="fine">
                        Applies to tests and practice, including photo reading.
                        Provider default leaves the choice to Meta; it does not
                        mean High. More thinking can take longer and use more
                        output tokens. This does not change practice difficulty.
                        Save, retest both roles, and assign active connections
                        after changing it.
                      </p>
                    </>
                  )}
                  <label>
                    Structured output
                    <select
                      value={draft.structured_output_mode}
                      onChange={(event) =>
                        change(
                          "structured_output_mode",
                          event.target.value as Draft["structured_output_mode"],
                        )
                      }
                    >
                      <option value="native">
                        Server enforces JSON structure
                      </option>
                      <option value="json_prompt">
                        Ask for JSON and validate it
                      </option>
                    </select>
                  </label>
                  <p className="fine">
                    For compatible servers without native structured output,
                    choose the second option. Both require a successful
                    connection test.
                  </p>
                </fieldset>
              </details>
              {saveFailure && (
                <p role="alert" className="error">
                  {saveFailure}
                </p>
              )}
              <div className="actions">
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !terms ||
                    !draft.id.trim() ||
                    !draft.model.trim() ||
                    !draft.base_url.trim() ||
                    (draft.api_key_action === "replace" &&
                      !draft.api_key.trim()) ||
                    apiKeyFormatInvalid ||
                    (keyMustChange && draft.api_key_action === "keep") ||
                    metaKeyMissing
                  }
                >
                  Save connection
                </button>
                <button type="button" disabled={busy} onClick={cancel}>
                  Cancel connection
                </button>
              </div>
            </form>
          )}
          <section aria-labelledby="saved-connections-heading">
            <div className="section-heading subsection-heading">
              <div>
                <h3 id="saved-connections-heading">Saved connections</h3>
                <p>
                  These entries store how to reach each model. Testing and
                  assigning them happen in the next steps.
                </p>
              </div>
            </div>
            {error && errorSection === "connections" && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="provider-list">
              {providers.map((provider) => {
                const blocked = policyBlocks(provider);
                const needsTest =
                  !provider.tutor_probed ||
                  (provider.image_input && !provider.vision_probed);
                const readyRoles = [
                  ...(provider.tutor_probed ? ["tutor"] : []),
                  ...(provider.image_input && provider.vision_probed
                    ? ["photo reader"]
                    : []),
                ];
                const selected = Object.values(configuration.routes).includes(
                  provider.id,
                );
                return (
                  <article className="card" key={provider.id}>
                    <div className="provider-card-heading">
                      <h4>
                        {provider.id}
                        {!provider.enabled && " (disabled)"}
                      </h4>
                      {provider.managed && (
                        <button
                          disabled={busy || policy.demo_mode}
                          onClick={() => start(provider)}
                        >
                          Edit connection
                        </button>
                      )}
                    </div>
                    <p>
                      {provider.model} ·{" "}
                      {provider.boundary === "local_network"
                        ? "Local network"
                        : provider.boundary === "cloud"
                          ? "Cloud"
                          : "Synthetic demo"}
                    </p>
                    {provider.key_needs_replacement ? (
                      <p className="notice">
                        Replace the saved API key before testing this
                        connection.
                      </p>
                    ) : !provider.enabled ? (
                      <p className="notice">
                        Enable this connection before testing or assigning it.
                      </p>
                    ) : blocked ? (
                      <p className="notice">
                        Saved, but blocked by App permissions.{" "}
                        <button onClick={() => openSection("policy")}>
                          Open App permissions
                        </button>
                      </p>
                    ) : readyRoles.length === 0 ? (
                      <p className="notice">
                        Saved, but not ready to assign until its required tests
                        pass.{" "}
                        <button onClick={() => openSection("tests")}>
                          Test this connection
                        </button>
                      </p>
                    ) : (
                      <p className="notice">
                        Ready for {readyRoles.join(" and ")}.{" "}
                        <button onClick={() => openSection("roles")}>
                          Assign active connections
                        </button>
                        {needsTest && (
                          <>
                            {" "}
                            Other roles still need testing.{" "}
                            <button onClick={() => openSection("tests")}>
                              Test this connection
                            </button>
                          </>
                        )}
                      </p>
                    )}
                    <details>
                      <summary>Technical details and actions</summary>
                      <p>
                        {provider.adapter}
                        {provider.base_url && <> · {provider.base_url}</>}
                      </p>
                      <p>
                        Allowed users:{" "}
                        {provider.audience === "adult_only"
                          ? "Adults only"
                          : "Adults and children"}
                        . API key:{" "}
                        {provider.key_configured
                          ? "saved on the server"
                          : "not saved"}
                        .
                      </p>
                      <p className="fine">{provider.eligibility_record}</p>
                      {provider.adapter === "meta" && (
                        <p className="fine">
                          Thinking effort:{" "}
                          {provider.reasoning_effort &&
                          provider.reasoning_effort !== "default"
                            ? provider.reasoning_effort
                            : "Provider default"}
                          .
                        </p>
                      )}
                      {provider.managed ? (
                        <>
                          <div className="actions">
                            <button
                              disabled={
                                busy ||
                                policy.demo_mode ||
                                (selected && provider.enabled)
                              }
                              onClick={() => updateConnection(provider)}
                            >
                              {provider.enabled
                                ? "Disable connection"
                                : "Enable connection"}
                            </button>
                            <button
                              className="danger"
                              disabled={busy || policy.demo_mode || selected}
                              onClick={() => updateConnection(provider, true)}
                            >
                              Delete connection
                            </button>
                          </div>
                          {selected && (
                            <p className="fine">
                              Assign a different tutor and photo reader before
                              disabling or deleting this connection.
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="fine">
                          This connection is managed by the server administrator
                          and is read-only here.
                        </p>
                      )}
                    </details>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
      {message && (
        <aside
          role="status"
          className="notice settings-toast"
          aria-live="polite"
        >
          <p>{message}</p>
          <button type="button" onClick={() => setMessage("")}>
            Dismiss
          </button>
        </aside>
      )}
      {section === "tests" && (
        <section aria-labelledby="settings-tests-heading">
          {error && errorSection === "tests" && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="section-heading">
            <div>
              <h2 id="settings-tests-heading" tabIndex={-1}>
                Connection tests
              </h2>
              <p>
                Confirm that each saved connection can produce the formats the
                tutor needs. A test never includes learner work.
              </p>
            </div>
            <button disabled={busy} onClick={() => void act(onChanged)}>
              Refresh status
            </button>
          </div>
          <p className="fine">
            A tutor test sends up to two sample text requests; a photo-reader
            test sends one sample image. Cloud providers may charge for these
            calls even if a response fails validation. Tests run only when you
            press a test button and confirm.
          </p>
          <div className="provider-list">
            {providers.map((provider) => {
              const blocked = policyBlocks(provider);
              return (
                <article className="card" key={provider.id}>
                  <h3>
                    {provider.id}
                    {!provider.enabled && " (disabled)"}
                  </h3>
                  <p>{provider.model}</p>
                  {provider.vision_probed && !provider.tutor_probed && (
                    <p className="fine">
                      Photo reading passed, so this connection can accept the
                      image request. Tutoring is a separate test: it must create
                      an activity and return feedback in two structured text
                      responses.
                    </p>
                  )}
                  <dl className="readiness-list">
                    <div>
                      <dt>Tutor test</dt>
                      <dd>
                        {provider.tutor_probed ? "Passed" : "Not passed yet"}
                      </dd>
                    </div>
                    <div>
                      <dt>Photo-reader test</dt>
                      <dd>
                        {!provider.image_input
                          ? "Not supported"
                          : provider.vision_probed
                            ? "Passed"
                            : "Not passed yet"}
                      </dd>
                    </div>
                  </dl>
                  <RecentTests tests={provider.recent_tests ?? []} />
                  {provider.key_needs_replacement && (
                    <p className="notice">
                      The saved API key must be replaced before testing.{" "}
                      <button onClick={() => openSection("connections")}>
                        Open Connections
                      </button>
                    </p>
                  )}
                  {!provider.enabled && (
                    <p className="notice">
                      This connection is disabled.{" "}
                      <button onClick={() => openSection("connections")}>
                        Open Connections
                      </button>
                    </p>
                  )}
                  {blocked && (
                    <p className="notice">
                      App permissions currently block this connection, so its
                      test buttons are unavailable.{" "}
                      <button onClick={() => openSection("policy")}>
                        Open App permissions
                      </button>
                    </p>
                  )}
                  {provider.requires_approval &&
                    provider.enabled &&
                    !blocked &&
                    !provider.key_needs_replacement &&
                    (provider.tutor_probed ||
                      (provider.image_input && provider.vision_probed)) && (
                      <p className="notice">
                        Assign this connection to a role whose test has passed
                        in the final step.{" "}
                        <button onClick={() => openSection("roles")}>
                          Assign active connections
                        </button>
                      </p>
                    )}
                  <div className="actions">
                    {(["tutor", "vision"] as const).map((stage) => (
                      <button
                        key={stage}
                        disabled={
                          busy ||
                          (policy.demo_mode && provider.adapter !== "mock") ||
                          !provider.enabled ||
                          blocked ||
                          provider.key_needs_replacement ||
                          (stage === "vision" && !provider.image_input)
                        }
                        onClick={() => {
                          if (
                            provider.adapter !== "mock" &&
                            !window.confirm(
                              `Send ${stage === "tutor" ? "up to two sample text requests" : "one sample photo request"} to ${provider.id}? This provider may charge for these calls. No learner work is included.`,
                            )
                          )
                            return;
                          void act(async () => {
                            setBusy(true);
                            setError("");
                            setMessage("");
                            let tested = false;
                            try {
                              await api(
                                `/admin/providers/${provider.id}/probe`,
                                "POST",
                                {
                                  stage,
                                  authorize_synthetic_call: true,
                                } satisfies Schema<"ProbeInput">,
                              );
                              tested = true;
                              await onChanged();
                              setMessage(
                                `${provider.id}: ${stage === "tutor" ? "tutor" : "photo reader"} test passed.`,
                              );
                            } catch (cause) {
                              setErrorSection("tests");
                              setError(
                                tested
                                  ? "The test completed, but its results could not be refreshed. Refresh status before assigning active connections."
                                  : `${provider.id} test failed. ${probeError(cause)}`,
                              );
                              if (!tested) {
                                try {
                                  await onChanged();
                                } catch {
                                  setError(
                                    (current) =>
                                      `${current} Saved test history could not refresh; use Refresh status.`,
                                  );
                                }
                              }
                            } finally {
                              setBusy(false);
                            }
                          });
                        }}
                      >
                        Test {stage === "tutor" ? "tutor" : "photo reader"}
                      </button>
                    ))}
                    {provider.managed && (
                      <button
                        disabled={busy || policy.demo_mode}
                        onClick={() => {
                          start(provider);
                          openSection("connections");
                        }}
                      >
                        Edit connection
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}
      {section === "policy" && (
        <section aria-labelledby="settings-policy-heading">
          <div className="section-heading">
            <div>
              <h2 id="settings-policy-heading" tabIndex={-1}>
                App permissions
              </h2>
              <p>
                This is one app-wide permission gate for every connection and
                learner. It does not choose a model or send any requests.
              </p>
            </div>
          </div>
          <ProviderPolicy
            key={JSON.stringify(policy)}
            policy={policy}
            act={act}
            onChanged={async () => {
              await onChanged();
              setMessage(
                "App permissions saved. Test the permitted connections next.",
              );
              openSection("tests");
            }}
          />
        </section>
      )}
    </section>
  );
}

function ProviderPolicy({
  policy,
  act,
  onChanged,
}: Pick<Props, "act" | "onChanged"> & {
  policy: Schema<"ProvidersPublic">["policy"];
}) {
  const [cloud, setCloud] = useState(policy.allow_cloud_inference);
  const [audience, setAudience] = useState(policy.app_audience);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="card"
      onSubmit={(event) => {
        event.preventDefault();
        if (!consent || busy || policy.demo_mode) return;
        void act(async () => {
          setBusy(true);
          setError("");
          try {
            await api("/admin/providers/policy", "POST", {
              allow_cloud_inference: cloud,
              app_audience: audience,
              acknowledge_data_boundary: true,
            } satisfies Schema<"ProviderPolicyInput">);
            await onChanged();
            setConsent(false);
          } catch {
            setError(
              "App permissions could not be changed. Check your adult sign-in and the server-managed restrictions, then retry.",
            );
          } finally {
            setBusy(false);
          }
        });
      }}
    >
      <p>
        These permissions apply to every learner and connection. A
        connection&apos;s Allowed users setting is checked as well.
      </p>
      <label>
        Who uses this app?
        <select
          value={audience}
          disabled={busy || policy.audience_locked || policy.demo_mode}
          onChange={(event) => {
            setAudience(event.target.value as typeof audience);
            setConsent(false);
          }}
        >
          <option value="mixed">Adults and children</option>
          <option value="adult_only">Adults only</option>
        </select>
      </label>
      {policy.audience_locked && (
        <p className="fine">
          The server administrator has locked the app audience. Contact them to
          change it.
        </p>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={cloud}
          disabled={busy || policy.cloud_locked || policy.demo_mode}
          onChange={(event) => {
            setCloud(event.target.checked);
            setConsent(false);
          }}
        />
        Allow cloud AI for this app
      </label>
      {policy.cloud_locked && (
        <p className="fine">
          The server administrator has locked cloud access. Contact them to
          change it.
        </p>
      )}
      <p className="fine">
        Cloud providers receive the content for their selected role. A cloud
        tutor receives text read from photos, even if a local model reads the
        image. Enabling this permission alone sends no requests.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={consent}
          disabled={busy || policy.demo_mode}
          onChange={(event) => setConsent(event.target.checked)}
          required
        />
        I confirm this audience and authorize the selected data boundary.
      </label>
      <button disabled={busy || !consent || policy.demo_mode}>
        Save app permissions
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
