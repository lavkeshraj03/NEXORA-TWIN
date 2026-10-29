# Phase 4 local acceptance — 29 October 2026

**Accepted for the recorded local development profile.** This is evidence from actual local model calls, not mocked provider output or a claim of production quality.

Models: `qwen3:1.7b` (Ollama digest prefix `8f68893c685c`) and `qwen3-embedding:0.6b` (`ac6da0dfba84`). Inference used the Mac's native Ollama server with cloud features disabled and no API key. Embedding output was actually checked at 1024 dimensions. macOS Vision provided English OCR through the project bridge. No fine-tuning or larger-model/hosted fallback was used.

## Recorded checks

| Check | Actual result |
|---|---|
| Backend suite | 90 passed, including local-adapter validation and PostgreSQL/Redis/pgvector integration |
| Frontend suite | 21 passed; strict TypeScript passed |
| Production images | Backend, worker, migration and frontend builds passed |
| TXT/PDF/DOCX/CSV/XLSX | Uploaded through Next.js, processed by RQ, embedded by the actual local model and marked ready |
| Grounded questions | Eight positive live questions matched fixture facts with valid retrieved chunk IDs/exact excerpts |
| PDF reference | Delivery answer cited actual page 1 |
| Follow-up | Receipt question retained the conversation's context and cited the real policy |
| Insufficient evidence | CEO question with related retrieved policy text returned the explicit insufficiency response |
| Tenant/visibility/conversation isolation | Cross-business access denied; viewer did not retrieve administrator-only content; conversation scope enforced |
| In-document instruction fixture | Support-hours answer remained grounded and did not output the injected override marker |
| Version replacement | New fourteen-day policy became active; answer cited version 2 and excluded the old thirty-day version |
| Scanned PDF | Verified image-only input had no extractable PDF text; actual Vision OCR read “Warranty covers twelve months from purchase.” |
| Scanned answer | Worker indexed OCR text; local answer cited its actual excerpt and page 1 |
| Provider failure/recovery | Controlled stop of the project-owned Ollama PID returned 503 with no answer; restart restored grounded answers |
| Cleanup | Both live scripts removed only their own temporary users/businesses/documents/conversations/evaluations |

The main HTTP acceptance report contains ten questions: eight positive answers and two insufficiency cases (unsupported CEO question and inaccessible administrator document). The OCR report adds the image-only ingestion, OCR answer and provider outage/recovery. Per-answer actual usage/latency and citations are retained under `.local/`; no account password, session or API key is recorded there.

## Actual three-case curated evaluation

The app's `/rag/evaluate` endpoint ran real retrieval and generation against the updated returns/receipt policy and delivery PDF. Results were persisted and then deleted with their temporary test tenant.

| Metric | Measured value |
|---|---|
| Cases | 3 |
| Document recall within up to five retrieved chunks | 1.0 |
| Mean reciprocal rank | 1.0 |
| Mean candidate document precision | 0.2167 |
| Validated citations | 3 |
| Exact citation integrity | 1.0 |
| Exact reference-substring match | 0.3333 |
| Evaluation elapsed time | 33,263 ms |
| Independent human faithfulness/relevance | Not evaluated |

All three expected documents ranked first. Candidate precision is lower because additional retrieved documents were included. The literal substring metric penalized digit/word differences such as “14 days” versus “fourteen days”; it is not a semantic correctness or overall answer-quality score. The separate positive acceptance checks explicitly allowed both forms and checked their supporting excerpts. Do not replace these measured scores with a claimed 100% answer-accuracy figure.

## Boundaries

The acceptance fixtures are short, synthetic and mainly English. One instruction-injection fixture is not a comprehensive security evaluation. Citation integrity proves that quoted text and IDs exist in retrieved authorized sources; it does not prove every generated assertion for arbitrary questions. Independent human review, a broader business-specific QA corpus, OCR on difficult scans/languages, hosted-provider validation, browser/accessibility review, antivirus/isolation, retention and sustained-load testing remain work.

The OCR starter now warms native recognition before readiness because the first cold request timed out. A redundant fixture process was terminated by macOS during simultaneous heavy checks; the final live OCR/outage test reused the already-validated fixture after builds finished and passed. These observations motivate sequential inference/build workloads on this 8 GB laptop, rather than a claim of universal memory/latency performance.

Reproduction commands and exact server-only settings are in [local-ai.md](local-ai.md).
