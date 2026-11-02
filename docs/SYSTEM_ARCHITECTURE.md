# Actual system architecture: execution core v0.2

FastAPI (company bearer tokens) -> SQLite relational storage -> atomic durable task queue -> single polling worker -> independent resource admission check -> deterministic tool -> outcome validation -> task state + events + usage -> tenant memory when applicable.

Implemented tools: `internal.echo`, `internal.add`, `math.evaluate` (bounded Decimal AST), `research.fetch` (bounded opt-in HTTPS, URL/IP pinning, untrusted source tagging), `knowledge.store` (tenant-scoped persisted text). Approval gates remain enforceable; all actual effectful high-impact tools are unavailable. Unconfigured services are exposed as unconfigured, never mocked live.

CPU/RAM/disk admission checks are estimates, not reservations; Docker enforces container quotas. Task claims include a cryptographically random lease token, and completion is fenced on that token. Lease recovery does not guarantee exactly-once external side effects; for future integrations implement idempotency keys and effect-outbox patterns.

Current limitations: SQLite single-host, incomplete multi-tenant RBAC, no independent policy service, no true machine virtualization, no real AI model provider, no semantic memory retrieval, no scientific solver, no distributed queue, no deployment validation. See `docs/HOSTINGER_VPS.md`.

Target architecture: PostgreSQL with RLS + transactional outbox + idempotent worker pool + resource quotas + provider adapters + per-tool policy checks + isolated remote execution + provenance-aware retrieval + cost budgets + approval/control plane + verifiable outcomes. Preserve the hard execution kernel and avoid decorative breadth.
