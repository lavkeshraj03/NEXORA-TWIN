# Local AI profile — Apple M1, 8 GB RAM

This profile is installed and verified on the development laptop. It uses no paid API key and no fine-tuning. Requests go to native services on this Mac; the application continues to store tenant documents/chunks/vectors in its local PostgreSQL container.

| Component | Selected implementation |
|---|---|
| Answering | Ollama `qwen3:1.7b`, quantized, about 1.4 GB |
| Embeddings | Ollama `qwen3-embedding:0.6b`, about 639 MB, actual output 1024 dimensions |
| Scanned English PDFs | macOS Vision via the project OCR bridge |
| Database / queue / app | Existing PostgreSQL pgvector / Redis / FastAPI / Next.js Docker services |

Ollama is installed on the Mac, outside Docker, to use Apple Silicon acceleration. Both selected model tags were pulled explicitly; the existing llama3.2 model was preserved and is not a fallback. The application never silently substitutes models. Downloads require internet; the selected inference profile does not need a hosted model endpoint.

## Start after a reboot

From the repository root:

```sh
sh scripts/start_local_ai.sh
sh scripts/start_local_ocr.sh
docker compose up -d
```

The starters detach their owned processes, record PIDs/logs under `.local/` and bind to loopback only. Ollama starts with cloud features disabled, one loaded model, one parallel request, a 4096-token context and zero keep-alive. If another Ollama server is already running, the starter leaves it unchanged; its existing process settings still apply. Do not expose either native service port publicly.

The OCR starter requires macOS and the installed Swift command-line tools. It compiles the project-owned helper once into `.local/nexora-ocr`, then warms recognition on a generated fixture before declaring service readiness. Cold native framework initialization exceeded the first request deadline during setup; startup warm-up addresses that first-call case. Subsequent acceptance OCR passed. No OCR service or Swift compiler is bundled into the Linux images. English is the configured/tested recognition language.

## Configuration already applied

These server-only entries are in the ignored `.env` on this laptop:

```dotenv
AI_PROVIDER=ollama
AI_BASE_URL=http://host.docker.internal:11434
AI_API_KEY=
AI_CHAT_MODEL=qwen3:1.7b
AI_EMBEDDING_MODEL=qwen3-embedding:0.6b
AI_REQUEST_TIMEOUT=120
DOCUMENT_CHUNK_SIZE=800
DOCUMENT_CHUNK_OVERLAP=100
OCR_URL=http://host.docker.internal:11435/ocr
OCR_API_KEY=
```

`host.docker.internal` is for the containerized backend/worker. A native Python API process should use `http://127.0.0.1:11434` and `http://127.0.0.1:11435/ocr` instead. The native Ollama adapter uses the server root, not `/v1`. The existing hosted-compatible adapter remains selectable with AI_PROVIDER=compatible; no hosted-provider live validation is claimed.

If changing `.env`, apply it with `docker compose up -d --force-recreate backend worker`. Open Documents & answers, upload a file and wait for ready. For older uploads awaiting configuration, choose Re-index. Changing embedding model, endpoint, adapter or query-instruction version requires re-indexing; incompatible old vectors are excluded automatically.

## Memory and latency

This is a sequential prototype profile for an 8 GB machine, not a throughput guarantee. The local adapter disables thinking, limits output to 768 tokens, supplies at most three authorized retrieved excerpts and unloads models after requests. Documents use 800-character chunks; questions receive the Qwen retrieval instruction and documents do not. This distinction follows the [embedding model's retrieval guidance](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).

Run builds and heavy inference separately when possible. The laptop showed substantial swap use, and an extra native fixture-generation process was terminated during concurrent checks. The final OCR test reused the validated image-only fixture and passed after builds finished. The application does not close other apps or change global Docker resource settings. Larger context, concurrent users and long documents need further memory/latency testing. Fine-tuning is not required by the passed fixtures and was not attempted.

## Verify

From `backend/`, using the installed backend test environment:

```sh
RUN_INTEGRATION=1 .venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python ../scripts/verify_rag_http.py
PYTHONPATH=. .venv/bin/python ../scripts/verify_local_ocr_http.py --test-owned-provider-outage
```

The last command briefly stops only the Ollama PID recorded by the project starter, verifies an explicit 503 without an answer, restarts the service and verifies recovery. It should be run when no other user is issuing local inference requests. Both HTTP scripts create temporary synthetic tenants and delete only their own records. Their measured reports are `.local/phase4-live-report.json` and `.local/phase4-ocr-report.json`; [phase4-verification.md](phase4-verification.md) preserves the accepted results.

## Troubleshooting

- Local server unavailable: run the AI starter and check `.local/ollama.log`.
- Selected models missing: inspect `ollama list`; explicitly pull the two configured tags if they were removed. Do not redownload them on every startup.
- Upload failed: inspect the saved version error and worker log; retry/re-index once the native service is ready.
- Scanned PDF failed: run the OCR starter, check `.local/ocr.log` and verify the page contains legible English text. A timeout, blank OCR result or malformed response is a failure, never an invented transcript.
- Source citations rejected: the model's quote/ID did not pass validation. The app returns an error rather than fabricating a successful answer.
- Out of memory or slow response: avoid simultaneous builds, keep one inference request at a time and reduce open workloads. No larger model or paid fallback is selected automatically.

The local bridge performs bounded rendering/recognition; it is not a hardened sandbox or antivirus scanner. Broader languages, difficult scans, independent quality/security review, retention and production load testing remain later work.
