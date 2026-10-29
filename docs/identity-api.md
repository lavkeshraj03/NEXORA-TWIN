# Phase 2 API contract

All backend routes use `/api/v1`. The browser uses `/api/backend/...`, a bounded same-origin Next.js proxy with an explicit auth/business route allowlist. The proxy forwards the session cookie, Origin, and CSRF header; credentials remain in HttpOnly cookies. OpenAPI at `/api/docs` is authoritative for request/response schemas.

| Method | Route | Behavior |
|---|---|---|
| POST | /auth/register | Name, email, password; creates account/session, returns 201 |
| POST | /auth/login | Email/password; rotates to a newly created session |
| GET | /auth/me | Current user, session expiry, and CSRF token |
| POST | /auth/logout | Revokes current session and deletes cookie; 204 |
| GET | /businesses/profiles | Supported profile/module registry |
| GET | /businesses | Only the user's memberships and associated businesses |
| POST | /businesses | Creates validated business and owner membership; 201 |
| GET | /businesses/{id} | Authorized business settings and effective permissions |
| PUT | /businesses/{id} | Full validated settings replacement; owner/admin |
| GET | /businesses/{id}/members | Team roster; owner/admin/analyst |
| POST | /businesses/{id}/members | Add an existing registered account; owner/admin restrictions |
| PATCH | /businesses/{id}/members/{user_id} | Change role; preserves final owner; 204 |
| DELETE | /businesses/{id}/members/{user_id} | Revoke membership; preserves final owner; 204 |
| GET | /businesses/{id}/audit-logs | Tenant events; owner/admin; limit 1–100 and offset |

Registration/login require an allowed Origin. Other mutations require an authenticated session, allowed Origin, and `X-CSRF-Token`. Business requests always verify membership in PostgreSQL; a client-supplied ID never grants access. Platform flags do not bypass this check. Nonmembers receive 404; members lacking a permission receive 403.

Roles: owner, administrator, analyst, viewer. Administrators can manage analyst/viewer membership; only owners manage owner/administrator roles. An account may have different roles in different businesses. Team membership is added by an authorized actor to a registered account; email invitations are not implemented.

Passwords are 12–128 characters, preserving whitespace. Emails normalize to lowercase. Session responses never include password hashes or session identifiers. The eight-hour identifier is only set in a cookie; its database representation is a digest. Production enables the Secure cookie flag and requires HTTPS.

Redis fixed-window limits: five registrations per source IP/hour, 120 login attempts per source IP/15 minutes, 20 login attempts per normalized email/15 minutes, and 30 business creations per user/hour. The app does not trust arbitrary forwarding headers. Behind the current Next.js proxy, users share its source-IP limit; trusted-ingress client identification and limit tuning are required for production scale.

Business country/currency codes receive uppercase shape validation; this phase does not perform currency conversion or validate every code against a maintained ISO registry. Timezones are validated with IANA ZoneInfo. Modules must be a nonempty, unique subset supported by the selected profile.

Identity lists are intentionally small-workspace APIs; the business list and team roster are not paginated yet. Audit history is paginated. No operational records, reports, documents, model data, or forecasts exist in this phase. Password recovery, email verification, MFA, invitations, and platform-administration screens remain unimplemented.
