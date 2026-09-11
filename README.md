# Zeli Recruitment Sourcing Agent — V4

V4 turns the previous operator-reviewed prototype into a **multi-source, feedback-aware sourcing system**.

## Product stance

Zeli should not depend on scraping LinkedIn. In the near term it is best treated as a **complementary sourcing/workflow layer** that can sometimes make LinkedIn unnecessary for a particular search, but it does not replace LinkedIn's professional graph, passive-candidate reach, or messaging network.

The system owns the workflow:

`brief → criteria → search plan → multi-source discovery → evidence/ranking → operator review → publish → recruiter Yes/No → active candidate workspace → learning signals`

LinkedIn can remain one destination/profile source without becoming the system's foundation.

## Source adapters implemented

1. **Recruiter-owned internal pool**
   - Import CSV records from an ATS/CRM/exported candidate pool.
   - Search happens locally in SQLite.
   - This is the highest-control source and mirrors Thomas's existing behavior: search his known candidate pool first.

2. **Public-web discovery**
   - Pluggable provider support for Brave Search API, Serper, or a SearxNG endpoint.
   - Uses search result metadata/snippets for candidate discovery.
   - V4 may use `site:linkedin.com/in ...` as a search-engine locator query, but **does not log into, automate, or scrape LinkedIn pages**.
   - Public-web candidates remain operator-reviewed before publication.

3. **GitHub**
   - Optional supplementary source for technical roles.
   - Uses GitHub's public API; optional token increases available rate limits.
   - Not treated as a general recruitment database.

4. **Manual/operator evidence**
   - Add or edit candidates directly in the control room.
   - Candidate evidence is rescored after edits.

## Feedback-aware ranking

Recruiter feedback creates a bounded preference ledger keyed by recruiter.

A first Yes/No can add small signals for:
- title tokens
- company
- location tokens
- criteria that were evidenced

Those signals can move a future candidate score only modestly (currently capped at ±12 points). They **cannot override the brief**. The point is to learn Thomas's preferences gradually without pretending one test is enough to train a model.

## Recruiter workspace

After the recruiter reviews the published shortlist:
- only **Yes** candidates remain in the workspace;
- statuses can move through `Not contacted → Contacted → Replied → Screening → Call scheduled → Submitted / Not interested`;
- each candidate has a persistent note / next-step field;
- the operator sees the same pipeline state.

## Run locally

```bash
export ZELI_ADMIN_TOKEN='choose-a-long-random-value'
python server.py
```

Open:

- recruiter: `http://localhost:8080/`
- operator: `http://localhost:8080/admin?admin_token=YOUR_TOKEN`

## Configure public-web discovery

Configure **one** of the following. The engine chooses them in this order:

```bash
# Option A
export BRAVE_SEARCH_API_KEY='...'

# Option B
export SERPER_API_KEY='...'

# Option C: self-hosted / controlled search endpoint
export SEARXNG_URL='https://your-searxng.example.com'
```

Optional GitHub token:

```bash
export GITHUB_TOKEN='...'
```

No external search provider is required for internal-pool/manual operation.

## CSV import

The operator dashboard accepts CSV files. Useful columns:

```text
name,title,company,location,profile_url,summary,skills
```

Aliases such as `full_name`, `candidate`, `job_title`, `employer`, `linkedin_url`, `url`, `notes`, and `experience` are also accepted by the backend.

A sample is included at `sample_internal_pool.csv`.

## What was tested in this build

The server was exercised end-to-end with the internal-pool adapter:

- create recruiter run;
- import recruiter-owned candidates;
- execute search rounds;
- deduplicate repeated source hits;
- stage and score candidates;
- operator approve;
- publish shortlist;
- recruiter choose Yes;
- create active pipeline record;
- persist recruiter learning signals;
- verify those signals create a small ranking adjustment on a later run.

Live Brave/Serper/SearxNG/GitHub calls require external credentials/network access and were **not live-tested in the build environment**.

## Before production

This is still an early system. Before deploying for real users, replace the built-in `http.server` with a production web framework/server, move SQLite to managed PostgreSQL, add real user authentication, encrypt/separate secrets, add background jobs for discovery, add provider rate limiting/retries, and implement a clear retention/deletion policy for candidate personal data.
