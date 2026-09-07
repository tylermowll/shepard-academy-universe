# Provider implementation and verification

All live routes default to disabled. No real learner content, paid inference,
provider credential, or model weights were accessed during implementation.
Adapter contract tests are evidence of software behavior, not model quality or
eligibility for a particular audience.

| Adapter    | Implemented protocol                                                                                  | Automated evidence                                                   | Live status                                                              |
| ---------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Mock       | Explicit synthetic generation/guidance and one recognized public image fixture; other images rejected | Worker, schema, automatic clear reading, rejection and fixture tests | No model; not an OCR or quality result                                   |
| Meta Spark | Bounded Chat Completions messages/image data URI, structured JSON                                     | Wire shape, errors, cloud boundary and selected-audience policy      | Pending exact approved model/account and current provider contract check |
| Ollama     | Native `/api/chat`, separate system message, base64 image, `format` schema                            | Text/image mapping and typed error contracts                         | Pending exact installed model/runtime                                    |
| vLLM       | `/chat/completions`, content image blocks and JSON schema response format                             | Capability and compatible transport contracts                        | Pending exact served model/runtime/template                              |
| Compatible | Bounded Chat Completions endpoint, explicit native or JSON-prompt mode                                | Strict payload, malformed/refusal/429/timeout handling               | Pending exact endpoint semantics                                         |
| Bedrock    | boto3 Converse content blocks, system, image bytes, output schema                                     | SDK Stubber with locked boto3 schema; no static keys                 | Pending approved region/model/profile and IAM access                     |

The implementation uses documented
[Ollama chat](https://docs.ollama.com/api/chat),
[vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/),
[Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html),
and [Bedrock JSON schema](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_JsonSchemaDefinition.html).
Meta's official developer structured-output documentation required authenticated
access during review. Its exact deployed wire contract must be checked against
the operator's current documentation before enabling; do not infer a verified
endpoint/model from the disabled example.

## Activate one reviewed route

1. In adult **Settings → Connections**, select Ollama, vLLM, a compatible
   API, or Meta. Enter the exact installed/approved model ID and endpoint, and an
   API key if required. Review model/provider terms, intended audience and data
   handling. Declare image capability and context limits honestly; a text-only
   route cannot receive images. Save sends no model request and changes no route.
2. Open **App permissions** in Settings. This installation-wide ceiling is
   separate from any one connection. Enable cloud processing only
   deliberately. Adult-only routes require an adults-only app audience and an
   adult learner; mixed routes use the operator's separate terms attestation.
   Meta-hosted connections display a provider-specific age/data disclaimer but
   do not impose a provider-specific audience value. Explicit deployment
   `ALLOW_CLOUD_INFERENCE` and `APP_AUDIENCE` values lock their UI controls; absent
   values allow saved Settings policy, defaulting to cloud off and mixed ages.
   Local routes stay local and never fall back to cloud.
3. Open **Connection tests**. Saved changes are visible to API and worker without
   restarting. Explicitly authorize the synthetic test for each required stage.
   The tutor test makes two bounded sample calls, checking activity generation
   and feedback. The photo test makes one call using the current work-reading schema and must
   return the known synthetic `1/2` transcription as a clear, unambiguous reading;
   mere HTTP success is insufficient. A matching probe lasts seven days and is
   invalidated by capability/configuration/key changes.
4. Open **Assign active connections** and select the tested tutor and photo
   reader with the displayed data-boundary acknowledgment. This app-wide choice,
   not saving a connection, changes future learner routing. Record exact runtime,
   model, configuration and prompt versions, date, sample counts, failures,
   latency, token usage and human review.
   A failed local route never invokes an alternate provider.

Saved keys are encrypted in the private SQLite database and never returned in
responses, errors or learner exports. Edit a connection to keep, replace or
remove its key. Changing the endpoint cannot silently reuse the old credential.
Connection/key changes invalidate prior tests and require renewed route-selection
approval before learner use; a successful test alone never activates changed
settings. If the deployment secret changes,
replace unreadable keys in Settings and retest; preserve that secret separately
when backing up the database (D010).

Advanced operators may still set `PROVIDER_CONFIG` to a reviewed private file
using `config/providers.example.yaml`. These connections appear read-only in
Settings and require restarting after file changes. Bedrock remains configured
this way, with workload IAM credentials rather than a browser form for static
AWS keys. File-managed and browser-managed connection identifiers cannot collide.

Select both **tutor** and **vision** for the T25 experience. They may point to the
same model or to separate local/API models. The probes establish transport,
current activity/feedback/reading schema support and the known photo reading,
not teaching or general handwriting quality. Exercise the actual application loop using
[TUTOR_EVALUATION](TUTOR_EVALUATION.md) before claiming those tasks work well on
your model. Increase the explicitly configured context budget to match your
actual server when needed; the app rejects over-budget work rather than silently
clipping a paragraph or switching providers.

The fixed request budget is six calls per operation, with no hidden SDK retries
and no automatic schema repair. Live calls have a 90-second total deadline in a
short-lived child process, plus up to 2.1 seconds to stop/reap it (D008). This cannot
cancel inference already accepted by a remote provider. Visible errors are
sanitized. Model-call records contain redacted status/usage, not raw prompts,
photos, endpoint credentials or model response bodies. Prices are not hardcoded;
cost is unknown unless externally assessed from current provider billing.

## Synthetic evaluation

`make eval-mock` checks 33 exact-math cases and 30 mock vision cases. It does not
score OCR or pedagogy. For an explicitly authorized three-call text smoke test:

```bash
make eval-live PROVIDER=YOUR_CONFIGURED_ID
```

For a separately authorized vision evaluation, use the original fixture set and
an explicit maximum call budget (1–30):

```bash
uv run --project apps/api --locked python -m math_tutor.evaluation --fixtures evals/fixtures/rational-v1.json --output /private/evaluations/vision.json --live-provider YOUR_CONFIGURED_ID --stage vision --authorize-synthetic-calls --max-calls 30
```

Each output carries fixture expectations and model metadata for adult review.
Record transcription exactness/ambiguity, false corrections, early solutions,
schema failures/refusals, answer rejection, and latency separately. Reserve the
six held-out images for final review, not prompt tuning. The images are rendered
synthetic typeset exercises, not a representative handwriting benchmark; add
original consenting adult handwriting before claiming handwriting performance.
The primary tutor has no photo approval step. It displays the reading and
automatically continues clear work. Unclear readings stop with concrete
handwriting/organization advice. The historical exact-math fixture evaluator
does not certify this new multi-subject tutoring loop.

The optional browser research uses WebLLM 0.2.84 and the exact model/runtime hashes
in `apps/web/src/research-manifest.json`. Only public metadata was fetched during
implementation. No weights were downloaded and no actual device was measured.
Use the adult research screen's consent, synthetic evaluation, cancel/unload and
cache-delete controls; record memory, thermal/battery, eviction and quality limits
before treating T23 as accepted. Research cannot grade learner practice.
