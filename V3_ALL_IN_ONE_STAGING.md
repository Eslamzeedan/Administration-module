# EuP Administration v3 — all-in-one staging candidate

**Branch:** `feature/administration-v3-all-in-one-staging`  
**Version:** `3.0.0rc1` — **NOT approved for production**. This repository is currently public: keep personnel data, passwords and backups out of commits.

## Scope already present in this branch
- 20 additive v3 DocTypes; all original 18 v2.2 DocTypes retained.
- Registry links Fleet, Meetings, Runner, Supplies and Custody source documents without changing their state machines.
- General service requests, role/department/company-scoped multi-step approvals with delegation, self-approval prohibition and decision audit.
- Two-person administrative stock count + locked adjustments, separated from ERPNext stock.
- Vehicle availability/cost KPIs and document verification; meeting room availability and check-in.
- Custody transfer requiring acknowledgement by the receiving employee; requester feedback.
- ERPNext Purchasing **draft-only** bridge with mapping, feature flag, role check and idempotent creation.
- HRMS employee lookup; Nextcloud link validation (no upload integration).
- V3 Workspace, Sidebar and Desktop Icon under ERPNext; a basic Desk page and action buttons.
- Email/SLA/accounting integrations are **not fully implemented**: event outbox stores signals; external sending and accounting posting remain disabled.

**Known limits:** No mobile Flutter app; no real Careem booking; no email delivery, general SLA escalation or automated GL posting. No automatic meeting cancellation. These require separate integration design, credentials and stage testing. The staging RC is a foundation, not a blanket claim that all roadmap requirements are complete.

## Deployment on a clean independent v16 staging bench

Never run on `erpnext-v16.eup-cairo.local`, or the production bench/source. First reproduce the baseline from a **scrubbed** backup, separate database, Redis, site URL and code checkout. Disable email, webhooks, external connections and scheduled background jobs.

```bash
cd /home/frappe/frappe-bench-staging
SITE=test-administration.eup-cairo.local
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" disable-scheduler
bench --site "$SITE" backup --with-files
bench --site "$SITE" migrate
bench build --app eup_administration
bench --site "$SITE" clear-cache
bench --site "$SITE" execute eup_administration.v3.bootstrap.configure
bench --site "$SITE" execute eup_administration.v3.registry.rebuild_registry
bench --site "$SITE" set-config allow_tests 1
bench --site "$SITE" set-config adm_allow_integration_tests 1
bench --site "$SITE" run-tests --app eup_administration
```

## Integrated acceptance gate (ALL at once, not production by default)

1. Repeat migration twice; preserve legacy record counts, unique names, fields, permissions, customized workspace; compare before/after snapshots using `tools/compare_snapshots.py`.
2. Verify all 38 DocTypes, new workspace/sidebar/desktop icon, 6 existing reports, new Desk route and site roles.
3. Make active test Employees from **two companies** and departments, distinct requester/approver/manager/driver/runner/storekeeper/receiver; assert cross-company and self-approval blocked.
4. Enable v3 requests **only in isolated staging**, create exactly one active Policy for company General with sequential role steps. Submit → two distinct step approvals → assign → start → complete → close → feedback.
5. Fail same-user approval, forged state updates, direct creation of registry/decision/event/stock posting records and unauthorized POST/GET routes.
6. Concurrent assignment of the same vehicle; odometer and expense validation; expired licenses, private attachments, in-progress maintenance.
7. Meeting capacity/buffer conflict, repeat booking atomicity, check-in once during active booking, no-show (manual); private titles never disclosed in availability response.
8. Runner/Careem approval and receipt authentication; no `ADM Trip` created, no external booking.
9. Supplies: receipt, approver limits, partial issue, insufficient stock, cancellation, negative stock denial.
10. Stock count with two separate people, posted adjustments, exact balances, concurrent issue/count and stale-count rejection.
11. Custody transfer between separate employees with dual handover, return condition and non-editability.
12. Purchasing mapping wrong company/unmapped item fails, flag off blocks create, flag on produces a single **draft** Material Request after explicit manager action, no double posting or stock deduction.
13. Role-specific dashboard and request list for requester/approver/manager/auditor; no leaked private fields.
14. All external flags disabled by default; no outgoing email, finance transaction, Nextcloud upload or live API call during tests.
15. Restore both code and database from the exact pre-upgrade snapshot in another disposable VM; verify rollback.
16. Run GitHub static CI plus live MariaDB integration and browser tests; do not accept skipped tests as passing.

## Deployment rule
Merge only after all applicable checks pass on an isolated restored database and security review. Never run the whole-bundle migration for the first time on production.
