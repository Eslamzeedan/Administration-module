# Independent administration staging bundle

Base: PR #8, `feature/administration-v3-all-in-one-staging`, commit `210d9d188512d7eeac93fbf23bd55522b6a98a2f`.
Candidate: `feature/administration-v4-independent-staging`. No production deployment or merge is authorized by this delivery.

## Implemented source

- **Administration Command Center:** Desk route `/app/administration-command-center`, permission-filtered counts, operations, overdue work, contract notices, preventive due dates/odometer, incident/facility categories and weekly date window.
- **Employee Self-Service:** authenticated website `/administration_self_service`; active Employee identity, company supplied by server, facility/document/parcel/equipment requests, workflow actions, request status and service rating. The initial view covers the last seven days. The Desk lists provide older history and the existing fleet/runner/supplies services.
- **Smart dispatch:** advisory smallest adequate vehicle, then odometer ranking; excludes occupied/maintenance vehicles, expired or missing license/insurance, missing/failed daily checklist and overdue preventive plans. Existing trip assignment remains authoritative. No automatic assignment.
- **Facilities:** ADM Facility Ticket, categories/location, priority, assignment and protected resolution updates.
- **Daily Driver Checklist:** vehicle/date/odometer, safety checks and mandatory defect explanations. Does not change trip APIs.
- **Preventive Maintenance:** ADM Preventive Plan, date and odometer thresholds, intervals and protected service updates; command-center due signals and dispatch exclusions.
- **Meeting check-in:** existing v3 protected API and DocTypes retained; no second state machine.
- **QR custody:** authenticated private-record link encoded locally as SVG QR, a form action and no bearer authorization token. Existing custody/handover logic retained.
- **Internal documents / parcels:** ADM Parcel with tracking type, unique tracking number, sender, recipient, private attachment, workflow history and recipient-only one-time acknowledgement.
- **Equipment booking:** company-scoped ADM Shared Equipment and booking intervals, serialized resource locking, conflict validation and explicit release.
- **SLA/escalation:** state-level SLA hours and escalation Role; opt-in job emits a unique internal escalation record and audit event once per state visit. Internal role/company-filtered list, no external mail, automatic approvals or reassignment.
- **Contracts:** counterparty, start/end, notice period, private attachments and notice list. Renewal is a new register record, preserving old history.
- **Incidents:** category/severity, cause/corrective action updates and grouped analysis.
- **Recurring tasks:** manager-configured schedules, opt-in daily processor, locked advancement, unique occurrences. One overdue occurrence per task per invocation; no unbounded catch-up loop.
- **Employee satisfaction:** requester-only single rating 1–5 after terminal state; manager-visible aggregate.
- **Consumption estimate:** last up-to-28 daily issue quantities, including zero days, with seven-day mean-based estimate and explicit insufficient-history result. Operational quantities only.
- **Weekly reports:** on-demand scoped weekly report API/menu. No email distribution.

## Workflow Designer

Standard editable policy form with child tables for states, transitions and sequential approval bands, a review template, flow preview, and a condition-building dialog. Company/target-specific active policy, unique database key, supported-role transitions, AND conditions with `eq/ne/in` over a fixed field list, same-company approvals, optional department restriction, optional time-bound v3 delegation, distinct approvers, self-approval denial, rejection reason, protected run/audit records, expected revisions and row locks.

Conditional approval routes are configured as transitions with different conditions and their own sequential bands. There are no financial thresholds or posting actions. States must all be reachable and able to reach a terminal state. Used policy structure is frozen; disable the old version and duplicate into a new version. Existing runs retain the original policy even when disabled. Direct state edits, forged audits and arbitrary target DocTypes are denied.

The designer operates on **nine new administrative operation DocTypes only**. It deliberately does not replace v2.2/v3 controllers, workflows or whitelisted APIs. Existing service approval policies/delegations remain available. Existing legacy DocType JSON files were not edited.

## Boundary

No new controller imports ERPNext or writes Purchasing/Stock/Assets/GL/Payment/Material Request records. Runtime workflow targets use a closed server-side allowlist. Company, Department, Employee, User and Role are references. PyQRCode is declared as a dependency for local QR generation; no third-party QR service receives custody data.

18 additive DocTypes (including child tables), their controllers, form actions, website and Desk pages, hooks and sidebar entries. Current installation continues to depend on ERPNext as inherited from PR #8; this is logical administrative isolation, not a standalone database product.

## Validation actually performed

