# Autonomous Company Execution Core — verified local slice

A **functional, limited execution kernel**, not the full requested AI Company Operating System. AI models, autonomous general intelligence, software engineering containers, CRM, billing, and commercial integrations are **NOT IMPLEMENTED**. Bounded opt-in public HTTPS retrieval and cultural-source refresh are implemented but not live verified. The `internal.echo` and `internal.add` tools are genuine deterministic local operations, not autonomous AI employees.

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

## 0.2: bounded internet, persistent knowledge, capacity and exact mathematics

This is an incremental, tested extension of the same execution core, **not AGI or a fully autonomous business**.

- `GET /capacity` measures host/cgroup CPU, cgroup-aware memory, available disk and swap, and temperature when visible. `THROTTLED` jobs remain queued; container CPU/RAM/process limits provide the stronger guard. Missing temperature sensors are reported honestly. Capacity figures are *snapshots*; tool estimates are assumptions.
- `POST /missions/estimate` estimates tool memory, disk and input bytes without inventing AI token costs; requires the company's bearer token.
- `math.evaluate`: bounded decimal arithmetic using a safe syntax tree, not `eval()` or natural-language guessing. It does **not** implement symbolic algebra, proofs, higher mathematics or a general numerical solver.
- `research.fetch`: opt-in, capped 64 KiB HTTPS reads of **specific public URLs** with DNS/IP validation, pinned IP TLS connections, response limits and redirect revalidation. No global crawling/search and no authenticated/private-network browsing. Source contents are untrusted and persisted as `retrieved_unverified`.
- `knowledge.store`, `GET/POST /knowledge`: company-scoped SQLite knowledge with provenance. `GET /usage`: measured task latency and input/output bytes; provider charges remain unknown.
- Worker lease fencing prevents a stale worker overwriting task results; blocked dependencies propagate to waiting approvals. Local execution still lacks a production-grade sandbox or real provider integration.
- `Dockerfile` and `compose.yaml`: conservative API/worker containers designed for a Hostinger VPS (no nested VMs); loopback-only API port, non-root user, read-only root filesystems, CPU/memory/process budgets, limited container swap, capped logs. These configurations have **not** been deployed to a Hostinger VPS.

Enable outbound research only after reviewing the network policy with `POLSIA_NETWORK_ENABLED=1` in `.env`. User-added network data remains untrusted; no reasoning model is configured.

See `docs/HOSTINGER_VPS.md` for deployment preparation, swap vs company memory, backup, risk and operational limits.

**Running the tests:** `python -m pytest -q` (28 tests passed locally on 2026-11-02). GitHub CI and VPS deployment are not verified. A model cannot guarantee zero hallucinations, $1B monthly revenue, universal knowledge, or authorization-free actions. Security and legal/financial approvals must not be bypassed.


## 0.3: cultural studies, Vedic traditions and astronomy (new)

This is a small, grounded, **evidence-labeled** module—not an all-knowing cultural agent or a validated astrology prediction engine.

- `GET /culture/catalog` exposes a starter catalog: NASA/JPL Horizons, NASA PDS, NASA NTRS, GRETIL (Indological textual corpus), and Smithsonian Open Access. The catalog **does not** mean their entire contents have been downloaded or learned. Rights and terms must be reviewed before ingestion.
- `POST /culture/records` saves a manually supplied excerpt with a citation URL, tradition, topic, work, passage, language and evidence classification. It is **always** marked `user_supplied_unverified`, even if the author selected `historical_primary_text`. `GET /culture/records?query=` is tenant-filtered; all input is treated as untrusted text, not instructions.
- Mission tool `culture.record` creates a similarly evidence-labeled persisted record. Historical texts, translations, scientific measurements, scholarly interpretations, folklore, mythology, beliefs and hypotheses remain different kinds of evidence.
- `GET/POST /culture/subscriptions` let a company register up to **10 specific HTTPS sources**, no more frequently than **once per 24 hours**. `POST /culture/subscriptions/{id}/pause` and `/resume` control source polling. The worker checks one due source only when idle, and **only** when both `POLSIA_NETWORK_ENABLED=1` and `POLSIA_CULTURE_REFRESH_ENABLED=1`. HTTP fetches are bounded by existing 64 KiB / 5 s-per-connection controls, redirect/IP safety, and resource admission. It stores only changed snapshots, labels them `retrieved_unverified`, and never tries to follow every link or download the internet. New subscriptions are pre-authorized for read-only retrieval by the company owner, not for arbitrary execution or spending.
- Mission tool `astronomy.horizons` requests **live geocentric J2000 ecliptic position/velocity** from NASA/JPL Horizons for one of nine fixed major bodies and a date from 1900–2100. Parsed results retain the source URL and retrieval hash. When offline, unsupported or malformed, the mission fails rather than inventing positions. **Live Horizons connectivity has not been validated on Hostinger**. No birth-chart implementation is provided.
- `POST /cosmos/zodiac` and mission tool `astrology.zodiac` classify a **caller-supplied** ecliptic-of-date longitude into a tropical sign. Optional **caller-supplied** ayanamsha enables conventional sidereal sign and 27-nakshatra classification. **No ayanamsha is silently chosen; JPL J2000 coordinates are not automatically passed to this classifier.** Interpretation is cultural, not scientifically demonstrated causal prediction.
- `GET /cosmos/catalog` lists supported bodies and connection configuration. Astronomical measurements can inform science, but traditional astrological interpretations must not autonomously determine medical, financial, legal or other irreversible actions. Respect the person's traditions and free choice.

Example: create a bounded NASA ephemeris mission after enabling internet in `.env`:

```bash
curl -X POST http://127.0.0.1:8000/missions \
  -H "Authorization: Bearer $COMPANY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"objective":"NASA/JPL Mars ephemeris","tasks":[{"name":"mars","tool":"astronomy.horizons","inputs":{"body":"mars","date_utc":"2026-11-02"}}]}'
```

Example: record a cited text excerpt (not a factual endorsement):

```bash
curl -X POST http://127.0.0.1:8000/culture/records \
  -H "Authorization: Bearer $COMPANY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"Textual passage","tradition":"Vedic","topic":"cosmology","work":"Text edition","passage":"chapter reference","language":"Sanskrit","source_url":"https://gretil.sub.uni-goettingen.de/","evidence_class":"historical_primary_text","content":"Example user-supplied note needing source verification"}'
```

Detailed model, source policy and limitations: `docs/CULTURAL_ASTRONOMY.md`. Tests: `python -m pytest -q` (42 passed locally in this revision; no live NASA or VPS validation).
