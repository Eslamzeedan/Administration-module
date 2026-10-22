# Runner source candidate — local validation record

On 2026-10-22, a **local staging-only** package was constructed from the archived `eup_administration-v2.zip` (not verified to be identical to the installed app).

- Candidate app version: `2.1.0rc1`
- Main changes: `ADM Service Request`, `ADM Careem Ride`, `ADM Errand Stop`, new roles, permission hooks, POST workflow, private receipts, Careem fares, JS actions.
- `python -m unittest discover -s tests -v`: **55 tests passed**.
- `python -m compileall -q eup_administration`: passed.
- `node --check` on app JS: passed.
- **Staging bench migration/integration and browser tests not run**.
- **Not uploaded as app source to this repo yet**; current GitHub PR contains specification documents only.

Local ZIP SHA-256: `9865feab82234282900710f51d7901917760f23187cfc1b8966efe19ab422ab3`.

Local upgrade patch SHA-256: `74694ad9d4e27852264e5b4ef7d7e335bff91284c0856ae4621e2852ca9c87f9`.

Do not deploy from these hashes or archived versions without confirming the server baseline and completing staging checks.
