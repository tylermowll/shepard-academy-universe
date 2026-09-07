# Threat model and operating limits

The supported isolation unit is one private household deployment. The host owner
and adult administrator are trusted with managed learner data. Internet clients,
learner text, model output, and uploaded files are untrusted. This is not a
multi-tenant service or a claim of regulatory certification.

| Boundary | Enforcement and evidence |
|---|---|
| Browser identity | Argon2id adult login, hashed opaque cookies, expiry/revocation, CSRF and exact configured Origin/Host; no tokens in localStorage |
| Pairing | Five-minute browser-bound token, explicit adult approval, single claim, rate limits; guessed request ID reveals no learner |
| Learner ownership | Backend principal and joins on every practice/photo/operation route; two-learner isolation tests |
| Private answers | Separate public DTOs; learner problem payloads omit expected answers, seeds and parameters; full solution requires policy-authorized request |
| Untrusted math | Bounded ASCII parser and Fraction arithmetic; no eval, SymPy parser, code execution or tools |
| Model authority | Strict output schemas reject extra verdict fields; deterministic checking owns progress; protected help uses authored messages |
| Provider egress | Operator-owned routes, explicit cloud enablement, audience/capability checks and recent synthetic probes; no redirect or automatic alternate route |
| Image upload | Auth before decoding, bounded body/pixels, accepted raster formats only, decode/normalize, metadata removal, opaque private object keys |
| Browser rendering | Escaped text, restricted markdown and KaTeX with trust disabled, CSP, no remote content rendering; public-only service-worker cache |
| Worker recovery | Short immediate claims, lease-token completion checks, six-call budget, immutable confirmations, unique evaluation/progress records |
| Deletion | Immediate revocation/cancel, late-result discard, content-free tombstone journal replayed on restore |
| Repository | Private-path/key/token checks, locked dependency audits, no credentials or live learner fixtures |

Host files use private permissions and should reside on an encrypted local volume.
SQLite does not encrypt itself. Backups use authenticated encryption with a
separate passphrase; losing the passphrase loses recovery. Preserve the current
deletion ledger separately from old archives. Operator settings/secrets require
their own secure recovery process.

No model-based reasoning-quality verdict is implemented. Visible steps remain
available for adult review and are labeled not checked. External problem answers
remain unverifiable. Authored help can be useful but is not proof of learning.
Live providers need a reviewed eligibility/privacy record for the intended
audience. An operator can mislabel a remote endpoint as local; review endpoint
DNS/network ownership and apply host egress controls where required.

Rate limits are process-local and reset on restart, which matches one API process.
The fixed body cap is 16 KiB for JSON and 8 MiB for images; images are capped at
24 million pixels and normalized to 2048 pixels. Provider responses are bounded,
timeouts are at most 90 seconds, and operation calls at most six. Resource limits
reduce abuse; they are not a substitute for authenticated private deployment.

Pending external review: physical device camera/certificate/update behavior,
manual keyboard/screen-reader audit, provider eligibility and quality, AWS account
policy/cost review, and browser model resource measurements. No WCAG conformance,
penetration-test, multi-host availability, or production-readiness claim is made.
