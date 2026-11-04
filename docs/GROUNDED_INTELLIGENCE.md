# Evidence-grounded research — v0.4 (2026-11-04)

## Implemented, not a claim of general intelligence

This release integrates **one** bounded research-answer operation into the existing persistent mission/worker engine. There is no autonomous web search engine, vector embedding index, mathematical theorem prover, multi-agent collaboration, model self-training, or continuously refreshed world model. The answer generator requires a real configured OpenAI Responses API connection; it **never** uses a fabricated model response in normal execution.

### Research path

`company-owned knowledge/culture records` → `tenant-scoped keyword retrieval` → `source metadata + bounded excerpts` → `opt-in Responses API call` → `strict JSON response` → `citation-ID validation` → `persisted task result + usage + audit`.

Each source is labeled with the original source URL, record ID, evidence class, review status and recording time. The source's classification is *metadata*, not an endorsement of correctness. Cultural and scientific assertions are differentiated, and the prompt instructs the provider not to treat retrieved pages as executable instructions. Passing citation-ID validation **does not** establish the factual truth of all claims. Source relevance is determined by bounded token overlap, **not** semantic embeddings or comprehensive research. An empty result fails with `INSUFFICIENT_EVIDENCE` rather than prompting the model to guess.

The provider is called only if `POLSIA_NETWORK_ENABLED=1`, `POLSIA_AI_ENABLED=1`, `POLSIA_OPENAI_API_KEY`, and `POLSIA_OPENAI_MODEL` are all set. The fixed endpoint is `https://api.openai.com/v1/responses`; neither a task nor source document can change that endpoint. The configured model name is sent exactly, and an unexpected returned model is rejected. `/intelligence/provider` reports `configured_not_checked` until actually called, **never** automatically reports live connectivity. Model availability, pricing, and access vary by provider/account.

Every AI mission is one-attempt to avoid unbounded retry charges, including after a worker crash or timeout. The per-tenant daily call ceiling defaults to 10, with a hard configuration range of 1–100. The limit is by UTC day; it is **not a US-dollar budget**. A timed-out call may still be billed externally. The provider's token usage is recorded *only if supplied* and cannot be turned into a price without current verified pricing data. Raw API keys are never persisted. Application task outputs contain generated content; access to the database must be protected. The research pipeline sends the selected company knowledge excerpts to the external model provider when explicitly enabled: do not connect sensitive or regulated datasets without suitable permissions and agreements.

### API workflow

1. Authenticate as a company owner (see the root README).
2. Store user-provided notes with `POST /knowledge` or cited cultural records with `POST /culture/records`. Data is recorded as unverified, not audited truth.
3. Inspect source matching using `GET /intelligence/evidence?query=...` (requires any company bearer token). Nothing is sent to an external model by this endpoint.
4. Inspect `GET /intelligence/provider` and `GET /usage` for configuration/quotas.
5. Submit `POST /intelligence/questions` with `{"question":"What is the Vedic astronomy tradition?","min_sources":1}` to queue a persistent mission. It does not immediately generate an answer.
6. The existing worker performs the read-only model call when capacity and policy allow it; review the outcome via `GET /missions/{mission_id}` and `GET /missions/{mission_id}/events`.

You may also create a mission with tool `intelligence.answer` and an explicit `approval_required=true` flag. Normal missions already require an authenticated company owner, and activating the provider independently requires a server administrator. No model or task may bypass approvals for write, payment, communication, or production actions. None of those actions are implemented in this release.

### Local verification versus live operation

`python -m pytest -q` exercises tenant separation, source attribution, no-evidence failures, opt-in configuration, strict response and citation validation, model mismatch, prompt-injection placement, per-company quotas, usage accounting, explicit approval, and HTTP-error sanitization with mocked provider traffic. **Mocks are confined to automated tests** and must not be confused with a successful real call. No paid model invocation, internet search, live VPS load test, production deployment, or fact-checking benchmark was performed in this environment.

### Next engineering work

1. PostgreSQL migrations and row-level security; dedicated tool permissions, encryption at rest, hardened policy enforcement and proper auth.
2. Source ingestion respecting copyright/licensing; stronger domain evaluation, text parsing, versioning, citation checking, retrieval evaluation, opt-in semantic retrieval, source contradiction analysis.
3. Durable budget reservations by actual current model pricing and reconciliation with provider invoices, cancellation, request idempotency and recovery.
4. Multi-provider adapters and agent registry; independent verification agents, scientific computation service, safe branching/release workflow.
5. Production Hostinger VPS staging and resource-pressure/load/failure tests before launch.

## Reference

OpenAI Responses API: https://developers.openai.com/api/reference/resources/responses/methods/create  
Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
