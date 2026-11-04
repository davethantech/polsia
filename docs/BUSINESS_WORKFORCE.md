# Polsia Business Workforce — v0.9 beta

## What a user can do now

Enter a business idea, industry and target market in **Company Studio** or POST to
`/business/programs`. With a configured local Ollama model, the system persists
an actual company-scoped `business_programs` record, creates a nine-task mission
with a dependency DAG, and queues the following specialist draft-producing roles:

| Role | Output | External effects |
|---|---|---|
| CEO / Strategy | strategy, objectives, roadmap, risk assumptions | none |
| Research | market hypotheses, questions and customer segments | no live searches automatically |
| Product | requirements and release roadmap | no app built |
| Engineering | architecture, milestones, database and tests plan | use separate Software Factory to propose code |
| Marketing | campaign briefs and SEO drafts | no ad purchases or publishing |
| Sales | ICP, CRM stages and outreach drafts | no lead discovery or email sending |
| Customer Support | support scripts and escalation workflows | no customer messages sent |
| Social Media | channel-specific post drafts and calendar | no public posts published |
| Operations | handoffs, checkpoints and checklists | no outside workflows automatically executed |

The local-model output is validated to a bounded JSON schema, stored in
`business_artifacts` and labeled `local_model_draft_unverified`. The worker
resolves only **same-company, same-mission** earlier artifacts as context.
No AI-generated claims about real-world markets, customers, conversion rates,
revenue, websites, payments, ad spend or external actions are considered verified.
The model is **not** nine independent neural networks; these are nine bounded
specialist roles sharing the same locally hosted model and execution kernel.

With the existing `POLSIA_AI_DAILY_CALL_LIMIT=10` default, one full nine-role plan
requires nine allowed local model calls. Limits can stop a program; there is no
silent bypass or unbounded retries. If the model cannot be reached, tasks fail
rather than returning mock answers. A model's response may still be wrong.

## Actual company ledgers

`/business/leads` creates/lists **user-supplied** company-scoped CRM leads.
`PATCH /business/leads/{id}` updates a lead stage: `new`, `qualified`,
`contacted`, `converted`, or `lost`. These statuses reflect operator choices,
**not** independently verified transactions.

`/business/tickets` records supplied support issues.
`PATCH /business/tickets/{id}` updates `open`, `needs_follow_up`, `closed`.
No email or customer response is sent when a ticket is saved or marked closed.

HTTP endpoints require a company membership and CSRF for browser writes. Owners
and editors can create/modify; viewers can inspect only their workspace. All
queries enforce company IDs in SQL. Source, email and ticket content are stored
in local SQLite; back up and protect that database. Never paste credentials.

## Typical API interaction

After authenticating via `/auth/login` and selecting company scope:

```json
POST /business/programs
{"idea":"Build healthcare SaaS for independent clinics","industry":"Healthcare software","market":"India"}
```

Returns a durable program ID, mission ID and `ACTIVE` queue state. Worker processes
`business.draft` tasks in prerequisite order. Poll `/business/programs/{program_id}`
to see statuses and persisted drafts. A completed mission means **all nine drafts
were saved**, not that a profitable operating business exists.

## Operational boundaries and future integration work

- `POLSIA_AI_ENABLED=1`, `POLSIA_LOCAL_MODEL=<installed-model>` and a reachable
  private/local Ollama endpoint are required for the business program.
- Existing separate software-factory code includes **opt-in** sandbox-test,
  draft-PR and deployment job components. No live Docker, GitHub PR, or Hostinger
  release is verified as part of this update. Never enable a sandbox worker
  on the production API or give arbitrary generated code host-level privileges.
- GitHub repository management, real web/app deployment, database provisioning,
  Stripe billing, Meta ads, email delivery, real lead discovery, social publishing,
  customer support messaging and analytics integrations still require
  independently configured credentials, tools, explicit authorization and
  outcome verification. This release does **not** perform those operations.
- High-impact actions, including payments, external outreach, advertising and
  production deployment, must not bypass independent policies or approvals.
- Production-readiness needs PostgreSQL RLS, security review, load tests,
  Hostinger VPS tests, local-model evaluation and verified integration workflows.

## Verification

Automated tests use a **stubbed local-model response**. They verify the DAG,
transactional persistence, document shape, model usage ledger, failure behavior,
tenant access isolation, company switching, CSRF, role enforcement, CRM records,
support tickets and default-off sandbox/publishing gates. They **do not** prove
business success, live model quality or actual external actions.
