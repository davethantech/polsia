# Software factory v0.7 — implemented slice and boundaries

This extension creates a **persistent engineering proposal**, not a self-modifying
or production-deploying agent. It uses the existing mission DAG, tenant identity,
local-only model runtime, capacity admission, bounded call accounting, audit
log and reviewable artifacts.

## Operation

1. An authenticated owner/editor supplies a goal and a small mapping of paths
   to source text through the dashboard or `/factory/missions`.
2. The first task, `software.inspect`, checks size/path constraints and statically
   parses Python or JSON. A hash and syntax diagnostic are recorded; the source
   isn't executed.
3. The dependent `software.propose` task submits a structured JSON request to the
   configured local Ollama runtime. Only an allowlisted local endpoint is accepted.
   The call reserves one per-company inference slot and cannot be retried by the
   worker after an unknown outcome.
4. Returned file paths and text are checked for bounds, protected paths, duplicate
   names, unchanged files and Python/JSON syntax. This does not make code safe.
5. On success the worker stores the complete untrusted candidate under a tenant
   scoped `factory_proposals` database record. Mission outputs and audit events
   carry only the artifact ID and summary metadata.
6. Users review candidate files via `/factory/proposals/{id}` or Mission Control.
   No tool in this workflow alters the source repository, pushes a branch,
   opens a PR, executes the candidate, or deploys it.

## Resource and trust limits

- Inputs: 1–10 files, 20 KB total, 8 KB/file. Output: at most five files,
  16 KB total, 8 KB/file. No `.env`, hidden files, Git/CI workflows or credentials.
- Time: model transport has a 75-second timeout; worker applies current VPS
  capacity admission rules. Production usage must be tested on the actual VPS.
- Model output is treated as **untrusted data**. Local source files can contain
  prompt injection. Never copy generated code directly into production.
- Only Python AST and JSON grammar are checked. JavaScript/TypeScript/YAML/HTML
  and other text files require proper language-specific parsers and test suites.
- Audit logs intentionally omit full candidate source. Mission input includes
  the supplied source and is already restricted by company-scoped access.
- The database stores source and generated code; supply only content that may be
  stored on the VPS. No secret detection can be assumed complete.

## Status and verification

Automated tests cover path rejection, size limits, syntax failure,
source hashing, tenant authorization, model configuration failure,
model quota accounting, durable proposals, and verified API retrieval.
The local language model transport is **stubbed in tests**: live generation,
software execution in an isolated container, PR creation, automated builds,
merge and deployment are all **unverified or not implemented**.

## Next dependency-ordered milestones

1. PostgreSQL tenant RLS, migrations and deployment security validation.
2. Dedicated sandbox worker (no API-host Docker socket) with restricted network,
   read-only inputs, disposable storage, CPU/RAM/PID limits, timeouts, evidence
   collection and adversarial testing.
3. GitHub App repository import, isolated branches, source-diff review, PRs,
   checks and least-privilege credentials.
4. Versioned QA/test agent, regression evaluation, business research and
   multi-specialist executive planning integrated into the same mission engine.
