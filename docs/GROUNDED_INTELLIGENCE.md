# Grounded intelligence: self-hosted mode

The v0.4 **historical** cloud AI adapter has been retired. Current reasoning
calls ONLY an allowlisted local Ollama runtime on loopback or the private Docker
service; it never reads or forwards any cloud API key. Models must be installed
by an operator who has reviewed license, size, computational and privacy costs.

Pipeline: tenant-scoped knowledge or culture records → bounded lexical retrieval
(+ optional company-specific neural ranker score) → local model constrained JSON
→ strict citation-ID validation → persisted mission output and local token usage.
Citation presence does not mean the underlying claim is scientifically true.
Source refreshes are opt-in, limited to provided HTTPS addresses, and labeled
unverified. Polsia does not automatically ingest or learn the whole internet.

The custom neural ranker is a small two-layer relevance model; updates require
evaluated pairwise source feedback, improve a measured loss, and are tenant-
scoped, versioned, audited and capped. It is *not* a trained language model and
must not be portrayed as human-like or general intelligence.

Local model availability is checked against the running service via
`GET /intelligence/local-models`. Inference is disabled until explicitly
configured. The backend does not autonomously pull weights or fall back to cloud
models. A bounded 75-second timeout, one task attempt, output limit, capacity
admission and per-company daily usage caps limit runaway consumption.

No automatic production code deployment, purchases, external messaging or
arbitrary shell tool is enabled. Those operations require independent policy
checks, permissions, budgets, verification and safeguards before being added.

See `docs/SELF_HOSTED_INTELLIGENCE.md` and the repository README for setup and
validation limits. Hostinger deployment and actual local inference are unverified.
