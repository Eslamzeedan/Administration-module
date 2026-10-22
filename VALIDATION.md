# Validation record

Delivery date: 2026-10-13. Based on the user-supplied eup_administration.zip, v0.1.0.

## Executed locally

- Original baseline: 12 tests passed before modification.
- Final suite: **42 tests passed**, Python 3.12.14. See validation/local-tests.txt.
- Python compilation: application, tools and tests passed.
- JavaScript syntax: all **9** application/report/page/calendar files passed Node syntax validation. See validation/javascript-checks.json.
- All JSON definitions and fixtures parsed successfully. Original five DocType names, naming rules, field names/types and prior Select options are retained.
- Boundary coverage: v16 ptype permission handling; driver role/enabled record; assigned versus unassigned driver; requester draft editing; direct state/reading forgery; manager-only approval/rejection; POST mutation restriction; fuel cost calculation; private receipt rejection; immutable fulfilled services; recurrence rollback and action-context reset; bounded permission-aware reports; workspace setup preservation; snapshot comparison rejects changed data/permissions or missing workspace.
- Finite/nonnegative readings, overflow, zero distance, backwards readings, gap reason, scheduling/buffer boundaries and recurrence validation are covered.

Tests using a framework double verify application boundaries, not real Frappe permission evaluation, SQL locking or transactional durability. See tests/test_security.py.

## Included but not executed locally

- Real Frappe/ERPNext v16 installation, editable-package installation, migrations and asset build.
- Actual DocPerm/Custom DocPerm and Company User Permission evaluation.
- Integration suite on a disposable v16/MariaDB site. It has a production-site/explicit-test-flag guard.
- Concurrent authenticated requests and database lock/deadlock behavior.
- Actual data preservation snapshots from the company site and backup restore rehearsal.
- Browser/calendar/mobile Desk rendering and Africa/Cairo DST checks.
- CI workflow execution on GitHub; a workflow is included, but no repository was updated.

The user will install manually. Follow STAGING_ACCEPTANCE.md and UPGRADE_AND_ROLLBACK.md before production.

## Scope

No remote server access, production backup, data extraction, migration, build, restart or deployment was performed. Schema preservation is verified against the supplied source definitions, not against an inspected live database. Costs are operational records and do not automatically create accounting entries.
