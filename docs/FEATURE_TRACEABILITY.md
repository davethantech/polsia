# Current implementation and evidence (2026-11-02)

| Capability | Status | Evidence |
|---|---|---|
| Persistent missions, task DAG, tenant-scoped access | VERIFIED local | `tests/test_core.py` |
| Approval gates and failed-task handling | VERIFIED local | `tests/test_core.py`, `tests/test_capabilities.py` |
| Lease fencing and dependency failure propagation | VERIFIED local | `tests/test_capabilities.py` |
| Cgroup-aware capacity admission | VERIFIED by deterministic tests; NOT VPS validated | `app/capacity.py`, `tests/test_capabilities.py` |
| Exact bounded arithmetic | VERIFIED local | `app/mathematics.py`, `tests/test_capabilities.py` |
| Private network/SSRF rejection | VERIFIED by mocked DNS tests; live service unverified | `app/research.py` |
| Real HTTPS research on configured internet | IMPLEMENTED_UNVERIFIED (live); mocked tests only | `app/research.py`, opt-in flag |
| Persistent company knowledge and basic text retrieval | VERIFIED local | `app/core.py`, `tests/test_capabilities.py` |
| Usage measurements and estimated capacity | VERIFIED local (estimates explicitly assumptions) | `app/core.py`, tests |
| Docker resource limits for Hostinger | IMPLEMENTED_UNVERIFIED (no VPS deploy) | `compose.yaml`, `Dockerfile` |
| Multi-provider AI agents, advanced reasoning, semantic graph | NOT_IMPLEMENTED | no real adapters or agent models |
| Global internet search, continuous crawling | NOT_IMPLEMENTED | only bounded URL fetch |
| VM-based untrusted code isolation | BLOCKED on typical nested-virtualization-disabled Hostinger VPS | container-only config; separate sandbox required |
| Model token/cost accounting and billion-dollar revenue | NOT_IMPLEMENTED / not guaranteed | no provider configured, no business metrics |
| Production readiness | NOT VERIFIED | missing security/load and deployment validation |

| Cultural evidence records and cross-tenant isolation | VERIFIED local | `app/culture.py`, `app/core.py`, `tests/test_cosmos_culture.py` |
| NASA/JPL geocentric ephemeris request/parser | IMPLEMENTED_UNVERIFIED live (mocked provider tests only) | `app/cosmos.py`, tests |
| Sidereal/tropical/nakshatra classification on supplied coordinate | VERIFIED local for conventional equal divisions | `app/cosmos.py`, tests; not a birth chart or forecast |
| Bounded, opt-in cultural source refresh and deduplication | VERIFIED local with stubbed HTTPS; real network unverified | `app/core.py`, tests; min 24h, 10 per company |
| Complete religion/history/astrology encyclopedia | NOT_IMPLEMENTED | seeded source directory only |
| Machine-learned reasoning and automated high-impact decisions | NOT_IMPLEMENTED | no provider or independent decision agent |

Local tests: `python -m pytest -q` -> 42 passed (2026-11-02). These tests do not establish production safety or unrestricted autonomy.

## 0.4 extension (2026-11-04)

| Capability | Status | Evidence |
|---|---|---|
| Tenant-scoped keyword retrieval across company knowledge and culture | VERIFIED local | `app/evidence.py`, `tests/test_intelligence.py` |
| Local Ollama adapter with bounded requests and strict JSON | VERIFIED in stubbed tests; live inference UNVERIFIED | `app/providers.py`, `tests/test_intelligence.py` |
| Retrieved citation-ID validation, unverified-source labeling | VERIFIED for ID checks only; factual truth UNVERIFIED | `app/intelligence.py`, `tests/test_intelligence.py` |
| Persistent worker research missions and read-only question API | VERIFIED local with mocked provider | `app/core.py`, `app/main.py` |
| Tenant-scoped daily provider call budget and token accounting | VERIFIED local for quotas/recorded mock usage; actual dollars NOT IMPLEMENTED | `app/core.py`, `tests/test_intelligence.py` |
| Autonomous internet-wide research, semantic/vector memory, independent reasoning agents | NOT IMPLEMENTED | Future milestone |
| Production model availability, scientific correctness, actual provider billing, Hostinger deployment | BLOCKED/UNVERIFIED | Requires real configuration, external evidence and deployment validation |

