# Document intelligence — Phase 4 verified locally

Document storage, extraction, version history, background ingestion, pgvector/English full-text retrieval, cited answers, evaluation and the UI are implemented and verified with actual local Qwen3 models. Live checks covered TXT/PDF/DOCX/CSV/XLSX, an image-only PDF through macOS Vision OCR, citations/pages, follow-ups, replacement versions, access isolation, unsupported questions and provider outage/recovery. Provider doubles remain isolated to unit/integration tests. See local-ai.md and phase4-verification.md for the exact local profile and measured limits.

## Setup

Set server-only variables in `.env`: `AI_BASE_URL` (compatible API root including `/v1` where required), `AI_EMBEDDING_MODEL`, `AI_CHAT_MODEL`, and `AI_API_KEY` if the service requires authentication. Names/models are explicit; there is no default model or fallback provider. The same adapter supports hosted or operator-served compatible inference endpoints. Compose forwards these values to the backend and worker. Restart both after configuration, then choose Re-index on documents awaiting configuration. Changing the embedding endpoint/model requires re-indexing before that version is eligible for retrieval. Do not change model implementations behind an unchanged endpoint/model identifier.

The adapter uses the documented [embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create) and [chat-completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) contracts. Compatible endpoints must implement those request/response shapes and return valid JSON answers as requested. Models that do not support this contract fail clearly. Response sizes, vector shape/finiteness, result indexes, answer shape and citations are checked. Calls time out, retry once on transient errors and never silently substitute a model. Usage is recorded when returned; costs stay null without configured pricing. The compatible adapter labels provider health “Not checked”. The native Ollama adapter probes /api/tags and distinguishes unavailable servers and missing selected models; installed models alone do not prove answer quality.

Optional OCR: configure `OCR_URL` and `OCR_API_KEY`. The operator-hosted service accepts POST `application/pdf` and returns `{"pages":[{"number":1,"text":"actual extracted text"}]}`. Page numbers must be unique integers 1–100 and text is bounded. The app sends the PDF only to this explicitly configured endpoint. Scanned/empty pages without OCR fail with an actionable message. The macOS Vision bridge on this laptop was verified on an image-only English PDF. Other external OCR services and languages remain unverified.

## API

All paths start `/api/v1/businesses/{business_id}` and require membership. Document reads/queries permit all business roles. Upload, replacement, re-index and evaluation require owner/administrator. Mutations require Origin and CSRF validation.

| Route | Contract |
|---|---|
| GET /documents?limit=20&offset=0 | Visible library with version statuses |
| POST /documents?filename=...&title=...&visibility=team | Raw upload, 202 with durable version status |
| POST /documents?...&document_id=... | New version of an existing tenant document |
| POST /documents/{id}/versions/{version_id}/reindex | Queue retry/re-index; stale processing can retry after five minutes |
| GET /documents/{id}/versions/{version_id}/chunks | Paginated extracted text, without vectors or original binaries |
| GET /rag/status | Configuration, OCR state and latest evaluation, initially null |
| POST /rag/search | `{question, document_ids?:[]}` returns actual retrieved excerpts |
| POST /rag/ask | `{question, document_ids?:[], conversation_id?:null}` returns answer/citations |
| POST /rag/evaluate | `{cases:[{question,expected_document_ids:[...],expected_answer}]}` |

Visibility is fixed at initial creation: `team` or `administrators` (owners/administrators only). Document and conversation tenant/actor filters are enforced before content reaches a provider. Conversations belong to the requesting user, keep up to 20 turns and use the last three user questions as context; prior answers never become evidence. No shared retrieval cache or tool execution exists.

## Ingestion and retrieval

Limits: 2 MiB original, 20 MiB expanded archive, 100 PDF pages, 200000 extracted characters, 300 chunks, 20 documents/business and five versions/document. CSV/XLSX inherit structured-import bounds; tables retain row/column labels. DOCX headings and tables and PDF page numbers are preserved. Defaults are 1200-character chunks and 150-character overlap, configurable through DOCUMENT_CHUNK_SIZE / DOCUMENT_CHUNK_OVERLAP for native processes. Compose uses those defaults. Original files are stored in PostgreSQL bytea. No public file path or executable preview is exposed.

Redis/RQ performs extraction and indexing. Version status is queued, extracting/indexing, ready, awaiting_configuration or failed. Intermediate stages occur within the processing transaction; polling may show queued until completion. With no embedding configuration, extracted chunks are retained for review and the version awaits configuration. Queue failures preserve the upload and mark it failed. A failed/replacement index does not activate the new version. Successful newer versions become active; old versions/chunks remain auditable but retrieval excludes them. Older versions cannot replace a newer active version. Re-indexing the current version temporarily removes it from retrieval until success. A crashed job may need explicit retry after five minutes.

Retrieval joins tenant and document visibility filters, active ready versions, embedding endpoint/model identity and vector dimensions. It combines exact pgvector cosine search and English PostgreSQL full-text rankings using reciprocal-rank fusion, removes duplicate text and returns up to five chunks. Scores express ranking relevance, not confidence probability. This bounded release uses exact vector scans, without approximate indexes or a reranker. Multilingual full-text tokenization needs further work.

The model sees only authorized retrieved excerpts, the question and earlier user questions. Uploaded text is explicitly untrusted data; no tool access is granted. Returned citation IDs must exist in the retrieved set, and every supporting quotation must be an exact substring. Invalid citations reject the answer. Insufficient evidence returns an explicit insufficiency response. Citation validation establishes source integrity; it does not establish every generated claim's truth or defeat all prompt injection.

## Evaluation

Submit up to ten curated cases through /rag/evaluate. The endpoint runs real retrieval/generation, stores measured document recall/precision at five chunks, reciprocal rank, validated citation count/integrity, exact reference-substring matching and latency. Substring matching is labelled as such, not answer faithfulness. Answer faithfulness and relevance remain “Not evaluated — requires human review.” Results stay absent until an evaluation actually runs. Evaluation uses provider calls and can incur configured-provider charges. A small fixture lives in datasets/rag/; import it explicitly and substitute the actual document ID in your evaluation request.

## Limits beyond local acceptance

The selected local models and English OCR profile passed the recorded acceptance fixtures. This is not broad real-business quality certification. Independent human faithfulness/relevance evaluation, additional languages/scans, hosted-provider validation, antivirus deployment, independent prompt-injection assessment, browser/accessibility QA, production processing isolation, retention/deletion controls and load testing remain work. Signature/format checks are not antivirus scanning. Exact evaluation scores and limitations are recorded in phase4-verification.md; no unmeasured score is presented.

## Native local adapter

Set AI_PROVIDER=ollama and use the Ollama server root, without /v1. The native adapter requests structured JSON, explicitly disables thinking, limits answer generation/context, unloads models after requests and adds the Qwen embedding query instruction only to questions. Documents are embedded without a query instruction. Its identity includes provider mode and instruction version; changing these requires re-indexing. Only the first three authorized retrieved passages are sent to the small answering model, and its citation schema permits those IDs only. AI_REQUEST_TIMEOUT is configurable (5–180 seconds); the local profile uses 120. The browser proxy permits up to 300 seconds for RAG operations. Generation failure or truncation returns an error; no model substitution occurs.
