# Feature traceability

| Feature | Status | Evidence/verification |
|---|---|---|
| Persistent company/mission/tasks | VERIFIED (local tests) | app/core.py; tests/test_core.py |
| Dependency DAG validation and ordering | VERIFIED (local tests) | tests/test_core.py |
| Tenant scoping for mission + approvals | VERIFIED (local tests) | tests/test_core.py |
| Persisted approval gating | VERIFIED (local tests) | tests/test_core.py |
| Bounded retry/fail state | VERIFIED (local tests) | tests/test_core.py |
| Worker lease recovery | IMPLEMENTED_UNVERIFIED | app/core.py; expiration race tests missing |
| Full user authentication/RBAC | PARTIALLY_IMPLEMENTED | company tokens only |
| AI planning/provider execution | NOT_IMPLEMENTED | no AI adapter configured |
| Independent production policy engine | NOT_IMPLEMENTED | only simple tool allowlist and owner checks |
| True external action verification | NOT_IMPLEMENTED | local deterministic tools only |
| Memory, software factory, company generator | NOT_IMPLEMENTED | no implementation |
| CRM, growth, digital twin, analytics, marketplace | NOT_IMPLEMENTED | no implementation |
| Production deployment | BLOCKED | no deployment environment; no deployment validation |