## v0.5 browser and company access (2026-11-04)

| Capability | Status | Evidence |
|---|---|---|
| Responsive cinematic landing + mission-control frontend | IMPLEMENTED_UNVERIFIED (visual/browser QA pending) | `app/static/index.html`, `dashboard.html`, `styles.css`, `app.js`; HTTP contract tests |
| Password-hashed users, login, cookie sessions | VERIFIED (local API tests) | `app/identity.py`, `tests/test_multitenant_ui.py` |
| Tenant authorization for API + company switching | VERIFIED (local API tests) | `app/main.py`, `tests/test_multitenant_ui.py` |
| Role-scoped company invitations | VERIFIED (local API tests) | `app/identity.py`, `tests/test_multitenant_ui.py` |
| CSRF protection, no-store and CSP | VERIFIED (local API tests) | `app/main.py`, tests |
| Dashboard real mission, events and task counts | IMPLEMENTED_UNVERIFIED (browser user journey pending) | `app/core.py` overview/list queries + `app/static/app.js` |
| Single-host online SQLite backup | VERIFIED (local integration test) | `scripts/backup_sqlite.py` |
| PostgreSQL RLS, penetration testing, VPS validation | NOT IMPLEMENTED/UNVERIFIED | See `docs/FRONTEND_AND_SECURITY.md` |
| Hostinger production deployment | BLOCKED | No production VPS access or live deployment test |

## v0.6 self-hosted neural and bounded multitasking (2026-11-04)

| Capability | Status | Evidence |
|---|---|---|
| Local-only Ollama adapter, no cloud endpoint/configurable cloud URL | VERIFIED stubbed tests; live Ollama unverified | `app/providers.py`, `tests/test_local_si.py` |
| Hostinger container isolated model endpoint, resource caps | CONFIGURED; deployment unverified | `compose.yaml` |
| Tenant-specific trainable two-layer neural relevance ranker | VERIFIED local algorithm and tenant tests | `app/neural.py`, `tests/test_neural.py` |
| Versioned, bounded evaluated training feedback | VERIFIED local; feedback does not prove factual truth | `app/core.py`, `tests/test_neural.py` |
| At most two parallel independent task executions | VERIFIED local with SQLite task claims | `app/worker.py`, `tests/test_neural.py` |
| Train capable general-purpose model entirely from scratch | NOT IMPLEMENTED | Requires training data, computing capacity and evaluation infrastructure |
| Full autonomous one-machine-company functionality | NOT IMPLEMENTED | CRM, sales outreach, software factory and human-facing controls incomplete |
| Real VPS deployment and live inference performance | UNVERIFIED | Requires VPS and installed licensed model |

## v0.7 self-hosted engineering proposals (2026-11-04)

| Capability | Status | Evidence |
|---|---|---|
| Deterministic source inspection with per-file SHA-256 | VERIFIED local | `app/factory.py`, `tests/test_factory.py` |
| Path restrictions, input/output caps, Python/JSON syntax validation | VERIFIED local | `tests/test_factory.py` |
| Local model full-file patch proposal | VERIFIED with stubbed transport; live model UNVERIFIED | `app/providers.py`, `app/factory.py` |
| Durable inspect → propose mission dependencies | VERIFIED local | `app/core.py`, `tests/test_factory.py` |
| Tenant-isolated proposal database/API access | VERIFIED local | `app/core.py`, `app/main.py`, `tests/test_factory.py` |
| Model quota, one-attempt call and usage records | VERIFIED local with simulated usage | `app/core.py`, `tests/test_factory.py` |
| Browser Software Factory interface | IMPLEMENTED_UNVERIFIED in live browser | `app/static/dashboard.html`, `app.js`, `styles.css` |
| Actual untrusted-code execution, isolated tests, Git branches/PRs | NOT IMPLEMENTED | No code-runner or GitHub execution tool in app |
| Live Hostinger model and production security/performance | UNVERIFIED | Requires VPS configuration and deployment checks |
