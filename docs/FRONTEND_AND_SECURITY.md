# Polsia v0.5 — cinematic frontend and tenant identity

## Implemented

- **Cinematic landing page** at `/`: responsive, original visual identity, animated orbital stage, section navigation and reduced-motion accessibility support. All assets are local; there are no CDN dependencies or fabricated performance metrics.
- **Live dashboard** at `/dashboard`: sign-in and registration (when enabled), company selector, persisted missions, execution states, approval actions, real task status breakdown, event history, knowledge CRUD (add/search), infrastructure capacity readings, optional AI research, team access and invitations. Charts count actual persisted tasks, never demo numbers.
- **Database-backed user identity** with salted scrypt passwords, hashed seven-day sessions, HttpOnly SameSite=Strict cookies, synchronizer CSRF header, account lockout after repeated failed logins, workspace memberships and scoped owner/editor/viewer permissions.
- **Company-scoped API**: a browser session with multiple memberships must send its selected `X-Company-ID`. Attempts to select another tenant are rejected by the backend, not just by the UI.
- **Team invitations**: one-use seven-day tokens, server-side hash storage, owner-only issue. Existing users must authenticate with their password; invitations never send an email without an actual email connector. A viewer cannot modify work; an editor can create missions but not issue invitations.
- **Security response headers**: restrictive Content Security Policy, no framing, no referrer leakage, and no-store API data. No cross-origin allowlist is added.
- **Deployment**: current Dockerfile includes static assets. `Caddyfile.example` illustrates HTTPS reverse proxy on the VPS with Docker API bound to local loopback.

## Setup (development)

```bash
python -m pip install -r requirements.txt
export POLSIA_SIGNUP_ENABLED=1
export POLSIADB=./polsia.db
uvicorn app.main:app --port 8080
# open http://localhost:8080/dashboard and register a company
python -m app.worker
```

## VPS hardening checklist (must be completed before exposing to production traffic)

1. Configure DNS and Caddy automatic TLS; firewall only allow SSH/80/443, restrict Docker API port to `127.0.0.1:8080`.
2. Set `POLSIA_ENV=production`, `POLSIA_SECURE_COOKIES=1` and **empty** `BOOTSTRAP_TOKEN`. Startup fails if secure cookies are disabled or legacy bootstrap is still enabled.
3. For the initial owner, enable `POLSIA_SIGNUP_ENABLED=1` only while registering, then set to `0` and restart. New users should thereafter join through invitations. Do not publish `.env`, SQLite volume, backups or tokens.
4. Keep the worker's tool access constrained. Never run arbitrary AI-generated code in the API or worker containers. No production deployments, payments, or external messages should run without policy gating.
5. Configure local online SQLite backups via `scripts/backup_sqlite.py` from a host cron or another isolated process; encrypt and replicate off-host. Restore-test the backup. SQLite works only for **single-host, low-volume** use; **migrate to PostgreSQL, RLS, and a dedicated queue** before high-volume or horizontal production use.
6. Monitor backups, service health, RAM, CPU, disk, application errors, HTTPS certificates, and server patch status; configure offsite incident notification and tested disaster recovery.
7. Run end-to-end browser testing on actual VPS, multiple concurrent-user load tests, security review/penetration test, restore exercises, and real integration tests. None of those are certified by a unit-test pass.

## Important limitations

**Production-ready is not verified.** This repo is now a functional production-oriented single-host beta. It does **not** yet provide PostgreSQL RLS, distributed sessions, generic agent execution, real software sandboxes, automated email delivery, subscription billing, WAF, per-IP registration throttling, formal security audit, live deployment tests, or SLO monitoring. This release does not promise completely autonomous operation or guaranteed revenue. Claims of completion require confirmed outputs, not visual polish.
