# Hostinger VPS deployment and constrained autonomy

Status: **documented, not deployed or load tested on Hostinger.**

## Architecture

Hostinger KVM VPS does not offer nested virtualization as a standard feature. The provided `Dockerfile` and `compose.yaml` use **containers**, not full virtual machines. Docker provides useful process isolation and resource limits, but *not* full VM-grade isolation for arbitrary generated programs. Do not run untrusted generated code in these containers; use an independently hardened remote sandbox provider or a properly isolated host.

Two application containers share a persistent SQLite volume (temporary single-host MVP). The API binds only `127.0.0.1:8080`; configure TLS and an authenticated reverse proxy before opening access. `BOOTSTRAP_TOKEN` must be strong, kept confidential and disabled after onboarding. `.env` is never committed. All resource budgets in `compose.yaml` are starting values, not claims of measured production requirements. Use a **minimum ~2 GiB VPS for a tiny test install and preferably 4 GiB+** to leave headroom for Docker, OS, proxy, backups and database; verify with actual benchmarks.

```sh
cp .env.example .env
# Edit .env with a cryptographically strong BOOTSTRAP_TOKEN and specific settings.
docker compose up --build -d
curl http://127.0.0.1:8080/health
docker compose logs --tail 100
```

Only enable `POLSIA_NETWORK_ENABLED=1` for user-authorized bounded HTTPS research, with appropriate VPS egress policies. If behind a cloud load balancer or proxy, restrict incoming connections to loopback and trusted hosts. Configure access logs, TLS, limits and firewall rules in the reverse proxy; this file is not a complete internet-facing deployment.

## Virtual memory versus AI memory

- **Virtual memory/swap** is disk-backed OS memory. Swap can help survive occasional memory spikes, but frequent swapping can severely slow a VPS. Docker `memswap_limit` caps total memory plus swap per service and does not create swap on the host.
- **AI/company memory** here is persisted SQLite knowledge, independent of swap. It survives application restarts if the Docker volume is preserved; it is simple text retrieval, not a trained model, semantic graph or global memory.
- **Hardware temperature** is normally not visible from within many VPS guests. If unavailable, API explicitly reports `temperature_monitored=false`. It cannot prevent host overheating, override provider throttling or repair hypervisor faults.

## Capacity admission

The worker checks memory available (including cgroup limits), free disk, host load normalized by host CPU count, per-cgroup CPU pressure if exposed, and temperature where available. If uncertain/unsafe it refuses to claim tasks and retries later. Disk checks observe the host-visible filesystem, not a reserved future allocation. Tool memory/disk estimates are conservative **assumptions**, not prediction or reservation; `GET /usage` records observed tool-run times and bytes only. A second guard runs after a claim and returns work to the queue if thresholds changed. Resource enforcement depends primarily on Docker cgroup limits and hosting quotas, not just those admission checks.

## Restore, backup, monitoring

Stop writer containers before taking a raw volume copy, or use SQLite's online backup API / `sqlite3 .backup` from a consistent database connection. Preserve SQLite WAL files with raw filesystem snapshots, and test restores. Monitor disk space, API availability, memory pressure, CPU throttling, error rates and backup integrity. Set OS patches, log rotation, host firewall, TLS renewals and system alerts. Load test on the chosen Hostinger VPS plan. For multiple workers/hosts, move to PostgreSQL with tenant row-level security and a production queue; don't run SQLite over NFS.

## Explicit exclusions

No automated provisioning of Hostinger resources, no internet-wide search, no model provider, no math theorem prover, no business-money guarantee, no live external actions, and no policy bypass. High-impact spending, production changes, sending messages and destructive actions need separate scoped permissions and approval policies. An autonomous agent may make routine, reversible, low-risk decisions within preauthorized limits; no safe platform can promise universal approval-free operation.


## v0.3 cultural refresh resource policy

Automatic cultural-source refresh is disabled by default. Enable `POLSIA_NETWORK_ENABLED=1` **and** `POLSIA_CULTURE_REFRESH_ENABLED=1` only after reviewing source rights, robots/terms and tenant quotas. Each company can create at most 10 HTTPS subscriptions with a refresh interval of 24–2160 hours. One background worker checks at most one due source when no mission task is pending. A source fetch must pass resource admission checks, URL/DNS/IP restrictions, response-length limits and timeouts. Remote text is stored as untrusted evidence, not instructions, and is not automatically treated as authoritative. Source refresh may be delayed when the VPS is under pressure. There is no online-learning model or guaranteed freshness interval.

A NASA/JPL Horizons request relies on internet access and may fail or be unavailable; it is not guaranteed by the container configuration. JPL's J2000 reference plane and selected timescale must not be confused with an astrological chart's ecliptic-of-date or local time. The tool does not automatically turn positions into predictions.
