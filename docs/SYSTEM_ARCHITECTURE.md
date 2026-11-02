# Current architecture and target architecture

Current: FastAPI HTTP entrypoint -> company bearer token checks -> SQLite relational records -> polling worker -> atomic transactional task claim -> deterministic internal tools -> tool result verification -> persisted events. Approval holds tasks until an owner approves. Dependency names are validated to form a DAG. Worker recovers expired leases with limited retries.

Target: PostgreSQL + RLS, outbox/event bus, horizontal workers with fenced leases, signed capability tokens, OPA-style independent policy engine, multi-provider router, encrypted secret store, sandboxed tool execution, durable memory + source retrieval, explicit verification contracts, budgets, observability, audit store, workflow scheduler, human approval UX. **These target services are NOT present.**

Target state machine: PLANNED/QUEUED -> WAITING_APPROVAL -> RUNNING -> VERIFYING -> SUCCEEDED/FAILED/BLOCKED/CANCELLED. The current subset is QUEUED/WAITING_APPROVAL/RUNNING/SUCCEEDED/FAILED/BLOCKED; verification is synchronous and limited to deterministic tool result schema.
