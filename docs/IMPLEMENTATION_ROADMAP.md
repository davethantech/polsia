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

## v0.5 milestone

Built locally: cinematic landing page, real-data mission control frontend, user/password login, tenant membership/roles, invitation redemption, CSRF-protected browser sessions, workspace selection, mission/knowledge/team/capacity operations, single-host SQLite backup helper and an example HTTPS reverse proxy. All changes must still receive CI and live browser/deployment validation. Next dependency: PostgreSQL + RLS, distributed sessions, concurrency testing, reverse-proxy hardening and deployed Hostinger test environment, before claiming production readiness.

## v0.9 next release gates

1. Run a real local model on the target VPS and measure token throughput, RAM,
   disk usage, failure rate and quality of nine-agent plans.
2. Integrate company program outputs into an approved engineering pipeline:
   repository connection, feature tickets, isolated tests, draft PRs and staging.
3. Add licensed/authorized research search, sources, company financial forecasts,
   verified customer-data imports, lead scoring and outbound policy controls.
4. Implement real email, payment, social and ad adapters separately, each with
   credential storage, quotas, approvals, retries, receipts and independent
   success verification. Never simulate success when disconnected.
5. Migrate to PostgreSQL with tenant row-level security, perform pentesting,
   browser QA, load testing and Hostinger staging-to-production verification.
