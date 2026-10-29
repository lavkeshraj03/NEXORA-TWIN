# Phase 10 — hardening and local delivery verification

Verified on **29 October 2026**, on the existing Apple Silicon laptop. This is acceptance of the documented local MVP, not certification for public production.

## Delivered changes

- Direct API request-body middleware now enforces 16 KiB ordinary requests and 2 MiB exact POST import/document routes before JSON parsing or endpoint authentication. It counts streamed chunks, rejects malformed/duplicate declared lengths, handles oversized numeric headers safely, and preserves the normal safe error/request-ID envelope.
- Document listing batches visible version retrieval in one tenant-scoped query, removing the per-document version query. Existing tenant/date, graph and private-report indexes were reviewed. Graph and training caps remain explicit; no unmeasured scalability claim is made.
- All public/login/workspace main landmarks have keyboard skip targets. Sidebar buttons expose current navigation. Focus has visible contrasting rings; reduced-motion preference covers animations/transitions. Existing labelled forms, keyboard graph actions and tenant-switch clearing remain covered.
- Compose host API/frontend ports are configurable, allowing a second isolated installation. The new fresh-install verifier owns a random project and removes only its temporary resources. The graph/report HTTP verifier accepts NEXORA_BASE_URL. A reusable Node/Chrome browser verifier records screenshots and a receipt.
- README, security and deployment instructions now cover the complete local release, guarded demo loading, matching API/worker provider identities, recovery and outstanding production limitations. Previous release progress/README are preserved in progress-phase9-history.md and readme-phase9-history.md.

## Measured checks

| Check | Result |
| --- | --- |
| Complete backend suite on the existing local PostgreSQL/Redis | **167 passed**, 37.93 seconds |
| Complete backend suite on a new isolated database and Redis | **167 passed**, 40.36 seconds |
| Frontend component/regression suite | **37 passed**, nine files |
| Strict TypeScript | Passed |
| Alembic comparison, existing and fresh databases | No new upgrade operations detected |
| Schema head | **0009_insights** |
| Production backend/worker/migrate and frontend image builds | Passed, Python 3.12 / Node 22 images |
| Fresh Compose migration/startup | Five services healthy from empty dedicated volumes |
| Real HTTP graph/report acceptance through Next.js | Passed, including strict PDF parsing and cross-business denials |
| Local browser check | Chrome login at 1280×900 and 390×844; home at 390×844; main accessibility roles, labelled email field, first-tab skip link, focus transfer and no horizontal overflow; no browser runtime exceptions |
| Existing Nexa reconciliation | Passed in a read-only transaction; original counts and financial totals retained |

Native backend tests used Python 3.14; the fresh seed and running API/worker used Python 3.12 inside the built images. Native frontend/browser tooling used Node 25; production Next.js built under Node 22. One upstream Starlette TestClient/httpx deprecation warning remains. No new dependency was needed.

## Fresh demo and live AI acceptance

The isolated project generated a new synthetic package covering 2 May–28 October 2026, then loaded customers, suppliers, products, orders, inventory and expenses atomically. It reconciled 84 customers, three suppliers, six products, 342 orders (522 item rows), 538 stock movements and 68 expenses. Three evaluated numerical model runs were saved; no model was implicitly activated.

The isolated RQ worker indexed two generated text documents with real qwen3-embedding:0.6b. Real qwen3:1.7b returned a cited returns-policy answer. The loader ran a second time against the same package to check operational/model/document idempotency and repeated the live answer/evaluation checks. Reloading can add verification history; it does not duplicate the six resource sets.

The two curated policy cases measured document recall 1.0, MRR 1.0, validated citation integrity 1.0 and reference-substring matching 0.5. Reference matching is a literal text metric, not semantic accuracy. Human faithfulness/relevance remain unevaluated. Prior Phase 4 verification covers the five upload formats and image-only English OCR; this fresh seed uses two text files and does not claim to repeat all OCR/adversarial quality tests.

An initial harness attempt used the Mac provider address for checking embeddings indexed with the container address. Retrieval correctly excluded a different provider identity, and that attempt failed. The harness was corrected to load/check inside the API container, preserving the isolation rule. The complete acceptance then passed. No fallback answers or weakened citation/provider validation were introduced.

Only the randomly named acceptance project's containers, network and volumes were removed. The original Nexa database, Redis and unrelated Docker resources were retained.

## Existing Nexa preserved

The read-only owner-scoped check retained seven documents, four numerical runs, three snapshots, two saved scenarios, three investigations, seven generated reports, 1,055 graph nodes and 2,468 graph edges, alongside the original operational counts. For 29 September–28 October 2026, revenue remains INR 150,562.00, COGS 81,550.00, gross profit 69,012.00, recorded expenses 26,300.00 and operating profit 42,712.00, over 70 paid orders.

## Reproduce and inspect

From the repository root after configuration/build:

```sh
backend/.venv/bin/python scripts/verify_fresh_install.py
node scripts/verify_browser.cjs
python3 scripts/validate_environment.py
```

The fresh verifier requires configured real local AI and free acceptance ports; see deployment.md. Backend tests, frontend checks and builds are also documented in README. macOS Desktop offloading stalled some source reads, so matching downloaded copies under /private/tmp were used for native tests and image build contexts. No runtime dependency on those copies was introduced. Keep source/dependency files downloaded for future builds.

Local receipts: `.local/phase10-fresh-install.json`, `phase10-browser.json`, `phase10-nexa-state.json`; logs: `phase10-backend-tests.log`, `phase10-frontend-tests.log`, `phase10-backend-build.log`, `phase10-frontend-build.log` and `phase10-release-acceptance.log`. Browser screenshots use `phase10-login-1280.png`, `phase10-login-390.png` and `phase10-home-390.png`.

## Remaining limitations

The original brief's configurable industry profiles do not provide every restaurant/manufacturing/service ERP module. Model quality is evaluated only on the recorded data/fixtures; customer inactivity is a proxy, simulations are assumption-driven and causal claims are unsupported. Local chat may be slow and generated answers require evidence review. Standard-font PDFs escape unsupported Unicode; CSV preserves it. Source, run and history caps, synchronous training and bounded graph reads limit scale.

No public cloud/TLS deployment, automated backup/restore acceptance, independent security/penetration review, load/concurrency benchmark, broad screen-reader/WCAG audit, additional OCR languages, production content sandbox/antivirus, MFA/reset/email verification, retention automation or database RLS is delivered. The limited Chrome checks cover public/login views; full authenticated workflows have component and HTTP coverage, not comprehensive browser/screen-reader coverage. See security.md and deployment.md before collecting production-sensitive data.
