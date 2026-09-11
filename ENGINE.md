# Zeli Recruitment Sourcing Engine — V4 architecture

## Core principle

**Zeli owns the sourcing decision loop; no single data source owns Zeli.**

The system should be capable of using LinkedIn as a complementary profile/network surface while remaining useful when LinkedIn is absent from a particular search.

## Flow

### 1. Brief compiler
Input: recruiter role brief + optional context.

Output:
- must-haves;
- strong signals;
- equivalent titles;
- explicit exclusions;
- unknowns that require verification.

### 2. Search planner
Creates progressively broader rounds:

- Round 1 — narrow title + evidence terms + location;
- Round 2 — relax supporting keywords / alternate titles;
- Round 3 — broader adjacent-title search.

It also produces optional professional-profile locator queries. Those are search-engine queries only; V4 does not authenticate to or scrape LinkedIn.

### 3. Source fan-out
The same query can run against multiple adapters:

- `internal_pool`
- `public_web`
- `github` for technical roles
- `manual` operator additions

Every source hit is normalized to a candidate-like object with provenance.

### 4. Identity resolution
Candidates are deduplicated first by normalized profile URL, then by normalized name + company.

Multiple hits become multiple `candidate_sources` records rather than duplicate candidates.

### 5. Evidence model
For each criterion the engine stores:

- `MET`
- `UNKNOWN`

V4 deliberately avoids turning missing public-profile evidence into `NOT MET` because Thomas explicitly described contacting candidates to verify missing information rather than rejecting them based on an incomplete profile.

A future version can add true `NOT MET` only when evidence affirmatively contradicts a requirement.

### 6. Ranking
Current score is composed from:

- must-have evidence;
- strong-signal evidence;
- equivalent-title fit;
- location evidence;
- a small learned recruiter adjustment.

The operator sees:

`base score + learned adjustment = final internal score`

The recruiter does **not** see this number, avoiding anchoring.

### 7. Operator quality gate
No candidate is published merely because the engine discovered it.

Operator can:
- inspect source provenance;
- open source links;
- edit evidence;
- rescore;
- approve/reject;
- add notes;
- publish only approved candidates.

This is how the first runs optimize for quality while the engine is still learning.

### 8. Recruiter decision
For each published candidate the recruiter answers only:

**Would you contact this candidate? Yes / No**

If No, explanation is optional.

A Yes becomes an active workspace record.

### 9. Learning ledger
On the recruiter's first decision for a candidate, V4 records small signals for matching title tokens, company, location tokens and evidenced criteria.

The signal uses Bayesian smoothing and low confidence at small sample sizes. Future candidate ranking adjustment is capped at ±12 points.

Important: the system does not blindly fine-tune or retrain a model from a handful of clicks.

### 10. Active workspace
Selected candidates continue beyond sourcing:

- status;
- notes / next action;
- source profile;
- last update.

This is intentionally the beginning of a recruiter operating surface, not an end-of-test survey.

## What LinkedIn means in this architecture

### Near term
LinkedIn is **complementary**.

Zeli can reduce the amount of manual LinkedIn sourcing dramatically, and in some roles a recruiter may never need LinkedIn to discover enough good candidates. But Zeli should not claim to replace LinkedIn's network/data coverage or its direct candidate communication channel.

### Product target
The right ambition is:

> Make LinkedIn optional for a sourcing run, not make LinkedIn disappear from recruiting.

If internal pools + public sources + specialist sources return enough high-quality candidates, the recruiter can operate without opening LinkedIn. When the search is sparse or highly passive, LinkedIn remains another surface the recruiter can use.

## Next engine upgrades

1. LLM-backed brief compilation with a strict structured schema.
2. Evidence extraction from permitted public pages / licensed data providers.
3. Better identity resolution across sources.
4. Recruiter-account IDs rather than name-derived keys.
5. Search budget management (stop broadening when enough high-confidence candidates exist).
6. Calibrated ranking learned across many recruiter decisions while preserving recruiter-specific preferences.
7. Contact-channel enrichment using licensed/permitted providers.
8. ATS/CRM connectors so the internal pool syncs automatically rather than via CSV.
