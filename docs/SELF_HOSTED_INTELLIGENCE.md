# Self-hosted SI architecture and honest capabilities

## Two distinct neural systems

1. **Local language model runtime**: Ollama executes *pre-trained open-weight*
   language models on the user's Hostinger VPS, not an external inference API.
   These model weights are third-party foundation models, not weights Polsia
   trained itself. Model downloads require operator opt-in, license review and
   enough verified RAM, disk and CPU. No silent cloud fallback is supported.
2. **Polsia native neural ranker**: `app/neural.py` is our own small neural
   network (two layers with tanh activations). It learns local search relevance
   from evaluated pairs and saves tenant-specific model versions in SQLite.
   It does not generate fluent answers or learn human knowledge from scratch.

## Actual autonomous loop

- User-authorized bounded source subscriptions can refresh publicly accessible
  HTTPS documents as often as the configured interval permits (minimum daily).
- Retrieval preserves company boundaries and evidence provenance. New text is
  labeled `retrieved_unverified` until independently reviewed.
- The mission worker can execute up to 2 independent tasks concurrently using
  SQLite claims and capacity admission. Local inference itself is limited to
  one loaded model and one parallel generation in Docker.
- A configured local model can generate a structured source-cited response. The
  system verifies citation IDs, not factual truth.
- User-evaluated source preference pairs train the *small* ranking network
  using gradient updates. The loss must improve or the new weights are rejected.

## Safety and quality limits

- The neural ranker is not a general intelligence model; automated source
  retrieval is not model-weight training. This must not be called recursive
  self-improvement, autonomous scientific discovery, or world understanding.
- No automatic download of internet data without opt-in subscriptions; no
  blanket web crawling, private host access or hidden data collection.
- Offline inference needs enough memory. Hostinger virtual CPU, available RAM,
  model weight size and temperature sensors determine safe throughput; do not
  assume the VPS has GPU support or nested virtualization.
- No safety policy, payments, production deployments or resource quotas are
  modifiable by the model. More automation should be added only with audit,
  rollback, evaluator, test suite and human-override support.
- Training a strong foundation model from zero generally requires massive
  licensed datasets, advanced GPUs and a verified training/evaluation pipeline;
  it is not feasible to promise on an unspecified shared VPS.

## Verified and unverified

The API/worker/neural components are unit- and integration-tested locally,
using stubbed model transport. We have not run a trained language model on a
real Hostinger VPS, validated commercial marketing outcomes, performed
penetration testing or proven general intelligence.

## v0.7 engineering specialist

`software.inspect` is deterministic static source analysis. `software.propose`
uses the configured local model with strict input/output bounds and stores
untrusted candidate files under a tenant. Together these form the initial
software engineering specialist workflow; they are **not** an autonomous
software factory capable of building, testing and deploying an application.
See `docs/SOFTWARE_FACTORY.md` for current restrictions and next steps.
