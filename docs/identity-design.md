# Identity and tenancy design

Phase 2 scope: registration, login/logout, session inspection, business creation and switching, validated business configuration, existing-account team membership management, role enforcement, and audit history. Password reset and email verification require a delivery integration and are outside this milestone; no nonfunctional UI controls will be exposed for them.

## Security contract

- Passwords use salted scrypt with N=32768, r=8, p=3, one of the [OWASP documented configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Require 12–128 characters.
- The browser receives a random session identifier only in an HttpOnly, SameSite=Lax cookie, with Secure enabled in production. PostgreSQL stores its SHA-256 digest, expiry, user, and a separate CSRF token. No bearer credentials go into localStorage.
- Unsafe browser requests must have an explicitly allowed Origin. Authenticated mutations must also present the session's CSRF token. Login and registration validate Origin to prevent login CSRF.
- Redis enforces finite authentication attempt windows. Infrastructure failures fail closed. Client-supplied forwarding headers do not determine the rate-limit identity.
- Business IDs are UUIDs but their unpredictability is never an authorization boundary. Every protected endpoint resolves membership in PostgreSQL. A nonmember receives 404 for existing and absent business IDs alike.
- Roles are a closed, centralized permission registry, backed by a database constraint: owner, administrator, analyst, viewer. A separate platform administrator flag grants no implicit access to tenant records.
- Only owners may grant owner/administrator membership. Administrators manage analyst/viewer access. Membership changes serialize on the business row and preserve at least one owner.
- Audit records contain event names and identifiers, not passwords, session tokens, request bodies, or document contents. Tenant audit access requires membership and the audit permission.

## Data model

`users` → `auth_sessions`; `users` ↔ `businesses` through `business_memberships`; `audit_logs` has nullable user/business references for global authentication events and tenant events. Identity timestamps are timezone-aware. Membership uses a composite (business_id, user_id) primary key. Email uniqueness is applied to normalized lowercase emails. Global user lookups are never exposed through list endpoints.

## Acceptance evidence required

1. Register, login, inspect a session, logout, and reject the old cookie.
2. Reject invalid passwords, duplicate emails, missing CSRF, and untrusted Origin.
3. One account creates two businesses with independent settings and switches between them.
4. A second account cannot fetch another business, members, or audits, or change membership without access.
5. A viewer can inspect an authorized business but cannot edit its settings or team.
6. An administrator cannot grant owner or administrator access; the final owner cannot be removed.
7. Expired sessions are rejected and failed login attempts are limited.
8. Frontend clears the old tenant's state during switching and protects the workspace on the server.
