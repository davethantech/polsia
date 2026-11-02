# Actual system architecture: execution core v0.2

FastAPI (company bearer tokens) -> SQLite relational storage -> atomic durable task queue -> single polling worker -> independent resource admission check -> deterministic tool -> outcome validation -> task state + events + usage -> tenant memory when applicable.

Implemented tools: `internal.echo`, `internal.add`, `math.evaluate` (bounded Decimal AST), `research.fetch` (bounded opt-in HTTPS, URL/IP pinning, untrusted source tagging), `knowledge.store` (tenant-scoped persisted text). Approval gates remain enforceable; all actual effectful high-impact tools are unavailable. Unconfigured services are exposed as unconfigured, never mocked live.

CPU/RAM/disk admission checks are estimates, not reservations; Docker enforces container quotas. Task claims include a cryptographically random lease token, and completion is fenced on that token. Lease recovery does not guarantee exactly-once external side effects; for future integrations implement idempotency keys and effect-outbox patterns.

Current limitations: SQLite single-host, incomplete multi-tenant RBAC, no independent policy service, no true machine virtualization, no real AI model provider, no semantic memory retrieval, no scientific solver, no distributed queue, no deployment validation. See `docs/HOSTINGER_VPS.md`.

Target architecture: PostgreSQL with RLS + transactional outbox + idempotent worker pool + resource quotas + provider adapters + per-tool policy checks + isolated remote execution + provenance-aware retrieval + cost budgets + approval/control plane + verifiable outcomes. Preserve the hard execution kernel and avoid decorative breadth.


## v0.3 cultural-astronomy extension

- `culture_records`: company-scoped, citation-aware source text, work/passage, tradition, evidence class and review status. No model embedding is claimed. All user-supplied records stay `user_supplied_unverified`; downloaded material stays `retrieved_unverified`.
- `culture_subscriptions`: owner-created, bounded HTTPS sources with explicit polling interval, active/paused state, next check and last checksum. The worker polls a single due source when idle, after resource admission and two independent environment opt-ins. It reserves the next check before outbound I/O and deduplicates unchanged checksums. No external action beyond read-only retrieval is permitted.
- `cosmos`: a deterministic classifier accepting explicitly supplied ecliptic-of-date longitude plus optional caller-chosen ayanamsha. Independent NASA/JPL Horizons request and defensive parser for geocentric J2000 state vectors. The frames are intentionally not silently mixed.
- No NLP reasoning engine, foundation-model integration, training process or autonomous religious/predictive advisor exists. The source catalog is a directory, not imported content. See `docs/CULTURAL_ASTRONOMY.md`.