- Local baseline: **79 offline tests passed**.
- New total: **149 offline tests passed**, no skips. Includes real workflow engine behavior against a mocked Frappe boundary, scope/role checks, actual reused delegation/self-approval primitive, stale revision handling, graph validation, expression rejection, forecasting and source contracts.
- Python source compilation passed under local **Python 3.13.7**.
- All application JavaScript parsed using Node VM, including the website and form scripts. This is syntax validation, not browser acceptance.
- Financial/procurement source search found no new runtime financial targets or bridges.
- Shell syntax check could not run locally: Git Bash was blocked by the Windows execution environment. CI includes `bash -n` for both acceptance scripts.
- Added **seven live Frappe/MariaDB tests**, not executed locally: full approval/feedback/audit flow, stale/direct edits, policy freezing, equipment conflict/release, recurring idempotency, SLA idempotency and audit forgery. Each snapshots counts **and full-content hashes** of installed protected ERPNext tables before/after.

Offline passing does not establish real Frappe v16 behavior, database locking correctness, permission enforcement in actual HTTP requests or financial non-interference. The linked official Frappe database, document, hooks and v16 migration documentation was consulted. The current version-16 upstream declares a newer Python runtime than this local test runtime; use the Python version required by the exact staging Frappe commit.

## Explicitly not completed or not verified

- No live migrate/build/install, real MariaDB execution, browser/mobile/accessibility acceptance, multi-company live acceptance, HTTP/CSRF tests, concurrent-transaction stress, sanitized v2.2 upgrade rehearsal or backup/restore rehearsal was run here.
- No guaranteed optimal routing, GPS/traffic prediction, machine-learned forecasting, automatic fleet allocation or automatic maintenance work-order generation. The implemented suggestions/alerts and baseline estimate are described above.
- No scheduled weekly email, outbound notification delivery, calendar/provider integration, drag-and-drop canvas, Flutter app or public unauthenticated employee portal.
- Inbox has a strict 1000-pending-run guard; reports reject more than 5000 visible rows. Paging/export beyond these limits remains a scaling task.
- Custom approval/escalation roles must be granted appropriate read permissions where their users need Desk lists; the protected approval inbox performs its own scoped authorization.
- Existing v3 email/outbox limitations remain. No financial bridge is pending or intended.
- A successful CI run is **not** production acceptance. Do not describe this candidate as fully tested or production ready.

## Isolated commands

Offline, from the app checkout:

```bash
python -m unittest discover -s tests -v
python -m compileall -q eup_administration
find eup_administration -name '*.js' -exec node --check {} \;
bash -n tools/run_v4_staging_acceptance.sh
```

Use a separately provisioned bench, MariaDB database, Redis, app source, hostname, sanitized fixtures and blocked outbound integrations. Never use `erpnext-v16.eup-cairo.local` or `/home/frappe/frappe-bench`. Do not point a staging bench at the primary checkout.

Precreate a staging Company and an enabled User/active Employee in that company with Administration Manager; use fictitious data. The application/test code does not create HR/financial fixture records.

```bash
cd /home/frappe/frappe-bench-staging
SITE=test-administration-v4.local
git -C apps/eup_administration checkout feature/administration-v4-independent-staging
bench --site "$SITE" disable-scheduler
bench --site "$SITE" set-config adm_test_company "Isolated Test Company"
bench --site "$SITE" set-config adm_test_approver "approver@example.test"
bench --site "$SITE" set-config adm_v4_jobs_enabled 0
bash apps/eup_administration/tools/run_v4_staging_acceptance.sh "$SITE"
```

The script performs backup, two migrations, build, original snapshot comparisons and all app integration tests. It refuses known primary paths/sites and shared primary source; a naming/path check alone does not prove physical isolation. Missing v4 fixtures fail the suite. Scheduler and maintenance mode remain disabled/enabled respectively for later controlled browser acceptance.

Target the new integration module separately while diagnosing:

```bash
bench --site "$SITE" run-tests --app eup_administration --module eup_administration.tests.test_v4_independent_integration
```

Only on the disposable site, set `adm_v4_jobs_enabled=1` to exercise the scheduled processors (or the tests temporarily enable it in memory). Return it to zero afterward. The full acceptance gate must also exercise two companies, multiple departments/users, forbidden HTTP GET mutations, duplicate submits, concurrent booking/approval/cancellation, private attachments, failed checklists, delegation expiry, legacy flows and restored backup integrity. No skipped test counts as acceptance.

Official references:
- https://docs.frappe.io/framework/user/en/api/database
- https://docs.frappe.io/framework/user/en/api/document
- https://docs.frappe.io/framework/user/en/python-api/hooks
- https://github.com/frappe/frappe/wiki/Migrating-to-version-16
