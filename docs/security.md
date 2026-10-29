# Security review — local MVP through Phase 10

## Identity, roles and tenant boundaries

Passwords use salted scrypt (N=32768, r=8, p=3). Only hashed session identifiers are stored; sessions expire after eight hours and logout revokes them. Cookies are HttpOnly, SameSite=Lax and Secure in production. Mutations require an explicit allowed Origin and a per-session CSRF token. Redis authentication limits fail closed. Sessions are not kept in localStorage; logs omit passwords, session tokens and request bodies.

Every business API requires current membership. The platform flag does not bypass membership. Nonmembers receive 404; members without permission receive 403. Business-scoped queries and composite tenant foreign keys protect linked records. Business/membership writes lock the business row and refresh permissions; final-owner and administrator-grant rules are enforced. Owner/admin control operational writes; analysts have only explicitly granted model/scenario/investigation/report actions; viewers read. Investigations and generated reports remain creator-private. Re-reading/exporting document-backed evidence rechecks current document visibility.

The Next.js server resolves the session before displaying private workspace state. Business switching aborts prior requests and clears prior-business data. A streamed anonymous workspace response may use HTTP 200 plus a login instruction; it contains no private account data. Backend authorization remains mandatory.

## Request and export boundaries

Both the same-origin proxy and the direct API cap ordinary request bodies at **16 KiB**. Only exact POST document/import upload routes allow **2 MiB**. The API checks declared lengths and counts streamed chunks before parsing JSON or running endpoint dependencies, so missing or misleading lengths do not bypass the cap. Direct API rejection includes the correlation ID and no-store headers. Configure ingress timeouts, concurrency and aggregate memory limits separately; a byte cap does not prevent slow-client or distributed denial of service.

Explicit CORS origins, no-store API responses, safe validation/errors, request IDs and non-root app containers are enabled. Frontend responses include nosniff, frame denial and referrer policy. The proxy preserves binary PDF bytes and forwards only selected authentication/request headers. CSV cells neutralize spreadsheet commands. PDFs are server-generated from bounded saved report payloads, never uploaded active content.

## Operational data, documents and models

Imports cap bytes, rows, columns and cell length. XLSX archive expansion is bounded; formulas/macros/external links and multiple sheets are rejected. Supported XML uses defusedxml. Confirmation is explicit and idempotent; invalid rows do not partially commit. Historical unit costs and expense-completeness declarations govern calculated profit. Missing inputs remain unknown rather than becoming invented zeroes.

Document retrieval filters tenant, role, current active version, embedding identity and dimensions before selecting context. Citation validation requires a retrieved chunk and an exact excerpt. Uploaded text is untrusted context and cannot grant tool authority. This validates source integrity; it does not prove every generated claim or prevent every prompt injection. Worker extraction has format, size, page/text/chunk and job-deadline limits. EICAR detection is not antivirus, and extraction is not a hardened content sandbox. Raw binaries are not served inline.

Model artifacts are internal versioned JSON, never pickle or arbitrary uploaded paths. Training is tenant-local, bounded and explicit. Historical splits, baseline comparisons and demo scope are retained. Activation requires owner/admin permission. Snapshots, saved scenarios, investigations, graph builds and report payloads retain source hashes and immutable/finalized database guards. Graph links represent recorded ownership/foreign keys, not inferred causality. Analyst tools are a bounded allowlist; they expose no arbitrary SQL, filesystem access, external messages or autonomous business mutations. Redis leases and deadlines bound requests.

Provider and OCR endpoints are operator configuration, not user-supplied URLs. API and worker must use identical provider identity settings. Native Ollama/OCR ports are loopback-only; they are unauthenticated and must stay private. The selected local model profile disables cloud use and limits loaded models/concurrency. There is no paid-provider fallback.

## Phase 10 review and query work

The full suite checks expiry/logout, CSRF, invalid Origin, role escalation, final-owner rules, cross-business reads/writes/sources, document visibility changes, private report/investigation histories and immutable evidence. New direct-ASGI tests cover streamed overflow, deceptive/missing lengths, malformed/duplicate lengths, upload route matching and exact boundaries. Document listing now batches version retrieval in a single tenant-scoped query instead of issuing one query per document. Existing tenant/date and graph/report indexes remain in place. This is a bounded local workload, not a large-scale query/load benchmark.

Keyboard skip links, main landmarks, current-navigation semantics, visible focus and reduced-motion handling are implemented. Measured browser coverage and limits are recorded in phase10-verification.md; these checks do not certify WCAG conformance.

## Explicit production gaps

There is no password reset, email verification, MFA, email invitations, PostgreSQL RLS, automated retention/session cleanup or general API-wide rate limiter. Team management adds an existing registered account directly. The current authentication source-IP limit aggregates requests behind Next.js; trusted ingress identity must be designed before scale-out. Business/member lists are not paginated. A single database role performs runtime queries and migrations. RQ/Redis are trusted internal infrastructure.

Before public use, configure TLS, trusted ingress/hosts, least-privilege runtime and migration credentials, secret management, network segmentation, pinned/scanned images, backups with restore tests, content sandboxing/antivirus, retention/deletion policies and resource monitoring. Run independent security/tenant tests, concurrency/load tests, broader browser/screen-reader evaluation and human AI-quality review. Configurable business profiles do not imply that every restaurant/manufacturing/service module in the original brief is implemented. No penetration-test, production or regulatory certification is claimed.
