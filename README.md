# Autonomous Company Execution Core — verified local slice

A **functional, limited execution kernel**, not the full requested AI Company Operating System. AI models, web research, software engineering containers, CRM, billing, and real integrations are **NOT IMPLEMENTED**. The `internal.echo` and `internal.add` tools are genuine deterministic local operations, not autonomous AI employees.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BOOTSTRAP_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
uvicorn app.main:app --reload
# In a separate shell, using the same environment and working directory:
python -m app.worker
```

Create a company (the bootstrap token is a local setup secret):

```bash
curl -s -X POST http://127.0.0.1:8000/bootstrap -H "X-Bootstrap-Token: $BOOTSTRAP_TOKEN" -H 'Content-Type: application/json' -d '{"name":"Example Company"}'
```

Save the returned `token` as `COMPANY_TOKEN`. Create a mission:

```bash
curl -s -X POST http://127.0.0.1:8000/missions -H "Authorization: Bearer $COMPANY_TOKEN" -H 'Content-Type: application/json' -d '{"objective":"Demonstrate a durable two-step workflow","tasks":[{"name":"calculate","tool":"internal.add","inputs":{"values":[2,3]}},{"name":"report","tool":"internal.echo","inputs":{"text":"Finished"},"depends_on":["calculate"],"approval_required":true}]}'
```

The worker executes the first task, then waits for explicit approval on the second. `GET /missions/{id}` reports task IDs and status; `POST /tasks/{task_id}/approve` approves the second task. `GET /missions/{id}/events` returns the persisted audit trail. `GET /health` reports unavailable integrations accurately.

```bash
pytest -q
```

## What this slice does
- Company-scoped bearer tokens (hashes persisted; raw token returned only on creation)
- Transactional SQLite mission/task/event persistence
- Atomic task claims with time-bound leases and bounded retry attempts
- Explicit dependencies and cycle validation
- Mandatory approval gate when specified; execution cannot bypass it
- Real deterministic tool execution with result-shape validation
- Tenant authorization on mission, approval, and event endpoints
- Clear unconfigured AI/integration state

## Important limitations
This is **not production-ready**. Bootstrap currently permits multiple company registrations to anyone possessing its secret; turn it off after setup. A production implementation needs PostgreSQL + row-level-security policies; per-action permissions; cryptographically authenticated service workers; robust lease fencing and heartbeats; idempotency keys and tool-specific deduplication; outbox events; versioned migrations; budget reservation and enforcement; cancellation; deadline enforcement; auditable evidence verification; external tool sandboxing; rate limiting; TLS; secrets vault; full auth; CSRF strategy; provider adapters; security review; and deployment/load testing. SQLite is local single-host only. An expired lease for external side effects would need additional fencing to prevent duplicate actions. The only included tools have no external side effects.
