# Threat model and operating limits

The supported isolation unit is one private household deployment. The host owner
and adult administrator are trusted with managed learner data. Internet clients,
learner text, model output, and uploaded files are untrusted. This is not a
multi-tenant service or a claim of regulatory certification.

| Boundary             | Enforcement and evidence                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Browser identity     | Argon2id adult login, hashed opaque cookies, expiry/revocation, CSRF and exact configured Origin/Host; no tokens in localStorage                                                                       |
| Pairing              | Five-minute browser-bound token, explicit adult approval, single claim, rate limits; guessed request ID reveals no learner                                                                             |
| Learner ownership    | Backend principal and joins on every practice/photo/operation route; two-learner isolation tests                                                                                                       |
| Private answers      | Separate public DTOs omit hidden answers, seeds and private parameters; AI generation returns an activity, not a solution key                                                                          |
| Untrusted math       | Bounded ASCII parser and Fraction arithmetic; no eval, SymPy parser, code execution or tools                                                                                                           |
| Model authority      | Typed output permits flexible conceptual/reasoning guidance but not permission changes or verified grades; server owns durable transitions                                                             |
| Homework references  | Separate reference intake from student responses; generate distinct analogous practice, exclude original assignments from later tutoring context; actual answer-leak resistance needs model evaluation |
| Photo interpretation | Persist and display reading before feedback; automatically continue clear readings, stop unclear work with concrete advice; no approval gate; confidence is an uncalibrated model claim                |
| Provider egress      | Operator-owned routes, explicit cloud enablement, audience/capability checks and recent synthetic probes; no redirect or automatic alternate route                                                     |
| Image upload         | Auth before decoding, bounded body/pixels, accepted raster formats only, decode/normalize, metadata removal, opaque private object keys                                                                |
| Browser rendering    | Escaped text, restricted markdown and KaTeX with trust disabled, CSP, no remote content rendering; public-only service-worker cache                                                                    |
| Worker recovery      | Short immediate claims, lease-token completion checks, six-call budget, persisted generation/reading/tutoring stages and idempotent results                                                            |
| Deletion             | Immediate revocation/cancel, late-result discard, content-free tombstone journal replayed on restore                                                                                                   |
| Repository           | Private-path/key/token checks, locked dependency audits, no credentials or live learner fixtures                                                                                                       |

Host files use private permissions and should reside on an encrypted local volume.
SQLite does not encrypt itself. Backups use authenticated encryption with a
separate passphrase; losing the passphrase loses recovery. Preserve the current
deletion ledger separately from old archives. Operator settings/secrets require
their own secure recovery process.

The primary tutor provides model-based reasoning guidance across subjects. It is
not an independently verified grade, a proof of mastery, or a guarantee of factual
correctness. A clear/high-confidence reading can still be wrong; the student can
point out the error or resubmit. Ambiguous work is not guessed into a solution.
The no-homework-answers policy uses source separation, instructions and bounded
output checks. These do not prove that arbitrary model text can never disclose an
answer. Human review of actual-model failures is required; mock success is not
evidence of robust anti-cheating or handwriting accuracy.
Live providers need a reviewed eligibility/privacy record for the intended
audience. An operator can mislabel a remote endpoint as local; review endpoint
DNS/network ownership and apply host egress controls where required.

Rate limits are process-local and reset on restart, which matches one API process.
The fixed body cap is 16 KiB for JSON and 8 MiB for images; images are capped at
25 million pixels and normalized to 2048 pixels. Provider responses are bounded,
timeouts are at most 90 seconds, and operation calls at most six. Resource limits
reduce abuse; they are not a substitute for authenticated private deployment.

Pending external review: physical device camera/certificate/update behavior,
manual keyboard/screen-reader audit, provider eligibility and quality, AWS account
policy/cost review, and browser model resource measurements. No WCAG conformance,
penetration-test, multi-host availability, or production-readiness claim is made.
