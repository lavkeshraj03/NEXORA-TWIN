# Development progress — 28 October 2026

## Current milestone

Phase 1's original disk and Docker blockers have been resolved. Phase 2 implements identity and multi-business workspaces. The running application is available at http://localhost:3000/login. This is a local development deployment, not production.

## Phase 1 completed

Restored dependencies, recovered offloaded source files, restarted the stuck Docker backend, and isolated Python bytecode caching outside the cloud-backed Desktop. The patched Next.js frontend passed type checking, four initial tests, and its production build. Eight initial backend tests passed against real PostgreSQL/Redis. The built frontend returned HTTP 200 and its health proxy confirmed PostgreSQL, pgvector, Alembic revision, and Redis readiness. The full Docker stack, including the RQ worker, reached healthy status. The original interruption is archived in progress-phase1-history.md.

## Phase 2 implemented

- Identity: normalized account registration, salted scrypt passwords, login/logout, eight-hour server-side sessions, hashed session identifiers, HttpOnly cookies, Secure cookies in production, Origin/CSRF validation, and Redis attempt limits.
- Tenancy: create independent businesses, switch businesses, inspect/update profile settings, and configure profile-specific modules. Business switching immediately hides stale tenant state and aborts outstanding requests.
- Authorization: centralized owner/administrator/analyst/viewer permissions; platform flags do not bypass memberships. Every business operation checks membership on the backend. Administrators cannot grant privileged roles; membership writes preserve at least one owner.
- Team and audit: add existing registered accounts, change roles, revoke membership, and inspect paginated tenant audit history. No invitations or other messages are sent.
- Frontend: public entry links, account forms, server-protected workspace, business configuration, empty states, loading/error/retry states, team management, audit history, and responsive styles.
- Operations: identity migration, administrator provisioning CLI, reproducible tests, HTTP smoke script with owned-record cleanup, and synchronized operating/security/API/schema documentation.

## Files and commands

Backend: app/models.py, app/schemas.py, app/core/security.py, app/core/permissions.py, app/api/auth.py, app/api/businesses.py, router registration, readiness revision, migration 0002_identity.py, and security/integration tests. Frontend: typed API client, bounded backend proxy, server-session helper, login/workspace routes, account/business/workspace components, workspace styles, public entry links, and identity flow tests. Scripts: create_admin.py and verify_identity_http.py. Documentation: identity design/API, database schema, security, deployment, architecture, README, and this log.

Commands run: locked pip/npm installation; npm tests/typecheck/build; Alembic upgrade and check; PostgreSQL/Redis pytest integration suite; Docker Compose configuration/build/start; real frontend/API health probes; administrator CLI --help; full-stack HTTP identity verification. No administrator credentials were invented or provisioned automatically.

## Verification

- Final backend suite: **22 tests passed** against PostgreSQL/Redis, including malformed CSRF rejection and Secure cookie configuration. No unresolved test failures remain.
- Frontend: **9 tests passed**, strict TypeScript passed, production build passed. The final public entry-link change was also included in the successful Docker frontend build.
- Alembic: **No new upgrade operations detected** after applying 0002_identity.
- Docker: frontend, backend, worker, PostgreSQL, and Redis reached healthy state; frontend login and health proxy returned HTTP 200.
- Full-stack HTTP identity workflow passed: protected workspace, registration, cookie proxy, two independent businesses, cross-tenant denial, CSRF denial, viewer write denial, audit history, and logout. Temporary accounts/businesses were removed. The final rebuilt image passed the HTTP flow again, and the four known registration-counter increments from these two successful smoke runs were removed so they do not block user sign-up.
- Regression discovered: a non-ASCII CSRF header raised TypeError instead of returning 403. The regression was reproduced, then corrected by constant-time byte comparison and added to the suite.
- The first HTTP redirect assertion failed because it assumed every Next.js redirect used a 3xx response. The smoke script now explicitly verifies the observed streamed login refresh and absence of private workspace content.
- Package install audit: **0 vulnerabilities**. Remote CI and interactive browser/accessibility QA have not been run. One upstream Starlette/httpx deprecation warning remains.

## Configuration and limitations

No new environment variables are required beyond .env.example. AI variables are unused; no AI credentials are needed for this milestone. Production must configure HTTPS, ENVIRONMENT=production, trusted origins, restricted database roles, secrets, and backups.

Password recovery, email verification, MFA, email invitations, platform administration screens, operational data imports, analytics, RAG, ML, digital twins, scenarios, knowledge graphs, and reports are not implemented. Lists are appropriate for small workspaces; only audit history is paginated. The proxy aggregates source-IP authentication limits; see identity-api.md before production scaling. This milestone does not satisfy the full product definition of done.

## Next milestone — Phase 3

Add normalized customers, products, orders/order items, inventory, expenses/transactions; validated mapped imports; tested Decimal financial calculations; and dashboard metrics from actual tenant-scoped records. Do not seed or fabricate metrics silently. Phase 3 has not been started in this milestone.
