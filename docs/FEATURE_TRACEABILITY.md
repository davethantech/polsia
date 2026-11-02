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
