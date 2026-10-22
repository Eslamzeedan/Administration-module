# Source import and staging protocol

The current GitHub repository did **not** contain the existing Frappe application source when work started. Available archived code exists as `eup_administration.zip` (legacy) and `eup_administration-v2.zip` (v2 candidate); the actual server's installed source and DB configuration must be treated as authoritative.

## Before importing code
1. On the application host, record `bench version`, `bench --site <site> list-apps`, current Git remote and commit SHA (if any).
2. Export a **code-only** archive of the installed `apps/eup_administration` app, excluding `.env`, `site_config.json`, credentials, database backups, receipts, large assets and private attachments.
3. Compare installed hooks, DocType definitions, migrations, workspace JSON and Custom Fields against the archived v2 source and preserve differences.
4. Choose a reviewed baseline commit; do not blindly replace deployed code with an archived version.
5. Preserve the canonical app name `eup_administration` and existing DocType names for backward compatibility.

## Staging
- Create a separate bench/site with **separate app directory** (not a symlink into production).
- Restore anonymized sample data and test backups; block external mail/financial automations.
- Install dependencies at exact compatible Frappe/ERPNext versions.
- Run the original regression tests and any new runner integration tests.
- Verify permission queries against Frappe v16, private attachments, status workflow, and no fleet trip on a Careem ride.
- Rehearse rollback and compare original data counts, workspace shortcuts and permission deltas.

## Git
- `main`: approved base and later signed-off merges.
- `feature/runner-careem-foundation`: initial specification and the code-change candidate awaiting source import.
- Use draft PRs for proposed changes, do not merge before staging sign-off.
- Protect source ownership and avoid using actual employee or financial data in CI fixtures.

**Code archive not yet imported into GitHub.** Having the specifications and issues in the repo is not equivalent to an installable app.
