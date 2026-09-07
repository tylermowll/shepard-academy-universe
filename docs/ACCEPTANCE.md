# Acceptance evidence and final maintainer checklist

Automated checks use synthetic data and on-disk temporary SQLite. They prove
software behavior only. The maintainer explicitly deferred physical phone checks,
live provider/model verification and actual browser-model measurements. Those
remain required before claiming the associated release gates complete.

## Functional/security mapping

Paths below are relative to the repository. `workflows` means
`apps/api/tests/integration/test_workflows.py`; `providers` means
`apps/api/tests/unit/test_provider_contracts.py`; browser scenarios live in
`tests/smoke/bootstrap.spec.ts`. Exact command outcomes are in TASKS.

| Acceptance | Automated evidence |
|---|---|
| A01 correct exact answer | `test_math_domain.py`, 33 rational fixtures; persisted-practice browser flow |
| A02 incorrect answer and help | `test_equivalent_format_question_and_help_counters`; browser wrong answer then hint/revision |
| A03 equivalent unsimplified value | `test_value_format_and_equation_grammar_are_separate`; workflow format verdict |
| A04 alternate method accepted | Exact parser accepts equivalent fraction/decimal values independently of work text |
| A05 final answer separate from steps | `test_final_answer_is_separate_from_invalid_visible_reasoning`; reasoning explicitly not checked |
| A06 ambiguity requires confirmation | `test_photo_confirmation_is_explicit_immutable_and_stale_safe`; browser photo preview/confirmation |
| A07 questions do not count as wrong | `test_equivalent_format_question_and_help_counters` |
| A08 one result for duplicate work | `test_duplicate_canonical_payload_and_stale_versions`; duplicate photo confirmation test |
| A09 crash after response | `test_crash_after_provider_response_recovers_one_visible_result`; expired-lease and simultaneous-worker tests |
| A10 typed transport failures | Provider wire/refusal/timeout/429/malformed tests; `test_failed_provider_retry_budget_and_stale_retry` |
| A11 text-only vision rejected | Provider modality tests and effective-photo-feature policy |
| A12 no local-to-cloud fallback | Explicit route dispatch, typed local failure; `test_policy_change_never_replays_to_new_route` |
| A13 hostile text has no authority | Unsafe-parser cases; strict provider extra-field rejection; profile/solution-policy test; adversarial external fixture |
| A14 two-learner isolation | `test_pairing_is_bound_single_use_revocable_and_isolated`; adult/learner browser pairing/revocation |
| A15 hidden answer exclusion | `test_public_schemas.py`, persisted problem API payload assertions |
| A16 immutable profile snapshot | `test_profile_version_is_snapshotted_and_solution_policy_enforced` |
| A17 deletion during inference/restore | `test_deletion_during_work_prevents_resurrection_and_restore` |
| A18 hostile upload/math bounds | `test_images.py`, parser properties, `test_csrf_and_chunked_body_limits` |
| A19 reconnect same operation | Persisted-practice browser test disconnects after accepted submission, reloads and recovers one verdict; physical phone backgrounding pending |
| A20 Meta minor/mixed block | Provider audience/explicit-cloud policy tests |
| A21 protected help uses authored text | Profile/solution-policy test; models never provide protected hints; actual pedagogy/disclosure evaluation pending |
| A22 no previous learner UI/cache | Browser logout and paired-device revocation; offline cache asserts public assets only |
| A23 stale photo revision | `test_photo_confirmation_is_explicit_immutable_and_stale_safe` |
| A24 controlled update | Browser update waits for user, preserves unsent entry before refresh, and refreshes only after acknowledgment |

Additional checks cover migration up/down/schema drift, foreign keys, short
transactions and lock contention, UTC/UUID handling, backup authentication/tamper,
metadata stripping/HEIF, private S3 SDK calls, external questions remaining
unverifiable with zero progress, and offline exact arithmetic. No assertion was
removed to hide a defect. See TASKS for the bugs found and fixed.

## Items requiring the maintainer

1. **Actual phones (T11/T17).** Use a private HTTPS deployment and synthetic work
   on iPhone Safari and Android Chrome. Record device/OS/browser versions, trusted
   certificate, pairing, denied camera access, JPEG/HEIC capture, preview/crop/
   rotation, ambiguous transcription edit, 200% zoom, keyboard/screen-reader
   behavior, app installation, update prompt, and background/reconnect after
   submit. Confirm the same operation returns and logout/revocation clears content.
   Expected: no hidden answer before permitted solution, no sensitive browser
   cache, no automatic refresh losing unsent work. Attach original synthetic
   screenshots/results; do not upload real learner material.
2. **Live provider evidence (T09/T12/T13/T14/T18/T19).** Choose the providers you
   actually intend to run. Follow PROVIDER_STATUS with exact model/runtime/region,
   eligibility record, explicit data consent and bounded synthetic probes/evals.
   Check Meta's current authenticated wire documentation. Review every initial
   fixture error, especially ambiguity and premature solutions. Record latency,
   tokens and failures separately from correctness/pedagogy. Disabled/unverified
   optional providers must stay labeled that way.
3. **Browser model measurement (T23).** On one named WebGPU device, review the
   separate model license and explicitly consent to the pinned download. Run the
   three synthetic questions, export the report, fill device/memory/battery/
   thermal/eviction/quality fields, exercise cancel/unload/delete, and record cold
   versus warm latency and storage. This is text-only research, never the grading
   engine. No model was downloaded during coding.
4. **Private-host release rehearsal (T19).** Recover settings from your secret
   manager, rehearse encrypted restore into a fresh directory with the current
   deletion ledger, verify worker readiness, re-pair devices, and confirm backup
   retention and provider/data policy for the actual host. Native synthetic and
   CI container checks do not validate your private deployment configuration.

AWS provisioning is optional and was not performed. If selected, review the
specific AMI, network/certificate/SSM access, retained EBS mount, secret ARN,
least-privilege IAM, and budget before applying the template. No production or
public deployment is implied by pushing the code.
