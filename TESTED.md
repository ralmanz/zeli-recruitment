# V4 verification

Verified locally on September 9, 2026 using the internal-pool adapter:

- Python syntax compilation succeeded.
- Recruiter run creation succeeded.
- CSV-like internal candidate records imported successfully.
- Search plan executed across the internal pool.
- Repeated hits from multiple search rounds deduplicated into one candidate with multiple source records.
- Evidence scoring ranked a clearly matching sample Senior Project Engineer above weaker profiles.
- Operator approval + publication succeeded.
- Recruiter Yes decision persisted.
- Yes candidate automatically entered the active pipeline.
- Pipeline status and note persisted (`Contacted`, `Follow up Friday`).
- Recruiter preference signals were written to the learning ledger.
- A subsequent run can apply those signals as a bounded score adjustment.

Not live-tested here: Brave Search API, Serper, SearxNG, or GitHub network calls because external credentials were not available in the build environment.
