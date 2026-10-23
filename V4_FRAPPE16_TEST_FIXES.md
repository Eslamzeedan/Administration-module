# Frappe v16 integration test corrections (staging only)

Based on 7298268baf2fffa1df2135a713da4bd3cb2492d8 and the user's independent VM report:
Frappe 16.31.0, ERPNext 16.32.3, Python 3.14.7; seven v4 tests, five passed,
two errors. That report is not a live run performed by this agent.

- Duplicate feedback accepts DuplicateEntryError or UniqueValidationError only.
  It asserts one record for the reference key, no total-count increase on retry,
  and unchanged original rating/comment. The unique schema constraint is unchanged.
- Direct audit insertion uses a real ticket, enabled policy and started workflow.
  It requires the controller's PermissionError/message even with ignore_permissions=True,
  and checks unchanged audit identifiers/count and absence of a forged action.
  Audit.before_insert already enforces the internal ContextVar; no controller relaxation.
- ADM Trip declares Frappe v16's IGNORE_TEST_RECORD_DEPENDENCIES for all six direct
  Link targets. This stops recursive generation before entering Company/Cost Center
  and optional payments dependencies. Tests still run and create their own ADM
  records/users. No fake Payment Gateway, financial fixture, or ERPNext patch.
- Legacy integration setup requires the explicit existing adm_test_company fixture,
  fails if missing, and rejects unsafe sites before parent setUpClass can generate
  or commit records. Parent lifecycle is retained.
- Offline regression checks exercise the class setup guard, parent lifecycle, missing
  company failure and coverage of every ADM Trip Link dependency by the override.
  This is scoped to the existing test module; other modules without a DocType folder
  do not trigger recursive generation unless they explicitly declare extra dependencies.

The supported override is applied before dependency recursion in
[Frappe v16.31.0 generators.py](https://github.com/frappe/frappe/blob/v16.31.0/frappe/tests/utils/generators.py).
The class lifecycle is in
[integration_test_case.py](https://github.com/frappe/frappe/blob/v16.31.0/frappe/tests/classes/integration_test_case.py).

No v2-v4 production behavior, DocType schema, unique constraint or administrative-only
boundary is changed. No Accounting/Purchasing/Stock/Assets/GL/Payment writes added.
No production commands, migrate, reinstall, bench update or ERPNext modifications.

## Safe rerun on the disposable VM only

Run as the existing bench owner. These commands refuse another bench path, a dirty
checkout, another branch or an unexpected starting commit. Use the existing configured
Company/Employee/User fixtures; do not create ERPNext finance records for these tests.
Keep the terminal open so the rollback_ref variable remains available.

```bash
set -euo pipefail
cd /home/frappe/frappe-bench-v4
test "$(pwd -P)" = /home/frappe/frappe-bench-v4
site=test-administration-v4.local
test -f "sites/$site/site_config.json"
app=apps/eup_administration
branch=feature/administration-v4-independent-staging
test "$(git -C "$app" branch --show-current)" = "$branch"
test -z "$(git -C "$app" status --porcelain)"
test "$(git -C "$app" rev-parse HEAD)" = 7298268baf2fffa1df2135a713da4bd3cb2492d8
git -C "$app" remote get-url origin
# Confirm the printed origin is Eslamzeedan/Administration-module before proceeding.
rollback_ref="adm-v4-before-frappe16-fixes-$(date +%Y%m%d-%H%M%S)"
git -C "$app" branch "$rollback_ref"
bench --site "$site" backup --with-files
git -C "$app" fetch origin "$branch"
git -C "$app" log --oneline HEAD.."origin/$branch"
# Compare the fetched head with the tested commit linked in PR #9.
git -C "$app" merge --ff-only "origin/$branch"
bench --site "$site" clear-cache

# Targeted v4 (all seven tests), then legacy trip, then full application suite.
# pipefail preserves failure status while saving logs.
bench --site "$site" run-tests --app eup_administration \
  --module eup_administration.tests.test_v4_independent_integration 2>&1 | tee /tmp/adm-v4-targeted.log
bench --site "$site" run-tests --app eup_administration \
  --module eup_administration.eup_administration.doctype.adm_trip.test_adm_trip 2>&1 | tee /tmp/adm-trip-targeted.log
bench --site "$site" run-tests --app eup_administration 2>&1 | tee /tmp/adm-full-suite.log
```

No migration/build is required for these Python test changes. If a command fails,
stop and retain its log; do not reinstall or continue to production.

Simple code rollback (only this disposable checkout, and only if still clean):

```bash
cd /home/frappe/frappe-bench-v4
test "$(pwd -P)" = /home/frappe/frappe-bench-v4
test -z "$(git -C apps/eup_administration status --porcelain)"
git -C apps/eup_administration switch --detach "$rollback_ref"
bench --site test-administration-v4.local clear-cache
```

This restores code only. Frappe's test framework rolls back test transactions at class
cleanup, but do not assume every full-suite side effect is transactional. If the disposable
site must be restored, use the exact database/files backup paths printed by the backup
command with bench --site test-administration-v4.local restore, reviewing those paths first.
Do not restore any other site. There is no need to reset/force-push the GitHub branch.

## Validation scope

GitHub Actions runs the offline unittest suite on Python 3.12 and 3.14, Python compilation,
JavaScript syntax checks and both acceptance-script shell syntax checks. See the PR update
for the actual run result on the final commit. This workstation has no installed Python or
Frappe/MariaDB, and direct shell network access to GitHub could not resolve its host.
Live targeted v4, legacy trip and full-suite integration must be rerun by the user on the
specified isolated VM. No claim of a successful live rerun is made here.
