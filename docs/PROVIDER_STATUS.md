# Provider implementation and verification

All live routes default to disabled. No real learner content, paid inference,
provider credential, or model weights were accessed during implementation.
Adapter contract tests are evidence of software behavior, not model quality or
eligibility for a particular audience.

| Adapter | Implemented protocol | Automated evidence | Live status |
|---|---|---|---|
| Mock | Deterministic text and explicit blank/ambiguous vision result | Worker, schema, photo-confirmation and fixture tests | No model; not an OCR or quality result |
| Meta Spark | Bounded Chat Completions messages/image data URI, structured JSON | Wire shape, errors, adult-only/cloud policy | Pending exact approved model/account and current provider contract check |
| Ollama | Native `/api/chat`, separate system message, base64 image, `format` schema | Text/image mapping and typed error contracts | Pending exact installed model/runtime |
| vLLM | `/chat/completions`, content image blocks and JSON schema response format | Capability and compatible transport contracts | Pending exact served model/runtime/template |
| Compatible | Bounded Chat Completions endpoint, explicit native or JSON-prompt mode | Strict payload, malformed/refusal/429/timeout handling | Pending exact endpoint semantics |
| Bedrock | boto3 Converse content blocks, system, image bytes, output schema | SDK Stubber with locked boto3 schema; no static keys | Pending approved region/model/profile and IAM access |

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

1. Copy `config/providers.example.yaml` to private operator configuration. Select
   the exact installed/approved model ID, endpoint or region. Document eligibility,
   model license, intended audience and retention/data handling in
   `eligibility_record`. Explicitly declare image capability and context limits;
   a text-only route cannot receive images.
2. Export `PROVIDER_CONFIG` to that file. Local routes stay local; no automatic
   cloud fallback exists. Cloud requires `ALLOW_CLOUD_INFERENCE=true`. Adult-only
   routes require `APP_AUDIENCE=adult_only` and an adult learner. Meta is always
   adult-only; unknown/minor/mixed access is rejected by backend policy.
3. Restart API/worker after configuration changes. From the adult provider panel,
   explicitly authorize the synthetic probe for each required stage. Vision must
   return the known synthetic `1/2` transcription; mere HTTP success is insufficient.
   A matching probe lasts seven days and is invalidated by capability/config changes.
4. Select the eligible route with the displayed data-boundary acknowledgment.
   Test only synthetic material first. Record exact runtime/model/config/prompt
   versions, date, sample counts, failures, latency, token usage and human review.
   A failed local route never invokes an alternate provider.

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
Every photo still requires confirmation even after successful evaluation.

The optional browser research uses WebLLM 0.2.84 and the exact model/runtime hashes
in `apps/web/src/research-manifest.json`. Only public metadata was fetched during
implementation. No weights were downloaded and no actual device was measured.
Use the adult research screen's consent, synthetic evaluation, cancel/unload and
cache-delete controls; record memory, thermal/battery, eviction and quality limits
before treating T23 as accepted. Research cannot grade learner practice.
