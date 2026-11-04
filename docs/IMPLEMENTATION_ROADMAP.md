# Dependency-ordered roadmap

1. Upgrade persistence to PostgreSQL migrations and tenant RLS; add real user auth, sessions, roles and scoped audit.
2. Harden execution leases (fencing, heartbeat, claim ownership), budgets, deadlines, idempotency, approval revocation and event outbox.
3. Build real AI provider adapter and structured planning with verified model availability, usage and cost accounting.
4. Create tool registry with independent authorization and sandbox execution; supply secure web read and git read adapters.
5. Add versioned agent definitions, workload routing, company/project memory and evidence retrieval.
6. Build software factory with safe branch edits, testing, PRs and human-approved deployments.
7. Implement company generation as a resumable DAG writing actual company/CRM/brand/project records.
8. Add research, growth, CRM, finance and mission-control displays backed by persisted data.
9. Add simulation, intelligence, self-healing, marketplace, billing; validate security and deployment.

A module is complete only after it can be tested for actual persistence, effects and verification.

## Next dependency: beyond the v0.4 proof of research execution

The bounded provider integration and source-ID checks do not solve factual verification or multi-agent autonomy. Add PostgreSQL RLS, real research indexing, evidence freshness and contradiction detection, verified model cost attribution, independently evaluated agents and safe orchestration before expanding to autonomous business operations.
