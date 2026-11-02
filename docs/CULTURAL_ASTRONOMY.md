# Cultural knowledge, astrology, astronomy and world-history architecture

Status as of 2026-11-02: a small **locally tested, evidence-aware v0.3 slice**, not a complete encyclopedia, AI research agent, horoscopy service or scientific/medical advisor.

## Intended coverage

The broader project should study cultural history, mythological narratives, Vedic/Jyotisha traditions, other astrological systems, historical astronomy, NASA science, religions and philosophy, in the relevant language and time period. A single source or interpretation must not be presented as representative of every group. Distinguish a historical tradition *describing a claim* from independent evidence that the claim is true.

Future research should capture author/school, manuscript/critical edition, translation, translator, verse/chapter, date ranges with uncertainty, text version, geographical setting, varying interpretations and cultural context. No unverified universal religious facts, sensational occult claims or scientific causal assertions may be inferred from corpus proximity. Respect copyright and source usage policies; never scrape paywalled/private content or bulk-copy a text without rights.

## Initial verified directory (not imported content)

| Source | Purpose | Type |
|---|---|---|
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | Astronomical planetary ephemerides | Scientific measurements / calculations |
| [NASA Planetary Data System](https://pds.nasa.gov/) | Space mission archive | Mission/observational data |
| [NASA NTRS](https://ntrs.nasa.gov/) | Scientific and technical reports | Source-specific scientific literature |
| [GRETIL](https://gretil.sub.uni-goettingen.de/) | Digitized Vedic, Sanskrit, Pali, Prakrit, and other Indological texts | Historical source editions; provenance varies |
| [Smithsonian Open Access](https://www.si.edu/openaccess) | Cross-cultural museum collections | Artifacts, collection records, images, metadata |

Each directory entry is an access point; none is automatically read, cached, considered current, or comprehensively understood. Records added from one of these sources must be separately cited and reviewed. Source metadata and publication rights may vary.

## What is implemented

- Owner-supplied texts with `title`, `tradition`, `topic`, `language`, `work`, `passage`, `source_url`, `content`, `evidence_class`, and persistent `review_status=user_supplied_unverified`.
- Tenant-scoped record search by title, content, tradition, topic or work. This is text matching, **not** semantic understanding, translation, entity linking or a knowledge graph.
- Owner-subscribed HTTPS sources, each with a minimum 24-hour refresh period. Opt into public HTTPS reads **and** automatic refreshing; the background worker then stores changed, bounded source excerpts with checksum and retrieval time. No change creates no duplicate snapshot. These are unverified material and never executed as agent instructions.
- NASA/JPL Horizons `VECTORS` request for one named body, one UTC/UT date through a single `TLIST` time with explicit `TIME_TYPE=UT`; selected frame `ECLIPTIC` (J2000), Earth-centered 500@399, km and km/s vectors. Results are parsed only when the marker-delimited payload is complete. Source URL, checksum, retrieval time and frame are preserved; errors fail closed. The external live service is not tested in this environment.
- A conventional 12-sign tropical and optional sidereal/27-nakshatra **classification** of a supplied ecliptic-of-date longitude, requiring the caller to choose the ayanamsha. This does not derive longitude from a birth record or compute precise horoscopes. No causal predictions are made.

## Evidence model

`evidence_class` is a description of the **kind of claimed material**, and does not prove correctness. Accepted classes: `astronomical_measurement`, `historical_primary_text`, `scholarly_interpretation`, `cultural_belief`, `mythological_narrative`, `hypothesis`, and `unverified_claim`. `review_status` is independently set by the system and cannot be upgraded to `verified` by a user or fetched page. NASA ephemeris output is a remotely returned scientific calculation, not locally independently recomputed; literature is source-dependent and may contradict other editions.

Recommendations for consequential decisions must be supported by decision-relevant empirical data or explicit user preferences; cultural/astrological views may be discussed as optional context, never used as an automatic or sole basis for business, clinical, legal, financial or safety decisions. The platform has no autonomous recommendation engine at this stage.

## Continuing learning safely

The worker only checks owner-registered public-source URLs; it does **not** search the entire internet, automatically read all religious books, train its model, deploy code or exercise independent executive authority. A broader retrieval workflow requires a real search provider, corpus licensing, document parsing, verification/evaluations, semantic retrieval, cost/CPU limits, a registered AI model, authorization checks and counterfactual testing. New source content needs cross-referencing, freshness monitoring, and clear uncertainty labeling. The existing VPS capacity governor and 64-KiB fetch cap apply; snapshots are limited to a 12,000-character excerpt.

## API and runbook

- `GET /culture/catalog`: view the directory.
- `POST /culture/records`: store a cited excerpt; `GET /culture/records?query=...` retrieve within the company.
- `POST /culture/subscriptions`: register one source, `GET /culture/subscriptions` list, `POST /culture/subscriptions/{id}/pause` and `/resume` change status. Owner token required for writes. Set `POLSIA_NETWORK_ENABLED=1` and `POLSIA_CULTURE_REFRESH_ENABLED=1` on the worker to enable polling.
- `POST /missions`: `culture.record`, `astronomy.horizons`, and `astrology.zodiac` are task tools. The worker persists output and audit records.
- `GET /cosmos/catalog`: provider support and settings. `POST /cosmos/zodiac`: deterministic coordinate classifier.

Tests: `python -m pytest -q`. The `astronomy.horizons` provider call is exercised through a mocked network response, not a live NASA interaction. Do not claim external availability, accuracy of unverified inputs or VPS readiness without running the actual integration tests on the deployment target.
